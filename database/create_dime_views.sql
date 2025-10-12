-- DIME Database PostgreSQL Views
-- Create optimized views for frequently accessed statistics and analytics
-- Fixed for actual table structure: cost (not project_cost), implementing_offices (array), source_of_funds

-- View 1: DIME Basic Statistics (for main statistics card)
CREATE OR REPLACE VIEW dime_basic_stats AS
SELECT 
    COUNT(*) as total_projects,
    SUM(cost) as total_budget,
    AVG(cost) as avg_cost,
    COUNT(DISTINCT region) as regions_covered,
    SUM(CASE WHEN status IN ('On-going', 'Ongoing') THEN 1 ELSE 0 END) as active_projects
FROM projects;

-- View 2: DIME Status Distribution
CREATE OR REPLACE VIEW dime_status_distribution AS
SELECT 
    status,
    COUNT(*) as count,
    SUM(cost) as total_budget,
    ROUND((COUNT(*)::numeric / (SELECT COUNT(*) FROM projects)::numeric * 100), 2) as percentage
FROM projects
WHERE status IS NOT NULL
GROUP BY status
ORDER BY count DESC;

-- View 3: DIME Budget by Region (Top 10)
CREATE OR REPLACE VIEW dime_budget_by_region AS
SELECT 
    region,
    SUM(cost) as total_budget,
    COUNT(*) as project_count,
    AVG(cost) as avg_budget
FROM projects
WHERE region IS NOT NULL
GROUP BY region
ORDER BY total_budget DESC
LIMIT 10;

-- View 4: DIME Top Implementing Offices (Top 10)
CREATE OR REPLACE VIEW dime_top_offices AS
SELECT 
    implementing_offices[1]::text as office,
    SUM(cost) as total_budget,
    COUNT(*) as project_count,
    AVG(cost) as avg_budget
FROM projects
WHERE implementing_offices IS NOT NULL AND array_length(implementing_offices, 1) > 0
GROUP BY implementing_offices[1]
ORDER BY total_budget DESC
LIMIT 10;

-- View 5: DIME Project Types (Top 6)
CREATE OR REPLACE VIEW dime_project_types AS
SELECT 
    project_type as type,
    COUNT(*) as count,
    SUM(cost) as total_budget,
    ROUND((COUNT(*)::numeric / (SELECT COUNT(*) FROM projects)::numeric * 100), 2) as percentage
FROM projects
WHERE project_type IS NOT NULL
GROUP BY project_type
ORDER BY count DESC
LIMIT 6;

-- View 6: DIME Most Expensive Projects (Top 5)
CREATE OR REPLACE VIEW dime_expensive_projects AS
SELECT 
    project_name as name,
    cost,
    region,
    status,
    implementing_offices[1]::text as implementing_office
FROM projects
WHERE cost IS NOT NULL
ORDER BY cost DESC
LIMIT 5;

-- View 7: DIME Projects by Start Year
CREATE OR REPLACE VIEW dime_projects_by_year AS
SELECT 
    EXTRACT(YEAR FROM date_started) as year,
    COUNT(*) as count,
    SUM(cost) as total_budget
FROM projects
WHERE date_started IS NOT NULL
GROUP BY year
ORDER BY year;

-- View 8: DIME Source of Funds Distribution (Top 5)
CREATE OR REPLACE VIEW dime_source_of_funds AS
SELECT 
    source_of_funds as source,
    SUM(cost) as total_budget,
    COUNT(*) as project_count,
    ROUND((SUM(cost)::numeric / (SELECT SUM(cost) FROM projects WHERE cost IS NOT NULL)::numeric * 100), 2) as percentage
FROM projects
WHERE source_of_funds IS NOT NULL
GROUP BY source_of_funds
ORDER BY total_budget DESC
LIMIT 5;

-- View 9: DIME Progress Distribution
-- Note: physical_progress column doesn't exist, using status as proxy
CREATE OR REPLACE VIEW dime_progress_distribution AS
SELECT 
    CASE 
        WHEN status = 'Completed' THEN '75-100%'
        WHEN status IN ('Ongoing', 'On-going') THEN '50-75%'
        WHEN status = 'Not Yet Started' THEN '0-25%'
        ELSE 'Unknown'
    END as range,
    COUNT(*) as count,
    ROUND((COUNT(*)::numeric / (SELECT COUNT(*) FROM projects)::numeric * 100), 2) as percentage
FROM projects
GROUP BY range
ORDER BY range;

-- View 10: DIME Barangay Aggregates by Total Amount (Top 100)
CREATE OR REPLACE VIEW dime_barangay_aggregates AS
SELECT 
    barangay,
    region,
    province,
    city,
    COUNT(*) as project_count,
    SUM(cost) as total_amount,
    AVG(cost) as avg_amount,
    MIN(cost) as min_amount,
    MAX(cost) as max_amount,
    ROUND((SUM(cost)::numeric / (SELECT SUM(cost) FROM projects WHERE cost IS NOT NULL)::numeric * 100), 2) as percentage_of_total
FROM projects
WHERE barangay IS NOT NULL 
    AND barangay != '' 
    AND barangay != 'N/A'
    AND cost IS NOT NULL
GROUP BY barangay, region, province, city
ORDER BY total_amount DESC
LIMIT 100;

-- View 11: DIME Barangay Aggregates by Project Count (Top 100)
CREATE OR REPLACE VIEW dime_barangay_aggregates_by_count AS
SELECT 
    barangay,
    region,
    province,
    city,
    COUNT(*) as project_count,
    SUM(cost) as total_amount,
    AVG(cost) as avg_amount,
    MIN(cost) as min_amount,
    MAX(cost) as max_amount,
    ROUND((SUM(cost)::numeric / (SELECT SUM(cost) FROM projects WHERE cost IS NOT NULL)::numeric * 100), 2) as percentage_of_total
FROM projects
WHERE barangay IS NOT NULL 
    AND barangay != '' 
    AND barangay != 'N/A'
    AND cost IS NOT NULL
GROUP BY barangay, region, province, city
ORDER BY project_count DESC, total_amount DESC
LIMIT 100;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_region ON projects(region);
CREATE INDEX IF NOT EXISTS idx_projects_implementing_offices ON projects USING GIN(implementing_offices);
CREATE INDEX IF NOT EXISTS idx_projects_project_type ON projects(project_type);
CREATE INDEX IF NOT EXISTS idx_projects_date_started ON projects(date_started);
CREATE INDEX IF NOT EXISTS idx_projects_source_of_funds ON projects(source_of_funds);
CREATE INDEX IF NOT EXISTS idx_projects_cost ON projects(cost DESC);
CREATE INDEX IF NOT EXISTS idx_projects_barangay ON projects(barangay);

-- Grant permissions
GRANT SELECT ON dime_basic_stats TO PUBLIC;
GRANT SELECT ON dime_status_distribution TO PUBLIC;
GRANT SELECT ON dime_budget_by_region TO PUBLIC;
GRANT SELECT ON dime_top_offices TO PUBLIC;
GRANT SELECT ON dime_project_types TO PUBLIC;
GRANT SELECT ON dime_expensive_projects TO PUBLIC;
GRANT SELECT ON dime_projects_by_year TO PUBLIC;
GRANT SELECT ON dime_source_of_funds TO PUBLIC;
GRANT SELECT ON dime_progress_distribution TO PUBLIC;
GRANT SELECT ON dime_barangay_aggregates TO PUBLIC;
GRANT SELECT ON dime_barangay_aggregates_by_count TO PUBLIC;

