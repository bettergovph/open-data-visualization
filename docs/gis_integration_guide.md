# GIS Data Integration & Engineering District Extraction Guide

> [!NOTE]
> This document is designed to be a self-contained guide for an LLM or developer to implement the integration of DPWH GIS data into the Open Data Visualization project.

## 1. Context & Objective
The goal is to enhance the analysis of Annex A-5 (DPWH) projects by integrating geospatial data from the DPWH Road and Bridge Information Application (RBIA). Specifically, we want to:
1.  **Extract District Engineering Offices (DEOs):** Identify which DEO manages specific areas or road segments.
2.  **Match Projects to National Roads:** Link budget line items to specific national roads (Primary, Secondary, Tertiary) to visualize funding distribution by road classification.
3.  **Visualize Data:** Create a new tab (`/budget#gis`) to display these insights.

## 2. Data Source
**Source File:** `../DPWH_GIS/gis_data/all_roads.csv`
**Schema:**
- `region`: Region name (e.g., "Region I", "National Capital Region")
- `province`: Province name
- `deo`: District Engineering Office name (e.g., "Ilocos Norte 1st District Engineering Office")
- `cong_district`: Congressional District (e.g., "ILOCOS NORTE (1ST DISTRICT)")
- `road_class`: Classification (Primary, Secondary, Tertiary, Expressway)
- `road_name`: Name of the road segment
- `road_length`: Length in meters

## 3. Implementation Components

### Component A: Engineering District (DEO) Extraction
**Objective:** Create a master list of DEOs and their coverage areas.

**Script:** `scripts/extract_dpwh_deos.py`
**Logic:**
1.  Read `all_roads.csv`.
2.  Extract unique combinations of `region`, `province`, `deo`, and `cong_district`.
3.  Clean/Normalize DEO names (remove extra spaces, standardize formatting).
4.  **Output:** `static/data/dpwh_deos.json`
    ```json
    [
      {
        "deo_name": "Ilocos Norte 1st District Engineering Office",
        "region": "Region I",
        "province": "Ilocos Norte",
        "congressional_districts": ["ILOCOS NORTE (1ST DISTRICT)"],
        "total_road_length_km": 123.45
      },
      ...
    ]
    ```

### Component B: Road Matching Engine
**Objective:** Link 2026 Annex A-5 projects to GIS road data.

**Script:** `scripts/match_gis_roads.py`
**Logic:**
1.  **Load Data:**
    - Load `all_roads.csv`.
    - Load 2026 budget items (`static/data/budget_amendments_2026.json` filtered for "Annex A-5").
2.  **Preprocessing:**
    - **Roads:** Create a "normalized" version of `road_name` (lowercase, remove "road", "st", "ave", "highway", etc.).
    - **Projects:** Extract potential road names from project descriptions (look for patterns like "Construction of [Name] Road").
3.  **Matching Algorithm:**
    - **Exact Match:** Check if normalized project road name matches a normalized GIS road name.
    - **Fuzzy Match:** Use `thefuzz` (or `difflib`) to find high-confidence matches (>90% similarity).
    - **Location Constraint:** Enforce that the matched road must be in the same Region/Province as the project (if location data is available in the project item).
4.  **Output:** `static/data/gis_road_matches.json`
    ```json
    {
      "metadata": { ... },
      "matches": [
        {
          "project_id": "...",
          "project_name": "...",
          "matched_road": {
            "name": "Manila North Rd",
            "class": "Primary",
            "deo": "...",
            "similarity": 0.95
          }
        }
      ]
    }
    ```

### Component C: Frontend Visualization (`/budget#gis`)
**File:** `templates/budget.html`
**Changes:**
1.  **New Tab:** Add a tab button "🗺️ GIS Roads" (`#gis`).
2.  **Tab Content:**
    - **Summary Cards:**
        - Total Projects Matched
        - Total Amount by Road Class (Primary vs Secondary vs Tertiary)
        - Top DEOs by Budget
    - **Data Table/List:**
        - Display matched projects.
        - **Columns:** Project Name, Matched Road, Road Class, DEO, Amount.
        - **Filters:** Filter by Region, DEO, Road Class.

## 4. Step-by-Step Implementation Instructions for LLM

1.  **Setup:**
    - Verify `../DPWH_GIS/gis_data/all_roads.csv` exists.
    - Create `scripts/extract_dpwh_deos.py` and run it to generate the DEO master list.
    
2.  **Matching Script:**
    - Create `scripts/match_gis_roads.py`.
    - Implement the normalization and fuzzy matching logic.
    - **Crucial:** Ensure location constraints are applied to avoid matching "Rizal St" in Davao to "Rizal St" in Manila.
    - Run the script and validate `static/data/gis_road_matches.json`.

3.  **Frontend:**
    - Modify `templates/budget.html`.
    - Add the HTML structure for the `#gis` tab (copy structure from `#resu` or `#roads` as a base).
    - Implement JavaScript `loadGISData()` to fetch the two new JSON files.
    - Implement visualization logic (charts/tables).

4.  **Verification:**
    - Check if DEO list is complete and accurate.
    - Spot check road matches for false positives.

## 5. Future Enhancements
- **Map Visualization:** Use Leaflet.js or Mapbox to plot the DEOs and Roads on a map (requires geometry data, currently we only have CSV attributes, but DEOs can be mapped to province centroids).
- **Gap Analysis:** Compare "Road Length" per DEO vs "Budget Allocation" to find under/over-funded districts.
