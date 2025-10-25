# Scripts Directory

This directory contains all processing and utility scripts, organized by function.

## Directory Structure

### `processing/`
Scripts for data processing and analysis:
- `find_family_for_verification.py` - Find families for verification
- `find_fresh_family.py` - Find fresh family data
- `get_top5_dynasty_names.py` - Get top 5 dynasty names

### `analysis/`
Scripts for data analysis and computation:
- `compute_cri_analysis.py` - Compute CRI (Corruption Risk Index) analysis

### `database/`
Scripts for database operations and setup:
- `create_dynasty_tables.py` - Create dynasty database tables
- `expand_dynasty_database.py` - Expand dynasty database schema
- `import_organization_data.py` - Import organization data

### Root Scripts
General utility and enhancement scripts:
- `endpoint_enhancements.py` - API endpoint enhancements
- `new_endpoints_to_add.py` - New endpoints to add

## Usage

All scripts should be run from the project root directory:

```bash
# Database operations
python3 scripts/database/create_dynasty_tables.py

# Data processing
python3 scripts/processing/find_family_for_verification.py

# Analysis
python3 scripts/analysis/compute_cri_analysis.py
```

## Organization Principles

- **Root directory**: Only contains API clients, main application files, and configuration
- **Scripts directory**: All processing, analysis, and utility scripts
- **Family analysis**: Dynasty-specific processing in `family_analysis/`
- **Database scripts**: Database setup and maintenance in `scripts/database/`
- **Analysis scripts**: Data analysis and computation in `scripts/analysis/`
- **Processing scripts**: Data processing and transformation in `scripts/processing/`
