# Grading a challenge set into levels + tracking progress

A flat list of challenges is a task list. A graded set is a curriculum. When
the user asks for "different experience levels", they want a progression where
each level *teaches* the prerequisite for the next — not the same challenges
sorted by point value.

## Design the ladder from capabilities, not categories

Group by "what can the learner do afterwards", then place each existing
challenge into the level whose prerequisite it needs. Challenges that span
categories are the *bridge* between levels — put them at the boundary.

A workable shape for a multi-category set:

| Level | Post-condition ("after this you can…") | Challenge kinds |
|---|---|---|
| N1 beginner | read a header, run a tool, decode an encoding | `strings`, `file`, base64, log reading, default creds, EXIF |
| N2 beginner+ | pick a tool by situation, tamper with parameters | classic web bugs, service enumeration, known-plaintext, embedded files |
| N3 intermediate | chain two techniques, read a binary's data sections | first overflow, format-string leaks, side channels, stego |
| N4 intermediate+ | defeat a mitigation you can name | ROP, canary brute-force, heap corruption, inverse-modular decoding |
| N5 advanced | build an exploit without scaffolding | dl-resolve, anti-debug, multi-layer obfuscation |

Give each level an estimated time band. The band is the honest signal of
difficulty; points are not — re-weight points so the harder levels carry more,
and say so if the total shifts from the per-category sums.

Record, per level: the post-condition sentence, the challenge list with ids,
points, and category. Keep the level roster in a machine-readable structure —
the tracker and the guide are both generated from it, so they cannot drift.

## Tracker design

Ship one small script plus a JSON state file next to the challenges:

```
progress            # bars per level + total
level N             # the roster for one level, with solved marks
next                # the lowest unsolved challenge, with category + where the hint lives
check               # re-run verifiers, mark solved, reprint progress
```

Rules that matter:

- **A tracker cannot fake progress it has no evidence for.** If a category's
  challenges need a hand-written exploit, `check` must leave them unmarked
  rather than assume. Say so in the guide and let the learner mark them.
- **Where the verifier output is parsed, anchor on a stable prefix** per
  category (`^OK\s+r(\d)`, `^(C0[1-6])\b.*FLAG\{`). Reading `line.split()[0]`
  breaks the moment a label contains a space.
- **Log which verifier failed instead of swallowing it.** A silent `except:
  pass` per category produces a tracker that reports 0 solved for a lab that
  works fine — indistinguishable from a genuinely unsolved learner.
- **Resolve script paths from a known root**, counting up from the script's own
  location. `os.path.join(ROOT, "..", "..", "scripts")` is wrong the moment a
  directory is inserted; `dirname` at each level is not.
- Keep the state file in the repo's ignore list from the start; it is per-user,
  not source.

## Wires the guide needs

The no-spoiler guide should gain, beyond the per-category hints:

- the ASCII ladder diagram (levels, points, time bands),
- per level: the table of challenges and the post-condition sentence,
- the tracker commands,
- an explicit warning that `check` resolves challenges itself, so it is a reset
  tool, not a way to earn marks.

Reconcile the level points table against the per-category tables before
shipping. They are computed separately and will disagree the first time; make
the generator the single source so there is nothing to reconcile by hand.
