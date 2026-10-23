---
name: security-lab-setup
description: Use when building a pentest lab or CTF challenges on Linux.
version: 1.0.0
license: MIT
author: hermes-curator
metadata:
  hermes:
    tags:
      - security
      - pentest
      - docker
      - kali
      - lab-setup
    related_skills:
      - linux-system-maintenance
      - dogfood
---

# Security lab setup

Build a runnable offensive-security lab on a Linux host: containerized vulnerable
targets plus an attacker toolbox, wired so a future session can start attacking
in one command.

## When to Use

- The user asks for a pentest environment, CTF setup, or security lab.
- Vulnerable apps need deploying (Juice Shop, DVWA, WebGoat, Metasploitable,
  a deliberately misconfigured container).
- An attacker toolbox (Kali/Parrot toolset) needs installing on a workstation.
- Recreating or repairing a `~/pentest`-style workspace or its compose stack.
- Authoring flag-bearing CTF challenges, or a graded practice curriculum for
  web/network techniques.
- The user wants useful work done while away from the machine, so the lab must
  run without Docker and without sudo.
- Offline challenge categories: ELF binaries to reverse, or crypto artifacts
  (ciphers, hashes, signatures) to break. See
  `references/binary-and-crypto-challenges.md`.

Not for a one-off scan against a system the user already owns — that is a single
tool invocation, not a lab build.

## Design rules (apply to every instance)

- **Containerize the targets, never the host.** Deliberately vulnerable apps
  (Juice Shop, DVWA, Metasploitable) stay in containers on an isolated bridge
  network. Put the attacker toolbox (Kali) in a container on the SAME network so
  it reaches targets by service name.
- **Bind every published port to `127.0.0.1`.** `ports: ["127.0.0.1:3000:3000"]`,
  never `"3000:3000"`. An unqualified bind puts a deliberately broken app on the
  LAN.
- **Toolbox in a container, not the host, not a VM.** A `rm -rf` with a wrong path
  stays inside the container. A VM costs RAM the host may not have; a container
  costs ~nothing and rebuilds from a Dockerfile.
- **Split work by privilege, and never block on sudo.** `sudo` needs an interactive
  password, so the agent cannot supply it. Build every root-free piece first —
  workspace, release binaries, compose files, scripts, docs — then hand the user one
  copy-pasteable `sudo` block and say plainly what is still missing. Do not stall a
  task waiting on a password.
- **Verify by execution before reporting done.** Stand up a throwaway HTTP server,
  run the scanner against it, confirm real findings. A compose file that has never
  run is not a lab.

## Two deliverables: a lab AND challenges

These are different asks and the user distinguishes them. A **practice
curriculum** is prose: objectives, tool commands, a pass criterion per exercise.
A **CTF challenge set** is running software: each vulnerability reachable, each
one hiding a flag, each flag verifiable. If the user says "challenges", a
curriculum does not satisfy it — build the challenges.

When the user may be away from the machine, challenges must run with **no Docker
and no sudo**: pure-stdlib Python services on `127.0.0.1`. See
`references/ctf-challenge-authoring.md`.

## Procedure

1. **Recon the host first** — OS, RAM/CPU, free disk, virtualization support,
   which tools already exist. This decides container-vs-VM and whether RAM allows
   a full desktop VM.
2. **Ask the target profile in ONE clarify call** (objective, isolation strategy,
   toolbox distro, target categories). Do not serially ask one question per turn;
   these answers are independent and a form beats a chain of round-trips.
3. **Create the workspace layout** — `targets/ scripts/ tools/ wordlists/
   evidence/ notes/ reports/`, git-init it, `.gitignore` the vendored tool dirs.
4. **Install root-free tooling** — see `references/tooling-install.md`. Release
   binaries and `uv`-managed tools first; leave pacman/docker for the user's sudo.
   Write the sudo handoff as a committed, idempotent script (copy
   `templates/sudo-install.sh`), not only as prose in `notes/00-install.md`, so the
   user runs one command and the log survives.
