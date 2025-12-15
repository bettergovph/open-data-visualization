#!/bin/bash
# Script to stage (with size safeguards), commit, and push.
# Includes:
# - congressman JSON caches under static/data/congressman-projects-*
# - ranking JSON
# - cache generator script
# - ANY files you already staged manually
# - ANY other modified/untracked files, except excluded/oversize ones
# Skips files > 90MB and data/parquet/integrated_projects_classified.parquet

set -e  # Exit on error

# Optional: rewrite git history to remove large files before pushing.
# Usage:
#   CLEAN_HISTORY=1 scripts/commit_and_push_cache_files.sh
#   scripts/commit_and_push_cache_files.sh --clean-history
DO_CLEAN_HISTORY=0
if [ "${CLEAN_HISTORY:-0}" = "1" ]; then
    DO_CLEAN_HISTORY=1
fi
if [ "${1:-}" = "--clean-history" ]; then
    DO_CLEAN_HISTORY=1
fi

# Track any files that were already staged before this script runs
INITIAL_STAGED=$(git diff --cached --name-only | wc -l)

# Default exclusions that commonly exceed GitHub limits
EXCLUDE_PATHS=(
    "data/parquet/integrated_projects_classified.parquet"
    "static/data/congressman-projects-elizaldy-salcedo-co/all-projects-cache.json"
)

# Detect large blobs in history (GitHub hard limit is 100MB)
HISTORY_HARD_LIMIT_BYTES=$((100 * 1024 * 1024))

has_git_filter_repo() {
    git filter-repo --help >/dev/null 2>&1
}

check_large_blobs_in_history() {
    # Prints offending paths (best-effort) and returns 0 if any blobs exceed limit
    local limit_bytes="$1"
    local tmpfile
    tmpfile=$(mktemp)
    # Map objects to paths, then batch-check blob sizes
    # Output format: <type> <sha> <size> <path>
    git rev-list --objects --all \
        | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
        | awk -v limit="$limit_bytes" '$1=="blob" && $3>limit {print $4}' \
        | sed '/^$/d' \
        | sort -u > "$tmpfile"

    if [ -s "$tmpfile" ]; then
        echo "🚫 Found blobs > $((limit_bytes/1024/1024))MB in git history:"
        cat "$tmpfile" | sed 's/^/   - /'
        rm -f "$tmpfile"
        return 0
    fi
    rm -f "$tmpfile"
    return 1
}

clean_history() {
    echo ""
    echo "🧹 Cleaning git history (removing excluded paths)..."
    if ! has_git_filter_repo; then
        echo "❌ 'git filter-repo' is required but not installed."
        echo "   Install with: pipx install git-filter-repo  (or: pip install git-filter-repo)"
        echo "   Then re-run: CLEAN_HISTORY=1 scripts/commit_and_push_cache_files.sh"
        exit 1
    fi

    # Build arguments: --path <p1> --path <p2> ... --invert-paths
    local args=()
    for p in "${EXCLUDE_PATHS[@]}"; do
        args+=(--path "$p")
    done

    git filter-repo --force "${args[@]}" --invert-paths

    echo ""
    echo "✅ History rewritten. You must force-push:"
    echo "   git push --force --all"
    echo "   git push --force --tags"
}

# Function to check if a file is already staged
is_staged() {
    local file="$1"
    git diff --cached --name-only | grep -Fxq "$file"
}

# Function to check if a file has modifications
is_modified() {
    local file="$1"
    # Check if file is modified (not staged, or staged but also modified in working tree)
    # git status --porcelain returns:
    #   " M" = modified but not staged
    #   "M " = staged
    #   "MM" = staged and modified
    #   "??" = untracked
    local status=$(git status --porcelain "$file" 2>/dev/null)
    if [ -z "$status" ]; then
        return 1  # File not modified or not tracked
    fi
    # Check if it's modified (any M in the status)
    echo "$status" | grep -qE "^[ M]{2}" && return 0 || return 1
}

# Function to check file size limit (90MB)
check_size() {
    local file="$1"
    if [ ! -f "$file" ]; then return 0; fi
    
    # Get file size in bytes
    local size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null)
    local limit=$((90 * 1024 * 1024)) # 90MB
    
    if [ "$size" -gt "$limit" ]; then
        local size_mb=$(echo "scale=2; $size / 1024 / 1024" | bc)
        echo "   ❌ SKIPPED: $file is too large (${size_mb} MB > 90 MB)"
        return 1
    fi
    return 0
}

# Unstage any already-staged file that exceeds the size limit
unstage_oversize_files() {
    local limit=$((90 * 1024 * 1024)) # 90MB
    while IFS= read -r file; do
        if [ -f "$file" ]; then
            local size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null)
            if [ "$size" -gt "$limit" ]; then
                git restore --staged "$file" 2>/dev/null || git reset HEAD -- "$file" 2>/dev/null
                local size_mb=$(echo "scale=2; $size / 1024 / 1024" | bc)
                echo "   🚫 Unstaged oversize file: $file (${size_mb} MB > 90 MB)"
            fi
        fi
    done < <(git diff --cached --name-only)
}

