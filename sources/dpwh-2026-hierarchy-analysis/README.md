# DPWH 2026 GAA Hierarchy Explorer

This project contains scripts to convert Excel data to hierarchical JSON and a web interface to explore it.

## Files

### Hierarchy Generation
- `scripts/build_hierarchy_from_xlsx.py` - Builds hierarchy from XLSX with formatting awareness (recommended)
- `scripts/archive/build_hierarchy.py` - Legacy hierarchy builder from CSV
- `scripts/archive/xlsx_to_csv.py` - Converts XLSX to CSV format
- `scripts/archive/extract_unique_values.py` - Extracts unique values from columns

### Table Flattening
- `scripts/hierarchy_to_table.py` - Converts hierarchical JSON to flat table (CSV/JSON)
- `scripts/table_to_markdown.py` - Generates markdown documentation from table data
- `scripts/analyze_hierarchy.py` - Analyzes hierarchy structure statistics

### Visualization
- `index.html` - Interactive web interface to explore the hierarchy
- `data/` - Contains the source XLSX file and generated files (JSON, CSV, Markdown)

## Usage

### Generate Hierarchy JSON

```bash
# Install dependencies
pip install -r requirements.txt

# Generate hierarchy from XLSX (recommended - includes formatting)
python scripts/build_hierarchy_from_xlsx.py
```

This will create `data/FY 2026_DPWH DETAILS ENROLLED COPY (Final)_hierarchy.json`

### Generate Flattened Table

```bash
# Flatten hierarchy to CSV and JSON table formats
python scripts/hierarchy_to_table.py
```

This will create:
- `data/FY 2026_DPWH DETAILS ENROLLED COPY (Final)_hierarchy_table.csv` - CSV format
- `data/FY 2026_DPWH DETAILS ENROLLED COPY (Final)_hierarchy_table.json` - JSON table format

```bash
# Generate markdown documentation from table
python scripts/table_to_markdown.py
```

This will create a markdown sample: `data/FY 2026_DPWH DETAILS ENROLLED COPY (Final)_hierarchy_table_sample.md`

### Analyze Hierarchy Structure

```bash
# Analyze hierarchy levels and structure
python scripts/analyze_hierarchy.py
```

```bash
# Analyze patterns and distributions in flattened table
python scripts/analyze_table_patterns.py
```

This will create:
- `data/hierarchy_analysis_results.txt` - Full analysis output
- `docs/hierarchy_structure_analysis.md` - Formatted analysis with tables and insights

Key analyses include:
- Depth distribution (8 levels)
- Regional/district breakdowns (Levels 5-6)
- Top paths by amount
- Program category analysis (Level 4)
- Summary statistics and recommendations

### View in Web Browser

#### Option 1: Local Development

1. Start a simple HTTP server:
```bash
python3 -m http.server 8000
```

2. Open your browser and navigate to:
```
http://localhost:8000
```

3. The interactive hierarchy explorer will load automatically.

#### Option 2: GitHub Pages (Deployed)

The project is configured for GitHub Pages deployment. Once enabled in your repository settings:

1. Go to repository Settings → Pages
2. Select source branch (usually `main`)
3. Select folder (usually `/ (root)`)
4. The site will be available at:
```
https://csiiiv.github.io/dpwh-2026-hierarchy-analysis/
```

The interactive hierarchy explorer will load automatically from the deployed JSON file.

## Features

- **Hierarchical Tree View**: Expand/collapse nodes to navigate the structure
- **Search**: Search by name, amount, or description
- **Amount Display**: Shows monetary values in Philippine Peso format
- **Descriptions**: Displays italicized description text when available
- **Responsive Design**: Works on desktop and mobile devices

## Hierarchy Structure

Each node in the JSON contains:
- `value`: The node's name/title
- `amount`: Monetary value (if present)
- `description`: Description text (if present, from italic rows)
- `children`: Array of child nodes
