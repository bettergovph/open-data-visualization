# NEP Database Setup - Complete

**Date:** October 7, 2025  
**Status:** ✅ **SUCCESSFULLY LOADED**

---

## Summary

A new PostgreSQL database named `nep` has been created to store National Expenditure Program (NEP) data separately from the General Appropriations Act (GAA) data. This provides better data isolation and organization.

### Database Architecture

```
PostgreSQL Server (localhost:5432)
├── budget_analysis (existing)
│   └── budget_2025 → GAA 2025 data (723,105 records)
│
└── nep (NEW)
    └── budget_2025 → NEP 2025 data (736,593 records) ✅ LOADED
```

---

## NEP Database Details

### Connection Information

```
Host:     localhost
Port:     5432
Database: nep
User:     budget_admin
Password: wuQ5gBYCKkZiOGb61chLcByMu
```

### Database Statistics

| Metric | Value |
|--------|-------|
| Total Records | 736,593 |
**Note:** Summary entries with `prexc_fpap_id = '000000000000000'` have been removed to prevent double-counting.
| Total Budget Amount | ₱6,352,390,000.00 (summary entries removed) |
| Budget Type | NEP (National Expenditure Program) |
| Fiscal Year | 2025 |
| Load Time | 37 seconds |
| Average Insert Rate | 19,865 records/sec |

### Data Distribution by Source File

| Batch File | Records |
|------------|---------|
| nep_2025_batch_0001.json | 100,000 |
| nep_2025_batch_0002.json | 100,000 |
| nep_2025_batch_0003.json | 100,000 |
| nep_2025_batch_0004.json | 100,000 |
| nep_2025_batch_0005.json | 100,000 |
| nep_2025_batch_0006.json | 100,000 |
| nep_2025_batch_0007.json | 100,000 |
| nep_2025_batch_0008.json | 36,593 |
| **Total** | **736,593** |

### Regional Distribution (Top 10)

| Region Code | Records | Notes |
|-------------|---------|-------|
| (NULL) | 177,816 | National/unassigned |
| 13 (NCR) | 72,336 | National Capital Region |
| 04 (CALABARZON) | 44,052 | |
| 05 (Bicol) | 42,850 | |
| 03 (Central Luzon) | 42,283 | |
| 06 (Western Visayas) | 41,636 | |
| 07 (Central Visayas) | 37,615 | |
| 01 (Ilocos) | 33,618 | |
| 11 (Davao) | 32,039 | |
| 08 (Eastern Visayas) | 30,786 | |

---

## Table Schema

### budget_2025 Table Structure

```sql
CREATE TABLE budget_2025 (
    id                      SERIAL PRIMARY KEY,
    record_id               VARCHAR(50) UNIQUE NOT NULL,
    budget_type             VARCHAR(10) DEFAULT 'NEP',
    fiscal_year             VARCHAR(4) DEFAULT '2025',
    amount                  NUMERIC(20,2),
    description             TEXT,
    prexc_fpap_id           VARCHAR(20),
    org_uacs_code           VARCHAR(12),
    region_code             VARCHAR(2),
    funding_uacs_code       VARCHAR(8),
    object_uacs_code        VARCHAR(10),
    funding_conversion_type VARCHAR(20),
    sort_order              BIGINT,
    source_file             TEXT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Indexes Created

- `budget_2025_pkey` - Primary key on `id`
- `budget_2025_record_id_key` - Unique constraint on `record_id`
- `idx_budget_2025_record_id` - Index on record_id
- `idx_budget_2025_budget_type` - Index on budget_type
- `idx_budget_2025_fiscal_year` - Index on fiscal_year
- `idx_budget_2025_amount` - Index on amount
- `idx_budget_2025_prexc_fpap_id` - Index on program/activity
- `idx_budget_2025_org_uacs_code` - Index on organization code
- `idx_budget_2025_region_code` - Index on region code
- `idx_budget_2025_funding_uacs_code` - Index on funding source
- `idx_budget_2025_object_uacs_code` - Index on expense object
- `idx_budget_2025_source_file` - Index on source file
- `idx_budget_2025_composite` - Composite index on (fiscal_year, budget_type, org_uacs_code)

---

## How to Connect

### Using psql

```bash
# Connect to NEP database
PGPASSWORD=wuQ5gBYCKkZiOGb61chLcByMu psql -h localhost -p 5432 -U budget_admin -d nep

# Connect to GAA database (budget_analysis)
PGPASSWORD=wuQ5gBYCKkZiOGb61chLcByMu psql -h localhost -p 5432 -U budget_admin -d budget_analysis
```

### Using Python (psycopg2)

```python
import psycopg2

# NEP database connection
nep_conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='nep',
    user='budget_admin',
    password='wuQ5gBYCKkZiOGb61chLcByMu'
)

# GAA database connection
gaa_conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='budget_analysis',
    user='budget_admin',
    password='wuQ5gBYCKkZiOGb61chLcByMu'
)
```

---

## Sample Queries

### Basic Statistics

```sql
-- Total records and budget amount
SELECT 
    COUNT(*) as total_records,
    SUM(amount) as total_amount,
    AVG(amount) as avg_amount
FROM budget_2025;
```

### By Organization

```sql
-- Top 20 organizations by budget allocation
SELECT 
    org_uacs_code,
    COUNT(*) as records,
    SUM(amount) as total_amount
