# Binary (reversing) and crypto challenges

Two challenge categories that need no network and no Docker — just `gcc` and
Python stdlib. Same acceptance rule as the web set: **solve every flag yourself**
before shipping.

## Reversing: generating the binaries

Write a `build.py` that emits the C source, compiles it, and strips it. Keep
the flags in one dict at the top so the docs, the binary and the verifier cannot
drift apart.

```python
subprocess.run(["gcc", "-O0", "-fno-inline", "-o", out, path, "-w"])
subprocess.run(["strip", out])          # no symbols -> must read disassembly
```

`-O0` is deliberate: optimized code folds the patterns the challenge is built
around. `-fno-inline` keeps the vulnerable comparison visible as its own block.

Difficulty ladder that works:

| Level | Technique | Verified with |
|---|---|---|
| 1 | flag in plaintext | `strings` |
| 2 | XOR with a 1-byte key | brute force 0-255 |
| 3 | byte array + manual compare (no `strcmp`) | `objdump -s -j .rodata` |
| 4 | runtime decode loop | execute and read stdout |
| 5 | anti-debug | run under gdb, assert flag is *gone* |
| 6 | XOR + master key + anti-debug | known-plaintext |

## XOR: use known-plaintext, never brute force

A repeating short key is not brute-forceable (256^4 is 4 billion) and never
needs to be. If the flag format is known, `FLAG{` gives you 5 key bytes for
free: `key[i % klen] = ct[i] ^ plain[i]`. Try candidate key lengths in order
(4, 3, 5, 6, 2, 1) and accept the first whose bytes are self-consistent.

```python
key: list[int | None] = [None] * klen
for i, (c, p) in enumerate(zip(ct[:12], known[:12])):
    kb = c ^ p
    if key[i % klen] is None:
        key[i % klen] = kb
    elif key[i % klen] != kb:
        ok = False; break
```

Annotate `list[int | None]` explicitly — a `[None] * klen` infers as
`list[None]` and every assignment becomes a type error.

## The inverse of a modular map is a multiply, not a divide

Encoding `v = (c*3 + 7) mod 256` and "decoding" with `(v - 7 + 256) % 256 / 3`
silently truncates. 3 is invertible mod 256: `3 * 171 = 513 = 2*256 + 1`, so
171 is the inverse and decoding is `(v - 7 + 256) % 256 * 171 % 256`.

Rule: when a challenge decodes by dividing and the output is garbage, compute
the modular inverse instead. `pow(3, -1, 256) == 171`.

## Adversarial features must be proven, not assumed

Anti-debug is only a real challenge if the mitigation actually works. Verify
both directions:

```bash
./bin/r5-anti                       # -> flag present
printf 'run\nquit\n' | gdb -batch -q ./bin/r5-anti | grep FLAG   # -> must be EMPTY
```

Make the second assertion a real pass/fail line in `verify.sh`. If gdb still
sees the flag, the mitigation is decorative and the level teaches nothing.

Read `TracerPid:` from `/proc/self/status` for the check — it is the standard
mechanism and needs no ptrace of your own.

## Two C-generation traps

**gcc merges adjacent string literals back into one.** A challenge whose whole
point is "the flag is not contiguous in `strings`" fails the moment you build
it from `{"FLA", "G{a", "n", ...}` — the compiler folds them into the plaintext.
Store the bytes XOR-ed with a constant and decode at runtime instead; the
literal array then cannot be folded.

**A generator line and the template it feeds must not both close the block.**
Emitting `... + "\n};\n"` and then a template starting with `};` produces a
duplicate brace and a confusing `expected identifier before '}'`. Own the
delimiter in exactly one place.

Also: `atoi` needs `<stdlib.h>`; with `-w` the implicit-declaration warning is
suppressed and you get an error at the `bytes(...)` call instead.

## Parsing objdump output

`objdump -s -j .rodata` prints offset, four hex groups, then an ASCII column.
Feeding the whole line to `bytes.fromhex` fails because the ASCII column is not
hex. Anchor the regex on the offset and capture only the hex groups:

```python
m = re.match(r"^\s+[0-9a-f]{4,8}\s+((?:[0-9a-f]{2,8}\s+){1,4})", line)
hexs += m.group(1).replace(" ", "")
```

`cut -c11-60` looks right and is not — the offset field width varies with
section size, so the column offsets shift. Use the regex.

Keep the extractor as its own script and call it by absolute path from the
verifier; `$(dirname "$0")` resolves to `.` under some invocations and the
helper silently returns nothing.

## Crypto challenges: make each weakness the lesson

| Level | Artifact given | Attack |
|---|---|---|
| 1 | base64 token | decode — encoding, not encryption |
| 2 | double transform | invert substitution and ordering |
| 3 | XOR ciphertext + length | known-plaintext key recovery |
| 4 | a hash | preimage from a small dictionary |
| 5 | message + signature | timing attack on early-exit compare |
| 6 | pipeline | compose the above in the right order |

For the timing level, show the real measurement — a vulnerable byte-by-byte
compare versus `hmac.compare_digest` — so the user sees nanoseconds per
correct byte rather than being told to trust the docs.

Ship a solver per challenge and assert it returns the flag. A solver that
"should" work is worth nothing; run `crypto.py` and read the pass/fail table.

## Make every category reachable from one orchestrator

Add `rev` and `crypto` subcommands that build-if-missing, then run the
verifier. Keep `solve` for the networked set only — the offline categories have
their own harnesses, and mixing them makes `solve` slow and its output noisy.