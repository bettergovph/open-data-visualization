#!/usr/bin/env python3
"""
Delete rows containing document text instead of actual names or positions.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv


async def delete_document_text_rows(conn, dry_run=True):
    """Delete rows with document text in name or position fields"""
    
    print("🗑️  DELETING ROWS WITH DOCUMENT TEXT")
    print("=" * 80)
    
    if dry_run:
        print("⚠️  DRY RUN MODE - No rows will be deleted.")
        print("   Run with --execute flag to actually delete the rows.\n")
    
    # Build the deletion query
    # Exclude names that look like valid names (contain middle initials, proper capitalization, etc.)
    query = """
        DELETE FROM political_dynasties
        WHERE (
            (first_name IS NOT NULL AND first_name <> '' AND (
                LENGTH(first_name) > 50
                OR (
                    first_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
                    AND NOT first_name ~* '^[A-Z][A-Z ]+[A-Z]\\.? [A-Z]'  -- Exclude names with middle initials like "WILLIAM B."
                    AND NOT first_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z]'     -- Exclude proper name format
                )
            ))
            OR (last_name IS NOT NULL AND last_name <> '' AND (
                LENGTH(last_name) > 50
                OR (
                    last_name ~* '.*(SHALL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|STANDARD|CODE|REQUIREMENT).*'
                    AND NOT last_name ~* '^[A-Z][A-Z ]+[A-Z]\\.? [A-Z]'     -- Exclude names like "WILLIAM B. FUENTEBELLA"
                    AND NOT last_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z]'       -- Exclude proper name format
                    AND NOT last_name ~* '^[A-Z][A-Z]+-[A-Z][A-Z]+'          -- Exclude hyphenated names like "BALINDONG-PADATE"
                )
                -- Don't delete if it looks like a valid name structure (has middle initial or proper format)
                AND NOT (
                    last_name ~* '^[A-Z][A-Z ]+ [A-Z]\\. [A-Z]' OR          -- Pattern like "WILLIAM B. FUENTEBELLA"
                    last_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z][a-z]+' OR     -- Pattern like "William B. Fuentebella"
                    (LENGTH(last_name) < 80 AND last_name ~* '^[A-Z]+ [A-Z]+ [A-Z]+')  -- Three word structure likely a name
                )
            ))
            OR (position IS NOT NULL AND position <> '' AND (
                LENGTH(position) > 100
                OR position ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
            ))
        )
        -- Exclude rows where names look like valid Philippine names (have proper structure)
        AND NOT (
            (first_name ~* '^[A-Z][a-z]+' OR first_name ~* '^[A-Z]{2,}')    -- Starts with capital letter(s)
            AND (last_name ~* '^[A-Z][a-z]+' OR last_name ~* '^[A-Z]{2,}')  -- Last name also looks valid
            AND (
                last_name ~* '.*[A-Z]\\. [A-Z]' OR                          -- Has middle initial pattern
                (LENGTH(first_name) < 30 AND LENGTH(last_name) < 30)        -- Reasonable length
            )
        )
    """
    
    # First, count what will be deleted (with exclusions for valid names)
    count_query = """
        SELECT COUNT(DISTINCT id)
        FROM political_dynasties
        WHERE (
            (first_name IS NOT NULL AND first_name <> '' AND (
                LENGTH(first_name) > 50
                OR (
                    first_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
                    AND NOT first_name ~* '^[A-Z][A-Z ]+[A-Z]\\.? [A-Z]'
                    AND NOT first_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z]'
                )
            ))
            OR (last_name IS NOT NULL AND last_name <> '' AND (
                LENGTH(last_name) > 50
                OR (
                    last_name ~* '.*(SHALL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|STANDARD|CODE|REQUIREMENT).*'
                    AND NOT last_name ~* '^[A-Z][A-Z ]+[A-Z]\\.? [A-Z]'
                    AND NOT last_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z]'
                    AND NOT last_name ~* '^[A-Z][A-Z]+-[A-Z][A-Z]+'
                )
                AND NOT (
                    last_name ~* '^[A-Z][A-Z ]+ [A-Z]\\. [A-Z]' OR
                    last_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z][a-z]+' OR
                    (LENGTH(last_name) < 80 AND last_name ~* '^[A-Z]+ [A-Z]+ [A-Z]+')
                )
            ))
            OR (position IS NOT NULL AND position <> '' AND (
                LENGTH(position) > 100
                OR position ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
            ))
        )
        AND NOT (
            (first_name ~* '^[A-Z][a-z]+' OR first_name ~* '^[A-Z]{2,}')
            AND (last_name ~* '^[A-Z][a-z]+' OR last_name ~* '^[A-Z]{2,}')
            AND (
                last_name ~* '.*[A-Z]\\. [A-Z]' OR
                (LENGTH(first_name) < 30 AND LENGTH(last_name) < 30)
            )
        )
    """
    
    count = await conn.fetchval(count_query)
    print(f"📊 Rows to delete: {count:,}\n")
    
    if count == 0:
        print("✅ No rows to delete. Database is clean!")
        return
    
    if dry_run:
        print("⚠️  DRY RUN - Would delete the above rows.")
        print("   Run with --execute to proceed with deletion.")
        return
    
    # Execute deletion
    print("🗑️  Deleting rows...")
    result = await conn.execute(query)
    
    # Extract count from result message
    deleted_count = result.split()[-1] if result else "0"
    print(f"✅ Deleted {deleted_count} rows containing document text.")


async def main():
    load_dotenv()
    
    import sys
    dry_run = '--execute' not in sys.argv
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        await delete_document_text_rows(conn, dry_run=dry_run)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