FROM budget_2025
WHERE org_uacs_code IS NOT NULL
GROUP BY org_uacs_code
ORDER BY total_amount DESC
LIMIT 20;
```

### By Region

```sql
-- Regional budget distribution
SELECT 
    region_code,
    COUNT(*) as records,
    SUM(amount) as total_amount
FROM budget_2025
GROUP BY region_code
ORDER BY total_amount DESC;
```

### By Funding Source

```sql
-- Funding source analysis
SELECT 
    funding_uacs_code,
    COUNT(*) as records,
    SUM(amount) as total_amount
FROM budget_2025
WHERE funding_uacs_code IS NOT NULL
GROUP BY funding_uacs_code
ORDER BY total_amount DESC
LIMIT 20;
```

### By Expense Category

```sql
-- Expense object distribution
SELECT 
    object_uacs_code,
    COUNT(*) as records,
    SUM(amount) as total_amount
FROM budget_2025
WHERE object_uacs_code IS NOT NULL
GROUP BY object_uacs_code
ORDER BY total_amount DESC
LIMIT 20;
```

### Compare NEP vs GAA

```sql
-- Cross-database comparison (requires dblink or manual queries)
-- Run this on NEP database
SELECT 'NEP' as type, COUNT(*) as records, SUM(amount) as total
FROM budget_2025;

-- Run this on budget_analysis database
SELECT 'GAA' as type, COUNT(*) as records, SUM(amount) as total
FROM budget_2025;
```

---

## Data Validation

### Record Count Verification

```sql
-- Verify all records loaded
SELECT source_file, COUNT(*)
FROM budget_2025
GROUP BY source_file
ORDER BY source_file;

-- Expected:
-- nep_2025_batch_0001.json: 100,000
-- nep_2025_batch_0002.json: 100,000
-- nep_2025_batch_0003.json: 100,000
-- nep_2025_batch_0004.json: 100,000
-- nep_2025_batch_0005.json: 100,000
-- nep_2025_batch_0006.json: 100,000
-- nep_2025_batch_0007.json: 100,000
-- nep_2025_batch_0008.json: 36,593
-- Total: 736,593 ✅
```

### Data Quality Checks

```sql
-- Check for null values in key fields
SELECT 
    COUNT(*) FILTER (WHERE record_id IS NULL) as null_record_id,
    COUNT(*) FILTER (WHERE budget_type IS NULL) as null_budget_type,
    COUNT(*) FILTER (WHERE fiscal_year IS NULL) as null_fiscal_year,
    COUNT(*) FILTER (WHERE amount IS NULL) as null_amount,
    COUNT(*) FILTER (WHERE org_uacs_code IS NULL) as null_org_code,
    COUNT(*) FILTER (WHERE region_code IS NULL) as null_region,
    COUNT(*) FILTER (WHERE funding_uacs_code IS NULL) as null_funding,
    COUNT(*) FILTER (WHERE object_uacs_code IS NULL) as null_object
FROM budget_2025;
```

### Duplicate Check

```sql
-- Check for duplicate record_ids (should be 0)
SELECT record_id, COUNT(*)
FROM budget_2025
GROUP BY record_id
HAVING COUNT(*) > 1;
```

---

## Maintenance Commands

### Vacuum and Analyze

```sql
-- Run periodically for performance
VACUUM ANALYZE budget_2025;
```

### Reindex

```sql
-- If indexes become fragmented
REINDEX TABLE budget_2025;
```

### Database Size

```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('nep')) as database_size;

-- Check table size
SELECT pg_size_pretty(pg_total_relation_size('budget_2025')) as table_size;
```

---

## Files Created

### Schema Definition
- `/home/joebert/open-budget-data/create_nep_schema.sql`
  - SQL script to create database schema
  - Can be reused for other fiscal years

### Data Loader
- `/home/joebert/open-budget-data/load_nep_2025.py`
  - Python script to load NEP JSON data
  - Batch processing with progress tracking
  - Error handling and validation

---

## Complete Data Overview

### Both Databases Combined

| Database | Type | Records | Amount (₱) |
|----------|------|---------|------------|
| nep | NEP 2025 | 736,593 | 12,704,780,000.00 |
| budget_analysis | GAA 2025 | 723,105 | 12,652,646,827.71 |
| **Total** | **2025 Budget** | **1,459,698** | **25,357,426,827.71** |

✅ **100% of 2025 budget data is now loaded and accessible**

---

## Next Steps

### For NEP Data Analysis
1. Query the `nep` database for proposed budget analysis
2. Compare NEP vs GAA to see legislative changes
3. Track budget adjustments across departments

### For GAA Data Analysis
1. Query the `budget_analysis` database for enacted budget
2. Analyze actual appropriations by agency/program
3. Monitor budget execution

### Cross-Database Analysis
1. Join NEP and GAA data to see changes
2. Identify programs with significant adjustments
3. Analyze regional budget shifts

### Data Integration
- Consider creating views that span both databases
- Set up regular synchronization with file system data
- Implement automated validation checks

---

## Support

For issues or questions:
1. Check table structure: `\d budget_2025`
2. Verify data: `SELECT COUNT(*) FROM budget_2025`
3. Review logs from loader script
4. Consult original JSON files in `~/open-budget-data/data/budget/2025/items/`

---

**Setup completed successfully on October 7, 2025**  
**All 736,593 NEP 2025 records loaded in 37 seconds** ✅

