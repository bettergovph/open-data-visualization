# Investigation Report: District/Contractor Matching Across 5 DBs

## Summary
This report investigates how all 5 data sources (DIME, PhilGEPS, SSP, Microsite, Transparency) are used for district/contractor matching, how conflicts are handled during merging/deduplication, and reviews the dynasty parquet for district overlaps.

## 1. How All 5 DBs Are Used for District/Contractor Matches

### Data Flow:
1. **Source Processing** (lines 5180-5245):
   - All 5 sources are processed sequentially: SSP, DIME, PhilGEPS, Microsite, Transparency
   - Each source is filtered from the integrated/classified parquet file
   - Each source has its own processing function: `_process_flood_chunk`, `_process_dime_chunk`, `_process_philgeps_chunk`, `_process_microsite_chunk`, `_process_transparency_chunk`

2. **Unified Matching** (line 1231, 1435, etc.):
   - All sources use the same `_match_project_unified()` function
   - This function tries:
     - District match via `_find_congressman_by_district()`
     - Contractor match via `_find_congressman_by_contractor()`
   - Returns: `(final_congressman, match_type, match_score, district_congressman, contractor_congressman)`

3. **Match Assignment**:
   - Each processed project gets `district_congressman` and/or `contractor_congressman` assigned
   - These are stored in the project dict before deduplication

## 2. What Happens During Merging/Deduplication with Conflicts

### Deduplication Process (lines 5940-6002):

1. **Key Generation** (lines 5950-5970):
   - Projects are deduplicated by key
   - If `contract_id` exists: `key = f"ID:{contract_id_normalized}"`
   - Otherwise: `key = _build_project_key(proj)` (uses project_name, contractor, amount, location)

2. **Merging Logic** (lines 5984-5992):
   - If key not in `projects_by_key`: Create new entry
   - If key exists: Call `_merge_project_records(existing_project, new_project)`
   - **CRITICAL ISSUE**: The `_merge_project_records` function is called but I cannot find its implementation in the codebase

3. **Congressmen Tracking** (lines 5998-6002):
   ```python
   # Track both district and contractor congressmen
   if proj.get('district_congressman'):
       projects_by_key[key]['congressmen'].add(proj.get('district_congressman'))
   if proj.get('contractor_congressman'):
       projects_by_key[key]['congressmen'].add(proj.get('contractor_congressman'))
   ```
   - **PROBLEM**: ALL congressmen from ALL sources are added to the `congressmen` set
   - If DIME matches to Paolo Duterte and PhilGEPS matches to Isidro Ungab, BOTH are added
   - This set becomes `_all_congressmen` (line 6011)

4. **Final Project Assignment** (lines 6006-6079):
   - The merged project's `district_congressman` and `contractor_congressman` come from `data['project']`
   - This is the result of `_merge_project_records()` - but we don't know how it resolves conflicts
   - The `_all_congressmen` list contains ALL congressmen from all merged sources

### Conflict Resolution Issue:
- **Current Behavior**: When projects from different sources are merged:
  - If Source A matches to Paolo Duterte (district)
  - If Source B matches to Isidro Ungab (district) - incorrectly
  - Both are added to `congressmen` set
  - The merged project's `district_congressman` is determined by `_merge_project_records()` (unknown logic)
  - But `_all_congressmen` contains both, causing cross-contamination

## 3. District Overlaps in Dynasty Parquet

### District Key Structure:
- Districts are stored as: `"{province_name} {district_number} District"`
- Example: "Davao City 1st District", "Davao City 3rd District"

### Potential Issues:
1. **Same Province, Different Districts**: 
   - Davao City has 3 districts (1st, 2nd, 3rd)
   - If barangays/municipalities are not properly mapped, projects might match to wrong district
   - The `_apply_district_corrections()` function (lines 2666-2764) tries to fix this but may not cover all cases

2. **Barangay/Municipality Dictionary**:
   - The district_lookup should have `(province, municipality/barangay) -> [congressman]` mappings
   - If "Matina" is not properly mapped to "Davao City 1st District", it might match to multiple districts
   - The exact match lookup (line 4194) should return a single candidate if the mapping exists

## Key Findings

