# SEC Scraper

Automated system for scraping and correlating contractor SEC registration data.

## Directory Structure

```
sec_scraper/
├── sec_search.ahk              # AHK automation script (Windows)
├── sec_contractor_parser.py    # Python parser for SEC results
├── generate_sec_json.py        # Database → JSON generator
├── sec_results/                # Raw SEC search results (text files)
│   ├── JB_FELIPE_CONSTRUCTION.txt
│   ├── ST_TIMOTHY_CONSTRUCTION_CORPORATION.txt
│   └── ... (100+ files)
└── README.md                   # This file
```

## Quick Start

### 1. Run AHK Script (Windows)

```bash
# Double-click or run:
sec_search.ahk
```

Processes 100 contractors, saves results to `sec_results/`

### 2. Parse Results

```bash
cd /home/joebert/open-data-visualization
python3 sec_scraper/sec_contractor_parser.py
```

Parses text files, updates PostgreSQL database.

### 3. Generate JSON

```bash
python3 sec_scraper/generate_sec_json.py
```

Exports database to `static/sec_contractors_database.json` for frontend.

## Components

### sec_search.ahk

**Purpose:** Automate SEC website scraping

**Features:**
- Processes 100 contractors per run
- Skips existing results
- Uses Escape + Shift+Tab for efficient navigation
- Minimal logic - just gets raw data

**Requirements:** Windows + AutoHotkey

### sec_contractor_parser.py

**Purpose:** Parse SEC results and update database

**Features:**
- Handles encoding issues (ISO-8859-1, UTF-8)
- Extracts company details via regex
- Updates `contractors` table
- JV-aware correlation with flood projects
- Strict fuzzy matching (≥90% for strict, <90% for fuzzy)

**Requirements:** Python 3, asyncpg, aiohttp, chardet

### generate_sec_json.py

**Purpose:** Generate static JSON from database

**Features:**
- Single source of truth: PostgreSQL
- Maintains frontend compatibility
- Auto-generates summary statistics

**Requirements:** Python 3, asyncpg

## Database Schema

### contractors

```sql
CREATE TABLE contractors (
    id SERIAL PRIMARY KEY,
    contractor_name TEXT NOT NULL,
    sec_number VARCHAR(255),
    date_registered DATE,
    status VARCHAR(50),
    address TEXT,
    secondary_licenses TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    project_count INTEGER DEFAULT 0,
    UNIQUE(contractor_name, sec_number)
);
```

### project_contractors

```sql
CREATE TABLE project_contractors (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,
    contractor_name TEXT NOT NULL,
    contractor_role VARCHAR(50), -- 'main', 'jv_partner1', 'jv_partner2'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, contractor_name, contractor_role)
);
```

## Current Status

- **15 contractors** with SEC data
- **100 contractors** ready to process in AHK script
- **2,491 unique contractors** identified from flood projects
- **10,627 project-contractor relationships** (JV-aware)

See main [SEC.md](../SEC.md) for complete documentation.

