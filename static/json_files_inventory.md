# JSON Files Inventory for MongoDB Migration

## Current JSON Files in static/ Directory

### Root static/ directory:
- `contractor_sec_mapping.json` - SEC contractor mapping data
- `excluded_flood_contractors_cache.json` - Cached excluded flood contractors
- `sec_contractors_database.json` - SEC contractors database

### static/data/ directory:
- `budget_summary.json` - Budget analysis summary
- `contractor_stats_cache.json` - Contractor statistics cache
- `dime_stats.json` - DIME database statistics
- `dime_summary.json` - DIME summary data
- `fastest_dime_projects.json` - Fastest DIME projects
- `flood_baseline_pattern.json` - Flood baseline patterns
- `flood_control_data_backup.json` - Backup flood control data
- `flood_control_data_with_jv.json` - Flood control data with joint ventures
- `flood_control_data_working.json` - Working flood control data
- `flood_control_data.json` - Main flood control data
- `flood_dime_contractor_correlation_*.json` - Year-specific correlations (2020-2025)
- `flood_dime_contractor_correlation_all_years.json` - All years correlation
- `flood_dime_contractor_correlation.json` - Main correlation data
- `flood_same_amount_proximity_results.json` - Proximity analysis results
- `flood_summary.json` - Flood summary data
- `nep_2026_infrastructure_categories.json` - NEP 2026 categories
- `nep_2026_overall_analysis.json` - NEP 2026 analysis
- `nep_2026_red_flag.json` - NEP 2026 red flags
- `nep_summary.json` - NEP summary
- `philippines-regions.json` - Philippines regions GeoJSON
- `region-mapping.json` - Region mapping data

## Files Used by /flood Page:
1. `/static/data/region-mapping.json` - Region mapping
2. `/static/data/flood_control_data.json` - Main flood data
3. `/static/data/philippines-regions.json` - GeoJSON regions
4. `/static/data/contractor_stats_cache.json` - Contractor stats
5. `/static/data/flood_summary.json` - Flood summary
6. `/static/data/flood_same_amount_proximity_results.json` - Proximity results
7. `/static/sec_contractors_database.json` - SEC contractors
8. `/static/contractor_sec_mapping.json` - SEC mapping

## MongoDB Migration Strategy:
1. **Group by category**: Flood, Budget, NEP, SEC, Geographic
2. **Consolidate related files**: Merge similar datasets
3. **Create collections**: 
   - `flood_data` - All flood-related JSON files
   - `budget_data` - All budget-related JSON files
   - `nep_data` - All NEP-related JSON files
   - `sec_data` - All SEC-related JSON files
   - `geographic_data` - All geographic JSON files
4. **Maintain file structure**: Keep original JSON files as backup
5. **Update API endpoints**: Modify to read from MongoDB instead of static files
