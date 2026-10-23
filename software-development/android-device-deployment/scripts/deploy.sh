>#!/usr/bin/env bash
# Install an APK on a connected device, safely.
#
# Copy into the project root and edit the CONFIG block. The dry-run default is
# deliberate: report what is installed and from which source, and let a human
# approve any removal. Never let this script uninstall on its own initiative.
#
# Usage:
#   ./deploy.sh              # inspect only, changes nothing
#   ./deploy.sh --install    # remove incompatible group, then install
#   YES=1 ./deploy.sh --install   # skip the interactive confirmation (CI)
set -uo pipefail

# ============================== CONFIG ==============================
APK="${APK:-}"                       # path to the APK; default guessed below
PKG="${PKG:-com.example.app}"
MIN_SDK="${MIN_SDK:-26}"
LAUNCH_ACTIVITY="${LAUNCH_ACTIVITY:-}"   # optional; resolved from badging if blank
# Apps sharing android:sharedUserId with PKG. All must be signed identically and
# share a UID: remove the whole set together or none of it. See the pitfall in
# SKILL.md — partial removal leaves survivors with an unreassignable UID.
GROUP="${GROUP:-$PKG}"
# When set, an adb -s <serial> is used for every invocation. Useful when more
# than one device is attached; without it adb errors out on ambiguity.
ADB_SERIAL="${ADB_SERIAL:-}"
# ====================================================================

if [ -z "$APK" ]; then
  APK=$(find . -path '*/build/outputs/apk/*/*.apk' -name '*.apk' -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-)
fi

