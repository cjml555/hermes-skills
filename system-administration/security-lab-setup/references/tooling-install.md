# Root-free tooling install

Install order matters: everything here works without `sudo`, so do it before
asking the user for a password.

## Release binaries (Go tools)

No package manager needed; fetch the release asset directly.

```bash
cd ~/pentest/tools/bin

# ffuf — asset name is ffuf_<ver>_linux_amd64.tar.gz with a v-prefixed tag
VER=$(curl -s https://api.github.com/repos/ffuf/ffuf/releases/latest \
      | grep -m1 '"tag_name"' | cut -d'"' -f4)
curl -sSL -w "http=%{http_code} size=%{size_download}\n" -o ffuf.tgz \
  "https://github.com/ffuf/ffuf/releases/download/${VER}/ffuf_${VER#v}_linux_amd64.tar.gz"
file ffuf.tgz && tar xzf ffuf.tgz ffuf && chmod +x ffuf && ./ffuf -V

# nuclei — asset is nuclei_<ver-no-v>_linux_amd64.zip
NUC=$(curl -s https://api.github.com/repos/projectdiscovery/nuclei/releases/latest \
      | grep -m1 '"tag_name"' | cut -d'"' -f4)
curl -sSL -o n.zip \
  "https://github.com/projectdiscovery/nuclei/releases/download/${NUC}/nuclei_${NUC#v}_linux_amd64.zip"
unzip -oq n.zip nuclei && rm n.zip && chmod +x nuclei && ./nuclei -version
./nuclei -update-templates     # templates land in ~/nuclei-templates
```

Verify the template install actually produced files — `nuclei -update-templates`
reports success even when the directory is empty.

## Python tools via uv

`uv` handles isolated installs with no `sudo` and no `pip --user` mess. It CANNOT
install Go tools, and it cannot install a plain git repo that has no packaging
metadata.

```bash
export PATH="$HOME/.local/bin:$PATH"

# Works: real PyPI package
uv tool install <pypi-package>

# Fails: git repo with no pyproject.toml / setup.py
uv tool install "git+https://github.com/OWNER/REPO.git"
#   → "does not appear to be a Python project"
# Fix: clone, private venv, requirements
git clone --depth 1 https://github.com/OWNER/REPO.git tools/REPO
cd tools/REPO
uv venv .venv -q && . .venv/bin/activate && uv pip install -q -r requirements.txt
.venv/bin/python main.py -h          # verify
```

In scripts, call the venv interpreter explicitly:
`tools/REPO/.venv/bin/python tools/REPO/main.py`.

## Ruby-gem tools with no release binaries

```bash
curl -s https://api.github.com/repos/OWNER/REPO/releases/latest \
  | grep -oE '"browser_download_url": "[^"]*"'   # empty → no binaries published
git clone --depth 1 https://github.com/urbanadventurer/WhatWeb.git tools/whatweb-src
```

Do not try to build these on the host if Ruby is absent. Use them from the
toolbox container instead (`scripts/kali.sh -c "whatweb ..."`).

## What to hand the user for sudo (Arch/Manjaro)

Ship it as a **committed executable script**, not a code block in the note. Copy
`templates/sudo-install.sh` into `<workspace>/scripts/` and adjust it. A prose
block cannot tell the user which package silently failed six months later; the
script can, because it verifies and logs. Point the note and the README at the
one command (`sudo <workspace>/scripts/sudo-install.sh`) and keep the per-package
commentary in the note as reference.

The pieces the script must contain:

```bash
# container runtime — required for the whole stack
sudo pacman -S --needed docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"        # REQUIRES re-login / newgrp docker

# host-native offensive tooling
sudo pacman -S --needed nmap wireshark-cli radare2 john hashcat aircrack-ng \
  sqlmap hydra gobuster nikto openbsd-netcat socat jq metasploit masscan \
  lynis jdk-openjdk

# capture without sudo thereafter
sudo setcap cap_net_raw,cap_net_admin+eip "$(readlink -f "$(command -v nmap)")"
sudo setcap cap_net_raw,cap_net_admin+eip "$(readlink -f "$(command -v tshark)")"
```

Properties that make it survive contact with a real home:

