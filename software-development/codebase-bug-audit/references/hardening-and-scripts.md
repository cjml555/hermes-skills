# Hardening patterns and script fixes

Fix recipes for defect classes that recur across audits. Each entry: what the bug
is, the fix, and how to prove it.

## Shell-escaping a user-controlled path

A path from a text field or file picker interpolated raw into a script passed to
`sh -c` is injectable. One `"` closes the quote and the rest runs as commands.

Prefer **single quotes**: inside them the shell expands nothing — no `$`, no
backticks, no `\`. Only the single quote itself needs handling, by closing,
escaping, and reopening (`'\''`). Double quotes fix the quoting but still allow
`$(...)`, so they are the weaker choice; use them only where expansion is wanted.

Escape once per generator function into a local, then interpolate only the
escaped name, rather than escaping at thirty call sites.

Proof: execute the real generated script, unescaped first, then escaped, and
look for the payload's side effect (see `finding-verification.md` on why the
control must fire).

## Destructive multi-step shell scripts

`set +e` plus `cp` and `rm` as independent commands means a failed copy still
deletes the source, with `2>/dev/null` hiding the error. Chain with `if cp ...;
then rm ...; else echo FAILED; fi`. Also `cp -a "$dir"/.` instead of
`"$dir"/*` — the glob misses dotfiles and copies a literal `*` when it fails to
expand.

## Gating permissions on machine-written manifests

When a plugin/extension manifest is produced by a model rather than typed by the
user, a call that grants whatever the manifest declares with no prompt is a
finding. Before adding your own "is this dangerous" list, read the project's own
risk map and reuse it — duplicating the classification is how a permission that
the project already rates LOW gets promoted to a scary-looking consent dialog,
and how the two lists drift apart:

```kotlin
val asksHighRisk = permissions.any { permissionRiskMap[it] == PermissionRiskLevel.HIGH }
```

Keep the low-risk path uninterrupted. The friction the original author removed
was for permission levels that do not need a prompt; adding consent to those
trains the user to click through the dialog that matters.

Two things to check when you take this branch: the artifact is installed but NOT
enabled and NOT granted pending confirmation, and the temp file the install
wrote is still cleaned on the early-return path (a `return` placed after
`installPlugin` commonly orphans it).

A discarded `Result` followed by a literal `return true` shows the user "ok"
for a failed or security-denied command. Propagate `.isSuccess`.

## Incremental reads against a capped buffer

When the underlying transcript is truncated at a row limit and the read offset
is absolute, the offset ends up past the end and the function returns empty
forever. On `readOffset >= full.length`, assume truncation and re-anchor on the
current text.

## Blocklist filters: tokenize, and test the evasions

Substring blacklists are graded. Collapse whitespace runs (tab and multiple
spaces), split on `; | & $` backtick so chained commands tokenize, and compare
per-token command and option rather than the whole string. Evaluate
destructive-target patterns (`of=/dev/sd…`, redirect to a block device) before
the per-command branch, or a generic `dd` returning MEDIUM early hides the
destructive case. Guard the "has this permission" logic so root does not disable
the filter entirely — root means the user authorized a high level, not that
checking stopped mattering.

Always run both directions: the evasions the old filter missed must now be
caught, and ordinary commands (`ls`, `echo`, `rm file`) must not be newly
rejected. A stricter filter that starts failing everyday commands is not a fix.

## Missing permission checks are dead code

A validator with zero call sites provides no safety and actively misleads the
next reader. Find the entry point (JS bridge, intent, exported component), follow
the call path to the sink, and insert the check on that path.

## Reassembling a split string: keep the separator

`rpartition(sep)` returns `(head, sep, tail)` — the separator is the MIDDLE
element. Writing `head + tail` drops it and leaves markup unclosed. Reinsert it
explicitly.

## Scaffolding tools must not truncate real files

Any generator with an `--out` flag that opens the user's real file for writing
must refuse a non-empty target unless an explicit merge flag is passed, and the
merge path inserts before the closing tag rather than rewriting. Test the
destructive case on a copy, then test the merge path produces valid output with
zero keys lost.

## Two scanners over one tree can legitimately disagree

A resource key defined in both `strings.xml` and a sibling `avnc_strings.xml`
looks missing to a tool that reads only the first file and present to one that
merges every file in the locale directory. When an audit reports hundreds of
"missing" keys, compare the two tools' parse sets before treating any as a bug —
and when the reporting tool is the odd one out, regenerate from it and expect
`Duplicate resources` at merge time.

## Credentials: check the whole pipeline, not just the build file

Signing keys live in two places, and the workflow copy is worse: a private key
embedded as base64 in a committed CI workflow is the key in plaintext, and any
signed artifact it produces passes the shared-UID signature check. Move both to
environment/secret lookup with a per-value fallback, fail the workflow with a
clear message when the secret is absent, and state plainly that this does not
clean the git history — rotation is a separate human decision.

## Making a long build script testable without running the build

A script whose only test is a 20-minute compile cannot be fixed safely: the
only way to know a change works is to spend the build, so every edit is
unverified until the end. Give it a `--dry-run` that validates everything
*except* the expensive step, then exercise that mode with throwaway inputs
before touching the real build.

The dry-run must validate the **inputs the script will actually use**, not
restate the flag: SDK path, the pinned toolchain version, the compiler,
the generator, and the completeness of each package (a half-installed
toolchain shows up as a missing `source.properties`, not as a clean error).

```bash
# the version the project pins - the script must read this, not "the newest installed"
REQUIRED=$(sed -n "s/.*ndkVersion[[:space:]]*'\([^']*\)'.*/\1/p" app/build.gradle)
[ -d "$SDK/ndk/$REQUIRED" ] || fail "instala el NDK $REQUIRED: sdkmanager \"ndk;$REQUIRED\""
[ -f "$SDK/ndk/$REQUIRED/source.properties" ] || fail "instalación incompleta"
```

Exercise the branches with fake trees, each one cheap to build:

- the happy path (real SDK) — must select the pinned version;
- a forced wrong version — must warn that it differs from the pin;
- an SDK missing the pinned package — must fail with the install command;
- a package present but incomplete — must fail as an incomplete install, not
  as a downstream CMake error.

A warning is not a guard: a script that merely notes the mismatch and
proceeds has not prevented the mistake it just detected.

**A helper script that picks a toolchain version must read the project's
own pin.** "Newest installed" silently diverges from what the build system
uses, and the resulting mismatch surfaces as a build error that never
mentions the toolchain. Read the pin, and when the script is a *parallel*
path to the real build, say so — a helper that stages artifacts somewhere
the real build does not is a second way to build, and a disagreement between
them does not invalidate the artifact that already exists.

## Testing a script that drives a device or daemon

Write a fake on `PATH` answering each subcommand, then exercise the whole flow
including the destructive branch and its confirmation prompt, with the script
invoked from a directory other than the project root. Prove the tool accepts
every documented variable, and prove the destructive branch is gated.

Two traps: a fake created as a symlink to a script does not `exec` — write a real
file; and a stray tab in the fake's `echo` breaks an exact-match `grep` in the
script, producing a fake bug. A third: `case "$*" in` does not match a prefix the
script actually sends (`adb shell pm list packages` arrives as `shell pm list …`),
so the fake silently answers the wrong branch. When a simulated run reports a
finding the real tool contradicts, audit the fake before changing the script.

Prove the fake-driven run against a simulated state where the bug WOULD have
fired — a previously-installed package, an absent SDK — so the test covers the
fixed branch and not just the happy path.

**Getting the fake's state right takes more passes than it should, and each
mismatch looks like a script bug.** Three in a row here: an `echo` left a tab
that broke an exact-match `grep`; `case "$*"` matched a pattern for arguments
the script never sends; and a command that printed a package list was matched
by a branch written for a bare package name. Before concluding the script is
wrong, print what the fake received (`echo "DEBUG $*"` inside the fake) and
compare against what the script actually invokes. A fake that disagrees with the
script on one call site will disagree on the branch under test.

**A green fake run is not evidence the script is correct.** A stub emits a couple
of lines; real output is thousands, and bugs that depend on volume stay invisible
until hardware is attached. During one audit a mock-driven run of the whole
deploy flow came back clean, and the first real run against a device reported
"nothing to uninstall" for an app that was installed. Treat a fake as proof that
branches are reachable, never that behaviour is right, and re-run the destructive
path against hardware before trusting it. Corollary: when a real run contradicts
the mock, suspect the mock's fidelity before editing the script.

## Do not gate a destructive step on "is it installed?" alone

When a script installs over an existing app, the presence check is not the
condition that matters — the *signature* is. A check that uninstalls whenever the
package is present destroys the app's data on every run, even when the installed
build and the new build are signed with the same key and would have upgraded
in place.

Decide by comparing real fingerprints, not by an internal hash: `dumpsys` exposes
a short opaque value that cannot be compared against `apksigner`'s SHA-256, so
pull the installed artifact to a temp dir, hash it there, clean up, and compare.
Install over the top when the fingerprints match; only when they differ (or cannot
be read) is the uninstall actually required.

Verify it with the two timestamps: after an in-place upgrade `firstInstallTime`
stays put and only `lastUpdateTime` moves; after a reinstall both are fresh. A
reinstall loop is obvious in `firstInstallTime` resetting on every run.

Write the comparison as a difference, not an equality test, and read it twice
before shipping it: an in-place upgrade makes the two values DIFFER, so a script
asserting "equal means preserved" reports the opposite of the truth. When such a
check prints a confident verdict, confirm it measures the intended thing against
a state whose answer you already know.

While in that warning path, check what it tells the user. A prompt saying the
app data directory "is preserved" is false for an uninstall — that directory is
what is deleted, so say what is lost and link the backup docs.

**Gate the gate** applies to destructiveness too: a script that only confirms
before its irreversible step can still be run non-interactively by design, but
the confirmation must list exactly what will be removed, and the dry-run must
predict the real outcome rather than restating the flag.

Parameterize the paths while you are there: derive the project root from the
script's own location (`$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`), read the
SDK from the project's own config before the environment, detect tool
versions rather than pinning one, and route every invocation of the external
tool through one array so a device-selection variable is not honoured by some
call sites and ignored by others.

## `grep -q` under `pipefail` reports matches as failures

`grep -q` exits at the first match, the upstream writer takes SIGPIPE (141), and
`set -o pipefail` propagates 141 as the pipeline status — so

```bash
if adb shell pm list packages | tr -d '\r' | grep -qx "package:$p"; then …   # false on a MATCH
```

reports a present package as absent. It is invisible in dry-run/simulated tests
and becomes a real bug when it guards a destructive step. Read the list once
into a variable and test against it (`grep -qx "…" <<<"$pkgs"`), or redirect to
`/dev/null` with `!` where only the boolean matters. Sweep the whole script for
this shape, not just the line that failed.

Diagnostic that pins it: copy the script, replace the `if` condition with the
pipeline followed by `__rc=$?` and an `echo "DEBUG rc=$__rc" >&2`. A `141` next
to a package you can see listed is SIGPIPE, not a missing package. Note that the
copy changes `BASH_SOURCE`, so a root derived from the script's own location will
point elsewhere — pass the artifact path explicitly to the copy.