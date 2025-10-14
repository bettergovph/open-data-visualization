-- NEP Database Schema Creation
-- Creates tables and indexes for National Expenditure Program data

-- Drop existing tables if they exist
DROP TABLE IF EXISTS budget_2025 CASCADE;
DROP TABLE IF EXISTS budget_2024 CASCADE;
DROP TABLE IF EXISTS budget_2023 CASCADE;
DROP TABLE IF EXISTS budget_2022 CASCADE;
DROP TABLE IF EXISTS budget_2021 CASCADE;
DROP TABLE IF EXISTS budget_2020 CASCADE;

-- Create budget_2025 table for NEP 2025 data
CREATE TABLE budget_2025 (
    id SERIAL PRIMARY KEY,
    
    -- Core budget information
    record_id VARCHAR(50) UNIQUE NOT NULL,  -- From JSON "id" field (e.g., "NEP-2025-0000000001")
    budget_type VARCHAR(10) DEFAULT 'NEP',
    fiscal_year VARCHAR(4) DEFAULT '2025',
    amount NUMERIC(20,2),
    description TEXT,
    prexc_fpap_id VARCHAR(20),
    
    -- UACS codes
    org_uacs_code VARCHAR(12),           -- Organization UACS code
    region_code VARCHAR(2),              -- Region code
    funding_uacs_code VARCHAR(8),        -- Funding source UACS code
    object_uacs_code VARCHAR(10),        -- Object/expense UACS code
    
    -- Additional metadata
    funding_conversion_type VARCHAR(20),
    sort_order BIGINT,
    
    -- Audit fields
    source_file TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX idx_budget_2025_record_id ON budget_2025(record_id);
CREATE INDEX idx_budget_2025_budget_type ON budget_2025(budget_type);
CREATE INDEX idx_budget_2025_fiscal_year ON budget_2025(fiscal_year);
CREATE INDEX idx_budget_2025_amount ON budget_2025(amount);
CREATE INDEX idx_budget_2025_prexc_fpap_id ON budget_2025(prexc_fpap_id);
CREATE INDEX idx_budget_2025_org_uacs_code ON budget_2025(org_uacs_code);
CREATE INDEX idx_budget_2025_region_code ON budget_2025(region_code);
CREATE INDEX idx_budget_2025_funding_uacs_code ON budget_2025(funding_uacs_code);
CREATE INDEX idx_budget_2025_object_uacs_code ON budget_2025(object_uacs_code);
CREATE INDEX idx_budget_2025_source_file ON budget_2025(source_file);

-- Create composite index for common queries
CREATE INDEX idx_budget_2025_composite ON budget_2025(fiscal_year, budget_type, org_uacs_code);

-- Add comments
COMMENT ON TABLE budget_2025 IS 'NEP (National Expenditure Program) 2025 budget data';
COMMENT ON COLUMN budget_2025.record_id IS 'Unique record identifier from source JSON';
COMMENT ON COLUMN budget_2025.org_uacs_code IS 'Organization UACS code (12 digits)';
COMMENT ON COLUMN budget_2025.funding_uacs_code IS 'Funding source UACS code (8 digits)';
COMMENT ON COLUMN budget_2025.object_uacs_code IS 'Expense object UACS code (10 digits)';

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE budget_2025 TO budget_admin;
GRANT ALL PRIVILEGES ON SEQUENCE budget_2025_id_seq TO budget_admin;

-- Display table info
\d budget_2025

