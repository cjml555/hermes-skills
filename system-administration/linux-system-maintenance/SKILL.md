---
name: linux-system-maintenance
description: Use when asked if the PC has pending updates.
---

# Linux system maintenance checks

Read-only audit of pending updates and cruft on a Linux host. The goal is a trustworthy answer without root, because the user usually cannot type a password into an automated tool. Covers pacman/Arch/Manjaro, apt, dnf, Flatpak, orphans, and AUR.

## When to Use

- The user asks whether the PC has updates, whether it is up to date, or what needs upgrading.
- After installing something manually, to confirm the repos stayed consistent.
- Routine hygiene sweeps: orphans, Flatpak updates, stale package DBs.

## Rules (always on)

- **Never run a mutating package command** (`pacman -Syu`, `apt upgrade`, `dnf update`) to answer a "do I have updates?" question. Every one of them needs root and will hang or fail; report findings and let the user run it.
- **Report staleness explicitly.** Sync DBs have per-repo timestamps. Check them and say which repos are fresh and which are not, so the user knows how much to trust the result. A clean result from a 3-week-old DB is not the same as a clean result from today's DB.
- **Separate real updates from downgrade artifacts.** Report them as distinct sections; never present a snapshot-DB version difference as a pending update.
- Answer in **Spanish** (neutral Latin American, no voseo) — that is this user's language.
- Give the verdict first ("al día, 0 pendientes"), then the caveats, then optional cleanup. Do not narrate the commands you tried.

## pacman / Arch / Manjaro

`checkupdates` and AUR helpers (`yay`, `paru`) are often absent, and `pacman -Qu` needs root. Use the bundled script instead:

```bash
python3 scripts/pacman_pending.py
```

It reads `/var/lib/pacman/sync/*.db` and `/var/lib/pacman/local/*/desc` directly and diffs versions — no root, no mutation. It also prints each sync DB's mtime so you can judge staleness.

Pitfalls:
- **Never parse `desc` files with `key=value`.** The format is a `%KEY%` line followed by the value on the *next* line; a split-on-`=` parser silently yields zero packages.
- **`mhwd.db` is a Manjaro snapshot DB that can lag far behind the real repos.** If its offered version is *older* than what is installed (mesa 26.2.2 installed vs 26.1.6 offered), that is a stale artifact, not an update. Report it under a "falso positivo" note and do not tell the user a downgrade is pending.
- Do not "fix" a `sudo: a password is required` result by copying the pacman dbpath around; `pacman -Sy --dbpath <tmp>` still requires root and just errors.

Companion checks, all read-only:
```bash
flatpak remote-ls --updates    # empty = Flatpak al día
pacman -Qdt                   # orphan packages (deps no longer needed)
```

## apt / Debian-Ubuntu

```bash
apt list --upgradable 2>/dev/null | tail -n +2
apt-get --simulate upgrade   # shows what would change; needs no root
```
Check `/var/lib/apt/lists` mtimes for staleness; if the lists are empty or old, say the answer may be incomplete rather than claiming zero updates.

## dnf / Fedora

```bash
dnf --cacheonly check-update   # exit code 100 = updates available
dnf --cacheonly list --upgrades
```

## Reporting template

1. One-line verdict with the pending count.
2. Repo/DB freshness, so the user knows how much to trust it.
3. Any non-upgrade anomalies (snapshot DB artifacts) labeled as such.
4. Optional cleanup (orphans, caches) with the exact command, offered but not run.
5. If a real refresh is needed, say so and give the command for the user to run with their own password.
