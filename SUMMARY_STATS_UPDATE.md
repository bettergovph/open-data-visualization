# Summary Statistics Update Documentation

## Overview

Summary statistics are stored in JSON files under `static/data/` to avoid hardcoding values in frontend templates and to optimize page load performance.

## Current Summary Files

- `static/data/budget_summary.json` - Budget analysis statistics
- `static/data/nep_summary.json` - NEP statistics  
- `static/data/dime_summary.json` - DIME infrastructure statistics
- `static/data/flood_summary.json` - Flood control statistics

## Manual Update

To manually update summary statistics:

```bash
cd /home/joebert/open-data-visualization
python3 utils/generate_summary_stats.py
```

Or using the convenience script:

```bash
./deployment/update_summary_stats.sh
```

## What Gets Updated

The script queries the following databases and generates summary stats:

1. **Budget Analysis** (`budget_analysis` database)
   - Total items across years 2020-2025
   - Data source information
   - Date range

2. **NEP** (`nep` database)
   - Total items across years 2020-2026
   - Data source information
   - Date range

3. **DIME** (`dime` database)
   - Total project count from `projects` table
   - Data source information
   - Date range

4. **Flood Control** (MeiliSearch)
   - Total project count from MeiliSearch index `bettergov_flood_control`
   - Data source information
   - Date range

## Regeneration Strategy

**Decision: Manual regeneration only**

Since data imports happen infrequently (weekly, monthly, or even yearly), automatic periodic updates are not necessary. Summary statistics should be regenerated manually when:

1. New data is imported into any database
2. Significant changes are made to existing data
3. Footer statistics appear outdated

**No automatic scheduling is implemented.** This avoids unnecessary resource usage for data that rarely changes.

## When to Update

Summary statistics should be updated:

- After importing new data into any database
- After significant database changes
- Daily (via automated task)
- After deployment (optional)
- On demand when discrepancies are noticed

## Dependencies

The `generate_summary_stats.py` script requires:

- `asyncpg` - for PostgreSQL queries
- `aiohttp` - for MeiliSearch API calls
- Access to all databases (budget_analysis, nep, dime)
- Access to MeiliSearch on `MEILI_HTTP_ADDR` (127.0.0.1:7700)
- Environment variables from `.env` file

## Current Status

- ✅ Script created: `utils/generate_summary_stats.py`
- ✅ Convenience script: `deployment/update_summary_stats.sh`
- ✅ Templates updated to load from JSON files
- ✅ Fallback values in templates if JSON load fails
- ❌ Automatic regeneration: **NOT IMPLEMENTED** - manual updates only, run after data imports

## Notes

- JSON files are committed to git repository
- Changes to JSON files should trigger deployment to update production
- MeiliSearch must be accessible at `MEILI_HTTP_ADDR` for flood stats generation
- Database credentials must be in `.env` file

