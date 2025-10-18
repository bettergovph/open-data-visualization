# SEC Contractor Correlation System

## Overview

This system correlates government contractors with their Securities and Exchange Commission (SEC) registration data. It provides transparency by verifying contractor legitimacy and registration status for contractors involved in flood control, infrastructure, and other government projects.

## Architecture

### Data Flow

```
SEC Website → AHK Automation → Raw Text Files → Python Parser → PostgreSQL Database → JSON Export → Frontend Display
```

### Components

1. **AHK Automation Script** (`database/sec_search.ahk`)
   - Automates web scraping of SEC website
   - Processes 100 contractors per run
   - Saves raw HTML/text results to `database/sec_results/`

2. **Python Parser** (`sec_contractor_parser.py`)
   - Parses raw SEC result files
   - Extracts structured contractor data
   - Updates PostgreSQL `contractors` table
   - Handles JV-aware correlation with flood projects

3. **JSON Generator** (`generate_sec_json.py`)
   - Reads from PostgreSQL database
   - Generates `static/sec_contractors_database.json`
   - Ensures unified SEC data source

4. **PostgreSQL Database** (`philgeps` database)
   - Single source of truth for SEC data
   - Tables: `contractors`, `project_contractors`

## Database Schema

### `contractors` Table

Stores SEC registration data for contractors.

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

CREATE INDEX idx_contractors_name ON contractors(contractor_name);
CREATE INDEX idx_contractors_sec_number ON contractors(sec_number);
```

### `project_contractors` Table

Junction table handling joint venture projects.

```sql
CREATE TABLE project_contractors (
    id SERIAL PRIMARY KEY,
    project_id TEXT NOT NULL,  -- GlobalID from flood data
    contractor_name TEXT NOT NULL,
    contractor_role VARCHAR(50), -- 'main', 'jv_partner1', 'jv_partner2'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, contractor_name, contractor_role)
);

CREATE INDEX idx_project_contractors_project_id ON project_contractors(project_id);
CREATE INDEX idx_project_contractors_contractor ON project_contractors(contractor_name);
```

### `contractor_projects` View

Simplified view for contractor-project correlation.

```sql
CREATE VIEW contractor_projects AS
SELECT 
    c.contractor_name,
    c.sec_number,
    c.status as sec_status,
    pc.project_id,
    pc.contractor_role,
    COUNT(*) OVER (PARTITION BY c.contractor_name) as total_projects
FROM contractors c
LEFT JOIN project_contractors pc ON c.contractor_name = pc.contractor_name;
```

## Joint Venture (JV) Support

### JV Data Structure

The system properly handles joint venture projects where multiple contractors work together:

**MeiliSearch Flood Data:**
```json
{
  "GlobalID": "a3d64d20-0d8d-4b61-abdd-38a3bd840c77",
  "Contractor": "OCTAGON CONCRETE SOLUTIONS INC. / MAC BUILDERS CORP.",
  "is_joint_venture": true,
  "jv_partner1": "OCTAGON CONCRETE SOLUTIONS INC.",
  "jv_partner2": "MAC BUILDERS CORP."
}
```

**Database Representation:**
```
project_id: a3d64d20-0d8d-4b61-abdd-38a3bd840c77
├── Main: "OCTAGON CONCRETE SOLUTIONS INC. / MAC BUILDERS CORP."
├── JV Partner 1: "OCTAGON CONCRETE SOLUTIONS INC."
└── JV Partner 2: "MAC BUILDERS CORP."
```

### JV Statistics

- **9,855 main contractors** from flood projects
- **386 JV partner 1 entries**
- **386 JV partner 2 entries**
- **Total: 10,627 project-contractor relationships**
- **2,491 unique contractors** across all projects

## Contractor Name Normalization

### Cleaning Strategy

To improve matching accuracy, contractor names are cleaned before searching SEC:

**Original → Cleaned:**
- `J.B. FELIPE CONSTRUCTION` → `JB FELIPE CONSTRUCTION`
- `ALPHA & OMEGA GEN. CONTRACTOR` → `ALPHA OMEGA GEN CONTRACTOR`
- `E. E. MADAYAG CONSTRUCTION` → `E E MADAYAG CONSTRUCTION`
- `JLP CONSTRUCTION & SUPPLY` → `JLP CONSTRUCTION SUPPLY`

**Removed Characters:**
- Periods (`.`)
- Ampersands (`&`)
- Apostrophes (`'`)
- Slashes (`/`)
- Parentheses (`()`)

### Fuzzy Matching

The Python parser uses multi-strategy fuzzy matching to correlate contractors:

**Strategy 1: Exact Match** (100% similarity)
- Normalized name comparison

