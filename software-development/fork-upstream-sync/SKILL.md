---
name: fork-upstream-sync
description: "Sync a GitHub fork with upstream and verify its CI runs."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [fork, upstream, sync, merge, github-actions, ci, dependencies]
    category: software-development
    related_skills: [github, codebase-bug-audit, android-build-troubleshooting]
---

# Fork / Upstream Sync

Scope: pulling work from a fork's parent repo, keeping the fork's own automation
healthy, and verifying that a build which works on one machine can actually
build elsewhere. Not for reviewing a diff you wrote (`requesting-code-review`)
nor for hunting bugs (`codebase-bug-audit`).

## When to Use

- User asks whether a fork is in sync with its parent, to pull upstream
  changes, or to find out why a fork has fallen behind.
- A repo has one remote pointing at itself while the README credits an upstream
  — the parent is discoverable via `gh` and the remote often unconfigured.
- Before merging upstream work into a tree with uncommitted changes: prove the
  merge in a worktree first.
- User asks whether the fork's CI, releases, or builds actually work — a fork
  inherits the parent's workflows but not its secrets.
- A build succeeds locally and fails elsewhere, and the suspect is a dependency
  that resolves from this machine only.

Skip for: reviewing a diff you just wrote (`requesting-code-review`), hunting
bugs in the code itself (`codebase-bug-audit`), or release mechanics with no
fork relationship involved.

## Always-on rules

- **A fork's `origin` points at the fork, not the parent.** Before assuming a
  remote is missing, ask GitHub who the parent is — the relationship is a
  property of the repo, not of `.git/config`:
  ```bash
  gh repo view <owner>/<repo> --json isFork,parent,visibility
  ```
  A repo with exactly one remote, whose README credits an upstream, and whose
  oldest commit is an "Initial commit" rather than upstream history, is a fork
  whose `upstream` was never configured. That is the normal state, not damage.
- **Divergence counts are a `gh` API call, not a fetch.** Comparing without
  touching the working tree:
  ```bash
  gh api repos/<parent>/<repo>/compare/<fork>:main...main \
    --jq '{status,ahead_by,behind_by}'
  ```
  Use it to size the work before promising anything. Fetch only when you are
  about to merge.
- **Prove a merge without touching the working tree — use a worktree.** A dirty
  tree (in-flight edits, uncommitted subagent output) must not be the thing you
  risk to answer "will this merge?". `git worktree add <scratch> HEAD` gives an
  isolated checkout; merge there, read the result, remove it.
- **A build that only works on one machine is a finding.** After a worktree build
  fails for a reason that has nothing to do with the merge, check whether the
  dependency exists in a public registry at all. See
  `references/build-portability.md`.
- **A CI failure at 0 seconds with no log is not a failing job — it is a
  workflow GitHub cannot parse.** Do not go looking through job output; there
  isn't any. See `references/ci-parse-failures.md`.
- **Moving a value out of a workflow file can silently break the whole file.**
  Deleting the only key under a block leaves the block as `null`. Removing the
  value is not the same operation as removing the block.

## Procedure

1. **Establish the topology.** `gh repo view --json isFork,parent`. Then list
   what is actually configured:
   ```bash
   git remote -v
   git remote add upstream https://github.com/<parent>/<repo>.git   # if absent
   git fetch upstream main
   ```
   Adding a remote is non-destructive and reversible (`git remote remove`).
2. **Size the divergence before doing anything:**
   ```bash
   git rev-list --left-right --count upstream/main...main   # behind<TAB>ahead
   ```
   Read the left number as "commits of theirs I lack". Enumerate them and read
   their messages before merging — a single large commit may touch many files,
   and `behind:19` is not 19 separate decisions.
3. **Judge the merge risk from the diff, not from the count.** A large upstream
   commit that is purely additive (imports plus new functions) merges cleanly
   even when it rewrites 300 lines. Confirm by checking whether the lines it
   deletes exist verbatim in your tree:
   ```bash
   gh api repos/<parent>/<repo>/compare/<fork>:main...main --jq '.files[].patch'
   ```
   Then verify the anchors really are unchanged:
   ```bash
   rg -n '<the symbol being replaced>' <file>
   ```
4. **Test the merge in a worktree**, then compile there:
   ```bash
   git worktree add /tmp/wt HEAD
   cd /tmp/wt && git merge --no-commit --no-ff upstream/main
   # a build needs the gitignored local config the worktree will not have:
   cp <repo>/local.properties /tmp/wt/
   ./gradlew :app:compileDebugKotlin
   git worktree remove /tmp/wt
   ```
   A `BUILD FAILED` here that names a missing SDK/config file is the worktree,
   not the merge. Fix the worktree and re-run before drawing any conclusion.
5. **Merge for real only after the compile passes**, and say which direction and
   why you chose it.
6. **Audit the fork's own automation**, since a fork inherits workflows that
   assume the parent's secrets and registries. Compare against the parent and
   check the ones the fork needs actually exist:
   ```bash
   gh secret list --repo <owner>/<repo>          # empty = nothing configured
   gh run list --repo <owner>/<repo> --limit 25 --json conclusion,workflowName
   ```
7. **Report what you verified and what remains a human decision.** Merging
   upstream, rotating a signing key, and provisioning CI secrets all need
   something only the maintainer has.

**Updated Step 1.5: Strategy Selection (new).** After worktree merge completes
without conflicts, decide between `git merge` and `git merge -X theirs`:

