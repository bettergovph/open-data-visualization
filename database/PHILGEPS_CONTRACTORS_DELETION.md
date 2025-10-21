# philgeps.contractors Table - Marked for Deletion

**Date:** October 21, 2025  
**Status:** ⚠️ MARKED FOR DELETION  
**Decision:** Redundant table, replaced by `sec.contractors`

---

## Reason for Deletion

### 1. Redundant with sec.contractors

**philgeps.contractors:**
- 13,212 raw contractor names
- NO SEC registration data
- All `project_count = 0` (unmaintained field)
- Just a name dump
- Poor data quality (e.g., '. BLUE M', '. CTC BU / AICON INDUSTRIES')

**sec.contractors (replacement):**
- 10,981 cleaned contractor names
- ✅ 1,042 with SEC registration data (9.5%)
- ✅ Actual project counts (136,461 total projects)
- ✅ SEC status, addresses, registration dates
- ✅ Unified, cleaned, and enriched data

### 2. Not Used by Production Website

**Checked all API endpoints:**
- `/api/contractors/sec` → Uses `sec.contractors` ✅
- `/api/contractors/top` → Uses `sec.contractors` ✅
- `/api/contractors/venn` → Uses `sec.contractors` ✅
- `/api/contractors/projects/{name}` → Uses `sec.contractors` ✅

**Frontend pages:**
- `/contractors` → Uses `sec.contractors` via API ✅
- `/flood` contractors tab → Uses MeiliSearch (no DB table)

**Conclusion:** `philgeps.contractors` is not queried by any production code.

### 3. Only Used Internally

The table appears to be:
- A leftover from PhilGEPS contract imports
- Auto-populated from contractor names in `contracts.awardee_name`
- Never maintained or enriched
- Not part of any production workflow

---

## Dependencies to Remove First

### Foreign Key Constraint:

```sql
-- Self-referential foreign key
ALTER TABLE philgeps.contractors 
DROP CONSTRAINT IF EXISTS contractors_former_id_fkey;
```

This constraint tracks contractor name changes/mergers via `former_id → contractors.id`.

**Note:** Since we're not using this table, the merger tracking is not functional anyway.

---

## Deletion Steps

### Step 1: Drop Foreign Key Constraint

```sql
-- Connect to philgeps database
psql -h localhost -p 5432 -U budget_admin -d philgeps

-- Drop constraint
ALTER TABLE contractors DROP CONSTRAINT IF EXISTS contractors_former_id_fkey;
```

### Step 2: Drop Table

```sql
DROP TABLE IF EXISTS contractors CASCADE;
```

### Step 3: Verify Remaining Tables

```sql
\dt
-- Should show only:
-- 1. contracts (104,819 rows) - PhilGEPS contract awards
-- 2. project_contractors (10,627 rows) - JV-aware relationships for SEC parser
```

---

## Impact Assessment

### ✅ Safe to Delete:

1. **No API endpoints** query `philgeps.contractors`
2. **No frontend code** depends on it
3. **sec.contractors** is superior replacement
4. **All contractor data** preserved in `sec.contractors`

### ⚠️ Potential Issues:

1. **Old scripts** in `sec_scraper/` may reference it:
   - `sync_philgeps_contractors.py` - populates this table
   - `consolidate_duplicates.py` - may read from it
   - These scripts would need updates or deletion

2. **Database dumps** currently include it:
   - `database/philgeps_dump.sql` (36.90 MB)
   - Would become smaller after deletion

---

## Recommended Actions Before Deletion

1. ✅ **Verify sec.contractors** has all needed data
2. ✅ **Backup current state**: `database/philgeps_dump.sql` (already done)
3. ⚠️ **Audit old scripts** in `sec_scraper/` that may reference this table
4. ⚠️ **Test in development** first before production deletion

---

## Alternative: Keep for Historical Reference

If unsure, we can:
- Rename to `contractors_deprecated`
- Add note in description
- Keep as reference but mark unused

---

## Files That May Reference This Table

Scripts that might need cleanup after deletion:

- `sec_scraper/sync_philgeps_contractors.py`
- `sec_scraper/consolidate_duplicates.py`
- `sec_scraper/sync_project_contractors.py`
- `sec_scraper/update_project_counts.py`
- Any script that syncs contractor data

**TODO:** Audit these scripts and update or remove them.

---

**Marked by:** AI Assistant  
**Decision basis:** Redundancy analysis, API audit, data quality comparison  
**Next step:** Review old scripts, then execute deletion in development → production

