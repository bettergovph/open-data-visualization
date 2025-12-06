# Location Data Integration Plan

> [!NOTE]
> This document outlines the plan to create a unified location database by combining administrative boundaries with election district data. This will enable accurate district classification for projects.

## 1. Context & Objective
We need a single source of truth for location data that includes:
- **Administrative Hierarchy:** Region > Province > Municipality/City > Barangay
- **Political Districts:** Congressional Districts (Legislative Districts)

This data will be used to:
1.  Augment the dynasty projects analysis.
2.  Classify projects based on location clues in their names/descriptions.
3.  Visualize data by district.

## 2. Data Sources

### Source A: Administrative Boundaries
**Path:** `../philippine-regions-provinces-cities-municipalities-barangays/philippine_provinces_cities_municipalities_and_barangays_2019v2.json`
**Content:** Hierarchical structure of all administrative units.

### Source B: Election Data (District Mapping)
**Path:** `../ph-elections2025/data/`
**Content:** Folder structure `Province > Municipality > Barangay > Precinct CSV`.
**Key Insight:** The CSV files contain the specific "MEMBER, HOUSE OF REPRESENTATIVES" contest, which explicitly names the legislative district (e.g., "FIRST LEGDIST").

### Source C: DILG 2025 Barangay Data
**Path:** `data/dilg/`
**Content:** Official list of barangays from DILG as of September 2025.
**Source URL:** `https://archive.org/download/20250914.dilg.barangay/`
**Retrieval Method:** `scripts/download_dilg_data.py`

## 3. Implementation Components

### Component A: Master Location Database Builder
**Script:** `scripts/build_location_db.py`
**Logic:**
1.  **Load Admin Data:** Read the 2019v2 JSON to build the base hierarchy.
2.  **Crawl Election Data:**
    - Iterate through the `ph-elections2025/data` directory.
    - For each Municipality/City, read *one* sample CSV file (no need to read all precincts).
    - Extract the "MEMBER, HOUSE OF REPRESENTATIVES" contest name.
    - Parse the district name (e.g., "ILOCOS NORTE - FIRST LEGDIST" -> "1st District").
3.  **Merge & Enrich:**
    - Attach the extracted District information to the Municipality/City object in the base hierarchy.
    - Handle special cases (e.g., Lone Districts, Party-list only areas if any).
4.  **Output:** `static/data/ph_locations_districts.json` and `static/data/ph_locations_districts.duckdb`
    - **JSON Structure:**
        ```json
        {
          "regions": {
            "REGION I": {
              "provinces": {
                "ILOCOS NORTE": {
                  "municipalities": {
                    "ADAMS": {
                      "district": "1st District",
                      "barangays": [...]
                    }
                  }
                }
              }
            }
          }
        }
        ```
    - **DuckDB Table:** `locations` (region, province, municipality, barangay, district)

### Component B: Location Classifier Utility
**Script:** `scripts/classify_location.py` (or a module `utils/location_classifier.py`)
**Logic:**
- Input: Project Name, Description, Raw Location String.
- Process:
    - Tokenize input.
    - Match against the Master Location Database (fuzzy matching for misspellings).
    - Return: Best match Region, Province, District, Municipality.

## 4. Step-by-Step Implementation Instructions for LLM

1.  **Setup:**
    - Verify paths to both external repositories.
    - Install `duckdb` python package if missing.

2.  **Builder Script:**
    - Create `scripts/build_location_db.py`.
    - Implement the JSON walker and the CSV crawler.
    - **Optimization:** Only read the first few lines of one CSV per municipality to find the contest name.
    - Save outputs to `static/data/`.

3.  **DuckDB Integration:**
    - Ensure the script creates a DuckDB database file `static/data/locations.duckdb` for efficient querying by other scripts (like the dynasty analysis).

4.  **Documentation:**
    - Update `README.md` to reference this new capability.

## 5. Verification
- Check a few known municipalities (e.g., Adams, Davao City, Quezon City) to ensure correct district assignment.
- Verify that "Lone Districts" are handled correctly.