# Exclusions (hard-coded)
is_excluded() {
    local file="$1"
    [[ "$file" == "data/parquet/integrated_projects_classified.parquet" ]]
}

# Stage helper with exclusions + size checks; uses -A to capture deletions too
stage_path_safely() {
    local file="$1"
    if [ -z "$file" ]; then return 0; fi
    if is_excluded "$file"; then
        echo "   ❌ SKIPPED (excluded): $file"
        return 0
    fi
    if ! check_size "$file"; then
        return 0
    fi
    git add -A -- "$file"
    echo "   ✅ Staged: $file"
}

# Function to stage file if not already staged and if modified
stage_if_needed() {
    local file="$1"
    if [ ! -f "$file" ]; then
        echo "   ⚠️  File not found: $file"
        return 2  # Not found
    fi
    
    # Check git status for this file
    local status=$(git status --porcelain "$file" 2>/dev/null)
    
    # If file is not tracked or has no changes
    if [ -z "$status" ]; then
        # Check if it's a new untracked file
        if ! git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
            # Untracked file - stage it
            git add "$file"
            echo "   ✅ Staged (new): $file"
            return 0
        else
            echo "   ✓  No changes: $file"
            return 3  # Not modified
        fi
    fi
    
    # If already staged (M  or A  or MM)
    if echo "$status" | grep -qE "^[AM] "; then
        # Check if also modified in working tree (MM)
        if echo "$status" | grep -qE "^MM"; then
            # Staged but also modified - add again to update staging
            check_size "$file" || return 4 # Too large
            git add "$file"
            echo "   ✅ Updated staging: $file"
            return 0
        else
            echo "   ⏭️  Already staged: $file"
            return 1  # Already staged
        fi
    fi
    
    # If modified but not staged ( M)
    if echo "$status" | grep -qE "^ M"; then
        check_size "$file" || return 4 # Too large
        git add "$file"
        echo "   ✅ Staged: $file"
        return 0  # Newly staged
    fi
    
    # If untracked (??)
    if echo "$status" | grep -qE "^\?\?"; then
        check_size "$file" || return 4 # Too large
        git add "$file"
        echo "   ✅ Staged (new): $file"
        return 0
    fi
    
    echo "   ✓  No changes: $file"
    return 3  # Not modified
}

echo "📦 Staging congressman JSON cache files..."

# Get all modified/untracked JSON files from git status and stage them directly
MODIFIED_JSON_FILES=$(git status --porcelain | grep -E "^ M|^MM|\?\?" | grep "congressman-projects-.*\.json$" | awk '{print $2}')

NEWLY_STAGED=0
ALREADY_STAGED=0
NOT_MODIFIED=0
NOT_FOUND=0

# Stage all modified JSON files directly
if [ -n "$MODIFIED_JSON_FILES" ]; then
    while IFS= read -r json_file; do
        if [ -f "$json_file" ]; then
            # Check current status
            status=$(git status --porcelain "$json_file" 2>/dev/null)
            # Skip oversize files before any staging attempt
            if ! check_size "$json_file"; then
                continue
            fi
            
            if echo "$status" | grep -qE "^MM"; then
                # Staged but also modified - update staging
                git add "$json_file"
                echo "   ✅ Updated staging: $json_file"
                NEWLY_STAGED=$((NEWLY_STAGED + 1))
            elif echo "$status" | grep -qE "^[AM] "; then
                # Already staged
                echo "   ⏭️  Already staged: $json_file"
                ALREADY_STAGED=$((ALREADY_STAGED + 1))
            elif echo "$status" | grep -qE "^ M|\?\?"; then
                # Modified or untracked - stage it
                git add "$json_file"
                echo "   ✅ Staged: $json_file"
                NEWLY_STAGED=$((NEWLY_STAGED + 1))
            fi
        fi
    done <<< "$MODIFIED_JSON_FILES"
fi

# Also check all JSON files to catch any edge cases (files that might not show in git status)
TOTAL_FOUND=0
while IFS= read -r json_file; do
    TOTAL_FOUND=$((TOTAL_FOUND + 1))
    # Only process if not already in MODIFIED_JSON_FILES
    if [ -z "$MODIFIED_JSON_FILES" ] || ! echo "$MODIFIED_JSON_FILES" | grep -Fxq "$json_file"; then
        set +e
        result=$(stage_if_needed "$json_file" 2>&1)
        exit_code=$?
        set -e
        case $exit_code in
            0) NEWLY_STAGED=$((NEWLY_STAGED + 1)) ;;
            1) ALREADY_STAGED=$((ALREADY_STAGED + 1)) ;;
            3) NOT_MODIFIED=$((NOT_MODIFIED + 1)) ;;
        esac
    fi
done < <(find static/data -path "*/congressman-projects-*/*.json" -type f 2>/dev/null)