- **Use `git merge`** when you need the traditional merge commit and prefer to
  resolve conflicts explicitly. This is safer for production branches where you
  want to keep conflict resolution visible.

- **Use `git merge -X theirs`** when you want to prioritize upstream changes and
  accept their version on conflicts. This is faster but can obscure decisions.
  Best for:
  - **Documentation updates** (workflow files, READMEs, docstrings)
  - **Bug fixes** where upstream changes are more recent or targeted
  - **Large refactor merges** where you trust the upstream maintainers' work
  - **Experimental branches** where you want to pull in new features quickly

**Example workflow selection:**
```bash
# Check if current changes are safe for -X theirs
if git diff --stat HEAD upstream/main | head -5; then
  echo "Merge touches code - use --no-ff to preserve commit history"
  git merge --no-ff upstream/main
else
  echo "Merge touches documentation - use -X theirs for speed"
  git merge -X theirs upstream/main
fi
```

**Caution**: Use `-X theirs` only when you understand the trade-off:
- ✅ Fast-forward when upstream has well-tested, stable changes
- ⚠️ Avoid for core logic, critical paths, or when you need to review decisions
- ❌ Never for security-critical changes or user-facing behavior differences

**Final merge step enhancement**: After merging, verify the final state:
```bash
# Check what upstream added that was missing
upstream_additions=$(git log --oneline HEAD..upstream/main | wc -l)
echo "Upstream added $upstream_additions commits"

# Verify no accidental overwrites of your own changes
git diff --name-only HEAD upstream/main | head -10
```

**Enhanced reporting**: Include merge strategy rationale in your final report:
```
Merge completed: [strategy used] - [reason]
Upstream additions: [count] commits
Affected areas: [key files changed]
Resolution approach: [how conflicts were handled]
```

## Pitfalls

- **`git rev-list --left-right --count A...B` prints `left<TAB>right` where left
  is B's lead.** Read it as behind-then-ahead or you will invert the report.
- **`gh api …/compare` reports commit counts, and one large upstream commit can
  contain hundreds of files.** Do not read `behind_by: 19` as nineteen items of
  work; enumerate `--jq '.commits[].commit.message'` and read the file patches.
- **An unconfigured `upstream` is not a bug to escalate.** Adding it is the
  first step of the task, not a finding to report as a defect.
- **A merge that applies cleanly can still not compile.** "Automatic merge went
  well" speaks only to text; the worktree compile is what proves the change.
- **A gitignored config file is missing from every fresh worktree.** Copy it in
  before concluding the merge broke the build.
- **`gh secret list` returning empty is the whole story for a fork's release
  automation.** Parent workflows that reference a secret only ever worked in
  the parent; the fork inherits the reference and not the value. A workflow can
  be syntactically perfect and still unrunnable.
- **Do not push upstream's commits to the parent's branch to "help".** The
  parent is someone else's repo; merging in your fork is the end of your
  involvement.
- **Binary file conflicts with `.html.zip` assets**. These are generated docs,
  not hand-written content. Use `-X theirs` for pure documentation merges
  where binary files should be replaced with upstream's generated versions.

## Reporting

State the parent repo, ahead/behind with the direction named, what the merge
touched, whether the worktree compile passed, and the fork's CI state (which
workflows fail, which secrets are missing). Separate "I verified this" from
"this needs you" — rotating a key or provisioning secrets is never yours to do.

## References

- `references/build-portability.md` — dependencies that resolve from one machine's
  cache and nowhere else; how to check and what to report.
- `references/ci-parse-failures.md` — workflow files GitHub refuses to parse:
  symptoms, the `null`-block trap, and the YAML check that finds it.
- `references/merge-strategies.md` — detailed comparison of merge approaches,
  when to use `-X theirs` vs. traditional merges, and how to document the
  rationale.

## Pitfalls

- **`git rev-list --left-right --count A...B` prints `left<TAB>right` where left
  is B's lead.** Read it as behind-then-ahead or you will invert the report.
- **`gh api …/compare` reports commit counts, and one large upstream commit can
  contain hundreds of files.** Do not read `behind_by: 19` as nineteen items of
  work; enumerate `--jq '.commits[].commit.message'` and read the file patches.
- **An unconfigured `upstream` is not a bug to escalate.** Adding it is the
  first step of the task, not a finding to report as a defect.
- **A merge that applies cleanly can still not compile.** "Automatic merge went
  well" speaks only to text; the worktree compile is what proves the change.
- **A gitignored config file is missing from every fresh worktree.** Copy it in
  before concluding the merge broke the build.
- **`gh secret list` returning empty is the whole story for a fork's release
  automation.** Parent workflows that reference a secret only ever worked in
  the parent; the fork inherits the reference and not the value. A workflow can
  be syntactically perfect and still unrunnable.
- **Do not push upstream's commits to the parent's branch to "help".** The
  parent is someone else's repo; merging in your fork is the end of your
  involvement.

## Reporting

State the parent repo, ahead/behind with the direction named, what the merge
touched, whether the worktree compile passed, and the fork's CI state (which
workflows fail, which secrets are missing). Separate "I verified this" from
"this needs you" — rotating a key or provisioning secrets is never yours to do.

## References

- `references/build-portability.md` — dependencies that resolve from one machine's
  cache and nowhere else; how to check and what to report.
- `references/ci-parse-failures.md` — workflow files GitHub refuses to parse:
  symptoms, the `null`-block trap, and the YAML check that finds it.