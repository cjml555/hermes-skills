---
name: git-history-compaction
description: "Compact git history: purge binaries, squash, keep a backup."
version: 1.0.0
author: Jonathan (cjml555), Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [git, history, filter-repo, squash, force-push, cleanup, release]
    category: software-development
    related_skills: [fork-upstream-sync, github, requesting-code-review]
---

# Git History Compaction Skill

Rewrite a repository's history to purge committed binaries and collapse many commits into one clean root commit — without ever losing the old history irrecoverably. Not for routine rebases or a single bad commit; this is the "the repo is 200 MB of APKs and 224 commits" tool.

## When to Use

- A repo's `.git` is bloated by committed build artifacts (`*.apk`, `*.aab`, `output-metadata.json`) that CI regenerates anyway.
- A rebrand/fork should ship a clean linear history instead of inherited commit noise.
- A user asks to "compact the history", "flatten the commits", "shrink the repo", or "get the binaries out of the history".
- **Don't use for:** amending a recent commit, reordering a few commits, or splitting one commit — use `git rebase`/`git commit --amend` directly. History rewriting needs the user's explicit go-ahead, every time.

## Prerequisites

- `git` 2.30+ (for `git bundle` and `--force-with-lease`).
- `git-filter-repo` — install with `pip install --user git-filter-repo`, verify with `git-filter-repo --version`. If `python3 -m pip` says "No module named pip", use a standalone interpreter's pip (e.g. a toolchain python outside the active venv).
- A clean worktree (`git status --porcelain` empty) — the rewrite refuses to run otherwise.
- Push access to the remote. The rewrite ends in a force-push.

## How to Run

Call the helper script, then verify. The script performs the whole sequence with the safety checks baked in:

```bash
scripts/compact-history.sh --repo <repo-path> \
  --purge buildActionResult/ --purge screenshot.png \
  --message "v1.0 — historia compactada" --tag v1.0 --push
```

It is safe to run the destructive steps one at a time; the script's own order is the reference implementation. Use `--dump` to print the exact `git filter-repo` invocation without running anything.

## Procedure

1. **Back up before touching anything.** Two independent copies: a local bundle (`git bundle create <backup>.bundle --all`) and a backup branch pushed to the remote. *Done when:* the bundle file exists and is non-trivial in size, and `git ls-remote --heads origin` lists the backup branch.
2. **Audit history for secrets.** `git log --all --name-only | grep -iE '\.jks|keystore|\.pem$|\.env$|secret'`. *Done when:* the grep returns nothing, or you have decided the finding is acceptable.
3. **Purge paths from every commit** with `git filter-repo --force --invert-paths --path <p> --path <p>`. *Done when:* `git ls-files | grep <p>` is empty and the remote's `origin` is re-added (filter-repo removes it).
4. **Squash to a single root commit** via `git checkout --orphan <tmp> && git add -A && git commit`, then rename the branch. *Done when:* `git rev-list --count HEAD` prints `1`.
5. **Re-create and force-push the tags** pointing at the new commit. *Done when:* `git rev-parse v1.0^{commit}` equals `git rev-parse HEAD`.
6. **Drop the remote backup branch** once the rewrite is verified. *Done when:* `git ls-remote --heads origin` lists only the main branch. This step is what actually shrinks the repo — see Pitfalls.
7. **Garbage-collect locally.** `git reflog expire --expire=now --all && git gc --prune=now`. *Done when:* `du -sh .git` drops to roughly the size of one commit's worth of objects.
8. **Re-establish upstream tracking** — the orphan squash drops it. *Done when:* `git status -sb` shows `## main...origin/main`.

## Pitfalls

- **Never hardcode the branch name.** A fresh `git init` defaults to `master`, not `main`, so a sequence that assumes `main` aborts on `on branch 'master' but --branch is 'main'`. Default to the current branch (`git symbolic-ref --short HEAD`) and enforce a match only when `--branch` is passed explicitly.
- **`--path X` keeps only X.** To *remove* X you must add `--invert-paths`. Getting this backwards deletes your entire source tree. Read the tool's help before the first run.
- **Globs can eat files you meant to keep.** `--path-glob 'draw_tab*'` also matches `draw_tab_thumb.png`. Use exact `--path` entries for every file you want gone.
- **filter-repo removes the `origin` remote.** Re-add it before the push or the push fails with "no upstream".
- **A remote backup branch keeps the old blobs alive.** `git clone` fetches all branches, so a backup branch — remote *or local* — makes every fresh clone re-download the purged megabytes and resurrepts the deleted files under `git log --all`. Delete the remote ref **and** the local `refs/heads/<backup>` ref; the bundle is your only durable copy.
- **`grep -c` exits 1 when the count is 0.** That silently aborts `&&`-chains and `set -e` scripts, so an "assert absence" like `git log --all | grep -c junk.bin` reports `0` *and* fails the pipeline. Assert absence with `grep -q` inside an `if`, or append `|| true`, or read the count into a variable first.
- **Tags do not survive a rewrite.** Recreate them and force-push them; a tag that silently points at a dead commit breaks releases.
- **GitHub's API `size` field lies (temporarily).** It counts unreachable objects until GitHub's lazy GC runs, so it can report 146 MB while a fresh clone downloads 12 MB. Measure with a fresh clone, not the API.
- **`git reset --soft` to the root commit leaves two commits** (the old root plus the new one). Use `--orphan` for a genuine single-commit history.
- **Force-pushing a tag that has a GitHub release attached is fine** — the release follows the tag name; re-pointing the tag is enough. Confirm via the releases API afterwards.
- **The local `.git` stays huge** after the rewrite until you expire the reflog and gc. Users read that as "the cleanup failed".

## Verification

Ground truth is a fresh clone, not the working copy:

```bash
git clone --quiet <remote> /tmp/verify-clone && du -sh /tmp/verify-clone/.git && \
  git -C /tmp/verify-clone rev-list --count HEAD && git -C /tmp/verify-clone tag -l
```

All three must hold: clone `.git` far below the pre-rewrite size, commit count is `1` (or the intended small number), and the expected tags are present. Then confirm the tree survived: compare `git ls-files | wc -l` against the pre-rewrite count, and spot-check that the working files (docs, assets, source) are intact.

Report the before/after numbers to the user explicitly — clone size, commit count, and where the recoverable backup lives.