5. **Pre-flight the published ports against the host** — before writing
   `compose.yml`, run `ss -ltnp` and diff the desired host ports against what
   already listens. See the port-collision pitfall below.
6. **Write the target stack** as one `compose.yml` + one toolbox `Dockerfile`.
   Service names must be the addressing scheme the attacker uses.
7. **Write operator scripts** — `up.sh` (with useful group flags), `down.sh`,
   `scan.sh`, `<toolbox>.sh`, and a wrapper for any heavyweight scanner.
   `bash -n` every script.
8. **Write the notes** — install doc (the sudo block, verbatim), workflow doc
   (recon → mapping → scanning → exploitation → documentation), cheat sheet with
   per-app attack recipes and default credentials.
9. **Verify end-to-end** against a local test server, then clean up the server.
10. **If challenges were asked for, build them and solve them yourself** — see
   `references/ctf-challenge-authoring.md`. Ship the orchestrator with `start` /
   `stop` / `status` / `solve`, and run `solve` to prove every flag resolves.
11. **Add offline categories the user asks for** — reversing binaries, crypto
    artifacts — via `references/binary-and-crypto-challenges.md`. Each gets its
    own generator plus a verifier that proves every flag resolves, including
    negative assertions (an anti-debug level must be shown to actually block).
12. **If the user asks for different experience levels, or the set grows past
    ~20 challenges, level it** — see `references/difficulty-levels-and-progress.md`.
    Mix categories inside each tier, derive the points table from the tracker's
    data rather than by hand, and keep exploit-authoring challenges out of the
    auto-marked set.

## Pitfalls

- **A lab host is not a clean host — pre-flight every published port.** `ss -ltnp`
  before writing `compose.yml`, because long-lived host services already own the
  tidy numbers a lab reaches for first. On a Hermes host the messaging bridges and
  the desktop CDP port are always taken; a collide there means `docker compose up`
  fails with a bind error the user hits only AFTER the sudo block runs, so the
  root-free fix is invisible until it is too late. Pick non-colliding host ports
  (e.g. 1xxxx instead of 3000) and keep the mapping documented in one place.
- **Renaming a port means renaming it everywhere in one pass.** After changing a
  published port, grep the whole workspace — compose, operator scripts, notes,
  cheatsheets, README, hardcoded default target lists — or the docs send the user
  to a port that no longer answers. Exclude vendored tool sources from the grep or
  a cloned repo's own docs bury the real hits.
- **Ship the sudo handoff as a script that verifies itself.** A prose code block
  in a note cannot tell the user which packages silently failed. Make it one
  committed executable that logs, retries, verifies every binary at the end, and
  prints the manual follow-up (re-login for group changes, then which stack to
  start). See `templates/sudo-install.sh`; the details that make it survive a real
  home are in `references/tooling-install.md`.
- **`uv tool install` cannot install Go tools.** ffuf, nuclei, httpx and most of
  the modern web-tooling ecosystem are Go, not Python; the registry search fails
  with "No solution found". Fetch release binaries instead.
- **Verify a downloaded release is really the archive before extracting.** Pipe
  failures are silent-ish (`tar: not in gzip format`). Use
  `curl -sSL -w "http=%{http_code} size=%{size_download}" -o f.tgz <url>`, then
  `file f.tgz`. Drop the `-L` and GitHub's redirect returns an HTML page that
  poisons the extractor.
- **`set -e` in a multi-download loop hides later steps.** The first failure aborts
  the script and the remaining tools are silently absent while earlier output
  still looks like success. Verify each binary with `-V` / `--version`
  afterward, and check `ls tools/bin` actually lists everything expected.
- **List release assets before guessing filenames.** Query the API
  (`curl -s https://api.github.com/repos/OWNER/REPO/releases/latest | grep
  browser_download_url`). Some projects publish NO binaries at all — WhatWeb is a
  Ruby gem with no release assets, so clone the source and use it from the
  toolbox container.
- **A repo with no `pyproject.toml`/`setup.py` cannot be `uv tool install`ed from
  git either.** Clone it, create a private venv, and `uv pip install -r
  requirements.txt`. Use the venv's python explicitly in scripts.
