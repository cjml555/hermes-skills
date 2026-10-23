#!/usr/bin/env python3
"""List pending pacman updates without root or mutation.

Reads the sync DBs and the local DB directly and diffs versions. Also prints
each sync DB's mtime so the caller can judge how fresh the answer is.

Usage: python3 pacman_pending.py [sync_dir] [local_dir]
"""
import glob
import os
import sys
import tarfile
import time

SYNC = sys.argv[1] if len(sys.argv) > 1 else '/var/lib/pacman/sync'
LOCAL = sys.argv[2] if len(sys.argv) > 2 else '/var/lib/pacman/local'


def parse_desc(text):
    """Parse a pacman desc file. Format is '%KEY%' then the value on the next line."""
    fields = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('%') and line.endswith('%') and i + 1 < len(lines):
            fields[line.strip('%').upper()] = lines[i + 1].strip()
    return fields


def repo_versions():
    repos = {}
    for db in sorted(glob.glob(os.path.join(SYNC, '*.db'))):
        name = os.path.basename(db)[:-3]
        versions = {}
        try:
            with tarfile.open(db) as tar:
                for member in tar:
                    if not member.name.endswith('/desc'):
                        continue
                    text = tar.extractfile(member).read().decode('utf-8', 'replace')
                    f = parse_desc(text)
                    if 'NAME' in f:
                        versions.setdefault(f['NAME'], f.get('VERSION', ''))
        except Exception as exc:  # noqa: BLE001
            print(f'warn: could not read {db}: {exc}', file=sys.stderr)
        stamp = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(db)))
        repos[name] = (versions, stamp)
    return repos


def installed_versions():
    installed = {}
    for desc in glob.glob(os.path.join(LOCAL, '*', 'desc')):
        try:
            f = parse_desc(open(desc, encoding='utf-8', errors='replace').read())
        except Exception:  # noqa: BLE001
            continue
        if 'NAME' in f:
            installed[f['NAME']] = f.get('VERSION', '')
    return installed


def main():
    repos = repo_versions()
    installed = installed_versions()

    for name, (versions, stamp) in repos.items():
        print(f'# repo {name}: {len(versions)} pkgs, db synced {stamp}')

    pending = []
    for pkg, have in installed.items():
        for repo, (versions, _) in repos.items():
            if pkg in versions and versions[pkg] != have:
                pending.append((repo, pkg, have, versions[pkg]))
    pending.sort()

    print(f'\ninstalled: {len(installed)} | differing: {len(pending)}')
    for repo, pkg, have, want in pending:
        direction = 'UP' if want > have else 'repo-offers-older'
        print(f'{repo:10} {pkg:34} {have}  ->  {want}  [{direction}]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
