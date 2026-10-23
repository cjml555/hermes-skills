# Workflows GitHub refuses to parse

A run that fails **instantly with no log** is not a job that failed. GitHub
rejected the file before executing anything, so there is no step output to read
and `--log-failed` returns "log not found".

## Recognising it

```bash
gh run view <id> --repo <owner>/<repo>
# X <name> · <run id>
# This run likely failed because of a workflow file issue.
```

Two confirmations that no job ever started:

```bash
gh api repos/<owner>/<repo>/commits/<sha>/check-suites \
  --jq '.check_suites[] | select(.app.slug=="github-actions") | {conclusion,latest_check_runs_count}'
# {"conclusion":"failure","latest_check_runs_count":0}   <- never ran
```

`latest_check_runs_count: 0` on a failed suite is the tell. A job that ran and
failed has runs.

Distinguish it from a normal failure: a real failure names the step, takes
seconds to minutes, and its sibling workflows on the same push succeed for
unrelated reasons.

## Why it happens

Editing a workflow by hand often leaves a block whose only child was removed:

```yaml
env:
  # comments explaining where the value now lives
  # ...and nothing else
jobs:
  build:
    steps: …
```

YAML parses that as `env: null`, and GitHub rejects the whole document. Python
confirms it in one line:

```python
yaml.safe_load(open(path))["env"]      # -> None
'env' in yaml.safe_load(open(path))    # -> False once fixed
```

The trap is that the edit looks correct — the intent ("this value moved to
secrets") is fully expressed — and the file still parses as valid YAML. Only
GitHub's stricter schema rejects it.

## Fix

Remove the now-empty block rather than leaving a comment-only one:

```python
s = open(path, encoding="utf-8").read()
i = s.index("\nenv:\n  # ")
j = s.index("\njobs:")
open(path, "w", encoding="utf-8").write(s[:i] + "\n" + s[j:])
```

Then confirm the structural keys survived:

```python
d = yaml.safe_load(open(path, encoding="utf-8"))
list(d.keys())                          # no 'env'
list(d["jobs"].keys())                  # every job still present
list((d.get(True) or d["on"]).keys())   # triggers unchanged
```

A local `yaml.safe_load` catching a **syntax** error is necessary but not
sufficient: the file parsed fine here and still failed on GitHub. The `None`
value is the actual fault, and only inspecting the loaded structure finds it.

Note that a bare `on:` key loads as the boolean `True` under Python's YAML 1.1
resolver, so index it as `d.get(True)` — that is not itself a defect.

## The second half: valid syntax, missing secrets

Fixing the parse error is not the same as making the workflow runnable. A fork
inherits workflows that reference secrets which only ever existed in the parent
repo:

```bash
gh secret list --repo <owner>/<repo>     # empty list = nothing configured
```

Any unset `secrets.X` evaluates to an empty string, so the job starts and then
fails at the first step that uses it. Enumerate what the file expects and
compare with what the repo has:

```bash
grep -oE 'secrets\.[A-Z_]+' .github/workflows/*.yml | sort -u
```

Report the gap rather than inventing values. Provisioning secrets requires the
actual signing material and is the maintainer's call.

## Checklist

- `yaml.safe_load` succeeds **and** no top-level key loads as `None`
- job list unchanged from before the edit
- `gh run list` shows the workflow succeeding (or not running at all, if its
  only trigger is a release event)
- every `secrets.*` reference resolves in this repo