BT=$(ls -d "$HOME"/Android/sdk/build-tools/*/ 2>/dev/null | sort -V | tail -1)
BT="${BT%/}"
MODE="${1:-dryrun}"

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '\n\033[1;32mOK %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m!! %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mXX %s\033[0m\n' "$*" >&2; exit 1; }

# Route EVERY adb call through this array, so ADB_SERIAL is honoured everywhere.
# A script that honours a device-selection variable on some call sites and
# ignores it on others is the bug, not the feature.
ADB=(adb)
[ -n "$ADB_SERIAL" ] && ADB=(adb -s "$ADB_SERIAL")

installed_pkg() { "${ADB[@]}" shell dumpsys package "$1" 2>/dev/null | grep -m1 -oE 'installerPackageName=[^ ]*' | cut -d= -f2; }

# ------------------------------------------------------------------ device
say "Device"
adb start-server >/dev/null 2>&1 || warn "could not start the adb server"
# Without the timeout this waits forever when no phone is attached.
if ! timeout 15 "${ADB[@]}" wait-for-device 2>/dev/null; then
  die "No device connected.
   1) Plug in the phone and set USB mode to file transfer, not charge-only.
   2) Settings -> About -> tap Build number 7x to unlock developer options.
   3) Enable USB debugging and accept the authorization prompt on screen."
fi
"${ADB[@]}" devices -l | sed 's/^/   /'
[ "$("${ADB[@]}" get-state 2>/dev/null)" = "device" ] \
  || die "State is not 'device' (unauthorized = accept the prompt on the handset)."

model=$("${ADB[@]}" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
sdk=$("${ADB[@]}" shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r')
abi=$("${ADB[@]}" shell getprop ro.product.cpu.abi 2>/dev/null | tr -d '\r')
ok "$model · API $sdk · $abi"
[ "${sdk:-0}" -ge "$MIN_SDK" ] || die "Needs API ${MIN_SDK}+, device reports ${sdk:-?}"

# -------------------------------------------------------------------- APK
say "Artifact"
[ -n "$APK" ] && [ -f "$APK" ] || die "No APK found. Build one first: ./gradlew :app:assembleDebug"
ls -lh "$APK" | awk '{print "   size: "$5}'
our_sig=""
if [ -n "$BT" ] && [ -x "$BT/aapt2" ]; then
  "$BT/aapt2" dump badging "$APK" 2>/dev/null | grep -E "^package|locales|native-code" | sed 's/^/   /'
  if [ -z "$LAUNCH_ACTIVITY" ]; then
    LAUNCH_ACTIVITY=$("$BT/aapt2" dump badging "$APK" 2>/dev/null \
      | grep -m1 launchable-activity | sed -E "s/.*name='([^']+)'.*/\1/")
  fi
fi
if [ -n "$BT" ] && [ -x "$BT/apksigner" ]; then
  our_sig=$("$BT/apksigner" verify --print-certs "$APK" 2>/dev/null | grep -m1 SHA-256)
  echo "   sig: ${our_sig:-unknown}"
else
  warn "build-tools not found; skipping signature check"
fi
unzip -l "$APK" 2>/dev/null | grep -oE 'lib/[a-z0-9_-]+/' | sort -u | sed 's/^/   abi: /'

# ---------------------------------------------------------- current state
say "Currently on device"
# Fetch the package list ONCE. Two reasons:
#   - it is one adb call instead of one per package;
#   - `grep -q` piped from adb is unsafe (see below).
# Do NOT pipe adb into `grep -q` here. grep -q exits on the first match, adb
# takes SIGPIPE (141), and `pipefail` propagates 141 as the pipeline status, so
# `if ... | grep -q` reports an INSTALLED package as ABSENT. That turns a dry run
# that exists to prevent destructive work into a script that skips its own guard.
installed_pkgs=$("${ADB[@]}" shell pm list packages 2>/dev/null | tr -d '\r' || true)
adb_has() { grep -qx "package:$1" <<<"$installed_pkgs"; }

found=()
for p in $GROUP; do
  if adb_has "$p"; then
    src=$(installed_pkg "$p"); found+=("$p")
    echo "   PRESENT: $p   (installed by: ${src:-unknown})"
  fi
done
if [ ${#found[@]} -eq 0 ]; then
  echo "   none of [$GROUP] installed"
fi

# Signature already on the device, if the system will tell us.
existing_sig=""
if [ ${#found[@]} -gt 0 ]; then
  existing_sig=$("${ADB[@]}" shell dumpsys package "$PKG" 2>/dev/null | grep -m1 -oE 'signatures:\[.*\]' || true)
  echo "   device reports: ${existing_sig:-no signature info}"
fi

# Only treat the group as a removal candidate when the signatures DIFFER.
# Uninstalling when they match destroys app state for nothing: the install would
# have succeeded with `adb install -r`. Compare, don't assume.
need_removal=0
if [ ${#found[@]} -gt 0 ]; then
  if [ -n "$our_sig" ] && [ -n "$existing_sig" ]; then
    # Both known and different -> must remove. Same -> keep, install over it.
    case "$existing_sig" in
      *"$our_sig"*) need_removal=0 ;;
      *) need_removal=1 ;;
    esac
  else
    # Cannot compare. Removing is the safe-but-lossy branch; the user decides.
    need_removal=1
  fi
fi

if [ "$MODE" != "--install" ]; then
  say "Dry run — nothing was changed"
  echo "   To proceed: $0 --install"
  if [ "$need_removal" -eq 1 ]; then
    warn "would uninstall (signature mismatch): ${found[*]}"
  elif [ ${#found[@]} -gt 0 ]; then
    ok "signatures appear to match; would install over ${found[*]} WITHOUT removing"
  fi
  # Never let a `[ ... ]` be the last statement: a false test yields a
  # confusing nonzero exit status for the whole script.
  exit 0
fi

# -------------------------------------------------------------- confirm
if [ "$need_removal" -eq 1 ] && [ "${YES:-0}" != "1" ]; then
  say "These packages will be UNINSTALLED (irreversible)"
  printf '     %s\n' "${found[@]}"
  warn "App state is lost. Back up first if there is anything to keep."
  printf '\n   Continue? [s/N] '
  read -r reply
  case "$reply" in
    s|S|y|Y) ;;
    *) die "Cancelled by user. Nothing was changed." ;;
  esac
fi

# ------------------------------------------------------------- uninstall
if [ "$need_removal" -eq 1 ]; then
  say "Uninstalling"
  warn "sharedUserId means these apps cannot be replaced piecemeal."
  for p in $GROUP; do
    if adb_has "$p"; then
      "${ADB[@]}" uninstall "$p" >/dev/null 2>&1 && ok "uninstalled $p" || warn "could not uninstall $p (root?)"
    fi
  done
  sleep 2
fi

# -------------------------------------------------------------- install
say "Installing"
# Capture adb's exit status directly. `if adb install ... | sed ...; then :; fi`
# throws the status away (the pipeline reports sed's), so a failed install would
# fall through to the check below, find the OLD package still present, and
# report success.
if ! "${ADB[@]}" install -r -d "$APK" 2>&1 | sed 's/^/   /'; then
  warn "adb install returned an error"
fi
# Re-query: the cached list predates any uninstall, so it cannot answer this.
if ! "${ADB[@]}" shell pm list packages 2>/dev/null | tr -d '\r' | grep -x "package:$PKG" >/dev/null; then
  die "Install failed. INSTALL_FAILED_SHARED_USER_INCOMPATIBLE or a
   signature clash means leftover apps from the group remain: remove them from
   the device's Settings and retry. This loses app data."
fi
ok "$PKG installed"

say "Verify"
"${ADB[@]}" shell dumpsys package "$PKG" 2>/dev/null | grep -m1 -E 'versionName|versionCode' | sed 's/^/   /'
"${ADB[@]}" shell pm path "$PKG" | sed 's/^/   /'
[ -n "$LAUNCH_ACTIVITY" ] && "${ADB[@]}" shell am start -n "$PKG/$LAUNCH_ACTIVITY" 2>&1 | sed 's/^/   /'
ok "Launched."