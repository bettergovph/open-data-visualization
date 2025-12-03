# AMO Relationships → Constellation Cache Integration

## Overview

This document explains how AMO (Authorized Managing Officer) relationships added via `/philgeps#amo` become part of the relationship constellation cache when regenerated.

## Data Flow

### 1. AMO Relationships Discovery

**Location**: `scripts/generate_philgeps_amo_cache.py`

The AMO cache generation script discovers relationships by:

1. **Direct Matches**: AMOs who are themselves elected officials
   - Matches PCAB AMO names to `political_dynasties` table
   - Checks if they have elected positions

2. **Indirect Matches**: AMOs related to elected officials
   - Uses `find_related_elected_officials()` function (lines 120-163)
   - Queries the `relationships` table to find family relationships
   - Looks for relationships where:
     - The AMO (person_id) is related to an elected official (related_person_id)
     - Relationship types are family relationships (IDs 1-13: Father, Mother, Son, Daughter, Husband, Wife, Brother, Sister, Uncle, Aunt, Nephew, Niece, Cousin)
     - The related person is an elected official

```python
# From generate_philgeps_amo_cache.py lines 127-149
relationships = await dynasty_conn.fetch("""
    SELECT r.related_person_id, ct.name as relationship_type,
           p.first_name, p.last_name, p.middle_name,
           p.position, p.province, p.municipality_city, p.year
    FROM relationships r
    JOIN connection_types ct ON r.relationship_type = ct.id
    JOIN political_dynasties p ON r.related_person_id = p.id
    WHERE r.person_id = $1
      AND r.relationship_type = ANY($2::int[])
      AND (p.position_category IN ('Elected Officials', ...) OR ...)
""", person_id, family_type_ids)
```

### 2. Relationships Table Structure

**Key Table**: `relationships`

The `relationships` table stores all relationship connections:
- `person_id`: The person who has the relationship
- `related_person_id`: The person they are related to
- `relationship_type`: Foreign key to `connection_types` table
- `relationship_description`: Text description of the relationship
- `source_url`: Optional source URL
- `created_by`: Who created the relationship (e.g., 'LLM_Analysis', 'AMO_Verification')

### 3. Constellation Cache Generation

**Location**: `scripts/database/generate_relationship_constellations_cache.py`

The constellation cache reads from the `relationships` table to build relationship chains:

1. **Initial Chains** (lines 170-219):
   - Queries `relationships` table for starting relationships
   - Filters for relationships between different families
   - Creates initial chain records

2. **Recursive Extension** (lines 234-363):
   - Recursively extends chains by following relationships
   - Uses `recursive_extend()` function to build longer chains
   - Stops when hitting duplicate nodes or max depth (11 levels)

3. **Query Pattern**:
```python
# From generate_relationship_constellations_cache.py lines 265-313
ext1_query = """
    SELECT 
        r.related_person_id as next_person_id,
        COALESCE(r.normalized_description, r.relationship_description) as relationship_description,
        r.source_url,
        p2.last_name,
        p2.first_name,
        p2.position
    FROM relationships r
    JOIN political_dynasties p2 ON r.related_person_id = p2.id
    WHERE r.person_id = $1
      AND r.related_person_id != ALL($2::int[])
    ...
"""
```

### 4. How AMO Relationships Become Part of Constellations

**Prerequisites**: AMO relationships must be in the `relationships` table first.

When AMO relationships are added:

1. **If AMO is already in `political_dynasties` table**:
   - Relationship is added to `relationships` table
   - AMO → Elected Official relationship is stored
   - Example: "AMO_NAME is Son of ELECTED_OFFICIAL"

2. **When constellation cache is regenerated**:
   - Script reads from `relationships` table
   - AMO relationships are included in the initial chains query
   - Chains are extended recursively from AMO relationships
   - AMO becomes a node in the relationship network

3. **Result**:
   - AMO appears in constellation visualizations
   - Chains connecting through AMOs are discovered
   - Example chain: `Person A → AMO → Elected Official → Person B`

### 5. Integration Points

**Key Integration**: Both scripts read from the same `relationships` table:

- `generate_philgeps_amo_cache.py`: Reads relationships to identify indirect AMO matches
- `generate_relationship_constellations_cache.py`: Reads relationships to build constellation chains

**Important**: The AMO cache generation script **does not write** to the `relationships` table. It only reads existing relationships. Relationships must be added through:
- Manual database inserts
- CSV import scripts (e.g., `process_llm_csv_results.py`)
- Other relationship import processes

### 6. Regeneration Process

To include new AMO relationships in the constellation cache:

1. **Ensure relationships are in database**:
   ```sql
   -- Verify AMO relationships exist
   SELECT r.*, ct.name as relationship_type
   FROM relationships r
   JOIN connection_types ct ON r.relationship_type = ct.id
   JOIN political_dynasties p1 ON r.person_id = p1.id
   JOIN political_dynasties p2 ON r.related_person_id = p2.id
   WHERE p1.first_name = 'AMO_FIRST_NAME'
     AND p1.last_name = 'AMO_LAST_NAME'
   ```

2. **Regenerate AMO cache** (optional, for AMO tab):
   ```bash
   python3 scripts/generate_philgeps_amo_cache.py
   ```

3. **Regenerate constellation cache**:
   ```bash
   python3 scripts/database/generate_relationship_constellations_cache.py
   ```

4. **Result**: 
   - New relationships appear in constellation visualizations
   - AMO nodes are included in relationship networks
   - Chains connecting through AMOs are discovered

### 7. Example Flow

**Scenario**: AMO "JOHN DOE" is the son of "JANE DOE" (Mayor)

1. **Relationship added to database**:
   ```sql
   INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, created_by)
   VALUES (
     (SELECT id FROM political_dynasties WHERE first_name = 'JOHN' AND last_name = 'DOE'),
     (SELECT id FROM political_dynasties WHERE first_name = 'JANE' AND last_name = 'DOE'),
     3,  -- Son relationship type
     'Son of JANE DOE (Mayor)',
     'AMO_Verification'
   );
   ```

2. **AMO cache regeneration**:
   - `find_related_elected_officials()` finds the relationship
   - AMO appears in indirect matches
   - Shows in `/philgeps#amo` tab

3. **Constellation cache regeneration**:
   - Initial chains query includes the relationship
   - Chains are extended from JOHN DOE → JANE DOE
   - Any chains connecting to JANE DOE can now extend through JOHN DOE
   - JOHN DOE appears as a node in constellation visualizations

### 8. Key Files

- **AMO Cache Generation**: `scripts/generate_philgeps_amo_cache.py`
- **Constellation Cache Generation**: `scripts/database/generate_relationship_constellations_cache.py`
- **Relationship Table Schema**: `database/connection_table_specification.md`
- **Relationship Import Scripts**: 
  - `family_analysis/family_parser/process_llm_csv_results.py`
  - `family_analysis/family_parser/update_dynasty_relationships.py`

### 9. Notes

- AMO relationships must use standard relationship types from `connection_types` table
- Family relationship types (1-13) are used for indirect AMO matches
- The constellation cache includes all relationships, not just family relationships
- Both caches are independent but share the same source of truth (`relationships` table)
- Regenerating the constellation cache will include all relationships in the `relationships` table, including newly added AMO relationships



