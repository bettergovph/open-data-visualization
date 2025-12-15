#!/usr/bin/env bash
# One-shot fixer for GitHub "GH001: Large files detected" push failures.
# - Removes >100MB blobs from git history (and a small allowlist of known offenders)
# - Adds removed paths to .gitignore to prevent re-adding
# - Force-pushes the rewritten history to origin
#
# Usage:
#   scripts/fix_large_files_and_force_push.sh
#
# WARNING: Rewrites git history. Anyone who pulled the old history must re-clone or reset.

set -euo pipefail

HARD_LIMIT_BYTES=$((100 * 1024 * 1024))
REMOTE="${REMOTE:-origin}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ Missing required command: $1" >&2; exit 1; }
}

require_cmd git

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "❌ Not inside a git repository." >&2
  exit 1
fi

# Known offenders from your push errors (safe to remove from history)
KNOWN_REMOVE_PATHS=(
  "static/data/congressman-projects-elizaldy-salcedo-co/all-projects-cache.json"
  "data/parquet/integrated_projects_classified.parquet"
)

find_large_paths_in_history() {
  local limit_bytes="$1"
  git rev-list --objects --all \
    | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
    | awk -v limit="$limit_bytes" '$1=="blob" && $3>limit {print $4}' \
    | sed '/^$/d' \
    | sort -u
}

ensure_git_filter_repo() {
  if git filter-repo --help >/dev/null 2>&1; then
    return 0
  fi
  echo "❌ 'git filter-repo' is required to rewrite history but is not installed." >&2
  echo "   Install with: pipx install git-filter-repo   (or: pip install git-filter-repo)" >&2
  exit 1
}

append_gitignore_line() {
  local line="$1"
  [ -f .gitignore ] || touch .gitignore
  grep -Fxq "$line" .gitignore || echo "$line" >> .gitignore
}

echo "🔎 Scanning git history for blobs > $((HARD_LIMIT_BYTES/1024/1024))MB..."
mapfile -t DETECTED_REMOVE_PATHS < <(find_large_paths_in_history "$HARD_LIMIT_BYTES" || true)

declare -A REMOVE_SET=()
for p in "${KNOWN_REMOVE_PATHS[@]}"; do REMOVE_SET["$p"]=1; done
for p in "${DETECTED_REMOVE_PATHS[@]}"; do REMOVE_SET["$p"]=1; done

REMOVE_PATHS=()
for p in "${!REMOVE_SET[@]}"; do REMOVE_PATHS+=("$p"); done
IFS=$'\n' REMOVE_PATHS=($(sort <<<"${REMOVE_PATHS[*]}")); unset IFS

if [ "${#REMOVE_PATHS[@]}" -eq 0 ]; then
  echo "✅ No >100MB blobs detected in history. Attempting normal push..."
  git push "$REMOTE" "$BRANCH"
  exit 0
fi

echo "🧹 Will remove these paths from history:"
for p in "${REMOVE_PATHS[@]}"; do
  echo "   - $p"
done

ensure_git_filter_repo

# Unstage everything to avoid carrying staged state across rewrite
git reset

echo "🧼 Rewriting history with git filter-repo..."
args=()
for p in "${REMOVE_PATHS[@]}"; do
  args+=(--path "$p")
done
git filter-repo --force "${args[@]}" --invert-paths

echo "🛡️  Adding removed paths to .gitignore..."
append_gitignore_line ""
append_gitignore_line "# Prevent re-adding files removed from history (GitHub size limits)"
for p in "${REMOVE_PATHS[@]}"; do
  append_gitignore_line "$p"
done

if ! git diff --quiet -- .gitignore; then
  git add -- .gitignore
  git commit -m "Ignore large generated files"
fi

echo "📤 Force-pushing rewritten history to $REMOTE ($BRANCH)..."
echo "🔄 Fetching latest remote refs to avoid stale-lease rejections..."
git fetch "$REMOTE" --prune

set +e
git push --force-with-lease "$REMOTE" "$BRANCH"
push_exit=$?
set -e

if [ "$push_exit" -ne 0 ]; then
  if [ "${FORCE_PUSH:-0}" = "1" ]; then
    echo "⚠️  Lease rejected; FORCE_PUSH=1 set, using --force."
    git push --force "$REMOTE" "$BRANCH"
  else
    echo "❌ Force-with-lease was rejected (stale info)."
    echo "   Someone may have pushed to $REMOTE/$BRANCH since you last fetched."
    echo ""
    echo "Next steps:"
    echo "  1) Run: git fetch $REMOTE --prune"
    echo "  2) Re-run: scripts/fix_large_files_and_force_push.sh"
    echo "  3) If you are sure you want to overwrite remote history: FORCE_PUSH=1 scripts/fix_large_files_and_force_push.sh"
    exit "$push_exit"
  fi
fi

git push --force-with-lease "$REMOTE" --tags

echo "✅ Done."
