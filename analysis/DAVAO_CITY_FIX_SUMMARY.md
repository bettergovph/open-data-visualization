# Davao City District Assignment Fix Summary

## Analysis Results

From `scripts/analyze_davao_city_projects.py`:

### Current State:
- **1st District**: 
  - Paolo Duterte: 995 projects ✅ (correct)
  - Isidro Ungab: 0 projects ✅ (correct)
  
- **3rd District**:
  - Isidro Ungab: 3920 projects ✅ (correct)
  - Paolo Duterte: 1 project ❌ (should be 0 - **ISSUE**)

### Issue Identified:
There is **1 project** in 3rd District incorrectly assigned to Paolo Duterte (should be Isidro Ungab's).

## Fixes Applied

### 1. Stricter District Number Validation (lines 6640-6737)
**Location**: Individual cache creation validation

**Changes**:
- Added district number validation for Davao City projects
- If congressman has district number but project doesn't, try to extract from location
- If still can't determine project district for Davao City, **REJECT** to prevent cross-contamination
- This prevents Paolo Duterte (1st) from getting Isidro Ungab's (3rd) projects and vice versa

**Logic**:
```python
# For Davao City, if we can't determine project district, reject to be safe
# This prevents Paolo Duterte (1st) from getting projects that might be 3rd District
if cm_district_match and not proj_district_match:
    # Try to extract from location
    location_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s*DISTRICT\b', location_upper)
    if location_district_match:
        # Compare district numbers
        if cm_num != proj_num:
            should_include = False  # REJECT
    else:
        # Can't determine - reject to be safe for Davao City
        should_include = False  # REJECT
```

### 2. Stricter Matching Phase Validation (lines 4950-4957)
**Location**: `_find_congressman_by_district()` function

**Changes**:
- When multiple candidates match for Davao City and we can't determine district number, reject all candidates
- This prevents any match if district can't be determined

**Logic**:
```python
# For Davao City, if we can't determine district number, reject to prevent cross-contamination
if province_upper in ['DAVAO CITY', 'DAVAO DEL SUR']:
    if location_upper and len(validated_candidates) > 1:
        # Can't determine district - reject all to be safe
        validated_candidates = []
```

## Next Steps

1. **Run analysis script again** to see the problematic project:
   ```bash
   python3 scripts/analyze_davao_city_projects.py
   ```
   This will show the specific project that's causing the issue.

2. **Regenerate cache** with the fixes:
   ```bash
   python3 scripts/generate_dynasty_projects_cache_duckdb.py --force
   ```

3. **Re-run analysis** to verify the fix:
   ```bash
   python3 scripts/analyze_davao_city_projects.py
   ```
   Expected result: Paolo Duterte should have 0 projects in 3rd District.

## Expected Outcome

After regeneration:
- **1st District**: Paolo Duterte should have all projects (995+)
- **3rd District**: Isidro Ungab should have all projects (3920+)
- **3rd District**: Paolo Duterte should have 0 projects ✅

The 1 problematic project should either:
- Be correctly assigned to Isidro Ungab (if district can be determined)
- Be rejected/unassigned (if district cannot be determined - safer than wrong assignment)









