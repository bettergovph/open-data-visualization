# 2020 Data Investigation Summary

## Issue
The matching script (`find_resurrected_projects.py`) was not finding any DPWH matches for year 2020.

## Investigation Results

### PostgreSQL Database Status
- ✅ `budget_2020` table exists
- ✅ Contains **64,999 total rows**
- ✅ Year column format: `2020` (integer/text)
- ❌ **0 DPWH records found** (even without year filter)

### Department Analysis
The `budget_2020` table contains data for:
- Department of Agriculture (DA): 10,811 records
- Department of Education (DepEd): 8,682 records
- Department of Agrarian Reform (DAR): 6,741 records
- Department of Budget and Management (DBM): 861 records
- Congress of the Philippines (CONGRESS): 415 records
- Office of the President (OP): 319 records
- Office of the Vice-President (OVP): 72 records

**No DPWH-related departments found** in the PostgreSQL `budget_2020` table.

### JSON Files Status
- ✅ JSON files exist: `/home/joebert/open-budget-data/data/budget/2020/items/gaa_2020_batch_*.json`
- ✅ 6 GAA batch files found

## Conclusion
**2020 DPWH data exists in JSON files but has NOT been imported into PostgreSQL.**

The matching script (`find_resurrected_projects.py`) currently only loads data from PostgreSQL, so it cannot find 2020 matches until the data is imported.

## Recommendation
To enable 2020 matching:
1. Import 2020 GAA JSON files into PostgreSQL `budget_2020` table
2. Ensure DPWH records are properly tagged with department information
3. Verify the import includes all required columns (`amt`, `dsc`, `uacs_dpt_dsc`, `uacs_reg_id`, `uacs_agy_dsc`, `year`, `source_file`)

## Related Years Status
- **2016-2019**: No data available (no JSON files, no PostgreSQL tables with data)
- **2020**: Data in JSON, not in PostgreSQL
- **2021-2025**: ✅ Data available in PostgreSQL

