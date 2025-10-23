# Sync Scripts Documentation

## Overview
These scripts are responsible for syncing contractor data from various sources to create the unified contractor database used for the Venn diagram on the `/contractors` page.

## Critical Sync Scripts (DO NOT MISS THESE)

### 1. Individual Source Sync Scripts
- **`sync_flood_contractors.py`** - Syncs contractors from MeiliSearch (Flood Control data)
- **`sync_dime_contractors.py`** - Syncs contractors from DIME database  
- **`sync_philgeps_contractors.py`** - Syncs contractors from PhilGEPS contracts

### 2. Master Sync Script
- **`sync_all_sources_to_sec.py`** - **CRITICAL**: This is the main script that creates the Venn diagram data by syncing all sources to the SEC database and setting the `has_flood`, `has_dime`, `has_philgeps` boolean columns.

## Execution Order
1. Run individual sync scripts to populate PhilGEPS contractors table:
   ```bash
   python3 sec_scraper/sync_flood_contractors.py
   python3 sec_scraper/sync_dime_contractors.py  
   python3 sec_scraper/sync_philgeps_contractors.py
   ```

2. Run the master sync script to create Venn diagram data:
   ```bash
   python3 sec_scraper/sync_all_sources_to_sec.py
   ```

## What Each Script Does

### Individual Sync Scripts
- Extract contractors from their respective sources (MeiliSearch, DIME, PhilGEPS)
- Clean and normalize contractor names
- Split joint ventures into individual contractors
- Use fuzzy matching to avoid duplicates
- Insert new contractors into `philgeps.contractors` table
- Update existing contractors with source information

### Master Sync Script (`sync_all_sources_to_sec.py`)
- Fetches contractors from all raw sources with proper cleaning
- Uses strict fuzzy matching (90% threshold) to match contractors across sources
- Updates SEC database contractors with boolean flags:
  - `has_flood` - contractor appears in Flood Control data
  - `has_dime` - contractor appears in DIME database
  - `has_philgeps` - contractor appears in PhilGEPS contracts
- Generates final Venn diagram statistics

## Performance Optimization
- Current scripts use 5 threads for fuzzy matching
- **TODO**: Update to use 20 threads for better performance
- Consider parallel processing for large datasets

## Data Flow
```
Raw Sources → Individual Sync Scripts → PhilGEPS.contractors → Master Sync → SEC.contractors (with Venn flags)
```

## Important Notes
- **NEVER delete data** without understanding how to recreate it
- Always check existing scripts before creating new ones
- The Venn diagram depends on the boolean flags set by `sync_all_sources_to_sec.py`
- If Venn diagram shows zeros, run the master sync script
- These scripts are essential for the `/contractors` page functionality

## Troubleshooting
- If Venn diagram shows all zeros: Run `sync_all_sources_to_sec.py`
- If contractor counts are wrong: Run individual sync scripts first, then master sync
- If performance is slow: Consider increasing thread count to 20
