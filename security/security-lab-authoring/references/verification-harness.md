# Verification harness patterns

Per-category assertions that catch a *broken* challenge, not just one that
compiles. Each pattern below caught a real defect during authoring.

## Binary exploitation

```python
import subprocess

def run(args, stdin=b"", timeout=10):
    try:
        r = subprocess.run(args, input=stdin, capture_output=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, b"", b"TIMEOUT"
```

Return codes are negative signals: `-11` SIGSEGV, `-6` SIGABRT.

| Property | Assert | Pitfall it catches |
|---|---|---|
| Overflow is exploitable | `rc in (-11, 139, 134)` on long input | Buffer bug that never triggers |
| Short input still works | `rc == 0` on a short payload | Binary dies on valid input too |
| Canary is active | `b"stack smashing" in err` **or** `rc == -6` | Canary compiled out |
| Canary doesn't false-positive | `rc == 0` on short input | Canary misplaced, always aborts |
| Anti-debug works | normal run yields secret **AND** `gdb -batch -ex run` does not | Check is a no-op |
| Format string leaks | `re.search(rb"0x[0-9a-f]{6,}", out)` | Escape stripped before printf |
| Format string no canary abort | `b"stack smashing" not in err` | Mixed build flags |

`gdb` probe:
```python
rc, out, err = run(["gdb", "-batch", "-q", binary, "-ex", "run", "-ex", "quit"])
secret_leaked = b"FLAG{" in out
```

## Service / protocol

Assert the *behaviour branch*, not the process. For a stateful mock:

```python
# menu-driven: exercise alloc -> free -> view, assert the documented post-state
script = b"1\n0\n64\n2\n0\n3\n0\n5\n"
rc, out, _ = run([binary], stdin=script)
assert b"vacio" in out       # free'd slot reads as empty, per spec
assert rc == 0               # menu exits cleanly
```

For anything multi-step, assert the flag *count* matches the points table —
multi-flag challenges are where silent partial failures hide.

## Crypto

Always assert the recovered value equals the flag, never "the solver ran":

```python
assert solve_k1(token) == FLAGS["K1"]
```

Round-trip generated artifacts before shipping:
```python
enc = transform(flag); assert inverse(enc) == flag   # catches bad modular math
```

## Web

Resolve every challenge over HTTP with the real verbs. Include the
non-obvious payloads — comment-triggered flags, bonus flags, and challenge
chains — since those are what silently regress.

```bash
printf "  %s : " "$name"; curl -s -m 4 "$url" | grep -oE 'FLAG\{[^}]+\}' | head -1 || echo "no"
```

## Forensics

Assert the *structural* property, not just that `strings` finds the flag — a
library that rewrites the file can leave the flag visible while destroying the
header the challenge is about.

| Property | Assert | Pitfall it catches |
|---|---|---|
| Container magic intact | `raw[:2] == b"\xff\xd8"` for JPEG, `raw[:4] == b"SFS1"` | Broken hand-assembly |
| Custom header survived | `b"MM\x00\x2a\x00\x00\x00\x08" in raw` | TIFF header dropped by slicing |
| Library did not rewrite | `b"Exif\x00\x00" in raw` | Library dropped custom tags |
| Extension is a lie | `raw[:4] != b"%PDF"` **and** `raw[:2] == b"PK"` | Reto silently not a reto |
| `file` agrees | `"Zip" in file_output` | Magic/extension mismatch |
| Deleted data persists | flag present in a block whose inode size is `0` | Slack concept not reproduced |
| LSB round-trips | extract LSBs from the **re-read saved file** | Asserted on in-memory buffer |

Decode the embedded archive from the offset where its signature appears, not
from byte 0 — the cover file precedes it:
```python
idx = raw.find(b"PK\x03\x04")
z = zipfile.ZipFile(io.BytesIO(raw[idx:]))
```

## Assembly check

Count the flags actually reachable and reconcile against the guide:
```bash
{ curl -s "$B/robots.txt"; curl -s "$B/.git/config"; ... } \
  | grep -oE 'FLAG\{[^}]+\}' | sort -u | wc -l
```

A count higher than expected means two challenges share a flag (aliasing bug —
give each its own). A lower count means one is unreachable.