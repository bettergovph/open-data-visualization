# Database Dumps

## Overview
This directory contains PostgreSQL database dumps for the BetterGovPH visualization project. The dumps are too large for GitHub (>100MB), so they are stored locally and excluded from version control.

## Available Dumps

### 1. Dynasty Database (`dynasty_dump.sql`)
- **Size**: 59M uncompressed, 7.8M compressed
- **Lines**: 407,908
- **Last Updated**: $(date +"%Y-%m-%d")
- **Contents**:
  - Political dynasties data with enhanced schema
  - Family relationships (spouse, parent-child, cousin-in-law, etc.)
  - Politician-contractor associations
  - Party-list representatives
  - **New**: Frasco family dynasty (Duke, Christina, Panphil, Aljew)
  - **New**: Enhanced columns (aliases, dynasty_family_id, birth_date, maiden_name, district)

### 2. PhilGEPS Database (`philgeps_dump.sql`)
- **Size**: 37M uncompressed, 7.8M compressed
- **Lines**: 129,090
- **Contents**:
  - Philippine Government Electronic Procurement System data
  - Contract awards and procurement records

### 3. Infrawatch Database (`infrawatch_dump.sql`)
- **Size**: 113M uncompressed, 15M compressed
- **Lines**: 187,484
- **Contents**:
  - Infrastructure project monitoring data
  - Combined data from DIME, SSP, and PhilGEPS sources
  - Project-congressman associations with temporal validation

## Schema Updates

### Political Dynasties Table
New columns added:
- `aliases TEXT[]` - Array of alternative names
- `dynasty_family_id VARCHAR(255)` - Dynasty family identifier (e.g., "Garcia-Frasco")
- `birth_date DATE` - Date of birth
- `maiden_name VARCHAR(255)` - Maiden name for married individuals
- `last_updated TIMESTAMP` - Last update timestamp
- `district VARCHAR(100)` - Congressional district

### New Tables Created

#### family_relationships
Tracks family connections between politicians:
- `person_id` → `related_person_id`
- Relationship types: spouse, parent, child, sibling, cousin-in-law, etc.
- Includes source, confidence level, and notes
- Unique constraint on (person_id, related_person_id, relationship_type)

#### politician_contractors
Associates politicians with contractors:
- Links politician_id to contractor names
- Includes match confidence scores
- Tracks sources and notes

#### politician_party_list
Tracks party-list representatives:
- Links politician_id to party names
- Includes party-list numbers
- Supports multiple party affiliations

## Restoring Dumps

### Restore Dynasty Database
```bash
source .env
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d dynasty < dynasty_dump.sql
# Or from compressed:
gunzip -c dynasty_dump.sql.gz | PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d dynasty
```

### Restore PhilGEPS Database
```bash
source .env
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d philgeps < philgeps_dump.sql
# Or from compressed:
gunzip -c philgeps_dump.sql.gz | PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d philgeps
```

### Restore Infrawatch Database
```bash
source .env
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d infrawatch < infrawatch_dump.sql
# Or from compressed:
gunzip -c infrawatch_dump.sql.gz | PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d infrawatch
```

## Creating New Dumps

To update the dumps after making changes:

```bash
source .env

# Dynasty database
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d dynasty --no-owner --no-acl --clean --if-exists > dynasty_dump.sql

# PhilGEPS database
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d philgeps --no-owner --no-acl --clean --if-exists > philgeps_dump.sql

# Infrawatch database
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d infrawatch --no-owner --no-acl --clean --if-exists > infrawatch_dump.sql

# Compress for storage
gzip -k dynasty_dump.sql philgeps_dump.sql infrawatch_dump.sql
```

## Notes

- Dumps include `--clean --if-exists` flags for safe restoration
- `--no-owner --no-acl` flags make dumps portable across different PostgreSQL installations
- Compressed `.gz` files are ~87% smaller than uncompressed dumps
- All dumps are excluded from git via `.gitignore`

## Frasco Family Dynasty

The dynasty database now includes the Frasco political family:

- **Duke Frasco** (Vincent Franco Domingo Frasco)
  - Born: October 27, 1980
  - Position: Congressman, 5th District Cebu, Deputy Speaker (19th Congress)
  - Previous: Mayor of Liloan (2007-2016)
  - Dynasty: Garcia-Frasco

- **Christina Garcia Frasco**
  - Born: December 25, 1981
  - Position: Secretary of Tourism
  - Previous: Mayor of Liloan (2016-2022)
  - Maiden name: Garcia
  - Dynasty: Garcia-Frasco
  - Daughter of Gwendolyn Garcia (Governor of Cebu)

- **Panphil "Dodong Daku" Frasco**
  - Position: Former Mayor of Liloan
  - Father of Duke Frasco
  - Dynasty: Garcia-Frasco

- **Aljew Frasco**
  - Position: Mayor of Liloan (2022-present)
  - Cousin-in-law of Duke Frasco
  - Dynasty: Garcia-Frasco

Family relationships are properly mapped in the `family_relationships` table.
