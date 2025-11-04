# Quick Start: HuggingFace Data Integration

## What You're Getting

From https://huggingface.co/datasets/bettergovph/raw-philippine-data:
- **45,400 persons** (politicians with proper names: first, middle, last, suffix, nickname)
- **86,200 memberships** (political positions + party affiliations 2004-2016)
- **High quality data** for correcting names, adding parties, identifying dynasties

## One-Command Setup

```bash
# Install dependencies
pip install -r requirements_chromadb.txt

# Run integration into dynasty database
python integrate_huggingface_to_dynasty.py
```

**Time:** 15-30 minutes  
**What it does:**
1. Downloads HuggingFace dataset
2. Updates `party_list` table with accurate parties
3. Corrects names in `political_dynasties` (fills missing middle names/suffixes)
4. Adds new person records (2004-2016 data)
5. Generates `huggingface_potential_relationships.txt` - families for manual review

## What Gets Updated in Your Dynasty Database

### ✅ `party_list` Table
- Adds missing political parties (LP, NP, NPC, UNA, LAKAS-CMD, etc.)
- Updates party occurrence counts
- Example: "Liberal Party" → Code: "LP", Occurrences: 15,234

### ✅ `political_dynasties` Table
- **Name corrections**: Fills in missing middle names and suffixes
- **New records**: Adds persons from 2004-2016 (complements your 2020-2025 data)
- **Party data**: Accurate party affiliations from official source
- **Geographic data**: Proper region/province/locality mappings

### 📝 Generated Reports

**`huggingface_potential_relationships.txt`** - Use this to:
- Identify dynasty families (same last name, multiple politicians)
- Add relationships to `relationships` table
- Update `fat` field (dynasty classification)

Example from report:
```
AQUINO (15 persons):
  - BENIGNO SIMEON AQUINO III
  - CORAZON COJUANGCO AQUINO
  ...

MARCOS (12 persons):
  - FERDINAND ROMUALDEZ MARCOS JR.
  - IMELDA ROMUALDEZ MARCOS
  ...
```

## After Integration

### 1. Review the Output
```bash
# Check summary
tail -50 output.log

# Review potential dynasties
less huggingface_potential_relationships.txt
```

### 2. Verify Party List
```sql
-- Top parties by occurrence
SELECT party_name, occurrences 
FROM party_list 
ORDER BY occurrences DESC 
LIMIT 20;
```

### 3. Check Corrected Names
```sql
-- Persons with newly added middle names
SELECT first_name, middle_name, last_name, suffix, canonical_name
FROM political_dynasties
WHERE middle_name IS NOT NULL 
AND year BETWEEN 2004 AND 2016
LIMIT 20;
```

### 4. Identify Dynasties
```sql
-- Families with multiple politicians (potential dynasties)
SELECT last_name, COUNT(*) as count
FROM political_dynasties
WHERE winner = true
GROUP BY last_name
HAVING COUNT(*) >= 2
ORDER BY count DESC
LIMIT 50;
```

### 5. Update Dynasty Classification
```sql
-- Mark families as dynasties (fat = 1)
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

## Optional: ChromaDB Semantic Search

If you also want semantic search over legislative documents:

```bash
# Load into ChromaDB for semantic search
python load_philippine_data_to_chromadb.py

# Query the data
python query_philippine_data.py
```

This creates a separate ChromaDB database for searching bills by meaning (not used by /dynasty)

## Data Sources

The integration pulls from the same source you cited in `/sources`:
- [BetterGov.PH Raw Philippine Data on HuggingFace](https://huggingface.co/datasets/bettergovph/raw-philippine-data)
- Original data: Ateneo School of Government (ASoG) Participate Project
- License: CC0 1.0 Universal (Public Domain)

## Files Created

| File | Purpose | Use |
|------|---------|-----|
| `integrate_huggingface_to_dynasty.py` | Main integration script | Run once to integrate |
| `load_philippine_data_to_chromadb.py` | Semantic search loader (optional) | For document search |
| `query_philippine_data.py` | Query ChromaDB (optional) | Interactive search |
| `HUGGINGFACE_DYNASTY_INTEGRATION.md` | Full documentation | Reference guide |
| `PHILIPPINE_DATA_CHROMADB.md` | ChromaDB docs | Semantic search guide |

## Summary

**What this solves:**
✅ Missing middle names and suffixes in your dynasty database  
✅ Incomplete party list table  
✅ Gaps in 2004-2016 political records  
✅ Need to identify dynasty families  
✅ Name normalization and corrections  

**What you get:**
- 131,000+ records of high-quality political data
- Proper name components (first, middle, last, suffix)
- Accurate party affiliations
- Foundation for dynasty relationship mapping
- Report of potential political families

**Time investment:**
- Initial run: 30 minutes
- Review reports: 1-2 hours
- Update relationships: Ongoing as you identify dynasties

## Next Steps

1. ✅ Run `integrate_huggingface_to_dynasty.py`
2. ✅ Review `huggingface_potential_relationships.txt`
3. ✅ Verify party_list table
4. ✅ Mark dynasty families (update `fat` field)
5. ✅ Add relationships to `relationships` table for confirmed dynasties

## Questions?

- Full docs: `HUGGINGFACE_DYNASTY_INTEGRATION.md`
- ChromaDB guide: `PHILIPPINE_DATA_CHROMADB.md`
- Dataset source: https://huggingface.co/datasets/bettergovph/raw-philippine-data




