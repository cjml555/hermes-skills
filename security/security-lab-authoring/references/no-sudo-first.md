# No-sudo first, sudo later

The user is frequently away from the machine. Design the lab so the no-`sudo`
half is genuinely useful on its own, and leave the `sudo` half as a
copy-paste block for when they return.

## What you can do without sudo

| Need | No-sudo route |
|---|---|
| Go CLI tools (ffuf, nuclei, httpx) | Release binaries via `curl -sSL`, `unzip`/`tar xzf`, `chmod +x` |
| wordlists | `curl` individual files from the upstream repo's raw tree |
| Python CLIs | `uv tool install`, or `uv venv` + `uv pip install -r requirements.txt` |
| Source-only tools (WhatWeb) | `git clone --depth 1`; run from the container later |
| Vulnerable web/net targets | Python stdlib HTTP/socket servers — no deps at all |
| Reversing/pwn binaries | `gcc` is usually already present |

Check what the package manager actually offers before assuming:
`pacman -Si <pkg> | grep Repository` distinguishes real repos from AUR.

## Locating list files that moved upstream

A raw-URL guess 404s when upstream reorganizes. Walk the repo tree once and
filter locally rather than guessing paths:

```python
import json, re, urllib.request
tree = json.load(urllib.request.urlopen(
    "https://api.github.com/repos/<owner>/<repo>/git/trees/master?recursive=1"))["tree"]
paths = [t["path"] for t in tree if t["type"] == "blob"]
hits = [p for p in paths if re.search(r"pattern", p.lower())]
```

Write the API response to a file before parsing — a large tree truncates
in-memory and yields a JSON parse error that looks like a network problem.

Verify each download with `http=200 size=<n>`; delete anything that didn't land.

## The sudo handoff

Put the remaining `sudo` work in a single notes file as copy-pasteable blocks,
grouped, each with a one-line "why":

```bash
sudo pacman -S --needed docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # close and reopen the session after
```

Include the gotcha that the group change only applies to new sessions, and a
verification command (`docker run --rm hello-world`).

## Reporting split

Say plainly which half is verified now and which is blocked on them, and give
the exact command they'll run later. Don't imply the container half works —
it hasn't run yet.