#!/usr/bin/env bash
# compact-history.sh — purge paths from a repo's history and squash to one commit.
#
# Reference implementation for the git-history-compaction skill. Every destructive
# step is preceded by a safety check; the script aborts rather than guessing.
#
# Usage:
#   compact-history.sh --repo <path> --purge <path> [--purge <path>...] \
#   [--branch main] [--tag v1.0] [--message "..."] [--backup-dir ~/backups] \
#       [--push] [--drop-remote-backup] [--dump]

set -euo pipefail

REPO=""
BRANCH=""
EXPLICIT_BRANCH=0
BACKUP_DIR="$HOME/backups"
MESSAGE=""
PUSH=0
DROP_BACKUP=0
DUMP=0
PURGE=()
TAGS=()

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)            REPO="$2"; shift 2 ;;
        --purge)           PURGE+=("$2"); shift 2 ;;
        --branch)          BRANCH="$2"; EXPLICIT_BRANCH=1; shift 2 ;;
        --tag)             TAGS+=("$2"); shift 2 ;;
        --message)         MESSAGE="$2"; shift 2 ;;
        --backup-dir)      BACKUP_DIR="$2"; shift 2 ;;
        --push)            PUSH=1; shift ;;
        --drop-remote-backup) DROP_BACKUP=1; shift ;;
        --dump)            DUMP=1; shift ;;
        -h|--help)         usage; exit 0 ;;
        *)                 die "unknown argument: $1 (try --help)" ;;
    esac
done

[[ -n "$REPO" ]] || die "--repo is required"
[[ -d "$REPO/.git" ]] || die "not a git repository: $REPO"
cd "$REPO"

# ---------------------------------------------------------------- preflight
command -v git-filter-repo >/dev/null 2>&1 \
    || die "git-filter-repo not found — install with: pip install --user git-filter-repo"

[[ -z "$(git status --porcelain)" ]] \
    || die "worktree is dirty — commit or stash first"

# Default to the current branch; only enforce a switch when --branch is explicit.
if [[ -z "$BRANCH" ]]; then
    BRANCH="$(git symbolic-ref --short HEAD 2>/dev/null || echo main)"
else
    CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
    [[ "$CURRENT_BRANCH" == "$BRANCH" ]] \
        || die "on branch '$CURRENT_BRANCH' but --branch is '$BRANCH' — checkout the intended branch first"
fi

ORIGIN_URL="$(git remote get-url origin 2>/dev/null || true)"
COMMIT_COUNT_BEFORE="$(git rev-list --count HEAD)"
FILES_BEFORE="$(git ls-files | wc -l | tr -d ' ')"
GIT_SIZE_BEFORE="$(du -sh .git | cut -f1)"

FILTER_ARGS=()
for p in "${PURGE[@]:-}"; do
    [[ -n "$p" ]] && FILTER_ARGS+=(--path "$p")
done

if [[ $DUMP -eq 1 ]]; then
    echo "git filter-repo --force --invert-paths ${FILTER_ARGS[*]:-}"
    exit 0
fi

