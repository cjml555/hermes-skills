---
name: android-device-deployment
description: Use when installing a built APK on a device via adb.
license: MIT
metadata:
  version: "1.0.0"
  category: software-development
---

# Android Device Deployment

Scope: getting a built APK onto real hardware or an emulator and proving it
landed. Starts where `android-build-troubleshooting` ends (APK exists) and ends
before app-level manual QA. Not for building — that skill covers Gradle.

## Always-on rules

- **Default to a dry run that changes nothing.** Report what is installed, from
  which source, and what an install would do — then wait for explicit approval
  before any `adb uninstall` or `adb install`. "Prepare the build" is not
  "alter my phone"; conflating the two is a destructive error.
- **Check `adb devices` before planning anything.** An absent device is the
  normal state on a workstation. Assume nothing about what is installed until a
  device actually answers.
- **Wrap every adb call that can block in `timeout`.** `adb wait-for-device`
  with nothing attached hangs forever and burns the whole tool timeout.
- **Read the manifest for `sharedUserId` before touching the device.** It decides
  whether one app can be replaced in isolation or whether the whole family must
  be uninstalled together, and it changes the failure mode entirely.
- **Verify the artifact's identity before installing** — package, versionCode,
  signing certificate, ABIs. Installing only means something once you know what
  goes over what.
- Keep the deployment script in the repo. Reconstructing adb incantations for a
  shared-UID app family is not work to redo each session.

## Procedure

1. **Build clean, then read the artifact.** A stale APK from an earlier run is
   the most common false positive. Note `./gradlew clean` deletes the APK
   mid-flight — do not inspect it while a clean build is running.
2. **Record what ships**, and say it back to the user:
   ```bash
   BT=$HOME/Android/sdk/build-tools/<ver>
   $BT/aapt2 dump badging <apk> | grep -E '^package|locales|native-code|sdkVersion'
   $BT/apksigner verify --print-certs <apk> | grep SHA-256
   unzip -l <apk> | grep -oE 'lib/[a-z0-9_-]+/' | sort -u   # ABIs
   ```
   A debug build is signed with the `Android Debug` certificate. If the device
   holds a release-signed build of the same package, a signature conflict is
   guaranteed no matter what the version code says.
3. **Confirm the device and read its properties** — model, API level, ABI — then
   compare API against `minSdk`. An `unauthorized` state means the user must
   accept the RSA prompt on the handset; nothing on the host can clear it.
4. **Survey what is installed before proposing removals:**
   ```bash
   adb shell pm list packages | grep -E '^package:(com\.example|.*addon.*)$'
   adb shell dumpsys package <pkg> | grep -m1 -oE 'installerPackageName=[^ ]*'
   ```
   The installer reveals whether the existing build came from the Play Store,
   F-Droid, or a sideload — the origin explains a signature clash.
5. **If `sharedUserId` is set, uninstall the entire group or none.** See pitfall
   below; this is the step that most often goes wrong.
6. **Install, then verify from the package manager** rather than the install
   command's exit text alone:
   ```bash
   adb install -r -d <apk>
   adb shell pm list packages | grep -q "^package:<pkg>$" && echo installed
   adb shell dumpsys package <pkg> | grep -m1 -E 'versionName|versionCode'
   adb shell am start -n <pkg>/<launcher-activity>
   ```
7. **Give the user the in-app path to the feature you shipped.** For a new
   locale, they still select it in settings; installing does not surface it.

Use `scripts/deploy.sh` as the starting point — it parameterizes the package
family, keeps the dry-run default, honours `ADB_SERIAL` on every call site,
removes the group only on a signature mismatch, and asks before removing
anything.

## Driving the UI from adb

Use this to prove a screen renders instead of trusting a compile.

```bash
adb -s <serial> shell uiautomator dump /sdcard/ui.xml >/dev/null
adb -s <serial> shell cat /sdcard/ui.xml > /tmp/ui.xml   # parse bounds in Python
adb -s <serial> exec-out screencap -p > /tmp/shot.png    # pixel histogram + vision
```

- **A dump with only a handful of text nodes is the lock screen, not a broken app.**
  Four nodes (clock, date, battery) means the keyguard is up: check
  `dumpsys window | grep isKeyguardShowing` and ask the owner to unlock. Never
  describe the UI as broken from that dump.
- **An empty XML file is a race with an animation, not a missing view.**
  `uiautomator dump` occasionally writes nothing mid-transition; sleep ~1 s and
  retry once before concluding anything.
