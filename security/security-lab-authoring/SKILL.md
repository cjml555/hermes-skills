---
name: security-lab-authoring
description: Use when building a pentest/CTF lab or vulnerable challenge.
---

# Security lab authoring

Building practice environments: pentest labs, CTF challenges, deliberately
vulnerable targets, network practice ranges.

## When to Use

- The user asks for a pentest lab, CTF set, vulnerable target, practice range,
  or attack/defence exercise environment.
- You are writing a challenge that is *meant* to be exploited — overflow,
  injection, format string, weak crypto, reverse engineering, heap corruption.
- You are standing up deliberately vulnerable containers (Juice Shop, DVWA,
  Metasploitable, WebGoat) or local vulnerable services.
- You are deciding what tooling a security lab needs, and which parts of it can
  be installed without `sudo`.

Not for assessing real third-party systems — that needs a written scope and
authorisation first, which is step 1 below.

## The rule that governs everything here

**A challenge that was written is not a challenge that exists. Verify it by
exploiting it yourself, with the real tools, before reporting it done.**

Compiling is not working. A web app that starts is not working. Report only
what you saw a tool actually print.

## Order of work

1. **Decide isolation before writing any challenge.** Ask the user: authorized
   scope (own lab / CTF / client with written scope), isolation method
   (container / VM / native + localhost), and target categories. Never build
   before that answer. Record the answers in the lab README.
2. **Ship the zero-sudo path first.** Install what needs no `sudo` (release
   binaries, `uv` tools, Python stdlib servers) and get it verified. Leave the
   `sudo` steps in a notes file as a copy-paste block for later. If the user is
   away from the machine, the no-sudo half is the deliverable that matters.
3. **Bind every challenge to loopback or an internal Docker bridge.** Publish
   ports as `127.0.0.1:<port>:<port>`, never bare. Name the vulnerable images
   in a comment so nobody ships them by accident.
4. **Write the verification harness alongside each category.** A `verify.sh` /
   `verify.py` per category that resolves or proves each challenge. Run it. Fix
   the challenge when it fails — not the harness.
5. **Write the no-spoiler guide last**, from the finished challenges, with
   indirect hints, the CWE/technique mapping, and a points table.
6. **When the set spans several experience levels, grade it before writing the
   guide.** Group challenges by post-condition ("after this you can…"), not by
   category, and let the level roster generate both the guide and the tracker
   so the two cannot drift. See `references/curriculum-and-progress.md`.

## Proving a challenge works

Prove the *property announced*, not just that the program starts:

- **Overflow / memory corruption** — assert the crash signal (`rc == -11` for
  SIGSEGV), and that short input completes cleanly. A binary that also dies on
  valid input is broken.
- **Stack canary** — assert `SIGABRT` / `stack smashing detected` on a long
  payload *and* clean exit on short input. If both crash, the mitigation isn't
  being exercised.
- **Anti-debug** — assert BOTH branches: normal run yields the secret, `gdb
  -batch -ex run` must NOT. A single-branch check misses a no-op check.
- **Format string** — assert real leaked pointers match `0x[0-9a-f]{6,}`. Accept
  `SIGSEGV` on `%s` as correct behavior (reading an arbitrary pointer crashes);
  do not assert clean exit there.
- **Crypto** — assert the recovered value equals the flag, not merely that the
  function ran.
- **Web** — resolve every challenge end-to-end with `curl`, including the
  multi-flag challenges, and confirm the flag count matches the points table.

## Proving multi-layer transforms compose

Challenges that stack transforms (XOR a blob, then wrap in base64, then
compare byte-by-byte) fail in the middle, not at the edges. Build each layer
with a known answer and assert **every** boundary before compiling:

- encode → decode returns the original, per layer;
- the final compare target equals the flag, assembled from the parts;
- a hand-rolled split must not gain or lose a character — concatenate and
  assert equality rather than eyeballing the separator list.

Two bugs of this shape look identical and both compile cleanly once the
source is right, so the assertion is the only thing that catches them: a
modular division that needs the inverse, and a secret split into parts with a
duplicated piece.

## Assembling binary container formats by hand

Some forensics challenges depend on a specific tag or header, and the obvious
library silently rewrites it.

- **PIL drops custom EXIF tags.** `img.save(path, exif=handbuilt_exif)` does not
  preserve tags PIL does not itself model. When the challenge hangs on a
  particular tag, hand-assemble the file: a JPEG is `SOI` + `APP1` + `EOI`, with
  the APP1 payload `b"Exif\x00\x00" + tiff` where `tiff` is the **complete**
  header starting `MM\x00\x2a`. Slicing the TIFF with `tiff[6:]` and
  re-prepending the identifier drops the header — the file still opens as a JPEG,
  so only a structural assertion on the bytes catches it.
- **LSB steganography**: build the cover image with all non-message LSBs forced
  to zero so the result reads as a natural gradient, then re-read the *saved*
  file through the library and assert the message round-trips. Asserting against
  the in-memory buffer proves nothing about what was written.
- **Slack-space challenges** are best taught with an invented block layout: a
  superblock plus inodes where one inode points at a real block with size 0.
  That reproduces "deleted data still on disk" without needing a real filesystem
  image.

