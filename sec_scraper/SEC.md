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
   - Parses raw SEC result files (3,426 files)
   - **11 parallel threads** for fast processing
   - Extracts structured contractor data using regex
   - Updates PostgreSQL `contractors` table (SEC database)
   - Handles JV-aware correlation with flood projects (PhilGEPS database)
   - **Match threshold:** Score ≥ 0.966 using SequenceMatcher
   - **Databases:** Connects to both `sec` and `philgeps` databases

3. **JSON Generator** (`generate_sec_json.py`)
   - Reads from PostgreSQL database
   - Generates `static/sec_contractors_database.json`
   - Ensures unified SEC data source

4. **PostgreSQL Databases**
   - **`sec` database:** Stores contractor SEC registration data
     - Table: `contractors` (10,981 contractors, 1,042 with SEC data)
   - **`philgeps` database:** Stores project-contractor relationships
     - Table: `project_contractors` (10,627 relationships with JV data)
   - **Dual connection:** Parser connects to both databases simultaneously

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

### Fuzzy Matching Algorithm

The Python parser uses optimized matching with strict threshold:

**Step 1: Normalization**
- Remove suffixes: corp, corporation, inc, incorporated, ltd, limited, co, company
- Remove prefixes: "the "
- Normalize whitespace
- Convert to lowercase

**Step 2: Exact Match (O(1) dictionary lookup)**
- Build hash table of normalized SEC contractor names
- Instant lookup for exact matches
- Returns Score: 1.000

**Step 3: Fuzzy Match (SequenceMatcher)**
- Only runs if no exact match found
- Uses Python's difflib.SequenceMatcher
- Compares normalized names
- **Accepts only Score ≥ 0.966**

**Match Quality Examples:**
- **1.000:** Exact match after normalization
- **0.987:** "AGONG BUILDERS, INC." ↔ "AGONG BUILDERS INC" (punctuation)
- **0.979:** "F.F. GALANG" ↔ "F.F GALANG" (spacing)
- **0.974:** "VEN RAY" ↔ "VENRAY" (space removed)
- **0.966:** "ARCINUE COMM'L" ↔ "ARCINUE COMM'L." (period)

**Rejected (too low):**
- **0.963:** "JCO CONSTRUCTION" ↔ "JCL CONSTRUCTION" (different companies!)
- **0.960:** "MDP SERVICES" ↔ "JMD SERVICES" (different companies!)

**Algorithm Complexity:**
- Exact match: O(1) - instant dictionary lookup
- Fuzzy match: O(n) - linear scan only for non-matches
- Overall: Much faster than O(n×m) nested loops

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
# Run parser (output to console)
python3 sec_contractor_parser.py

# Run parser with output to file for analysis
python3 sec_contractor_parser.py > parser_output.txt 2>&1

# Analyze results later
grep "Score ≥" parser_output.txt
grep "0.98:" parser_output.txt
```

### Parsing Logic

Extracts company details using regex pattern:

```python
company_pattern = r'COMPANY DETAILS\nCompany Name\n(.*?)\n\nSEC Number\n(.*?)\n\nDate Registered\n(.*?)\n\nStatus\n(.*?)\n\nAddress\n(.*?)\n\nSECONDARY LICENSE DETAILS'
```

### Output (Latest Run: October 21, 2025)

```
🚀 Starting JV-aware SEC contractor data processing...
📁 Found 3,426 SEC result files
🧵 Using 11 threads for parallel parsing...

📊 Total companies parsed: 2,346
✅ Matched & Updated: 1,042 contractors

🔗 JV-aware correlating with existing contract data...
🔄 Loading flood projects with JV data...
📋 Loaded 9,855 flood projects
📋 Processing 9,855 flood projects for JV data...
✅ Inserted 10,627 project-contractor relationships
📋 Found 2,491 unique contractors in JV data
📋 Found 1,042 contractors in SEC contractors table
🔧 Building SEC contractor lookup index...
📋 Indexed 1,017 unique normalized SEC contractor names

📊 Score Distribution Statistics:
Total project contractors: 2,491
Total SEC contractors: 1,042

Score ≥ 1.00:  365 matches (Cumulative:  365, 14.65%)
Score ≥ 0.99:    0 matches (Cumulative:  365, 14.65%)
Score ≥ 0.98:    5 matches (Cumulative:  370, 14.85%)
Score ≥ 0.97:    8 matches (Cumulative:  378, 15.17%)
Score ≥ 0.96:   16 matches (Cumulative:  394, 15.82%)

✅ Valid matches accepted (Score ≥ 0.966): 386 matches (15.50%)
✅ JV-aware SEC contractor processing complete!
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

**Last Updated:** October 21, 2025

### Database Statistics