**Strategy 2: High Similarity** (>90%)
- SequenceMatcher ratio > 0.9
- Considered "STRICT" match

**Strategy 3: Substring Match** (>80% + word overlap)
- At least 2 common words
- Similarity > 0.8

**Current Results:**
- **67 total matches** found
- **5 strict matches** (≥90% similarity)
- **62 fuzzy matches** (<90% similarity)
- **2.7% match rate** (67 out of 2,491 contractors)

## AHK Automation Script

### Purpose

Automates scraping of SEC website to gather contractor registration data.

### Features

- Processes 100 contractors per run
- Skips contractors with existing results
- Uses optimized navigation (Escape + Shift+Tab pattern)
- Minimal error checking (delegates to Python parser)
- Saves raw clipboard data to text files

### Available Scripts

**1. `sec_search.ahk`** - Main production script
- Processes 100 contractors
- Optimized for speed and reliability
- Uses cleaned contractor names (removes `.`, `&`, `'`, etc.)

**2. `sec_search_single.ahk`** - Single contractor test script
- Tests one contractor at a time
- Original working version for validation

**3. Alternative Scripts** (legacy):
- `sec_complete_automation.py` - Python-based automation
- `sec_search_alternative.py` - Alternative Python approach
- `sec_search_automation.py` - Earlier automation attempt
- `sec_search_windows.py` - Windows-specific Python version

### Usage

```bash
# Run main script on Windows with AutoHotkey installed
cd sec_scraper
# Double-click sec_search.ahk
```

### Performance Optimizations

**Navigation Efficiency:**
- **Initial navigation:** Click + 9 tabs to search field (once)
- **Per contractor:** Escape + Shift+Tab to reset to search field
- **68% faster** than re-navigating each time

**Timing Optimizations:**
| Operation | Time | Notes |
|-----------|------|-------|
| Tab delays | 50ms | Minimal but reliable |
| Page load | 2s | Reduced from 3s |
| Search wait | 8s | Allows results to load |
| Processing | 100ms | Quick copy operations |
| **Per contractor** | **~12s** | Down from 14.7s |

**For 100 contractors:** ~20 minutes (vs 24.5 minutes unoptimized)

### Contractor Prioritization

Contractors are prioritized by project count (high-volume contractors first):

1. J.B. FELIPE CONSTRUCTION (450 projects)
2. ST. TIMOTHY CONSTRUCTION CORPORATION (427 projects)
3. E. E. MADAYAG CONSTRUCTION (389 projects)
4. QM BUILDERS (358 projects)
5. ALPHA & OMEGA GEN. CONTRACTOR & DEVELOPMENT CORP. (355 projects)
... (up to 100 contractors)

## Python Parser

### Purpose

Parses raw SEC result files and updates the PostgreSQL database.

### Features

- Handles encoding issues (ISO-8859-1, UTF-8)
- Extracts structured SEC data using regex
- Updates `contractors` table with upsert logic
- Loads flood projects from MeiliSearch
- Populates `project_contractors` with JV data
- Performs JV-aware fuzzy matching correlation

### Usage

```bash
python3 sec_contractor_parser.py
```

### Parsing Logic

Extracts company details using regex pattern:

```python
company_pattern = r'COMPANY DETAILS\nCompany Name\n(.*?)\n\nSEC Number\n(.*?)\n\nDate Registered\n(.*?)\n\nStatus\n(.*?)\n\nAddress\n(.*?)\n\nSECONDARY LICENSE DETAILS'
```

### Output

```
🚀 Starting JV-aware SEC contractor data processing...
📁 Found 33 SEC result files
📊 Total companies parsed: 38
✅ Updated: 15 contractors
📋 Found 2491 unique contractors in JV data
📋 Found 15 contractors in SEC contractors table
🔗 67 matches found
📊 JV-Aware Correlation Results:
   • Total matches: 67
   • Strict matches (≥90%): 5
   • Fuzzy matches (<90%): 62
   • Match rate: 2.7%
```

## JSON Generator

### Purpose

Generates static JSON file from PostgreSQL database for frontend consumption.

### Features

- Single source of truth: PostgreSQL database
- Maintains backward compatibility with `/flood` page
- Auto-generates summary statistics
- Includes source attribution

### Usage

```bash
python3 generate_sec_json.py
```

### Output Format

```json
{
  "summary": {
    "total_contractors": 15,
    "contractors_with_sec_data": 15,
    "contractors_with_zero_results": 0,
    "last_updated": "2025-10-18T16:43:43",
    "processing_batch": "database_generated",
    "source": "PostgreSQL philgeps.contractors table"
  },
  "contractors": [
    {
      "original_contractor_name": "CONTRACTOR NAME",
      "company_name": "CONTRACTOR NAME",
      "sec_number": "CS201234567",
      "status": "Registered",
      "date_registered": "2021-01-01",
      "registered_address": "ADDRESS HERE",
      "secondary_license_details": "No records...",
      "source": "database"
    }
  ]
}
```

