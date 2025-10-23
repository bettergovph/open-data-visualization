
# JSON Files to MongoDB Migration Report

## Summary
Total JSON files found: 29

## File Categories

### Flood Data
Files: 17
- data/flood_dime_contractor_correlation.json
- data/flood_dime_contractor_correlation_2024.json
- data/flood_control_data_working.json
- data/flood_dime_contractor_correlation_2020.json
- data/flood_control_data_backup.json
- data/flood_baseline_pattern.json
- data/flood_dime_contractor_correlation_2025.json
- data/flood_dime_contractor_correlation_2021.json
- data/flood_dime_contractor_correlation_all_years.json
- data/fastest_dime_projects.json
- data/flood_dime_contractor_correlation_2023.json
- data/flood_control_data.json
- data/excluded_flood_contractors_cache.json
- data/flood_summary.json
- data/flood_same_amount_proximity_results.json
- data/flood_dime_contractor_correlation_2022.json
- data/flood_control_data_with_jv.json

### Budget Data
Files: 1
- data/budget_summary.json

### Nep Data
Files: 4
- data/nep_2026_overall_analysis.json
- data/nep_summary.json
- data/nep_2026_red_flag.json
- data/nep_2026_infrastructure_categories.json

### Sec Data
Files: 2
- contractor_sec_mapping.json
- sec_contractors_database.json

### Geographic Data
Files: 2
- data/region-mapping.json
- data/philippines-regions.json

### Correlation Data
Files: 0

### Cache Data
Files: 2
- data/contractor_stats_cache.json
- data/dime_stats.json

### Summary Data
Files: 1
- data/dime_summary.json


## MongoDB Collections Plan

### flood_data
Description: Flood control projects and related data
Primary Key: project_id
Indexes: region, year, contractor, amount
Files: 17

### budget_data
Description: Budget analysis and financial data
Primary Key: budget_id
Indexes: year, department, region, category
Files: 1

### nep_data
Description: National Expenditure Program data
Primary Key: nep_id
Indexes: year, category, department, region
Files: 4

### sec_data
Description: SEC contractor and company data
Primary Key: sec_number
Indexes: contractor_name, status, registration_date
Files: 2

### geographic_data
Description: Geographic and regional data
Primary Key: region_id
Indexes: region_name, province, coordinates
Files: 2

### correlation_data
Description: Data correlation and analysis results
Primary Key: correlation_id
Indexes: year, contractor, correlation_type
Files: 0

### cache_data
Description: Cached data for performance optimization
Primary Key: cache_key
Indexes: cache_type, generated_at, expires_at
Files: 2

### summary_data
Description: Summary and aggregated data
Primary Key: summary_id
Indexes: data_type, year, region
Files: 1


## Migration Steps

1. Create MongoDB collections with proper schemas
2. Import JSON files into respective collections
3. Create indexes for performance optimization
4. Update API endpoints to read from MongoDB
5. Implement caching layer for frequently accessed data
6. Test all endpoints and visualizations
7. Deploy and monitor performance
8. Keep JSON files as backup during transition