- `set -uo pipefail`, **never `set -e`** — one failing step must not abort the
  daemon setup and the verification pass that come after it.
- Resolve the real user from `SUDO_USER` and set `export HOME` accordingly. Under
  `sudo`, `$USER` is root and `$HOME` is `/root`, so a log path built from them
  lands outside the workspace and the user cannot find the record.
- `exec > >(tee -a "$LOG") 2>&1` — the user watches progress and a file survives.
- `pacman -Sy` then retry the batch once: a stale/absent package list makes the
  whole multi-package install fail on a single missing member.
- Treat `systemctl start docker` failing as a warning, not fatal — the daemon
  refuses to start inside some containers/chroots while the install itself
  succeeded.
- End with a verification loop over `command -v` for every promised tool, plus
  `docker compose version` and `docker run --rm hello-world`, and print an honest
  `SIGUEN FALTANDO: ...` line rather than claiming success.
- Close with the manual steps the script cannot do: `newgrp docker` (or
  re-login, because the group change only applies to new sessions), then which
  stack group to start first and which are heavy.
- Tell the user the runtime: ~10-20 min, and the Kali image build alone is a big
  share of it, so they do not assume it hung.

Notes to state in the doc: `wireshark-cli` provides `tshark` on Arch (there is no
separate `tshark` package); the `usermod` group change only applies to NEW
sessions, so verify with `docker run --rm hello-world` after re-login; probe
package availability with `pacman -Si <pkg> | grep '^Repository'` and mark
AUR-only tools explicitly rather than assuming a repo copy exists.

## Choosing published ports on a live host

Run `ss -ltnp` **before** writing `compose.yml`, not after the sudo block fails.
Long-lived host services already own the tidy numbers a lab reaches for first,
and on a Hermes host the messaging bridges plus the desktop CDP port are always
taken. Pick 1xxxx for the first target rather than 3000, keep every bind on
`127.0.0.1`, and give the toolbox/proxy its own port so it cannot collide with a
target either.

When you renumber, treat it as one atomic change: grep the whole workspace for
the old port and update compose, operator scripts, hardcoded default target
lists, notes, cheatsheets, and the README. Exclude vendored tool sources from
that grep — a cloned WhatWeb or a SecLists checkout contains thousands of
incidental hits that bury the real ones. Then state the final port table in the
README so there is exactly one place to look, and record WHY the non-obvious
number is what it is.

## Wordlists: SecLists without hardcoded paths

SecLists paths move between releases; guessing them yields 404s. Read the repo
tree and filter locally instead of printing it (thousands of lines, truncates
mid-JSON):

```bash
curl -sSL -o /tmp/sl-tree.json \
  "https://api.github.com/repos/danielmiessler/SecLists/git/trees/master?recursive=1"
# then parse /tmp/sl-tree.json with a script, filtering .txt/.lst blobs by regex
```

Fetch each resolved path with
`curl -sSL -w "%{http_code}" -o dest "$BASE/$path"`, delete non-200 results, and
report the byte count. Categories worth having for web + network practice and
their current names: `Discovery/Web-Content/DirBuster-2007_directory-list-2.3-medium.txt`,
`Discovery/Web-Content/raft-medium-directories.txt`,
`Discovery/Infrastructure/nmap-ports-top1000.txt`,
`Discovery/DNS/combined_subdomains.txt`,
`Discovery/SNMP/common-snmp-community-strings.txt`,
`Fuzzing/LDAP.Fuzzing.txt`,
`Passwords/Common-Credentials/xato-net-10-million-passwords-100000.txt`,
`Passwords/Default-Credentials/ssh-betterdefaultpasslist.txt`,
`Usernames/Names/malenames-usa-top1000.txt`.

Compose a `users.txt` by concatenating several username lists plus service
defaults, and make sure every path referenced in your docs exists on disk.

## Distribution toolbox image

```dockerfile
FROM kalilinux/kali-rolling
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      kali-linux-default kali-tools-top10 kali-tools-web kali-tools-cryptography \
      kali-tools-credential-stuffing kali-tools-exploitation kali-tools-passwords \
      kali-tools-reporting zaproxy seclists \
    && rm -rf /var/lib/apt/lists/*
```

First build takes 10-20 minutes. Say so when handing it over.