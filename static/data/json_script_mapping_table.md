# JSON Files to Script Mapping Table

This table shows which script generates each JSON file in `static/data/`.

| JSON File | Script | Category | Dependencies |
|-----------|--------|----------|--------------|
| `sec_contractors_database.json` | `sec_scraper/generate_sec_json.py` | SEC Data | PostgreSQL SEC database |
| `contractor_sec_mapping.json` | `sec_scraper/sec_complete_automation.py` | SEC Data | SEC database, Flood data |
| `excluded_flood_contractors_cache.json` | `sec_scraper/generate_contractors_cache.py` | Cache Data | PhilGEPS database |
| `contractors_dashboard_cache.json` | `sec_scraper/generate_contractors_dashboard_cache.py` | Cache Data | SEC database, PhilGEPS database |
| `contractor_stats_cache.json` | API endpoint (generated on-demand) | Cache Data | Database queries |
| `flood_summary.json` | `utils/generate_summary_stats.py` | Summary Data | Flood API endpoint |
| `dime_summary.json` | `utils/generate_summary_stats.py` | Summary Data | DIME API endpoint |
| `budget_summary.json` | `utils/generate_summary_stats.py` | Summary Data | Budget API endpoint |
| `nep_summary.json` | `utils/generate_summary_stats.py` | Summary Data | NEP API endpoint |
| `flood_same_amount_proximity_results.json` | `analysis/flood_same_amount_proximity_analysis.py` | Analysis Data | Flood control data |
| `philippines-regions.json` | Static file (GeoJSON) | Geographic Data | External GeoJSON source |
| `region-mapping.json` | Static file (manual update) | Geographic Data | Manual updates |
| `flood_control_data.json` | API endpoint (generated on-demand) | Flood Data | Database queries |
| `flood_baseline_pattern.json` | API endpoint (generated on-demand) | Flood Data | Database queries |
| `flood_dime_contractor_correlation.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `flood_dime_contractor_correlation_2020.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `flood_dime_contractor_correlation_2021.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `flood_dime_contractor_correlation_2022.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `flood_dime_contractor_correlation_2023.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `flood_dime_contractor_correlation_2024.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `flood_dime_contractor_correlation_2025.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `flood_dime_contractor_correlation_all_years.json` | API endpoint (generated on-demand) | Correlation Data | Flood data, DIME data |
| `nep_2026_infrastructure_categories.json` | API endpoint (generated on-demand) | NEP Data | NEP database |
| `nep_2026_overall_analysis.json` | API endpoint (generated on-demand) | NEP Data | NEP database |
| `nep_2026_red_flag.json` | API endpoint (generated on-demand) | NEP Data | NEP database |
| `dime_stats.json` | API endpoint (generated on-demand) | DIME Data | DIME database |
| `fastest_dime_projects.json` | `sec_scraper/generate_api_cache.py` | DIME Data | DIME database |

## Summary by Script

### Python Scripts (7 scripts)
- `sec_scraper/generate_sec_json.py` → 1 JSON file
- `sec_scraper/sec_complete_automation.py` → 1 JSON file  
- `sec_scraper/generate_contractors_cache.py` → 1 JSON file
- `sec_scraper/generate_contractors_dashboard_cache.py` → 3 JSON files
- `sec_scraper/generate_api_cache.py` → 19 JSON files (API endpoints)
- `utils/generate_summary_stats.py` → 4 JSON files
- `analysis/flood_same_amount_proximity_analysis.py` → 1 JSON file

### Static Files
- 2 JSON files are static/manual files

## Master Script
All JSON files can be regenerated using the master script:
```bash
cd static/data && python3 generate_all_json.py
```

This script runs all the Python generators and provides a comprehensive inventory of all JSON files.
