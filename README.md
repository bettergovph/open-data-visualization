# 🇵🇭 Open Data Visualization Platform

A comprehensive platform for visualizing and analyzing Philippine government open data, including budget, infrastructure, flood control, and public works projects.

## 📋 Overview

This project provides a web-based visualization platform and analysis tools for various Philippine government datasets, including:

- **Budget Data**: National Expenditure Program (NEP), General Appropriations Act (GAB), and budget amendments
- **Infrastructure Projects**: DPWH projects, flood control initiatives, and public works
- **Contractor Data**: PHILGEPS contracts and SEC registration information
- **Political Relationships**: Family connections and political dynasty analysis
- **Geographic Data**: City, municipality, and barangay mappings

## 🚀 Quick Start

### Prerequisites

- Python 3.7+
- PostgreSQL (for budget and infrastructure data)
- Node.js (for frontend assets, if applicable)
- Sufficient disk space for data storage

### Installation

1. Clone this repository
2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables (copy `visualization.env` and configure):
```bash
cp visualization.env .env
# Edit .env with your database credentials
```

4. Run the API server:
```bash
python visualization.py
```

The API will be available at `http://localhost:8000` (or as configured).

## 📁 Project Structure

```
open-data-visualization/
├── visualization.py              # Main FastAPI application
├── *_client.py                   # Database clients (budget, NEP, flood, etc.)
├── routes/                       # Additional API routes
├── scripts/                      # Utility and analysis scripts
├── analysis/                     # Data analysis notebooks and scripts
├── sources/                      # Data source parsers and converters
├── sec_scraper/                  # SEC data scraper
├── family_analysis/              # Political relationship analysis
├── static/                       # Frontend assets (CSS, JS, images, data)
├── templates/                    # HTML templates
├── data/                         # Processed data files (Parquet, DuckDB)
├── database/                     # Database files and exports
├── deployment/                   # Deployment scripts and configs
└── utils/                        # Shared utilities
```

## 🔧 Main Components

### API Server (`visualization.py`)

The main FastAPI application providing REST endpoints for:
- Budget data queries and analysis
- Infrastructure project searches
- Flood control project data
- Integrated project data
- Geographic and administrative data

### Database Clients

- `budget_client.py` - Budget database queries
- `budget_postgres_client.py` - PostgreSQL budget client
- `nep_postgres_client.py` - National Expenditure Program client
- `flood_db_client.py` - Flood control projects client
- `relationship_sources_client.py` - Political relationship data client
- `infrawatch_postgres_client.py` - Infrastructure watch client
- `dime_client.py` - DIME projects client

### Scripts and Analysis

- `scripts/` - Utility scripts for data processing, inspection, and maintenance
- `analysis/` - Analysis notebooks and data exploration scripts
- `sources/` - Data source parsers (PHILGEPS, DO 172, etc.)

## 📊 Data Sources

The platform integrates data from multiple sources:

- **PHILGEPS** - Government procurement contracts
- **DPWH** - Department of Public Works and Highways projects
- **SEC** - Securities and Exchange Commission contractor registrations
- **Budget Documents** - GAB, NEP, and budget amendments
- **Flood Control Projects** - Infrastructure flood management data

## 🎯 Features

- **Interactive Visualizations**: Web-based charts and maps
- **Data Browser**: Search and filter across multiple datasets
- **API Endpoints**: RESTful API for programmatic access
- **Data Integration**: Combines multiple government data sources
- **Geographic Analysis**: Location-based project mapping
- **Contractor Analysis**: SEC and PHILGEPS contractor data integration

## 🔍 Key Documentation

- `CLASSIFICATION_DICTIONARIES.md` - Location classification system
- `CLASSIFICATION_WALKTHROUGH.md` - Classification process guide
- `INVESTIGATION_REPORT.md` - Data investigation findings
- `DAVAO_CITY_FIX_SUMMARY.md` - Data fixes documentation
- `docs/gis_integration_guide.md` - Guide for integrating DPWH GIS data and extracting engineering districts
- `docs/location_data_integration.md` - Plan for creating a unified location database with district information

## 🛠️ Development

### Running the API

```bash
python visualization.py
```

### Running Analysis Scripts

Analysis and utility scripts are located in:
- `scripts/` - General utility scripts
- `analysis/` - Data analysis scripts

### Data Processing

Data processing scripts are in:
- `sources/` - Source data parsers
- `scripts/` - Data transformation utilities

## 📝 Notes

- The platform requires PostgreSQL databases for budget and infrastructure data
- Large datasets are stored in Parquet format for efficient querying
- Some features require MeiliSearch for full-text search capabilities
- Environment variables must be configured for database connections

## 🤝 Contributing

Contributions are welcome! Please ensure:
- Code follows existing style conventions
- New features include appropriate documentation
- Database migrations are handled properly
- Tests are added for new functionality

## 📄 License

This project is for educational and research purposes. Please respect data source terms of service and usage policies.

---

**Last Updated**: 2025
