# Difficulty levels and progress tracking for a heterogeneous challenge set

A flat list of challenges is a to-do list. Grouping them into levels that
*build on each other* turns it into a curriculum. This applies once a lab has
more than one category.

## Design the progression across categories, not within one

A level should mix categories so the player exercises different muscles at the
same skill tier, and each tier should only require techniques introduced at or
below it. Concretely, three rules:

1. **No technique appears before it is taught.** If level 4 asks for a stack
   canary bruteforce, a stack overflow must exist at level 3 or earlier.
2. **Mix categories inside a level.** Putting all six web challenges in N1 and
   all six crypto in N2 makes the levels feel like subject blocks. Interleaving
   forces tool-switching, which is the actual job skill.
3. **Give each level an "after this you can…" line.** Naming the capability
   ("build a ROP chain", "spot a leaked metadata block") is what makes the
   ladder legible as a curriculum rather than a difficulty gradient.

## Points must come from the tracker, not from the prose

Write the tracker first, then generate the points table from it. Hand-estimating
points in the guide and then hand-counting in code produces two disagreeing
sources of truth — the guide claimed a total the tracker never reported.

```python
LEVELS = {
    1: [("C01", "web", "robots.txt", 10), ...],
    ...
}
TOTAL = sum(p for lvl in LEVELS.values() for _, _, _, p in lvl)
```

If a hand-written markdown table and the tracker's totals must both exist, derive
the markdown from the same dict and re-check after any point edit.

## Classify every challenge: auto-verifiable or manual-only

This is the decision that shapes the tracker's design. A challenge whose verifier
*knows the answer* can be auto-marked; one that requires a hand-written payload
cannot.

| Class | Example | Auto-markable? |
|---|---|---|
| Retrieval / decode | web endpoints, `strings`, base64, LSB, EXIF | yes — verifier resolves it |
| Behaviour assertion | canary aborts, format string leaks | yes — verifier proves the property |
| Exploit authoring | pwn ROP chains, heap UAF | **no** — requires pwntools and a written exploit |

Marking a manual-only challenge as "solved" because a script replayed the answer
teaches the player that verification equals solving. Leave those out of the
auto-track, and make `next` skip them so the suggestion is always actionable.

State this honestly in the guide: name which challenges the tracker cannot mark
and how the player records those instead.

## Tracker design

Shell out to each category's existing verifier and parse its stdout with a regex
per line, rather than duplicating solve logic in the tracker:

```python
r = subprocess.run([verifier, ...], cwd=cat_dir, capture_output=True, text=True)
for line in r.stdout.splitlines():
    m = re.match(r"^OK\s+(K[1-6])\b", line.strip())
    if m:
        progress[m.group(1)] = True
```

Anchor every regex to `^` and require the distinguishing token, so a failure line
or a progress-bar character can never be mistaken for a pass.

Persist to a small JSON file next to the lab (gitignored), and ship a documented
way to delete it — a tracker whose reset path is undocumented becomes a file
nobody can trust.

## Derive the project root by naming each level, not by counting `..`

```python
HERE    = os.path.dirname(os.path.abspath(__file__))   # .../labs/ctf
ROOT    = os.path.dirname(HERE)                       # .../labs
PENTEST = os.path.dirname(ROOT)                        # project root
```

Joining a fixed number of `..` onto a guessed depth silently resolves to a
directory that does not exist when the layout changes, and the failure surfaces
as an empty progress report rather than an error. Name each level explicitly.

A tracker that reports `0/35` after the verifiers all pass is almost always a
path bug — check the resolved script path before suspecting the parse.

## Verifier design for exploitation challenges

Assert the announced *property*, and accept every exit code the flaw
legitimately produces:

- long input reaches the crash signal (`-11`/`139`) **and** short input exits
  `0` — one without the other proves nothing;
- stack canary raises `SIGABRT`/`-6` on overflow;
- format string leaks `0x[0-9a-f]{6,}`; `%s` on an arbitrary pointer is *expected*
  to segfault, so accept `0`, `139` and `-11` there.

Stripped binaries break `ELF.symbols()`-based solvers. Either ship unstripped
for practice or state in the guide that addresses come from `objdump` — decide
deliberately and tell the player which one they got.