# Family Analysis Module

This module combines the functionality of `family_scraper` and `family_parser` components for comprehensive political dynasty analysis.

## Structure

- **`family_scraper/`** - Political dynasty relationship discovery tools
  - Wikipedia scrapers for automated family connection discovery
  - Advanced name matching for maiden/married names
  - Database integration for relationship mapping
  - Scheduled processing for continuous discovery
  - See `family_scraper/README.md` for detailed documentation

- **`family_parser/`** - Government officials and election data processing
  - Government officials import and classification
  - Election data processing and analysis
  - LLM-based relationship discovery with 20 optimal prompts
  - Data quality validation and cleanup
  - CSV parsing and relationship processing
  - See individual files for specific functionality

## Combined Functionality

This unified module provides:

1. **Data Discovery**: Wikipedia scraping and LLM-based relationship discovery
2. **Data Import**: Government officials and election data import
3. **Data Processing**: Advanced name matching and relationship analysis
4. **Data Management**: Database operations and data quality maintenance

## Usage

### Wikipedia-based Discovery
```bash
cd family_scraper
python3 optimized_wiki_scraper.py
```

### Government Officials Import
```bash
cd family_parser
python3 import_2025_government_officials.py
```

### LLM-based Relationship Discovery
```bash
cd family_parser
# Use the 20 optimal prompts for relationship discovery
python3 llm_relationship_prompt.py
# Process CSV results
python3 process_llm_csv_results.py
# Parse multiple relationship CSVs
python3 parse_multiple_relationship_csvs.py
```

## Integration

Both components work with the same `dynasty` database and share:
- Database connection patterns
- Political dynasty data types
- Relationship analysis functionality
- Data quality management

## Most Effective Method

The most effective relationship discovery method is:
1. Generate prompts based on data slices using the 20 optimal prompts
2. Send prompts to web-specialized LLM for CSV generation
3. Store CSV results locally for parsing
4. Process and validate discovered relationships

### 20 Optimal Prompts

The family_parser directory contains 20 optimized prompts (optimal_prompt_01.txt through optimal_prompt_20.txt) that have been refined for maximum effectiveness in discovering political dynasty relationships. These prompts are designed to work with web-specialized LLMs to generate high-quality CSV data for relationship analysis.

This approach is more efficient than direct Wikipedia scraping and provides higher quality relationship data.