echo "Repository : $REPO"
echo "Branch     : $BRANCH"
echo "Commits    : $COMMIT_COUNT_BEFORE"
echo "Files      : $FILES_BEFORE"
echo ".git size  : $GIT_SIZE_BEFORE"
[[ ${#PURGE[@]} -gt 0 ]] && echo "Purging    : ${PURGE[*]}"

# ---------------------------------------------------------------- 1. backup
STAMP="$(date +%Y%m%d-%H%M%S)"
REPO_NAME="$(basename "$REPO" | tr -cs '[:alnum:]._-' '-')"
mkdir -p "$BACKUP_DIR"
BUNDLE="$BACKUP_DIR/${REPO_NAME}-history-${STAMP}.bundle"

info "Creating history bundle -> $BUNDLE"
git bundle create "$BUNDLE" --all
[[ -s "$BUNDLE" ]] || die "bundle was not created"
info "Bundle size: $(du -h "$BUNDLE" | cut -f1)"

BACKUP_BRANCH="${BRANCH}-backup-${STAMP}"
if [[ -n "$ORIGIN_URL" ]]; then
    info "Pushing remote backup branch -> origin/${BACKUP_BRANCH}"
    git push origin "HEAD:${BACKUP_BRANCH}" --force >/dev/null
else
    BACKUP_BRANCH=""
    echo "WARNING: no origin remote — skipping remote backup branch" >&2
fi

# ---------------------------------------------------------------- 2. purge
if [[ ${#FILTER_ARGS[@]} -gt 0 ]]; then
    info "Purging paths from all history with git-filter-repo"
    git filter-repo --force --invert-paths "${FILTER_ARGS[@]}"
    # filter-repo removes the origin remote as part of its safety reset
    if [[ -n "$ORIGIN_URL" ]] && ! git remote get-url origin >/dev/null 2>&1; then
        info "Re-adding origin remote (filter-repo removes it)"
        git remote add origin "$ORIGIN_URL"
    fi
else
    info "No --purge paths given; skipping filter-repo"
fi

# ---------------------------------------------------------------- 3. squash
info "Squashing history into a single root commit"
git checkout --orphan "${BRANCH}-squashed" >/dev/null 2>&1
git add -A
if [[ -z "$MESSAGE" ]]; then
    MESSAGE="$(basename "$REPO") — history compacted"
fi
git commit -q -m "$MESSAGE"
git branch -D "$BRANCH" >/dev/null 2>&1
git branch -m "$BRANCH"

# ---------------------------------------------------------------- 4. tags
for t in "${TAGS[@]:-}"; do
    [[ -n "$t" ]] || continue
    info "Recreating tag $t on the new commit"
    git tag -d "$t" >/dev/null 2>&1 || true
    git tag -a "$t" -m "$t"
done

# ---------------------------------------------------------------- 5. push
if [[ $PUSH -eq 1 && -n "$ORIGIN_URL" ]]; then
    info "Force-pushing $BRANCH"
    git push --force origin "$BRANCH" >/dev/null
    for t in "${TAGS[@]:-}"; do
        [[ -n "$t" ]] || continue
        git push --force origin "$t" >/dev/null
    done
    info "Re-establishing upstream tracking"
    git fetch origin --prune >/dev/null 2>&1 || true
    git branch --set-upstream-to="origin/$BRANCH" "$BRANCH" >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------- 6. cleanup
info "Expiring reflog and garbage-collecting local objects"
git reflog expire --expire=now --all
git gc --prune=now --quiet 2>/dev/null || true

if [[ $DROP_BACKUP -eq 1 && -n "$BACKUP_BRANCH" ]]; then
    info "Deleting remote backup branch origin/${BACKUP_BRANCH}"
    git push origin --delete "$BACKUP_BRANCH" >/dev/null
fi
# Drop any local backup-branch ref too (the bundle is the durable backup).
if [[ -n "$BACKUP_BRANCH" ]] && git show-ref --verify "refs/heads/${BACKUP_BRANCH}" >/dev/null 2>&1; then
    git branch -D "$BACKUP_BRANCH" >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------- 7. report
FILES_AFTER="$(git ls-files | wc -l | tr -d ' ')"
echo
echo "==================== RESULT ===================="
printf '  commits      : %s -> %s\n' "$COMMIT_COUNT_BEFORE" "$(git rev-list --count HEAD)"
printf '  .git size    : %s -> %s\n' "$GIT_SIZE_BEFORE" "$(du -sh .git | cut -f1)"
printf '  tracked files: %s -> %s\n' "$FILES_BEFORE" "$FILES_AFTER"
printf '  backup bundle: %s\n' "$BUNDLE"
if [[ -n "$BACKUP_BRANCH" ]]; then
    printf '  remote backup: origin/%s%s\n' "$BACKUP_BRANCH" \
        "$([[ $DROP_BACKUP -eq 1 ]] && echo ' (deleted)')"
fi
echo "=================================================="
[[ "${FILES_BEFORE}" == "${FILES_AFTER}" ]] \
    || { [[ ${#FILTER_ARGS[@]} -gt 0 ]] \
         && echo "WARNING: tracked file count changed ($FILES_BEFORE -> $FILES_AFTER) — expected since --purge removed paths" >&2 \
         || echo "WARNING: tracked file count changed ($FILES_BEFORE -> $FILES_AFTER)" >&2; }
