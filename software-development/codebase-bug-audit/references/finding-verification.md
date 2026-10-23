# Verifying a finding before you report it

The expensive part of an audit is not finding candidates, it is discarding the
false ones without having told the user they are real.

## Type-check the sink

A shell injection needs a `String` an attacker can shape. Trace it:

```bash
rg -n 'fun killProcessPid' -A3 <file>     # is the interpolated value an Int?
rg -n 'killProcessPid\(' <file>            # what does every caller pass?
```

`"$pid"` where `pid: Int` is not injectable. Same question for path joins
(is the segment a constant?), for SQL (is it a literal?), and for `openUrl`
(is the scheme validated before `ACTION_VIEW`?).

## Confirm containment checks have a boundary

```kotlin
// passes for .../plugins/com.foobar when base is .../plugins/com.foo
file.canonicalPath.startsWith(pluginDir.canonicalPath)
// correct
file == base || file.path.startsWith(base.path + File.separator)
```

Any `startsWith` used as a containment check must include the separator, and
must resolve `..` and symlinks first.

## Confirm the file is actually tracked

```bash
git ls-files --error-unmatch <path>   # tracked?
rg -n '<name>' .gitignore              # ignored anyway?
```

A file that exists on disk and sits in `.gitignore` is not a leak. Say nothing
about it, or say it is correctly ignored.

## Confirm a permission check is reachable

```bash
rg -n 'canAccessFileSystem' app/src/main    # 0 call sites = dead code, not protection
```

A validator with no callers provides no safety, and a reviewer reading it will
believe the surface is protected. Follow the actual call path from the entry
point (the JS bridge, the intent, the exported component) to the sink and check
each hop for a permission check.

## Confirm a component's export is deliberate

```bash
rg -n '<Component>' app/src/main/AndroidManifest.xml   # exported? any intent-filter?
rg -n '<Component>' --glob '!*/AndroidManifest.xml'   # who launches it?
```

An exported component with no filter and no external caller is the finding. One
with a `SEND`/`VIEW` filter exists to be reachable from outside — leave it, and
explain why.

## Prove the exploit before you fix it

Write the harness so the UNESCAPED input runs first and must demonstrably fire:

```
=== SIN escape ===          PW? SI-BUG-CONFIRMADO
=== CON shellSingleQuote === PW? NO-OK
```

If the control also reports safe, the harness is wrong (wrong quoting, `eval`
re-parsing the escaped string, a command that cannot execute the payload). Fix
the harness before believing either result — this produces several
false-"passing" rounds that all look clean.

Common harness mistakes that make both runs look safe: reconstructing the
value with `sed` instead of executing the real generated script, quoting only the
literal `\"` so nothing executes, or using a non-executing command like `[ -d ]`
as the probe.

## Reproduce a destructive-script bug before fixing

Copy the target to a scratch path and count lines before and after:

```bash
cp res/values-es/strings.xml /tmp/probe.xml
wc -l res/values-es/strings.xml     # 1406 before
python3 tools/i18n/scaffold_locale.py --locale es --out /tmp/probe.xml
wc -l /tmp/probe.xml                # 4 after = the bug is real
```

Never point an `--out` flag at the real file to demonstrate a bug in it. Prove
it on the copy, then fix, then re-run against the copy to show the abort or the
merge-in-place behaviour.

## Compile after every scripted edit

A repo-wide replace leaks scope: variables defined in one function get
referenced in a sibling function that does not see them. `compileDebugKotlin`
in 5-15s catches this immediately; reading the diff does not.

## The test must not inherit the bug it is testing

A fix can pass its own regression test and still be wrong, because the test
reproduces the original defect. When a new test fails for the first time, decide
which of the two is wrong before changing either.

Telltale signs the harness, not the code, is at fault:

- the control run also reports the *fixed* behaviour (both runs "pass");
- the failing case was one the old code provably mishandled;
- the two runs differ only in a step you reconstructed rather than executed.

Re-derive the expectation from the original vulnerable version's output, not from
what the current code happens to emit. Checking the case table by hand catches
the arithmetic-order mistakes a whole-suite run does not: a filter branch that
returns `MEDIUM` early can shadow a later `HIGH` rule, and the suite still goes
green if no case happens to cover that order.