TOTAL_CONGRESSMAN_JSON=$(find static/data -path "*/congressman-projects-*/*.json" -type f 2>/dev/null | wc -l)
echo "   Total congressman JSON files: $TOTAL_CONGRESSMAN_JSON"
echo "   ✅ Newly staged: $NEWLY_STAGED"
echo "   ⏭️  Already staged: $ALREADY_STAGED"
echo "   ✓  Not modified: $NOT_MODIFIED"
if [ "${NOT_FOUND:-0}" -gt 0 ]; then
    echo "   ⚠️  Not found: $NOT_FOUND"
fi

echo ""
echo "📦 Staging ranking JSON file..."
set +e  # Temporarily disable exit on error
stage_if_needed "static/data/congressman-ranking.json" > /dev/null
exit_code=$?
set -e  # Re-enable exit on error
case $exit_code in
    0) echo "   ✅ Staged: congressman-ranking.json" ;;
    1) echo "   ⏭️  Already staged: congressman-ranking.json" ;;
    2) echo "   ⚠️  Not found: congressman-ranking.json" ;;
    3) echo "   ✓  No changes: congressman-ranking.json" ;;
esac

echo ""
echo "📦 Skipping classified parquet file (too large for GitHub): data/parquet/integrated_projects_classified.parquet"

echo ""
echo "📦 Staging cache generator script..."
set +e  # Temporarily disable exit on error
stage_if_needed "scripts/generate_dynasty_projects_cache_duckdb.py" > /dev/null
exit_code=$?
set -e  # Re-enable exit on error
case $exit_code in
    0) echo "   ✅ Staged: generate_dynasty_projects_cache_duckdb.py" ;;
    1) echo "   ⏭️  Already staged: generate_dynasty_projects_cache_duckdb.py" ;;
    2) echo "   ⚠️  Not found: generate_dynasty_projects_cache_duckdb.py" ;;
    3) echo "   ✓  No changes: generate_dynasty_projects_cache_duckdb.py" ;;
esac

# Stage any other modified/untracked files except excluded/oversize ones
echo ""
echo "📦 Staging remaining modified/untracked files (excluding >90MB and classified parquet)..."

# Tracked changes (unstaged)
while IFS= read -r -d '' path; do
    # Skip congressman caches here; handled separately with size check above
    if [[ "$path" == static/data/congressman-projects-* ]]; then
        continue
    fi
    stage_path_safely "$path"
done < <(git diff --name-only -z)

# Untracked files
while IFS= read -r -d '' path; do
    # Skip congressman caches here; handled separately with size check above
    if [[ "$path" == static/data/congressman-projects-* ]]; then
        continue
    fi
    stage_path_safely "$path"
done < <(git ls-files -o --exclude-standard -z)

echo ""
echo "📊 Checking staged files..."
STAGED_COUNT=$(git diff --cached --name-only | wc -l)
JSON_COUNT=$(git diff --cached --name-only | grep "\.json$" | wc -l)
PARQUET_COUNT=$(git diff --cached --name-only | grep "\.parquet$" | wc -l)
PYTHON_COUNT=$(git diff --cached --name-only | grep "\.py$" | wc -l)

echo "   Total files staged: $STAGED_COUNT"
echo "   JSON files staged: $JSON_COUNT"
echo "   Parquet files staged: $PARQUET_COUNT"
echo "   Python scripts staged: $PYTHON_COUNT"
echo "   (Includes any files you already staged before running this script: $INITIAL_STAGED)"

if [ "$STAGED_COUNT" -eq 0 ]; then
    echo ""
    echo "ℹ️  No files currently staged; skipping commit/push."
    exit 0
fi

# Final guard: unstage any oversize files (>90MB) before commit
unstage_oversize_files

# Always ensure the classified parquet is not staged
git restore --staged -- "data/parquet/integrated_projects_classified.parquet" 2>/dev/null || true

# Recount after un-staging oversize files
STAGED_COUNT=$(git diff --cached --name-only | wc -l)
if [ "$STAGED_COUNT" -eq 0 ]; then
    echo ""
    echo "ℹ️  All staged files were excluded/oversize; nothing left to commit."
    exit 0
fi

echo ""
echo "📝 Committing..."
git commit -m "Update cache files and staged changes"

echo ""
echo "📤 Pushing to remote..."

# If the remote rejects due to large files, offer (optional) history cleanup.
if check_large_blobs_in_history "$HISTORY_HARD_LIMIT_BYTES"; then
    if [ "$DO_CLEAN_HISTORY" -eq 1 ]; then
        clean_history
        exit 0
    else
        echo ""
        echo "ℹ️  Your history contains files over GitHub's 100MB limit."
        echo "   Run this script with history cleanup enabled:"
        echo "   CLEAN_HISTORY=1 scripts/commit_and_push_cache_files.sh"
        echo "   (or: scripts/commit_and_push_cache_files.sh --clean-history)"
        echo ""
        echo "   Then force-push:"
        echo "   git push --force --all"
        echo "   git push --force --tags"
        exit 1
    fi
fi

git push

echo ""
echo "✅ Done! Cache files have been committed and pushed."