## Current Status

### Database Statistics

**Contractors Table:**
- **15 contractors** with SEC data
- **15 with SEC numbers** (100%)
- **Status breakdown:**
  - Registered: 11
  - Delinquent: 2
  - Revoked: 2

**Project-Contractor Relationships:**
- **10,627 total relationships**
- **9,855 main contractors**
- **772 JV partners** (386 × 2)

### SEC Data Coverage

**PhilGEPS Contracts:**
- **10,666 unique contractors** in contracts table
- **15 with SEC data** (0.14% coverage)
- **Target: 100 contractors** (0.94% coverage)

**Flood Projects:**
- **9,855 flood control projects**
- **2,491 unique contractors** (including JV partners)
- **15 with SEC data** (0.6% coverage)

### Sample Results

| Contractor Name | SEC Number | Status | 
|-----------------|------------|--------|
| ST. TIMOTHY CONSTRUCTION CORPORATION | CS201413029 | Registered |
| J. B. FELIPE CONSTRUCTION CORPORATION | CS201908901 | Delinquent |
| ALPHA & OMEGA GEN. CONTRACTOR & DEVELOPMENT CORP. | CS201409477 | Registered |
| 1HB CONSTRUCTION Corp. | CS201952011 | Registered |
| 1FC DIZON CORP. | CS201808738 | Registered |

## Workflow

### Complete Processing Cycle

1. **Run AHK Script** (Windows)
   ```
   Run database/sec_search.ahk
   → Processes 100 contractors
   → Saves to database/sec_results/*.txt
   ```

2. **Parse SEC Results** (Python)
   ```bash
   python3 sec_contractor_parser.py
   → Parses text files
   → Updates contractors table
   → Performs JV-aware correlation
   ```

3. **Generate JSON** (Python)
   ```bash
   python3 generate_sec_json.py
   → Reads from database
   → Updates static/sec_contractors_database.json
   ```

4. **Frontend Displays** (Automatic)
   ```
   /flood page reads JSON file
   → Shows SEC status in contractor table
   → Displays SEC modal with details
   ```

## Integration Points

### MeiliSearch Flood Data

**Connection via GlobalID:**
```
MeiliSearch flood projects
  ↓ (GlobalID)
project_contractors table
  ↓ (contractor_name)
contractors table
  ↓ (sec_number, status)
Frontend display
```

### PhilGEPS Contracts

**Connection via contractor name:**
```
PhilGEPS contracts.awardee_name
  ↓ (fuzzy match)
contractors.contractor_name
  ↓ (sec_number, status)
Frontend display
```

## Frontend Integration

### Flood Page (`/flood`)

**SEC Tab:**
- Shows total SEC records
- Lists contractors without SEC data
- Displays SEC statistics

**Contractor Table:**
- Shows SEC status column
- Click contractor → SEC modal with details

**Data Source:**
- Reads from `static/sec_contractors_database.json`
- 4 fetch calls to the JSON file

## Future Enhancements

### Planned Improvements

1. **Scale to 1000+ contractors**
   - Batch processing via AHK
   - Automated scheduled runs

2. **API Endpoint**
   - Direct database queries instead of static JSON
   - Real-time SEC data access

3. **Enhanced Matching**
   - Machine learning-based name matching
   - Manual mapping overrides table

4. **SEC Data Enrichment**
   - Reportorial submissions parsing
   - Secondary licenses tracking
   - Historical status changes

## Files

### Directory Structure

All SEC-related files are organized in the `sec_scraper/` directory:

```
sec_scraper/
├── sec_search.ahk              # AHK automation for SEC website
├── sec_contractor_parser.py    # Parser for SEC result files
├── generate_sec_json.py        # Database to JSON generator
├── sec_results/                # Raw SEC search results (text files)
└── README.md                   # Quick start guide
```

### Generated Files
- `static/sec_contractors_database.json` - Generated JSON for frontend

### Database
- `philgeps.contractors` - SEC contractor data
- `philgeps.project_contractors` - JV-aware project relationships
- `philgeps.contractor_projects` - Correlation view

## Notes

- AHK script requires Windows + AutoHotkey
- Python scripts require: asyncpg, aiohttp, chardet, python-dotenv
- Database uses fuzzy matching for contractor name correlation
- JV partners are tracked separately for accurate project attribution
- SEC data is normalized and deduplicated in database

