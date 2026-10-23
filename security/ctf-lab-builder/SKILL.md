---
name: ctf-lab-builder
description: Use when building CTF or pentest challenge labs.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [ctf, security, labs, verification, docker]
    related_skills: [systematic-debugging, spike]
---

# Building self-contained security challenge labs

## When to Use

Use this when asked to build a CTF, a practice lab, vulnerable-by-design targets,
or a set of security challenges. Also use it when turning an existing app or
tool into training material.

Do NOT use it for real engagement work against systems you are not authorized
to test. The output of this skill is intentionally vulnerable code; the
techniques belong in a lab, never pointed at someone else's infrastructure.

Key discipline: ship a verifier and make it pass. A challenge nobody has
actually solved is not finished.

A challenge that was never solved is not a challenge — it is a file. Every
lab must ship with a verifier that resolves each flag using the same tooling a
player would use, and the verifier must pass before the work is reported.

## Verify by solving, not by inspection

Write `verify.sh` (or an equivalent) that resolves every challenge end to end
and prints `N OK / M failed`. Run it. A challenge whose solver returns empty is
a bug in the challenge, even when the source "looks right".

This catches real bugs that reading the code does not:
- an encoded table whose inverse uses division instead of the modular inverse
- flag fragments that concatenate into a typo (`antii`, `antes_t0er`)
- a check that passes because the verifier hardcoded the expected string

**Pitfall:** never let the verifier assert a literal you also wrote by hand.
Extract the value from the binary/token the way a player would. If the verifier
and the generator share a constant, a wrong flag passes as correct.

## Process and networking pitfalls

- `allow_reuse_address` must be set as a class attribute **before** the socket
  is constructed, because binding happens in `__init__`. Assigning
  `server_address` afterwards does not re-bind, and a fast restart dies with
  `EADDRINUSE` from TIME_WAIT.
- `$!` inside a `( ... & )` subshell yields the subshell's PID, not the
  daemon's. Use `setsid nohup ... &` to detach, then discover the real PID with
  `pgrep -f "python3 <script>"`. Kill by cmdline, not by the saved PID file.
- When a script's start subcommand spawns detached children, do not truncate its
  output through a shell pipeline — the pipeline blocks on the child's inherited
  stdout and the whole command appears to hang. Redirect the child's stdout to
  a log file instead, then read the file.
- Nested `.gitignore` files do **not** work. A `labs/ctf/.gitignore` is inert;
  generated state (DBs, PID files, compiled binaries) must be listed in the
  repo-root `.gitignore`, and already-committed files need
  `git rm --cached`.

## Binary analysis pitfalls

- `objdump -s` prints an offset, hex columns, **and a trailing ASCII column**.
  Flattening the whole line and feeding it to `bytes.fromhex` fails on the
  ASCII characters. Match only the hex groups with an anchored regex.
- `-O0` plus `strip` gives players a real binary without handing them symbols.
- Anti-debug via `/proc/self/status` `TracerPid` works: verify that
  `gdb --batch -ex run` actually suppresses the flag, and assert that negative
  case too.
- Fragmented string literals get constant-folded back into one plain string by
  the compiler. To keep a flag out of `strings`, store it XOR-encoded and decode
  at runtime.

## Toolchain pitfalls

- Go-distributed tools (ffuf, nuclei) are not on PyPI: `uv tool install` and
  `pip` both fail with "not found in the package registry". Fetch the release
  tarball/zip from the GitHub releases API and extract the single binary.
- GitHub release downloads need `curl -L`; without it you get an HTML error
  page and `tar` reports "not in gzip format".
- Do not pass `git+https://...` to `uv tool install` for repos with no
  `pyproject.toml`; clone and create a venv with `uv venv` +
  `uv pip install -r requirements.txt` instead.
- Check a tool's current CLI flags before scripting it. Flag names get renamed
  between major versions (nuclei v3 dropped `-target-lhost`), and a stale flag
  fails with "flag provided but not defined" rather than a useful error.
- Running the full nuclei template set against a trivial local server can hang
  for minutes on slow templates; scope with `-t <dir>` subsets when verifying.

## Generator scripts that emit C or binary formats

When a Python script writes a `.c` file, remember it is *two* layers of string
escaping. A `"""..."""` Python literal containing `\n` produces a **real newline**
in the generated C source, which gcc reports as `missing terminating " character`
far from the cause. Write `\\n` in the generator to get a `\n` escape in the C.

Compile every generated source and assert on the built artifact, not just on
exit status: a wrong byte table still compiles and ships a broken challenge.

### Binary-format assembly

- **EXIF/APP1**: PIL rewrites the JPEG `APP1` segment and silently drops tags
  it does not recognize, so `img.save(..., exif=handbuilt)` will not preserve a
  custom tag. When the challenge depends on a specific tag, hand-assemble the
  JPEG: `SOI` + `APP1` + `EOI`, where the APP1 payload is `b"Exif\x00\x00" + tiff`
  with the **complete** TIFF header (`MM\x00\x2a...`) intact — slicing the TIFF
  off with `tiff[6:]` and re-prepending it silently drops the header.
- **LSB steganography**: force the non-message LSBs to zero when building the
  cover image so the result looks like a natural gradient, and re-read the saved
  file through PIL to assert the message round-trips before declaring success.

## Verifier design: assert the bug, not the crash

A verifier for exploitation challenges must accept every behavior the flaw
legitimately produces, or it will report a working challenge as broken.

- A format-string leak with `%s` **is supposed to** `SIGSEGV` when it dereferences
  a non-readable pointer. Accept exit codes `0`, `139`, and `-11`.
- Assert the security property (`%p` leaks a pointer, the canary raises
  `SIGABRT`, the overflow reaches `RIP`) rather than one specific exit code.
- Run both the malformed input and a benign short input; "still crashes" alone
  does not prove the bug, and "completes cleanly" alone does not either.

## Static-analysis cleanliness in generated code

`pyright` flags a helper referenced from `__main__` but defined further down the
file. Define helpers above the entrypoint. Recovery-key buffers inferred as
`list[None]` also fail inference — annotate `list[int | None]` and filter before
`bytes(...)`.

## Writing non-ASCII content

Long Spanish prose written through the file tools intermittently picks up stray
ideographs (Han characters) that no reader would notice. Before committing,
grep the tree for the CJK ranges and fix anything found:

```bash
grep -rlP '[\p{Han}]' --include='*.md' --include='*.py' --include='*.sh' .
```

Note that a naive check can false-positive on separators or emoji; inspect the
matched line rather than trusting the file list.

## Scope the lab to run without elevated privileges

Prefer stdlib-only services and release binaries over containers when the user
may be away from the machine. A lab that needs `sudo` cannot be exercised at
all until they return, so it cannot be verified. Where a mock protocol is
involved, say so plainly in the guide and provide a stdlib client that speaks
it, since the real tool will not.