- **`checked` on a preference's text node is always `false`.** The real state lives
  on the child with class `android.widget.Switch` / `CheckBox`; query that node, or
  read `settings get global <key>`. Reporting "toggle off" from the text node sends
  you chasing a working feature.
- **A `GONE` view is absent from the dump — that absence is how you prove it is hidden.**
  `uiautomator dump` enumerates only attached, visible nodes, so a control set to
  `View.GONE` does not appear at all. Verify a conditional control is hidden by
  grepping the dump for its widget class (`grep -c 'class="android.widget.CheckBox"' ui.xml`
  → `0`), and confirm the *positive* case the same way before trusting a zero. Do not
  conclude "hidden" from a missing text string — the widget may simply render different text.
- **Dismiss the IME before tapping a coordinate you measured.** The soft keyboard shifts
  the input bar and everything above it, so taps computed from a pre-keyboard dump miss.
  Read the coords, then `input keyevent 111` (ESC) or `4` (BACK), wait a beat, and tap —
  or re-dump after the keyboard opens and recompute from the new bounds.
- **A BACK sent when no IME is open exits the activity.** Use BACK to close the keyboard
  only after confirming it is up; otherwise the same key press leaves the app and the next
  taps land on the launcher. The geometry tells you: with the IME shown the whole layout
  compresses (a bottom nav bar at y≈2290 on a 2400 px screen moves to y≈1420) and the page
  content can go blank, so a dumped nav bar far above the bottom IS the proof the keyboard
  is open. To defocus a field without any key event, tap a neutral label (a section title,
  the field's own caption) instead of sending BACK.
- **Re-dump after any action that grows page content.** A tap that inserts a result
  row, expands a section, or prints a status line pushes every control below it
  downward; reusing a coordinate measured before the change silently taps padding.
  Dump again once the layout settles and recompute the center from the fresh `bounds`.
- **Clearing a filled EditText needs a real clear, not a guessed DEL count.** Locate
  the field by its node (`class="android.widget.EditText"`) in a fresh dump — a screen
  can hold several, so pick by `bounds`. Tap it, send `input keyevent 123` (MOVE_END),
  then `input keyevent 67` (DEL) more times than the current string length, and confirm
  the field is empty with another dump before typing. A partial clear fuses the old
  prefix onto the new value (e.g. `https://oldhttps://new…`), which the app rejects with
  no visible error.
- **Under a lit screen the first tap after a wake only dismisses the screen-off
  state.** Send `input keyevent KEYCODE_WAKEUP`, then repeat the tap (e.g. a bottom
  tab) and re-dump to confirm the target page actually changed.
- **Compute a tap point from the clickable node's *clickable* bounds, not the
  visual bar.** A bottom-nav bar can be visually taller than the `clickable="true"`
  child it wraps; tapping the visual center may land in dead space (padding or the
  gesture strip) and silently do nothing — screenshots come back identical across
  tabs. Parse the clickable node's own `bounds="[x1,y1][x2,y2]"` from the
  `uiautomator dump` and tap its exact center. Confirm the tab actually changed:
  identical `screencap` MD5 hashes across successive taps means the taps are missing,
  not that the UI is frozen.
- Pair the dump with `dumpsys activity activities | grep ResumedActivity` and
  `pidof <pkg>`: text nodes prove the views inflated, the other two prove the
  process is alive and in front.

## On-device data and system dialogs

- **`ADB="adb -s <serial>"` then `"$ADB" shell …` fails in zsh: the variable holds a
  command with an embedded space.** `zsh: command not found: adb -s 192.168.1.239:38633`
  is the symptom, and it kills the whole command silently except for that line.
  Either use an array (`ADB=(adb -s "$SERIAL")` then `"${ADB[@]}" shell …`), or keep
  the serial separate: `adb -s "$SERIAL" shell …`. The same trap applies to
  `export ADB="adb -s …"` inside a background script.
- **`adb shell` re-splits the `$` in a nested class name.** `am broadcast -n
  "com.x/.Svc$BootReceiver"` arrives as `com.x/.Svc` because the device shell
  expands `$BootReceiver` to the empty string. Pass the whole remote command as a
  single-quoted argument and escape the dollar: `adb shell 'am broadcast -a ACTION
  -n "com.x/.Svc\$BootReceiver"'`. Verify with `dumpsys package <pkg> | grep -A3
  "Receiver Resolver Table"` that the component name in the broadcast matches the
  registered one exactly.
- **An implicit broadcast from the shell does not reach a backgrounded app on
  Android 14+.** `am broadcast -a ACTION` is accepted and reported as completed,
  but the app never receives it — the receiver must be addressed explicitly with
  `-n <component>`. Same for a non-exported Service: `am startservice` is refused
  with "not exported from uid", and `cmd activity start-service` *appears* to work
  but runs the Service under the shell uid, so it reads the wrong SharedPreferences
  and starts no server. The workable pattern is a small exported BroadcastReceiver
  inside the app that calls `startService` on its own Service, driven over
  `adb forward` + HTTP.
- **Hand-editing a SharedPreferences XML is pointless once the app has run.**
  The app holds the parsed map in memory and its next `edit().apply()` rewrites the
  whole file, dropping your line. Seed the preference through the app instead (a
  button, or a broadcast that reaches it), then confirm with
  `adb shell run-as <pkg> cat shared_prefs/<name>.xml | grep <key>`.
- **A backgrounded app loses the foreground and `screencap` returns a flat image.**
  When the owner is using the phone, `am start` briefly foregrounds your app and
  the screen then returns to theirs; a screencap taken right after can be the
  lock screen, the launcher, or another app entirely. Check
  `dumpsys window | grep mCurrentFocus` before analysing any capture, and prefer
  driving the app over HTTP (`adb forward tcp:PORT tcp:PORT` to a local server)
  so no taps are needed at all.
- **`adb shell` re-splits your quotes on the device.** A local `"…"` protects the
  argument only from the host shell; the device shell splits it again, so
  `adb shell mkdir -p "/sdcard/Pictures/My App"` runs `mkdir` on two paths and fails
  with `Read-only file system`. Send the whole remote command as one quoted string
  with single quotes inside: `adb shell "mkdir -p '/sdcard/Pictures/My App'"`. The
  same applies to `content query --where "relative_path LIKE 'x y%'"` — an unquoted
  `--where` gets shredded into flags.
- **Match system-dialog buttons by resource-id, not text.** Permission and delete
  dialogs are localized and differ per OEM: `com.android.permissioncontroller:id/
  permission_allow_all_button`, `…permission_allow_selected_button`,
  `…permission_deny_button`, and `android:id/button1` / `button2` for an AlertDialog.
  Grep the dump for the id and tap its bounds; "Allow"/"Permitir" as a selector breaks
  on the next locale.
- **Pre-grant a runtime permission to skip the dialog, revoke it to test the prompt.**
  `adb shell pm grant <pkg> <permission>` right after install; `pm revoke` re-arms the
  request path; `dumpsys package <pkg> | grep '<permission>: granted'` confirms which
  user the grant landed on.
- **Read files a debug build wrote with `run-as`**:
  `adb shell run-as <pkg> ls -l files/<dir>/`. Release builds reject it — assert
  through the UI instead of assuming the write failed.
- **Seed MediaStore before testing anything that lists media.** Push into the app's
  folder, make the scanner index it, then prove the row exists:
  ```bash
  adb push img.png "/sdcard/Pictures/My App/img.png"
  adb shell "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d \"file:///sdcard/Pictures/My App/img.png\""
  adb shell "content query --uri content://media/external/images/media --projection _id:_display_name --where \"relative_path LIKE 'Pictures/My App%'\""
  ```
  `content delete --where …` removes the row; deleting only the file leaves a stale
  row and the gallery keeps showing an item that no longer exists.
- **If `exec-out screencap -p` produces a file PIL refuses to open, pull the on-device
  capture** — `adb shell screencap -p /sdcard/s.png && adb pull /sdcard/s.png` — and
  retry once before calling the screen broken. Validate the PNG before analysing it.

## Wireless debugging

Two mechanisms, different persistence:

- **Classic:** `adb tcpip 5555` then `adb connect <ip>:5555`. Lost on reboot, no
  pairing code — fine for one session.
- **Native (Android 11+), survives reboots:** turn on *Developer options → Wireless
  debugging* (or `adb shell settings put global adb_wifi_enabled 1`), read the
  on-screen **IP address and port**, then `adb connect <ip>:<port>`. The port changes
  every time the toggle is flipped or the device reboots; the pairing itself persists.
  A previously paired host appears under "Paired devices"; pairing a new host needs
  the six-digit code shown by "Pair device with pairing code" (`adb pair <ip>:<port>`).
- Phone and workstation must share a subnet — confirm with `adb shell ip -f inet addr
  show wlan0` plus a `ping`, and note the host's own address on that interface.
- **Once on TCP the USB serial is gone**, so every later command needs
  `-s <ip>:<port>`. Verify with `adb devices` and `adb -s <ip>:<port> shell getprop
  ro.product.model` before running anything destructive. With USB **and** TCP attached
  to the same handset, plain `adb` fails with `more than one device/emulator` on every
  call — `-s` becomes mandatory, not just for destructive commands.
- Don't leave both transports connected for the same device: `adb disconnect <ip>:5555`
  after moving to the native port, or later `-s` choices become ambiguous.

## Pitfalls

- **`android:sharedUserId` turns one app into a group.** Every app carrying the
  same `sharedUserId` must share a UID *and* be signed by the same key. A build
  from a different source fails at install time with
  `INSTALL_FAILED_SHARED_USER_INCOMPATIBLE` or "signatures do not match". The
  trap is partial cleanup: uninstalling the main app and leaving its addons
  leaves survivors holding a UID the system will not reassign. Remove the whole
  family in one pass.
- **`adb wait-for-device` blocks indefinitely** with no device. Prefix with
  `timeout 15` and print the concrete unblock steps (USB mode, debugging toggle,
  on-screen authorization).
- **An install reporting success may not be the build you meant.** Confirm
  `versionCode`/`versionName` via `dumpsys` afterwards; `-r -d` replaces builds
  in ways that are easy to misread.
- **A green CI run is not a device install.** CI proves the APK assembles. Only
  `pm list packages` plus a launch proves it landed.
- **A black screencap is not a diagnosis.** An all-black screenshot can mean the display
  is off or the keyguard is on, not that the app failed. Check state first:
  `dumpsys power | grep mWakefulness` (`Dozing`/`Asleep` = screen off) and
  `dumpsys window | grep isKeyguardShowing`. A pixel histogram separates the cases
  cheaply — one colour total means nothing was drawn or the screen is off, tens of
  thousands of colours means real UI is present.
- **Behind the keyguard the app window legitimately reports
  `mDrawState=NO_SURFACE` / `mLastHidden=true`.** That is the lock screen covering it, not
  a rendering bug; do not chase it. Unlocking needs the owner's PIN or biometric — ask for
  it and wait, never attempt to bypass it.
- **Prove "it did not crash" from the crash buffer.** `adb logcat -d -b crash` together
  with `dumpsys activity activities | grep ResumedActivity` and `pidof <pkg>` is the
  authoritative post-launch check. A splash-only screenshot plus an empty `pidof` means the
  process died in `onCreate`; a black screenshot plus a resumed activity usually means
  "screen off".
- **`INSTALL_FAILED_UPDATE_INCOMPATIBLE: … signatures do not match` means the certificate
  changed** — a re-signed build cannot over-install the previous one. `uninstall` is
  required first and erases app data; confirm with the user and name what is lost
  (sessions, downloaded models, preferences) before running it.
- **For a local perf run, re-sign the release APK instead of uninstalling.** When the goal
  is measuring the `-O3` release build on a device that already holds a debug install plus
  gigabytes of downloaded models, `zipalign -p -f 4` then `apksigner sign --ks <debug-keystore>`
  the release APK and `adb install -r` it: matching the installed certificate keeps the data
  and the timing run stays valid. AGP's debug keystore is not always at `~/.android/debug.keystore`
  — locate it with `find ~ -maxdepth 4 -name debug.keystore` (an XDG / `ANDROID_USER_HOME` setup
  can place it under `~/.config/.android/`). Do this only for builds you install yourself; never
  hand out or publish a debug-key-signed artifact.
- **Never `pkill -f` a pattern that also matches your own command line.** Killing a background
  device job with `pkill -f "curl … <url>"` matches the shell Hermes itself is running that line
  in, so the tool call dies with SIGTERM (exit -15) instead of stopping the job. List first with
  `pgrep -af <pattern>`, keep the PIDs that are not your own shell, then `kill <pid>`.
- **Never clear the user's app data as a shortcut.** `adb uninstall` is
  irreversible for app state; when genuinely required, say what is lost (session
  history, downloaded packages) *before* doing it.
- **Compare signatures before uninstalling; do not remove just because something is
  present.** A deploy script that uninstalls the group whenever it finds it
  installed destroys home directory, installed packages and plugin state on every
  single reinstall, even when the keys match and `adb install -r` would have
  worked. Removal is required only when the installed signature differs from the
  artifact's. Compare the artifact's `apksigner verify --print-certs` digest with
  what the device reports for the package; when either side is unknown, treat it
  as needing removal but say so, and let the human decide. This also means the
  same-signature path never silently loses data on a rebuild-and-reinstall loop,
  which is the common way a developer exercises a change on-device.
- **Distinguish "the signatures differ" from "I could not compare them."** These
  are different states and only the first justifies the word *differs*. When
  `apksigner` is missing or the installed APK cannot be pulled, the script has no
  evidence — say that explicitly and state the consequence (an over-install will
  be rejected if they differ, and will preserve data if they match). A script that
  prints "firma distinta" from inside the unverified branch is reporting a
  conclusion it never reached, and it will read as authoritative to whoever runs
  it next.
- **Show both fingerprints when comparing them.** A verdict with the two digests
  printed above it is checkable by a reader; "firma distinta" alone is not, and it
  costs nothing to print what you already computed.
- **`dumpsys … installerPackageName` is the INSTALLER, not the signature, and it
  prints the literal string `null` for an adb sideload.** Emitting it after an
  arrow where the signature is expected (`PRESENTE: pkg  ← null`) reads as a
  failed signature lookup and sends the reader to the wrong field. Map
  `null`/empty to a readable origin and keep the digest on its own line.
- **Diagnose a script by reading what it actually computes, not the message it
  prints.** A diagnostic that looks like a failed lookup can be a perfectly
  healthy check that succeeded; the printed `null` may belong to a different
  field entirely. Reproduce the underlying command by hand before concluding the
  mechanism is broken — a plausible story about why it is broken costs more than
  the run that disproves it.
- **Install-time locale behavior is invisible to `aapt2 dump`.** After shipping a
  localized build, confirm the resource actually resolves — the APK can list a
  locale and still fall back to the base language if `resConfigs` filtered it
  (see `android-build-troubleshooting`).
- **`grep -q` + `pipefail` makes a present package look absent.** `grep -q` exits
  the instant it matches, the upstream `adb` takes SIGPIPE, and `set -o pipefail`
  surfaces **141** instead of 0 — so `if adb shell pm list packages | grep -q …`
  reports "not installed" for something that IS installed, and a dry run that
  exists to prevent destructive work silently skips its own guard. Fetch the
  list once and test against it:
  ```bash
  # wrong: rc 141 on a match
  if adb shell pm list packages | tr -d '\r' | grep -qx "package:$p"; then …

  # right: one adb call, no pipe into a short-circuiting grep
  pkgs=$(adb shell pm list packages 2>/dev/null | tr -d '\r' || true)
  is_installed() { grep -qx "package:$1" <<<"$pkgs"; }
  ```
  Reach for `grep -q` only where the rc is genuinely discarded (`>/dev/null`
  plus `!`), and never as the condition guarding an uninstall.
- **A fake `adb` on `PATH` will not reproduce volume-dependent bugs.** A stub that
  prints two packages hides anything that depends on the real output being large
  — SIGPIPE above is exactly that: a stub emits too little to trigger it. A mock
  is worth it for exercising the script's branches, but treat a green mock run
  as "no branch regressions", never as "the script is correct". Re-run against
  hardware before trusting a destructive path.
- **Verify the artifact on the device, not only on disk.** A build verified
  locally can differ from the one that installed. Pull what actually landed and
  check it: `adb pull $(adb shell pm path <pkg> | tr -d '\r' | sed 's/package://') /tmp/x.apk`,
  then inspect `resources.arsc` / `aapt2 dump` in that file. This is also the
  only way to read the *installed* app's signing digest, since `dumpsys` exposes
  only a short hash that is not comparable to `apksigner`'s SHA-256.
- **Proving the locale shipped needs two artifacts, not one.** The newly built
  APK and the APK pulled off the device are different evidence: the first shows
  the resource was packaged, the second shows what is actually installed. A
  release-signed build installed over a debug-signed one requires an uninstall
  first (different certificate), so confirm the installed digest from the pulled
  file rather than from what you built.
- **Reading localized values out of a built APK.** `aapt2 dump resources <apk>`
  prints each key with its per-locale values on consecutive lines — the `(es)`
  line is the authoritative check, and scanning it for source-script characters
  proves the locale shipped with the right values rather than merely present.
  `resources.arsc` inspection is the fallback when the values are not directly
  readable.

## Reporting

State the artifact identity (package, versionCode, ABIs, signing cert), what
was found on the device, what you removed and why, and the post-install
verification. If no device was connected, say plainly that nothing was installed
and the build is ready — never describe the deployment as done.