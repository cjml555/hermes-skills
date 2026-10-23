---
name: hermes-desktop-from-source
description: "Install and launch the Hermes desktop app from source."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [desktop, electron, setup, dev-server, install, verification]
    related_skills: [inspecting-hermes-desktop-dom, node-inspect-debugger]
---

# Bringing up the Hermes desktop app from source

## Overview

Use this when the user asks whether the desktop UI is installed, wants it
installed, or wants it running. The app is a Vite renderer plus an Electron main
process living in `apps/desktop` inside the hermes-agent repo. A git checkout is
NOT a working install — dependencies, a native build, and a dev server all have
to exist before a window appears.

Verify, don't assume: report what the process table and the live renderer say,
not what `npm install` printed.

## When to Use

- "Is the desktop UI installed?" / "open the desktop app"
- A dev-server port is missing and you need the window up to inspect it
- Distinguishing "not installed" from "installed but not running"
- "Package it for daily use" / "make an installer" — the step past dev mode

**Don't use for:** reading styles/DOM once it runs — that is
`inspecting-hermes-desktop-dom`. Start here to get the window, switch there to
query it.

## Step 1 — Establish the actual state

Never answer "installed" from the presence of the source directory. Check all
five signals; the checkout exists even on a machine that has never run it:

```bash
cd ~/.hermes/hermes-agent/apps/desktop
test -d node_modules && echo "deps ok" || echo "NO node_modules"
ls dist 2>/dev/null | head            # build output; empty means never built
command -v hgui electron              # launcher binaries
ls ~/.local/share/applications /usr/share/applications | grep -i hermes
ps aux | grep -c '[e]lectron'
curl -s --max-time 3 http://127.0.0.1:9222/json/version   # CDP: empty = nothing running
```

No `node_modules` + no `dist` + no `hgui` + no Electron process + closed CDP =
not installed. Report that, then offer to install it.

## Step 2 — Native build toolchain

`npm install` compiles `node-pty` from source and dies at `node-gyp` if no C
toolchain exists. Check first and let the user install it — you cannot answer a
sudo prompt:

```bash
command -v make gcc g++ || echo "toolchain missing"
```

If missing, hand the user the command and wait:

```
sudo pacman -S --needed base-devel     # Arch / Manjaro
```

macOS needs the Command Line Tools (`xcode-select --install`) for the same
reason. Only continue once `make` and `gcc` resolve.

## Step 3 — Install dependencies

```bash
cd ~/.hermes/hermes-agent/apps/desktop && npm install
```

This is a workspace root, so it installs into the repo-level `node_modules`.
Budget several minutes and run it in the background.

## Step 4 — Repair lost exec bits before launching

A checkout that lost its file modes makes `.bin` shims non-executable, and
`npm run dev` dies at the first shim it shells out to — typically `cross-env`
with `Permission denied` and exit code 126. Fix the shims in one pass rather
than chasing one shim per run:

```bash
cd ~/.hermes/hermes-agent
for f in node_modules/.bin/*; do
  t=$(readlink -f "$f")
  [ -f "$t" ] && [ ! -x "$t" ] && chmod +x "$t"
done
```

**`Permission denied` plus a `.bin` path in the error means missing +x on the
resolved target, not a broken package.** Read the failing path in the
`dev:electron` output, fix the mode, relaunch — do not reinstall.

## Step 5 — Launch

```bash
cd ~/.hermes/hermes-agent/apps/desktop && npm run dev
```

Background it with a notify pattern so you catch readiness or failure without
polling blindly. `concurrently -k` means one leg dying kills the other, so the
first error in the log is the real cause — read the `dev:electron` / `dev:renderer`
stream, not just the final npm error.

On Linux you need a real display; check `DISPLAY` / `WAYLAND_DISPLAY` /
`XDG_SESSION_TYPE` before blaming the app for not showing a window.

## Step 6 — Prove it is up

Three independent checks, all required:

1. Renderer served: `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5174/` returns 200.
2. CDP bound: `curl -s http://127.0.0.1:9222/json/version` returns browser JSON
   with an `Electron/` token in the User-Agent.
3. DOM actually mounted: `scripts/dom-ready-probe.mjs` prints
   `mounted: true`. See the readiness gate below.

Report the concrete evidence (package count, Electron version, window title,
visible session list) rather than "the app launched".

## Step 7 — Package for daily use

Dev mode is for working on the app. "For daily use" means a packaged artifact
in the user's PATH and application menu:

```bash
cd ~/.hermes/hermes-agent/apps/desktop && npm run dist:linux
```

