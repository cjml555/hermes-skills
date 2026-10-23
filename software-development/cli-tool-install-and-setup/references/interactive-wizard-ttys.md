# Driving interactive setup wizards from an agent

Some CLIs refuse to run without a real TTY. Two distinct failure modes, both of which
end with a hung prompt that never advances.

## Detect the TTY requirement

A wizard run non-interactively usually emits a structured error naming the cause, e.g.
`SETUP_REQUIRES_TTY` / "is interactive. Run it in a terminal without --json". That error
is the signal to stop retrying and switch approaches.

## What does not work

- `terminal(background=true, pty=true)` gives a PTY, but answering it through
  `process_manage` `write`/`submit` fails when the answer is purely numeric: the
  argument is coerced from `"4"` to int `4` and rejected by schema validation before the
  call is ever made. This is a wrapper-level coercion, so retrying with different
  serialization has no effect.
- Writing to `/proc/<pid>/fd/0` from another shell does not drive the PTY. The bytes may
  show up in the captured output while the prompt still waits, which looks like partial
  progress and wastes turns.
- Repeatedly re-issuing the same call after a coercion error is a loop, not a retry.

## What to do instead

1. Read the config template the tool generated on first run (commonly under
   `~/.toolname/profiles/<profile>/config.toml`). It documents every key and default in
   comments.
2. Write the values directly into that file or the documented env vars.
3. Run the non-wizard entrypoint (`<tool> start` with no `--setup`) and confirm it gets
   past config validation to the next real blocker — usually a missing credential.
4. If the wizard truly is the only path, hand the exact command to the user to run in
   their own terminal; they get the interactive experience and you resume from the
   resulting config file.

## Why this matters

A half-answered wizard leaves the tool in a state neither the user nor the next agent
expects, and the pull/compose work the wizard did beforehand (image download, digest
pinning, config generation) is the expensive part worth preserving — kill the process,
not the cached artifacts.