# HuggingFace → Dynasty Database Integration

## Overview

This integration enriches your dynasty database with high-quality data from the [BetterGov.PH Philippine dataset](https://huggingface.co/datasets/bettergovph/raw-philippine-data) on HuggingFace.

## What Gets Integrated

### 1. **Person Names** (45,400+ persons)
- ✅ First name, middle name, last name, suffix
- ✅ Nicknames
- ✅ Name corrections for existing records
- ✅ Canonical name generation

### 2. **Political Memberships** (86,200+ memberships)
- ✅ Political positions (Mayor, Councilor, Governor, etc.)
- ✅ Party affiliations
- ✅ Geographic data (region, province, locality)
- ✅ Year served

### 3. **Party List Table**
- ✅ Adds missing political parties
- ✅ Updates party occurrence counts
- ✅ Standardizes party codes

### 4. **Potential Relationships**
- ✅ Identifies families with multiple politicians (same last name)
- ✅ Generates report for manual review
- ✅ Foundation for relationship mapping

## Database Tables Updated

### `political_dynasties`
**What gets added/updated:**
- New person records with positions
- Missing middle names and suffixes
- Canonical names
- Party affiliations
- Geographic data

**Fields populated:**
```sql
first_name, middle_name, last_name, suffix, nickname,
party, region, province, municipality_city, position, year,
canonical_name, winner, fat
```

### `party_list`
**What gets added/updated:**
- New political parties
- Party occurrence counts
- Party codes

**Fields populated:**
```sql
code, party_name, occurrences
```

### Potential Future Integrations

**Not implemented yet, but data is available for:**
- `relationships` table - family/political connections
- `unified_persons` table - person deduplication
- `name_mappings` table - name variations
- `company_affiliations` table - business connections (if we correlate with SEC data)

## How to Use

### Prerequisites

```bash
pip install -r requirements_chromadb.txt  # Already includes datasets, asyncpg, etc.
```

### Run Integration

```bash
python integrate_huggingface_to_dynasty.py
```

### What Happens

1. **Downloads HuggingFace Data** (~5-10 minutes)
   - 45,400 persons
   - 86,200 memberships

2. **Loads Existing Database Data**
   - Indexes existing persons
   - Loads current party list

3. **Updates Party List**
   - Adds new parties found in memberships
   - Updates occurrence counts

4. **Corrects Existing Names**
   - Fills in missing middle names
   - Adds missing suffixes
   - Updates canonical names

5. **Integrates New Data**
   - Adds new person-membership records
   - Updates existing records with better data
   - Maintains data quality

6. **Identifies Relationships**
   - Groups persons by last name
   - Generates report: `huggingface_potential_relationships.txt`

## Output Files

### `huggingface_potential_relationships.txt`
Lists families with multiple politicians for manual review:

```
AQUINO (15 persons):
  - BENIGNO SIMEON AQUINO III
  - CORAZON COJUANGCO AQUINO
  - AGAPITO AQUINO JR.
  ...

MARCOS (12 persons):
  - FERDINAND ROMUALDEZ MARCOS JR.
  - IMELDA ROMUALDEZ MARCOS
  - IMEE ROMUALDEZ MARCOS
  ...
```

Use this to:
- Verify dynasty connections
- Add relationships to `relationships` table
- Update `fat` (dynasty) field

## Data Quality

### Strengths
✅ **Official source** - From ASoG Participate Project  
✅ **Comprehensive** - 2004-2016 coverage  
✅ **Structured** - Consistent field names  
✅ **Clean** - Properly normalized names  
✅ **Geographic** - Complete region/province/locality  

### Limitations
⚠️ **Time range** - Only 2004-2016 (complement with your existing 2020-2025 data)  
⚠️ **No relationships** - Family connections not explicitly defined (must be inferred)  
⚠️ **Elected officials only** - No appointed officials  

## Integration Strategy

### Conservative Approach (Recommended)
The script uses an **additive, non-destructive** approach:

1. **Never overwrites existing good data**
   - Uses `COALESCE(NULLIF($new, ''), existing)` pattern
   - Only fills in missing fields

2. **Deduplicates carefully**
   - Checks canonical_name + position + year + province
   - Updates if exact match found, inserts if new

3. **Maintains data provenance**
   - Existing records keep their IDs
   - New records clearly identifiable by date range (2004-2016)

### Aggressive Approach (Advanced)
If you want to **replace** existing data:

Modify the update query in `integrate_persons_and_memberships()`:
```python
# Change from:
first_name = COALESCE(NULLIF($1, ''), first_name)

# To:
first_name = $1
```

**⚠️ Warning:** This will overwrite existing data. Test on a backup first!

## Complementary Data Sources

This HuggingFace data **complements** your existing data:

| Data Source | Time Period | Coverage |
|-------------|-------------|----------|
| ASoG Dynasty Data | 2004-2016 | Local elected officials |
| Your Current DB | 2020-2025+ | All officials (elected + appointed) |
| **Combined** | **2004-2025** | **Complete coverage** |

## Next Steps

### 1. Review Potential Relationships
```bash
cat huggingface_potential_relationships.txt | less
```

Identify families that are clearly dynasties, then add to `relationships` table:

```sql
-- Example: Add Aquino family relationships
INSERT INTO relationships (person_id, related_person_id, relationship_type, confidence_level)
SELECT p1.id, p2.id, 1, 10  -- 1 = father/son, 10 = high confidence
FROM political_dynasties p1, political_dynasties p2
WHERE p1.canonical_name = 'BENIGNO SIMEON AQUINO JR.'
AND p2.canonical_name = 'BENIGNO SIMEON AQUINO III';
```

### 2. Update Dynasty Classification
Mark persons as dynasty members:

```sql
-- Update fat=1 for families with multiple politicians
UPDATE political_dynasties
SET fat = 1
WHERE last_name IN (
    SELECT last_name 
    FROM political_dynasties 
    WHERE winner = true
    GROUP BY last_name 
    HAVING COUNT(*) >= 2
);
```

### 3. Verify Party Affiliations
Check the updated party list:

```sql
SELECT party_name, occurrences 
FROM party_list 
ORDER BY occurrences DESC 
LIMIT 20;
```

### 4. Cross-Reference with SEC Data
If persons appear in both political and business contexts:

```sql
-- Find politicians who are also business owners
SELECT DISTINCT 
    pd.canonical_name,
    pd.position,
    ca.company_name,
    ca.role
FROM political_dynasties pd
JOIN company_affiliations ca ON UPPER(ca.person_name) = pd.canonical_name
WHERE ca.company_name IS NOT NULL;
```

## Troubleshooting

### "Too many duplicates being created"
Adjust the duplicate detection in `integrate_persons_and_memberships()`:
- Add more fields to the matching query (middle_name, party, etc.)
- Use fuzzy matching for name variations

### "Party codes are wrong"
The script auto-generates codes from party initials. To fix:
```sql
UPDATE party_list SET code = 'LP' WHERE party_name = 'Liberal Party';
UPDATE party_list SET code = 'NP' WHERE party_name = 'Nacionalista Party';
-- etc.
```

### "Names still have errors"
Run the name correction step multiple times, or manually review:
```sql
SELECT first_name, last_name, middle_name, suffix
FROM political_dynasties
WHERE canonical_name IS NULL OR canonical_name = '';
```

## Performance Notes

- **First run**: 15-30 minutes (downloads + processes 131k records)
- **Subsequent runs**: 10-15 minutes (downloads cached)
- **Database impact**: Adds ~50-100k records (deduplicated)
- **Memory**: ~500MB peak (dataset in memory)

## Data Lineage

```
HuggingFace Dataset (bettergovph/raw-philippine-data)
    ↓
  persons.parquet (45,400 records)
  memberships.parquet (86,200 records)
    ↓
integrate_huggingface_to_dynasty.py
    ↓
Dynasty Database
    ├── political_dynasties (persons + positions)
    ├── party_list (party affiliations)
    ├── relationships (future: family connections)
    └── unified_persons (future: deduplication)
```

## License

- **HuggingFace Dataset**: CC0 1.0 Universal (Public Domain)
- **Integration Script**: Same as project license
- **Resulting Database**: Your data, your choice

## Support

Issues? Questions?
- Check the generated report files
- Review database logs
- Check existing similar names: `SELECT * FROM political_dynasties WHERE last_name = 'AQUINO' ORDER BY year;`

## Credits

- **Data Source**: [BetterGov.PH](https://bettergov.ph) + [ASoG Participate Project](https://www.inclusivedemocracy.ph/)
- **Original Curator**: BetterGov.PH team
- **Integration**: This script




