# DPWH 2026 GAA Data Analysis Notes

## Overview

This document contains analysis notes and insights from the DPWH (Department of Public Works and Highways) 2026 General Appropriations Act (GAA) hierarchical data structure.

## Data Source

- **File**: `FY 2026_DPWH DETAILS ENROLLED COPY (Final).xlsx`
- **Format**: Excel spreadsheet with hierarchical structure
- **Processing**: Converted to hierarchical JSON using formatting-aware parser

## Data Structure

The data is organized as a hierarchical tree structure where:

- **Hierarchy levels** are determined by column indentation
- **Bullet markers** (a., 1.0, 2.0, etc.) indicate hierarchy position
- **Values** appear in the column immediately following bullets
- **Titles** are typically underlined and bold
- **Descriptions** are italicized and have no amounts
- **Amounts** are stored in column K (index 10)

## Key Observations

### Hierarchy Characteristics

1. **Multi-level Structure**: The data contains multiple nested levels representing:
   - Programs/Activities/Projects (top level)
   - Sub-programs and categories
   - Regional and district offices
   - Specific infrastructure projects

2. **Formatting Indicators**:
   - **Underlined + Bold**: Program/category titles
   - **Italic**: Descriptive text (attached as `description` field)
   - **Regular text**: Specific project entries

3. **Amount Distribution**:
   - Most nodes at the project level have amounts
   - Higher-level nodes may have aggregated amounts
   - Description nodes never have amounts

### Data Quality Notes

1. **Empty Rows**: Many empty rows exist in the source data - these are filtered out during processing

2. **Bullet Markers**: The hierarchy uses various bullet formats:
   - Letter bullets (a., b., c.)
   - Number bullets (1.0, 2.0, 3.0)
   - These are used to indicate hierarchy levels, not as content

3. **Description Handling**: 
   - Descriptions are italicized rows that immediately follow their parent node
   - They are attached to the previous node as a `description` field
   - Multiple description rows are concatenated

## Processing Pipeline

### Step 1: XLSX to Hierarchy JSON

```bash
python scripts/build_hierarchy_from_xlsx.py
```

**Process**:
1. Reads XLSX file using `openpyxl` to access formatting
2. Identifies hierarchy levels based on column position and bullets
3. Detects formatting (underline, italic, bold) to distinguish titles from descriptions
4. Builds tree structure maintaining parent-child relationships
5. Attaches descriptions to their parent nodes
6. Outputs JSON hierarchy

### Step 2: Web Exploration

The generated JSON can be explored using the interactive web interface:

```bash
python3 -m http.server 8000
# Open http://localhost:8000
```

## Data Schema

Each node in the hierarchy JSON contains:

```json
{
  "value": "Node name/title",
  "amount": 12345678.90,  // Optional: monetary value
  "description": "Optional description text",  // Optional: italicized description
  "children": [  // Array of child nodes
    {
      "value": "Child node",
      "amount": 5000000.00,
      "children": []
    }
  ]
}
```

## Analysis Insights

### Dataset Statistics

Based on analysis of the generated hierarchy:

- **Total Nodes**: 23,614
- **Nodes with Amounts**: 23,592 (99.9%)
- **Nodes with Descriptions**: 19
- **Nodes with Children**: 4,003
- **Total Budget**: ₱4,563,569,466,000.00 (approximately ₱4.56 trillion)
- **Largest Allocation**: ₱496,927,726,000.00 (CAPITAL OUTLAYS)

### Top-Level Categories

The data is organized into major categories such as:

1. **PROGRAMS / ACTIVITIES / PROJECTS**
2. **MAINTENANCE AND OTHER OPERATING EXPENSES**
3. **GENERAL ADMINISTRATIVE AND SUPPORT**
4. **SUPPORT TO OPERATIONS**
5. **CAPITAL OUTLAYS**

### Regional Distribution

Projects are organized by:
- **Regions**: National Capital Region, Region I-XIII, CAR, etc.
- **District Engineering Offices**: Specific offices within regions
- **Project Types**: Road widening, construction, maintenance, etc.

### Project Types

Common project categories include:
- Road Widening (Primary, Secondary, Tertiary Roads)
- Construction of By-Passes and Diversion Roads
- Construction of Missing Links/New Roads
- Construction of Flyovers/Interchanges/Underpasses
- Off-Carriageway Improvement
- Paving of Unpaved Roads

## Technical Notes

### Challenges Encountered

1. **Hierarchy Detection**: 
   - Initial approach using CSV lost formatting information
   - Solution: Use `openpyxl` to read formatting directly from XLSX

2. **Description Rows**:
   - Initially descriptions were incorrectly added as child nodes
   - Solution: Detect italic formatting and attach as field instead

3. **Bullet Markers**:
   - Long numeric values (amounts) were incorrectly identified as bullets
   - Solution: Limit bullet detection to short values (1-4 characters)

4. **Amount Column**:
   - Amounts in column K sometimes contain commas
   - Solution: Strip commas and convert to float

### Performance Considerations

- **File Size**: The XLSX file is large (~4.3MB)
- **Processing Time**: Full hierarchy generation takes ~30-60 seconds
- **JSON Output**: Generated JSON is ~120K lines, ~12MB

## Usage Recommendations

1. **For Analysis**: Use the web interface for interactive exploration
2. **For Processing**: Use the Python scripts for programmatic access
3. **For Updates**: Re-run the hierarchy builder if source XLSX changes

## Future Enhancements

Potential improvements:

1. **Aggregation**: Calculate totals at each hierarchy level
2. **Filtering**: Add filters by region, project type, amount range
3. **Visualization**: Create charts/graphs for budget distribution
4. **Export**: Add export to various formats (CSV, Excel, PDF)
5. **Search Enhancement**: Improve search with fuzzy matching
6. **Comparison**: Compare with previous year's data

## References

- Source: DPWH 2026 General Appropriations Act
- Processing Date: Generated from `FY 2026_DPWH DETAILS ENROLLED COPY (Final).xlsx`
- Tools: Python 3, openpyxl, python-calamine