- **Check `<tool> -h` before hardcoding flags into a script.** CLIs drop and rename
  flags across majors (nuclei v3 removed `-target-lhost`). A flag written from
  memory fails at runtime, not at authoring time.
- **Scope template-driven scanners when verifying.** A full nuclei run against a
  trivial server can exceed several minutes; pass explicit `-t <dirs>` to prove the
  toolchain works.
- **A `.gitignore` written after `git add` protects nothing.** Generated lab state
  (PID files, sqlite DBs, secret files the challenge generates at boot) lands in
  the first commit and stays tracked. Put every generated path in the ROOT
  `.gitignore` before committing, and `git rm -r --cached <paths>` + commit if
  they are already in.
- **Never pipe a script that spawns detached children into `tail`/`head`.** The
  children inherit the pipe's write end, so the reader never sees EOF and the
  call hangs until timeout even though the script succeeded. Redirect the
  script's own output to a file and read that instead.
- **A level must mix categories.** All-web in N1 and all-crypto in N2 makes the
  ladder feel like subject blocks; interleaving forces the tool-switching that is
  the actual job skill. Keep exploit-authoring challenges (pwn ROP chains, heap
  UAF) out of the auto-marked set — a script that replays the answer teaches the
  player that verification equals solving.
- **A "solvable" claim needs two independent proofs, not one.** A verifier that
  replays the known answer proves the answer is *embedded*; it does not prove a
  player can *obtain* it. Ship both when the classes differ: a generator-side
  assertion (the artefact contains the secret) plus a player-side decode
  (read the bytes the way a player would). The gap between those two is exactly
  where a challenge breaks while still passing every check.
- **Assert the encoded payload and the decoded value, not the constant.** When a
  challenge stores an obfuscated flag, have the verifier extract it the same way
  a player would — decode the table, not `grep` for a literal also present in the
  generator. A shared literal makes a wrong flag pass as correct.
- **Grep generated files for stray non-ASCII before committing.** Long generated
  YAML/Markdown/Compose picks up occasional foreign characters in comments; they
  survive lint and reach the commit, so grep every generated file and patch out.
- **Assume an optimizer or simplifier will undo obfuscation you wrote by hand.**
  gcc merges adjacent string literals back into one, so a challenge built from
  `{"FLA", "G{a", "n", ...}` to hide a flag from `strings` reveals it instantly.
  Store obfuscated bytes (XOR-ed with a constant) and decode at runtime instead
  of relying on source-level tricks the compiler can fold. Then verify with the
  real tool: if `strings` shows the flag, the level teaches nothing.
- **An adversarial control is not a challenge until you prove it blocks.** For an
  anti-debug level, assert BOTH directions — the flag appears when run normally
  AND is absent under `gdb`. Make the negative case a real pass/fail line in the
  verifier; a decorative mitigation that the tool walks straight past is worse
  than no level, because it teaches the opposite of the lesson.
- **`GROUPS` is a bash special variable — never use it as your own array.** It
  holds the user's supplementary GIDs and is effectively read-only: `GROUPS=(web net)`
  is silently ignored, no error. The script then passes the GIDs to the underlying
  command, which fails far away from the cause (`docker compose up 1001 90 98 ...`
  → `no such service: 1001`). Rename the variable and leave a comment, because the
  symptom points at the wrong file entirely.
- **A compose service name that does not exist is silent until `up`.** Pin real
  tags, not remembered ones: `webgoat/webgoat:8.0` does not exist (only `latest` and
  `vYYYY.N`); `vulnerables/web-dvwa:1.9` and `bkimminich/juice-shop:v20.2.0` do.
  Query the registry API for tags instead of guessing — a wrong tag aborts the whole
  pull and every other image comes back `No such image`.
- **Never mount a named volume over a single FILE the image's entrypoint writes.**
  WordPress + `volumes: [wp-config:/var/www/html/wp-config.php]` mounts it as a
  *directory*, so `cp wp-config-docker.php wp-config.php` dies with
  `wp-config.php: Is a directory` and the container restart-loops forever. Let the
  entrypoint generate the file from its own env vars.