**SEC Results Parsed:**
- **3,426 SEC result files** processed (from AHK scraper)
- **926 successful searches** (27.0%) - found companies in SEC
- **1,388 no results found** (40.5%) - not in SEC database
- **1,059 empty files** (30.9%) - AHK script failures
- **53 malformed files** (1.5%) - capture errors
- **1,112 contractors need retry**

**Contractors Table (SEC Database):**
- **10,981 total contractors** in database
- **1,042 with SEC data** (9.5% coverage)
- **9,939 without SEC data**
- **1,954 suspicious** (searched but no SEC results found)

**Status Breakdown (1,042 contractors):**
  - Registered: ~750+
  - Suspended: ~100+
  - Revoked: ~80+
  - Delinquent: ~50+
  - Expired/Dissolved: ~60+

**Project-Contractor Relationships (PhilGEPS Database):**
- **10,627 total relationships**
- **9,855 main contractors**
- **772 JV partners** (386 × 2)
- **2,491 unique contractors** (including JV partners)

### JV-Aware Correlation Results

**Match Threshold:** Score ≥ 0.966 (using SequenceMatcher)

**Match Quality:**
- **365 exact matches** (Score 1.00) - 14.65%
- **0 matches** at 0.99
- **5 matches** at 0.98+ (punctuation differences)
- **8 matches** at 0.97+ (spacing/initial differences)
- **16 matches** at 0.966-0.97 (minor variations)
- **Total valid matches:** ~394 contractors (15.8%)

### Performance Optimizations

**Parser Improvements:**
- **11 parallel threads** for file parsing (3,426 files)
- **Dictionary-based lookup** O(1) for exact matches
- **SequenceMatcher** for fuzzy matching (only on non-exact)
- **Dual database connections:** SEC for contractors, PhilGEPS for project_contractors
- **Output redirection** for easy analysis: `> output.txt 2>&1`

### SEC Data Coverage

**PhilGEPS Contracts:**
- **104,819 flood control contracts** (2021-2024)
- **37,284 linked to MeiliSearch** (35.57%)

**Flood Projects:**
- **9,855 flood control projects**
- **2,491 unique contractors** (including JV partners)
- **~394 with SEC correlation** (15.8% match rate via JV-aware fuzzy matching)

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
- `static/sec_contractors_database.json` - Generated JSON for frontend (10,981 contractors)
- `database/sec_dump.sql` - PostgreSQL database dump (1.44 MB, updated Oct 21, 2025)
- `sec_scraper/parser_run_output.txt` - Parser execution log with statistics
- `sec_scraper/contractors_to_retry.txt` - List of 1,112 contractors needing retry

### Databases
- `sec.contractors` - SEC contractor data (10,981 contractors, 1,042 with SEC numbers)
- `philgeps.project_contractors` - JV-aware project relationships (10,627 records)
- `philgeps.contractor_projects` - Correlation view (if exists)

## Recent Updates (October 21, 2025)

### What Was Done

1. **Parsed all SEC results** - Processed 3,426 SEC result files
2. **Updated SEC database** - 1,042 contractors now have SEC registration data
3. **Database fix** - Corrected to use `sec` DB for contractors, `philgeps` DB for project_contractors
4. **Performance optimization** - Added 11-thread parallel processing
5. **Match threshold calibration** - Set to Score ≥ 0.966 after analyzing score distribution
6. **Locale updates** - All numbers use 'en-PH' Philippine locale formatting
7. **JSON regeneration** - Updated `static/sec_contractors_database.json`
8. **Database dump** - Created `database/sec_dump.sql` (1.44 MB)

### Analysis Tools Added

- **`analyze_sec_results.py`** - Distinguishes between:
  - Empty files (AHK failures)
  - No results found (valid search, not in SEC)
  - Successful searches with results
  - Malformed captures

### File Detection Results

| Category | Count | Percentage |
|----------|-------|------------|
| ✅ Successful searches | 926 | 27.0% |
| ❌ No SEC results | 1,388 | 40.5% |
| 🚫 AHK failures (empty) | 1,059 | 30.9% |
| ⚠️ Malformed | 53 | 1.5% |

**Total companies found:** 2,346 across 926 successful searches  
**Average:** 2.5 companies per search  
**Hit 10-result limit:** 133 searches (14.4%)

## Notes

- AHK script requires Windows + AutoHotkey
- Python scripts require: asyncpg, aiohttp, chardet, python-dotenv, concurrent.futures
- Database uses SequenceMatcher for fuzzy matching (threshold: 0.966)
- JV partners are tracked separately for accurate project attribution
- SEC data is normalized and deduplicated in database
- Parser uses 11 threads for parallel file processing (~1000x faster)
- Frontend numbers use Philippine locale (en-PH) formatting