## Pitfalls

- **Challenge generators are themselves code — verify their math.** Encoding
  a value with an arithmetic transform and dividing it back is not an inverse.
  Modular division needs the modular *inverse* (`3⁻¹ mod 256 = 171`, not
  `/3`). Build the encoding, then assert decoding returns the original before
  shipping the binary.
- **Escape sequences in generated C.** When C source lives in a Python string,
  `\n` becomes a real newline and breaks `printf`. Keep the C escape doubled so
  the compiler receives `\n`. Symptom: `missing terminating " character`.
- **Watch for duplicated characters when hand-splitting a secret into parts**
  to defeat `strings()`. Concatenate the parts in Python and assert the result
  equals the flag; a duplicated or dropped piece compiles fine and is wrong.
- **`strip` makes binaries unsolvable with `ELF.symbols()`.** Either ship
  unstripped for practice, or state in the guide that addresses must come from
  `objdump`. Decide deliberately and tell the user.
- **`nuclei` v3 renamed flags.** `-target-lhost` is gone; use `-target` with a
  comma list. Check `nuclei -h` for the installed version rather than assuming.
- **Full nuclei against a trivial server hangs.** Scope with `-t` on
  template subdirectories (`http/technologies/`, `http/misconfiguration/`) plus
  a `timeout`.
- **GitHub release downloads need `-L`.** `curl` without it returns the redirect
  body, not the tarball; the symptom is `gzip: not in gzip format`. Use
  `curl -sSL` and confirm `http=200 size=<n>`.
- **`pip`/`uv` names differ from GitHub repos.** `ffuf` is Go, not Python —
  install from releases. Repos without `pyproject.toml`/`setup.py` won't
  `uv tool install`; use `uv venv` + `uv pip install -r requirements.txt`.
- **`bind()` without `allow_reuse_address` set beforehand fails with
  `EADDRINUSE` after a fast restart** (TIME_WAIT). Set it on a subclass
  *before* constructing — reassigning `server_address` afterwards does not move
  the socket.
- **Manage daemonized helpers by cmdline, not by saved `$!`.** A `$!` from a
  backgrounded subshell is the subshell, not the worker; `stop` then silently
  does nothing. Use `setsid` to detach, then `pgrep -f "python3 <script>"` for
  both status and stop.
- **Don't pipe a long-lived daemon's stdout to `head`/`tail`.** The reader
  never sees EOF, so the caller hangs until timeout even though the service came
  up. Redirect to a log file and read the file.
- **`objdump -s` has a trailing ASCII column.** Naive hex extraction mixes
  printable chars into the hex and `bytes.fromhex` raises. Slice the hex
  columns before decoding.
- **Nested `.gitignore` files do not exclude from a parent repo's index.** The
  root `.gitignore` must list generated state (databases, `.pid` files,
  compiled binaries, embedded clones), and `git rm -r --cached` the paths that
  already slipped in. Cloned tool repos get committed as gitlinks unless listed.
- **Write files without passing tool output back through.** Copying a helper's
  stdout into `write_file` embeds line-number prefixes or errors as file
  content, and the write is refused. Use `patch` for surgical edits instead.
- **Scan generated text for stray non-Latin characters before committing.**
  Accidental CJK/homoglyph insertion corrupts source strings and comments.
  `grep -nP '[\p{Han}]' <files>` over the files you just wrote. Note that
  table separators can be false positives from loose character classes —
  confirm the actual match before "fixing".
- **Mock protocols, don't fake binaries.** A text-mode SNMP stand-in cannot be
  spoken to by a real `snmpwalk`. State plainly which challenges are protocol
  mocks and keep real-tool exercises on the real container targets.
- **Keep generator helpers above the entrypoint.** `pyright` reports
  `reportUndefinedVariable` for a function called from `__main__` but defined
  lower in the file. Recovery-key buffers inferred from `[None] * n` also fail
  type inference — annotate `list[int | None]` and filter before `bytes(...)`.
- **Field-splitting a colon-delimited spec is a bug source.** A loop that
  strips `:` from the front `n` times to read field `n` mis-indexes when a field
  count changes. Use explicit parameter expansion per field.
- **Scratch paths are not `/tmp`.** The session's `TMPDIR` points at the agent's
  own scratch directory and `/tmp` may be cleared underneath you; files written
  to a throwaway path for a temporary test server can vanish mid-test and look
  like an application bug. Put test fixtures under the project.

## Reporting

State per category: challenges written, checks passing, and what remains
blocked on the user (usually `sudo`). Distinguish "verified by exploiting it"
from "compiles and starts". Give the exact command that reproduces the
verification. Don't paste flag tables into the chat — point at the guide and
the verifier.

## Support files

- `references/verification-harness.md` — reusable harness patterns per challenge
  category, with the assertions that actually catch a broken challenge.
- `references/no-sudo-first.md` — the split between what to install now and
  what to leave as a `sudo` block for later.
- `references/curriculum-and-progress.md` — grading a challenge set into
  levels by post-condition, and the progress tracker's parsing/paths rules.