# CTF challenge authoring

Build flag-bearing challenges that run with **no Docker and no sudo** — pure
stdlib Python on `127.0.0.1`. This is the only form that works when the user is
away from the machine, and it doubles as a self-test for the toolchain.

## The rule that makes it real: solve what you ship

A challenge set is not verified until every flag has been retrieved by an actual
request. Ship a `solve` subcommand that resolves all of them and run it. It is
both the acceptance test and the answer key.

```bash
./ctf.sh solve        # prints one line per challenge with its flag
```

If a challenge cannot be solved from outside the code, it is not a challenge.

## Flag design rules

- **One distinct flag per challenge.** Two challenges yielding the same string
  means one is a shortcut for the other. Give the second its own.
- **A hint must not BE the answer.** Putting the flag in `robots.txt` because
  "the dev left a note" is legitimate information-disclosure practice; putting it
  in the hint text of the challenge that teaches SQLi is a spoiler.
- **Reachability beats obscurity.** Prefill a DB, generate the secret file at
  boot, and put the flag where the vulnerable code path actually leads. Do not
  depend on a multi-step chain the challenge never describes.
- **Bonus flags are fine, but count them separately.** One challenge can yield two
  flags; say so in the docs so the score matches the count.

## Verifying each vulnerability class

Re-derive the payload with the tool the user will reach for, not by reading code.

| Class | Verify it moves |
|---|---|
| robots.txt leak | `curl -s $B/robots.txt \| grep FLAG` |
| exposed repo | `curl -s $B/.git/config` |
| SQLi auth bypass | `curl -X POST $B/login --data-urlencode "username=admin' OR '1'='1' --" --data-urlencode "password=x"` |
| IDOR | iterate the id: `for i in $(seq 1 20); do curl -s "$B/profile?id=$i"; done` |
| LFI | `curl -s "$B/download?file=secret.conf"` |
| SSTI | `curl -sG "$B/search" --data-urlencode 'q={{7*7}}'` — confirm the arithmetic result, then confirm the flag is in the rendered page |

Two of these fail in ways that look identical in a first pass: a flag present in
the source but not the response, and a payload needing URL-encoding. Check the
raw response body rather than trusting the grep pipeline.

For network challenges, ship a **stdlib client** too — the host may not have
`nc`, `hydra` or `snmpwalk` yet. The client is both the user's offline path and
your verification harness.

```python
with socket.create_connection((HOST, PORT), timeout=5) as s:
    s.settimeout(2)
    ...
```

## Service mocks must state their own limits

A protocol mock that speaks a simplified dialect must say so in the docs, or the
user burns time on the real tool. Example: SNMP over plain TCP text instead of
UDP BER — `snmpwalk` genuinely will not parse it. Tell them to use the bundled
client, and note what to use once real tooling is installed.

## Orchestrator patterns

See the SKILL.md section "Managing local lab processes" for PID handling, `setsid`
detachment, and `allow_reuse_address`. Two extra points specific to challenges:

- **Generate state at boot, delete it on reset.** The app creates its sqlite DB,
  its secret file and its fake `.git/config` on startup; `reset` removes them and
  restarts. This keeps the repo free of per-run artifacts.
- **Never read the orchestrator through a pipe.** `ctf.sh reset | tail` hangs
  because the detached children hold the write end. Run without a pipe.

## SecLists without hardcoded paths

Path names move between releases; guessing them yields 404s. Read the repo tree
and filter locally:

```bash
curl -sSL -o /tmp/tree.json \
  "https://api.github.com/repos/danielmiessler/SecLists/git/trees/master?recursive=1"
```

**Parse that file with a script, not by printing it** — the tree is thousands of
lines and terminal output truncates it mid-JSON. Filter for `.txt`/`.lst` blobs
and regex the categories you need (web content, DNS, SNMP, LDAP/AD, credentials).

Useful categories for network practice, with the naming conventions that changed:
`Discovery/Web-Content/DirBuster-2007_directory-list-2.3-medium.txt`,
`Discovery/Infrastructure/nmap-ports-top1000.txt`,
`Discovery/SNMP/common-snmp-community-strings.txt`,
`Fuzzing/LDAP.Fuzzing.txt`,
`Passwords/Common-Credentials/xato-net-10-million-passwords-100000.txt`,
`Usernames/Names/malenames-usa-top1000.txt`.

Concatenate several username lists and add the service defaults to build a
composable `users.txt`; name it and note in the docs which challenges reference
it, so the paths in the curriculum never drift from the files on disk.

## Docs: guide without spoilers

Two audiences at once. Split it:
- `labs/ctf/README.md` — indirect hints only, the challenge list, the flag-to-CWE
  map, a points table, and how to verify.
- Never list the literal payload in the hint table. Give the reasoning ("the
  endpoint downloads files — what if you ask for a different one?").

Put the curriculum and the challenges in different files: one is prose for
learning, the other is software to solve.