# Family Scraper Module

This module contains tools for discovering and managing political dynasty family connections through Wikipedia scraping and database management.

## Files Overview

### Core Scrapers
- **`optimized_wiki_scraper.py`** - Main Wikipedia scraper that targets provinces with exactly 2 political families
- **`targeted_wiki_scraper.py`** - Focused scraper for politicians likely to have Wikipedia pages
- **`wikipedia_scraper.py`** - Basic Wikipedia scraper for relationship discovery
- **`scheduled_wiki_scraper.py`** - Automated scheduler to run scrapers daily

### Name Matching & Database
- **`advanced_name_matcher.py`** - Advanced name matching for handling maiden/married names, hyphenated surnames, and fuzzy matching
- **`setup_connections.py`** - Database setup script for connection types and initial relationships

## Key Features

### 1. Wikipedia Relationship Discovery
- Scrapes Wikipedia pages for political figures
- Extracts family relationships (marriage, parent-child, siblings, etc.)
- Detects nicknames from Wikipedia content
- Maps relationships to database connection types

### 2. Advanced Name Matching
- Handles maiden names vs married names
- Manages hyphenated surnames (e.g., "Uy-Tan")
- Fuzzy matching for name variations
- Suggests potential connections between families

### 3. Database Integration
- Automatically updates connection relationships
- Populates nickname fields from Wikipedia
- Maintains bidirectional relationships
- Supports 20+ relationship types (Father, Mother, Son, Daughter, Husband, Wife, etc.)

### 4. Automated Processing
- Targets provinces with exactly 2 political families
- Processes 19 identified two-family provinces
- Runs daily to discover new relationships
- Updates database with found connections

## Usage

### Manual Scraping
```bash
python3 optimized_wiki_scraper.py
```

### Scheduled Scraping
```bash
python3 scheduled_wiki_scraper.py
```

### Database Setup
```bash
python3 setup_connections.py
```

## Connection Types

The system supports these relationship types:
1. Father
2. Mother  
3. Son
4. Daughter
5. Husband
6. Wife
7. Brother
8. Sister
9. Uncle
10. Aunt
11. Nephew
12. Niece
13. Cousin
14. Grandfather
15. Grandmother
16. Grandson
17. Granddaughter
18. Father-in-law
19. Mother-in-law
20. Son-in-law
21. Daughter-in-law

## Example Discovered Connections

- **STEPHANY TAN** ↔ **STEPHEN JAMES TAN** (Marriage)
- **STEPHANY TAN** ↔ **COEFREDO UY** (Father-Daughter)
- **STEPHEN JAMES TAN** ↔ **SHAREE ANN TAN** (Siblings)

## Integration with Main System

The scraped data integrates with:
- `/family` pages showing connected family members
- Hierarchy charts with relationship lines
- Nickname display in politician names
- Cross-family relationship discovery

## Data Quality

- Respects Wikipedia rate limits
- Handles HTTP 403 errors gracefully
- Filters false positive relationships
- Validates connection accuracy
- Maintains data integrity with foreign key constraints
