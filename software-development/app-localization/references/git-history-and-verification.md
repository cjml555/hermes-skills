# Git history and verification chores during a localization push

Operational procedures that recur around shipping a locale, kept out of the
translation path because they are about the repo rather than the text.

## Rewriting commit authorship after the fact

`git config user.name` does NOT fix already-pushed commits — it only sets the
identity for new ones, and `git rebase -i` with a scripted editor re-commits the
same tree with the author still unchanged. Set both environment variables:

```bash
git cat-file commit HEAD | head -3   # author vs committer lines differ

FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch -f --env-filter '
if [ "$GIT_COMMIT" != "<base-sha>" ]; then
  export GIT_AUTHOR_NAME="New Name";    export GIT_AUTHOR_EMAIL="new@example.com"
  export GIT_COMMITTER_NAME="New Name"; export GIT_COMMITTER_EMAIL="new@example.com"
fi' -- <base-sha>..HEAD

git diff <old-sha> HEAD --stat        # empty = content unchanged, only metadata moved
git push --force-with-lease=<branch>:<old-sha> origin <branch>
```

- **Scope to `base..HEAD`, never all history.** Skipping `base-sha` keeps the
  maintainer's existing commits attributed to them.
- **Verify the tree is identical** with `git diff <old> HEAD` before pushing.
- **Always `--force-with-lease=<branch>:<expected-sha>`**, never bare
  `--force` — the explicit SHA aborts if anyone else pushed meanwhile.
- **Check open PRs and other clones first** (`gh pr list`, `git branch -a`);
  rewriting published history breaks open PRs.
- **Confirm on the server**: `gh api repos/<o>/<r>/commits --jq '.[] |
  "\(.sha[0:7]) \(.commit.author.name)"'`. Local `git log` can agree with your
  intent while the remote still shows the old author.
- Every SHA in the range changes — tell the user, since links they shared to
  specific commits are now stale.

## Setting a repo-local identity

Set it per repo, not globally, and take the name/email from the account the user
actually owns (`gh api user --jq '{login,name,email}'`). If the repo has no
identity configured, the safest default is the author of the most recent commit
rather than an invented name — then say which you used.

## Pushing to a fork whose Pages site lives upstream

A working remote and the deployed site are often different accounts: CI runs on
the fork, Pages is deployed from upstream. Before "fixing" any badge or doc link
to match `git remote`, check both endpoints:

```bash
curl -sI https://<fork-owner>.github.io/<repo>/ | head -1   # often 404
curl -sI https://<upstream>.github.io/<repo>/ | head -1   # the one that is live
```

Links pointing at the other account are then correct as written; repointing them
breaks a working badge. Say this explicitly rather than silently leaving them.

## Reconciling an overlapping branch

When another branch (often an in-flight feature or i18n-infrastructure branch)
touches the same files, take its files individually instead of merging:

```bash
git fetch origin <branch>
git checkout FETCH_HEAD -- <paths...>   # per-file, keep your own version of contested ones
git diff --stat <upstream>...FETCH_HEAD   # see what that branch actually did
```

Two translations of the same file cannot be merged — pick the more complete one
and say so in the commit message. Fetching a branch that is not a local ref makes
`main..origin/<branch>` fail with "unknown revision"; compare against `FETCH_HEAD`.

Judging overlap is cheap and prevents a wasted merge: run the project's own audit
tool against both sides. A branch shipping 605 translated keys does not supersede
one shipping 1403 even if it also carries the infrastructure you want — take the
tooling and keep the larger translation.