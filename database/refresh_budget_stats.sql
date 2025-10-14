-- Refresh Budget Statistics Materialized Views
-- Run this after updating budget data to refresh the cached statistics

-- Refresh the statistics summary view
REFRESH MATERIALIZED VIEW budget_statistics_summary;

-- Refresh the overview stats view
REFRESH MATERIALIZED VIEW budget_overview_stats;

-- Verify the refresh
SELECT 'budget_statistics_summary' as view_name, last_updated
FROM budget_statistics_summary 
WHERE scope = 'all_years'
UNION ALL
SELECT 'budget_overview_stats' as view_name, last_updated
FROM budget_overview_stats;

-- Display overview stats
SELECT 
    stat_type,
    total_items,
    total_value,
    top_department,
    unique_agencies,
    unique_departments,
    last_updated
FROM budget_overview_stats;

-- Example usage:
-- PGPASSWORD=wuQ5gBYCKkZiOGb61chLcByMu psql -h localhost -p 5432 -U budget_admin -d budget_analysis -f refresh_budget_stats.sql

