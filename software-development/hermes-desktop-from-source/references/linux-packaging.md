# Linux packaging notes (Hermes desktop)

## Targets

| Target | Builder | Default in config? | Daily-use relevance |
|---|---|---|---|
| AppImage | electron-builder + appimage-tools runtime | yes (`linux.target`) | primary; self-contained, no install step |
| deb | electron-builder + `fpm` (portable Ruby under `build/prepared-packaging-tools/fpm/`) | opt-in flag | only for `dpkg`/apt-style flows |
| rpm | same `fpm` | opt-in flag | only for Fedora/RHEL-style flows |

Commands:

```bash
npm run build                  # renderer + electron main only
npm run builder                # whatever the config targets (AppImage on Linux)
npm run dist:linux             # build + AppImage deb rpm
npm run builder -- --linux deb # one target, useful for retrying after a fix
npm run dist:bundled           # stages a fresh bundled runtime (heaviest)
```

## fpm helper layout

`build/prepared-packaging-tools/fpm/` contains a self-extracting toolchain:

- `fpm` — bash wrapper, sources `ruby.env` then execs the real binary
- `ruby.env` — sets `PATH`, `GEM_HOME`, `RUBYLIB`, and `LD_LIBRARY_PATH` to the
  portable Ruby; this is why the helper can miss system libraries
- `ruby-3.4.3-portable/` — the interpreter and its bundled `.so` files

Debug it directly rather than through electron-builder:

```bash
cd ~/.hermes/hermes-agent/apps/desktop/build/prepared-packaging-tools/fpm
./fpm --version
```

If that succeeds but the build still fails, the problem is upstream of fpm
(electron-builder's env or the packaging config), not the Ruby.

## Version numbering

Without `--config.buildVersion=`, electron-builder falls back to `0.0.0` when it
cannot detect a version from the workspace lock file. Harmless for a personal
build; pass an explicit version if the artifact name matters.

## AppImage vs deb: which to install

Prefer the AppImage for daily use on Linux. It needs no root, survives Hermes
source updates, and can be symlinked into `~/.local/bin` plus a `.desktop` entry.
The deb installs into `/opt/<App>` and needs the `.deb` toolchain to build.

## Verifying a packaged build

- No CDP: packaged runs never bind `9222`, so DOM inspection is unavailable.
- Process evidence: `$TMPDIR/.mount_<App>XXXXXX/<binary>` exists while running.
- Log evidence: `install stamp: <hash> (main) from local`.
- Window evidence: `scripts/window-check.sh <name>` lists the X11 window.
