#!/bin/bash
# Script to commit and push cache generation files
# This includes congressman JSON caches, ranking JSON, classified parquet, and the generator script
# Intelligently skips files that are already staged or not modified

set -e  # Exit on error

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

# Function to check file size limit (50MB)
check_size() {
    local file="$1"
    if [ ! -f "$file" ]; then return 0; fi
    
    # Get file size in bytes
    local size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null)
    local limit=$((50 * 1024 * 1024)) # 50MB
    
    if [ "$size" -gt "$limit" ]; then
        local size_mb=$(echo "scale=2; $size / 1024 / 1024" | bc)
        echo "   ❌ SKIPPED: $file is too large (${size_mb} MB > 50 MB)"
        return 1
    fi
    return 0
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
        result=$(stage_if_needed "$json_file" 2>&1)
        exit_code=$?
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
echo "📦 Staging classified parquet file..."
set +e  # Temporarily disable exit on error
stage_if_needed "data/parquet/integrated_projects_classified.parquet" > /dev/null
exit_code=$?
set -e  # Re-enable exit on error
case $exit_code in
    0) echo "   ✅ Staged: integrated_projects_classified.parquet" ;;
    1) echo "   ⏭️  Already staged: integrated_projects_classified.parquet" ;;
    2) echo "   ⚠️  Not found: integrated_projects_classified.parquet" ;;
    3) echo "   ✓  No changes: integrated_projects_classified.parquet" ;;
esac

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

if [ "$STAGED_COUNT" -eq 0 ]; then
    echo ""
    echo "ℹ️  No new files to commit. All files are either already staged or have no changes."
    echo ""
    echo "Checking if there are already staged files ready to push..."
    if [ "$(git diff --cached --name-only | wc -l)" -gt 0 ]; then
        echo "   ✅ Found $(git diff --cached --name-only | wc -l) files already staged"
        echo ""
        read -p "Do you want to commit and push the already-staged files? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "   Cancelled."
            exit 0
        fi
    else
        echo "   No files staged for commit."
        exit 0
    fi
fi

echo ""
echo "📝 Committing..."
git commit -m "Update cache files: congressman JSON caches, ranking, classified parquet, and generator script

- Update all congressman project cache JSON files
- Update congressman-ranking.json
- Update integrated_projects_classified.parquet
- Update generate_dynasty_projects_cache_duckdb.py with improved PhilGEPS project name handling"

echo ""
echo "📤 Pushing to remote..."
git push

echo ""
echo "✅ Done! Cache files have been committed and pushed."