`dist:linux` = `build` + `builder --linux AppImage deb rpm`. The Linux target in
`electron-builder.config.cjs` is AppImage; deb and rpm are opt-in arguments on
top of it.

**Verify per artifact, not per exit code.** The three targets are built by
different toolchains, so one can fail while the others succeed — read the log for
`• building target=<name> ... file=<path>` lines and confirm each file exists on
disk. A later target failing does not un-write an earlier one.

Install the AppImage for daily use:

```bash
mkdir -p ~/.local/opt/<app> ~/.local/bin ~/.local/share/icons/hicolor/1024x1024/apps
mv release/<Name>-<version>-linux-x86_64.AppImage ~/.local/opt/<app>/<App>.AppImage
chmod +x ~/.local/opt/<app>/<App>.AppImage
ln -sf ~/.local/opt/<app>/<App>.AppImage ~/.local/bin/<app>   # CLI launcher
cp <repo>/assets/icon.png ~/.local/share/icons/hicolor/1024x1024/apps/<App>.png
```

Then a `.desktop` entry in `~/.local/share/applications/` with `Exec` pointing at
the **extracted AppImage path** (AppImages self-mount and forward args, so
`Exec=/path/to/App.AppImage %U` works), followed by `update-desktop-database`
and `desktop-file-validate`. Do not `chmod 4755` or try to run `--appimage-extract`
as an install step — moving the AppImage and symlinking it is the whole install.

**Prove it in the cold.** Shut down the dev instance you started this session,
then launch the packaged binary and confirm the window: the mount directory
appears under `$TMPDIR` (`.mount_<App>XXXXXX`), an `install stamp: <hash> (main)
from local` line appears in the log, and the X11 window list contains the app
name. Use `scripts/window-check.sh <name>`. A packaged build never opens CDP —
`electron/dev-cdp.ts` closes the port for packaged runs regardless of env vars —
so window and process evidence is the only readiness signal you get.

## Pitfalls

- **An `ERROR` line in the log is not an app failure.** On Xfce/GNOME desktop
  setups every `npm`/windowed launch also prints zsh `gitstatus failed to
  initialize`, `dbus/object_proxy.cc StartTransientUnit ... already loaded`, and
  `xdg-settings: invalid application name`. These come from the login shell and
  the session bus, not the app. Check whether the process and window still exist
  before investigating; report these as environment noise rather than sending
  the user chasing them.
- **`CompositorAnimationObserver is active for too long` means the window is
  unfocused.** A backgrounded Chromium keeps a button hover animation alive. It
  disappears when the window has focus and requires no action.
- **A watch pattern matching stale output is not a new failure.** A killed dev
  server flushes its buffered log afterwards, so an `exited with code` notification
  can land after you already moved on. Confirm which PID/session_id the notice
  belongs to before reacting.
- **The checkout existing is not installation.** Source present with empty
  `node_modules` means nothing has ever run; say so instead of hunting for a
  missing binary.
- **`rootChildren: 0` right after launch is normal.** The renderer serves an
  empty `#root` and a splash while the backend handshake completes, often tens
  of seconds. Re-probe on a loop until mounted; do not diagnose a broken
  install from the first probe.
- **A bound CDP port does not mean a mounted app.** Gate readiness on
  `readyState === 'complete'` AND `#root.childElementCount > 0`.
- **Exit code 126 on a `.bin` path is a file-mode problem.** Fix +x on the
  resolved target; reinstalling changes nothing.
- **`concurrently -k` hides the cause behind the survivor's SIGTERM.** The
  substantive error is earlier in the log than the `Lifecycle script failed`.
- **Never kill the user's dev server to make room for your own probe.** Launch
  an isolated instance on a different port and a separate `--user-data-dir`.
  Shutting down a dev server **you started in this session** in order to test the
  packaged build is fine; killing one the user launched is not.
- **A packaging-tool failure can be transient.** If a builder's helper binary
  fails with a missing shared library, run it directly to check before
  concluding the system lacks the library — retried invocation may simply work.
  Never record a resolved transient as a standing system requirement.

## Support files

- `scripts/dom-ready-probe.mjs` — poll-until-mounted readiness probe over CDP.
  Run it after launch instead of hand-writing a WebSocket client.
- `scripts/window-check.sh [name]` — list X11 windows, optionally filtered. Use it
  to confirm a packaged (CDP-less) build actually put a window on screen.
- `references/linux-packaging.md` — AppImage/deb/rpm target table, the bundled
  `fpm` toolchain layout, version numbering, and how to verify a packaged run.