- **A built-in container healthcheck can fail for reasons unrelated to the app.**
  `webgoat/webgoat` ships `HEALTHCHECK curl ...` but the image has neither curl nor
  wget, so it reports `unhealthy` while serving fine. Note also that `CMD-SHELL`
  runs under `/bin/sh` (dash), where `exec 3<>/dev/tcp/...` fails with
  `cannot create /dev/tcp/...` — `/dev/tcp` is a *bash* feature. Override with
  `test: ["CMD", "bash", "-c", ...]` and pick a probe that exists in the image.
- **Scanning a container by bare IP silently hits port 80.** Each image listens
  elsewhere (Juice Shop 3000, WebGoat 8080 *behind a context path*), so
  `curl http://$IP` returns "connection refused" and the recon script reports
  "sin respuesta" for a healthy target. Encode `name:port:path` per target.
- **On Hermes hosts, `TMPDIR` is redirected to the session scratch dir.** Files you
  create under `/tmp` are not where a later process expects them — put lab fixtures
  inside the workspace and pass an explicit `--directory`.
- **Verify a `setcap` grant actually took effect by running the tool without sudo.**
  `getcap /usr/bin/nmap` showing `cap_net_raw,cap_net_admin=eip` is only the intent;
  a real `-sT` scan with no password proves it. Also check the binary the user will
  actually invoke — `command -v` may resolve to a wrapper.
- **`command -v X` in a verify loop reports false negatives for split packages.**
  The package `metasploit` installs the binary `msfconsole`, never
  `metasploit-msfconsole`. Confirm with `pacman -Ql <pkg> | grep bin/` and verify the
  binary name, or a completed install reports as broken.

## Managing local lab processes

- **Find PIDs by command line, never by a saved `$!`.** `( cmd & echo $! )` records
  the subshell PID, so `kill` is a no-op and the service looks unstoppable.
  `pgrep -f "python3 app.py"` is robust across restarts; use it for both status
  and stop.
- **Detach with `setsid nohup ... < /dev/null &`** so the service survives the
  parent shell and does not hold any inherited descriptor.
- **Set `allow_reuse_address` as a subclass attribute before binding.** Assigning
  `server_address` after `ThreadingTCPServer(...)` is a no-op — the bind already
  happened, so a fast restart dies with `EADDRINUSE` from TIME_WAIT sockets.
- **Check the port before starting and verify it listens after**, via
  `ss -ltn | grep ":$port "`. A process that started but whose port is dead is a
  distinct failure worth reporting as its own message.

## Hosting a local server for verification

Start throwaway HTTP servers with `terminal(background=true)` — plain
`nohup`/`&`/`disown` wrappers are rejected by the terminal tool. Kill them via the
process tool when done, and verify readiness with a real request, not a sleep.

## references/

- `templates/sudo-install.sh` — copy into `<workspace>/scripts/sudo-install.sh`
  as the one-command sudo handoff: logs, retries, resolves the real user so
  `$HOME` is not `/root`, applies `setcap`, verifies every binary, prints the
  manual follow-up. Replace `<LAB>`/`<LAB_DIR>`/`<USER>` and the port list.
- `references/tooling-install.md` — root-free install recipes per tool, SecLists
  download, and how the sudo handoff script must be shaped.
- `references/target-catalog.md` — vulnerable-app catalog: image, ports, default
  credentials, and what each app is good for teaching.
- `references/ctf-challenge-authoring.md` — building and verifying flag-bearing
  web/network challenges that run without Docker or sudo; flag design,
  solve-the-lab self-test, orchestrator patterns, SecLists paths.
- `references/binary-and-crypto-challenges.md` — reversing and crypto challenge
  generation: compiling strippable ELF challenges, known-plaintext XOR recovery,
  modular-inverse decoding, proving anti-debug works, objdump parsing, and a
  crypto weakness ladder.
- `references/difficulty-levels-and-progress.md` — grouping a multi-category set
  into skill tiers that build on each other, deriving points from the tracker,
  classifying challenges as auto-verifiable vs exploit-authoring, and parsing
  verifier output into a progress file.