### Issue 1: Missing `_merge_project_records` Function
- **Location**: Line 5991 calls `_merge_project_records()` but the function is NOT defined in the codebase
- **Impact**: When projects are merged, the function call likely fails or uses a default merge that doesn't handle conflicts properly
- **Current Behavior**: The merged project's `district_congressman` and `contractor_congressman` come from `data['project']` which is the result of the first project added (or a broken merge)

### Issue 2: Congressmen Set Accumulation
- **Location**: Lines 5998-6002
- **Problem**: ALL `district_congressman` and `contractor_congressman` from ALL sources are added to the `congressmen` set
- **Example**: 
  - DIME matches project to Paolo Duterte (district)
  - PhilGEPS matches same project to Isidro Ungab (district) - incorrectly
  - Both are added to `congressmen` set
  - Both end up in `_all_congressmen` (line 6011)
  - Both get the project in their individual caches

### Issue 3: No Conflict Resolution
- **Location**: Lines 6006-6079
- **Problem**: The final project's `district_congressman` and `contractor_congressman` are taken from `data['project']` without checking for conflicts
- **Missing Logic**: Should resolve conflicts by:
  - Preferring higher `match_score`
  - Preferring district match over contractor match
  - Preferring matches from more reliable sources

### Issue 4: District Number Not Used in Merging
- **Location**: Lines 5998-6002
- **Problem**: When adding congressmen to the set, district numbers are not checked
- **Impact**: If a project matches to "Davao City 1st District" in one source and "Davao City 3rd District" in another, both are added without validation

## Recommendations

1. **Implement `_merge_project_records` Function**:
   - Create the missing function to properly merge two project records
   - When `district_congressman` conflicts:
     - Prefer the match with higher `district_match_score`
     - If scores are equal, prefer the match from the source with more reliable data
     - Only keep one `district_congressman` in the merged project
   - Same logic for `contractor_congressman`

2. **Fix Congressmen Set Logic**:
   - Only add congressmen to the set if they match the FINAL merged project's assignments
   - Don't add congressmen from individual sources if they conflict with the final assignment
   - Validate district numbers match when adding to the set

3. **Improve District Number Matching**:
   - The district number extraction and matching logic (lines 4840-4897) should be more robust
   - Should check municipality/barangay dictionary FIRST before falling back to district number extraction
   - Should validate district numbers match when multiple candidates exist

4. **Review Dynasty Parquet**:
   - Check if there are overlapping barangays/municipalities across districts
   - Ensure each barangay/municipality maps to only ONE district
   - Verify district numbers are correctly stored in congressmen data
   - Check if "Matina" is properly mapped to "Davao City 1st District" in the parquet

5. **Fix Individual Cache Creation**:
   - The validation logic (lines 6253-6296) should be stricter
   - Should reject projects where congressman is only in `_all_congressmen` but not directly assigned
   - Should verify district number matches when multiple candidates exist
   - Should check if the congressman's district number matches the project's district

## Implementation Status

### ✅ Fixed: `_merge_project_records` Function
- **Location**: Lines 4987-5086
- **Implementation**: Created the missing function that properly merges two project records
- **Conflict Resolution**:
  - When `district_congressman` conflicts: Prefers higher `district_match_score`
  - When `contractor_congressman` conflicts: Prefers higher `contractor_match_score`
  - If scores are equal: Keeps the existing value (first source wins)
  - Updates `match_type` based on final assignments (district takes precedence)

### ✅ Fixed: Congressmen Set Logic
- **Location**: Lines 6099-6106
- **Change**: Now only adds congressmen from the MERGED project, not from individual sources
- **Impact**: Prevents cross-contamination - if merging resolves conflict to Paolo Duterte, only Paolo Duterte is added to the set
- **Before**: Both Paolo Duterte and Isidro Ungab would be added if they matched in different sources
- **After**: Only the resolved congressman (from merged project) is added

### ✅ Fixed: District Number Matching
- **Location**: Lines 4840-4897, 4707-4746
- **Implementation**: 
  - Re-checks exact match from district_lookup when multiple candidates exist
  - Extracts district number from project_district or location
  - Filters candidates by district number match
  - Uses municipality/barangay dictionary to narrow down candidates

### ⚠️ Still Need to Review: Dynasty Parquet
- Need to verify:
  - Each barangay/municipality maps to only ONE district
  - "Matina" is properly mapped to "Davao City 1st District"
  - No overlapping assignments across districts









