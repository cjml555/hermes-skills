---
name: hermes-desktop-linux-build
description: "Build or install the Hermes desktop AppImage on Linux."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [desktop, electron, packaging, appimage, linux]
    related_skills: [inspecting-hermes-desktop-dom]
---

# Building the Hermes desktop AppImage on Linux

## When to Use

- Installing the Hermes desktop UI on Linux for the first time
- `npm install` in `apps/desktop` dies in `node-gyp` or at `cross-env`
- `npm run builder -- --linux AppImage` fails inside `icon-tool.js`
- Pairing a WhatsApp account via the Baileys bridge

Two failures block a cold build; both look like something else.

## Prerequisite: a C/C++ toolchain

`node-pty` builds natively. Without `make`/`gcc`, `npm install` dies with
`gyp ERR! stack Error: not found: make`.

```
sudo pacman -S --needed base-devel
```

Hermes cannot run sudo — the user must do this.

## Failure 1: `cross-env: Permission denied`

Symlink targets under `node_modules/.bin/` can lose the `+x` bit. `apps/desktop`
`npm run dev` then dies with exit 126 at `cross-env`, and `concurrently -k` kills
the renderer too, so the log shows two failures for one cause.

Fix the resolved target, not the symlink:

```bash
cd ~/.hermes/hermes-agent
for f in node_modules/.bin/*; do t=$(readlink -f "$f"); \
  [ -f "$t" ] && [ ! -x "$t" ] && chmod +x "$t"; done
```

## Failure 2: `require is not defined in ES module scope` (icon-tool.js)

`icons@1.2.1` ships a CommonJS `icon-tool.js` with no `package.json` of its own, so
it inherits the repo's `"type": "module"` and Node 26 refuses to run it. Fails at
`icon-tool.js:620` while building the AppImage `set` format.

**Do not** write a shim into `build/prepared-packaging-tools/icons/` or
`build/packager/linux-x64/icons/` — both are regenerated on every run and the
file is silently deleted. Modifying files after the prepare step also breaks the
`treeDigest` validation in `prepared.json` (which hashes the entire tree
including file modes and symlink targets), causing "Missing or changed packaging
input" errors.

Patch the two repo scripts that perform the copy, so the shim is written **before**
the digest is computed — immediately after each `cpSync`:

- `apps/desktop/scripts/prepare-packaging-tools.mjs` → in `copyTool()`
- `apps/desktop/scripts/run-electron-builder.mjs` → in `toolsetArguments()`

```js
if (name === 'icons' && fs.existsSync(path.join(destination, 'icon-tool.js'))
    && !fs.existsSync(path.join(destination, 'package.json'))) {
  fs.writeFileSync(path.join(destination, 'package.json'), '{"type":"commonjs"}\n')
}
```

Verify before a full rebuild: `node icon-tool.js --help` should print the usage
line instead of the ESM error.

## Build

`npm run builder` alone packages the existing `dist/` — it does not recompile.
Always `npm run build && npm run builder -- --linux AppImage`.

Build the .deb separately (`--linux deb`); do not batch them, an AppImage-only
run avoids the fpm/Ruby toolchain entirely.

## Install

```
mv release/Hermes-*-x86_64.AppImage ~/.local/opt/hermes/Hermes.AppImage
chmod +x ~/.local/opt/hermes/Hermes.AppImage
ln -sf ~/.local/opt/hermes/Hermes.AppImage ~/.local/bin/hermes-desktop
```

Plus a `.desktop` entry in `~/.local/share/applications/` and the icon copied to
`~/.local/share/icons/hicolor/1024x1024/apps/Hermes.png`. `desktop-file-validate`
flags `Categories: Development;Utility;` as two main categories — a hint only.

## Verifying

CDP (`127.0.0.1:9222`) is open for dev runs and closed for packaged builds, so
packaged smoke tests use `ps aux | grep -c '[.]mount_Hermes'` and `xprop -root
_NET_CLIENT_LIST`. Kill the dev instance first — packaged and dev builds cannot
both hold the profile.

Chromium emits `CompositorAnimationObserver is active for too long` and gitstatus
logs `gitstatus failed to initialize` under zsh/p10k. Both are environment noise,
not app failures.

## WhatsApp bridge session path

`~/.hermes/whatsapp/session` holds `creds.json` and the pre-keys — NOT
`~/.hermes/platforms/whatsapp/session`, which the website docs state and which
stays empty. `chmod 700`; it is full account access.

`hermes whatsapp` prints a QR and needs a TTY of 60+ columns. When run through a
backgrounded PTY the wizard accepts no input and hangs — the user must run it in
their own terminal. The gateway is a systemd user service
(`hermes-gateway.service`); restart it to load a new platform.