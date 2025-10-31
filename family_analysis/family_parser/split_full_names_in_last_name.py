#!/usr/bin/env python3
"""
Split full names that are incorrectly stored in the last_name field.

Example: "WILLIAM B. FUENTEBELLA" in last_name should become:
- first_name: "WILLIAM"
- middle_name: "B."
- last_name: "FUENTEBELLA"
"""

import asyncio
import asyncpg
import os
import re
from dotenv import load_dotenv


def split_full_name(full_name: str):
    """
    Split a full name into first, middle, and last name.
    Handles patterns like:
    - "WILLIAM B. FUENTEBELLA" -> ("WILLIAM", "B.", "FUENTEBELLA")
    - "WILLIAM B FUENTEBELLA" -> ("WILLIAM", "B", "FUENTEBELLA")
    - "JOHN MICHAEL SMITH" -> ("JOHN", "MICHAEL", "SMITH")
    - "JUAN DELA CRUZ" -> ("JUAN", None, "DELA CRUZ")
    """
    if not full_name or len(full_name.strip()) < 3:
        return None, None, None
    
    # Normalize spacing
    name = re.sub(r'\s+', ' ', full_name.strip().upper())
    parts = name.split()
    
    if len(parts) < 2:
        return None, None, None
    
    # Pattern 1: Has middle initial(s) with period(s) - "WILLIAM B. FUENTEBELLA"
    # Look for pattern: WORD [LETTER(S).] WORD(S)
    if len(parts) >= 3:
        # Check if middle part looks like an initial (single or double letter with optional period)
        middle_pattern = re.match(r'^([A-Z])\.?([A-Z])?\.?$', parts[1])
        if middle_pattern:
            first = parts[0]
            middle = parts[1] if '.' in parts[1] else parts[1] + '.'
            last = ' '.join(parts[2:])
            return first, middle, last
        
        # Pattern 2: Three words - assume first, middle, last
        if len(parts) == 3:
            first = parts[0]
            middle = parts[1]
            last = parts[2]
            return first, middle, last
    
    # Pattern 3: Two words - first and last (no middle)
    if len(parts) == 2:
        return parts[0], None, parts[1]
    
    # Pattern 4: Four or more words
    # Try to detect if there's a middle initial
    # First word is first name, last word(s) are last name
    # Middle words could be middle name(s)
    if len(parts) >= 4:
        # Check if second part is a middle initial
        if re.match(r'^[A-Z]\.?([A-Z])?\.?$', parts[1]):
            first = parts[0]
            middle = parts[1] if '.' in parts[1] else parts[1] + '.'
            last = ' '.join(parts[2:])
            return first, middle, last
        else:
            # First name, then middle name(s), then last name(s)
            first = parts[0]
            # Last 1-2 words are typically the last name (handle compound surnames)
            if len(parts) >= 4:
                # Assume last 2 words are surname for compound names
                last = ' '.join(parts[-2:])
                middle = ' '.join(parts[1:-2]) if len(parts) > 3 else None
            else:
                last = parts[-1]
                middle = ' '.join(parts[1:-1]) if len(parts) > 2 else None
            return first, middle, last
    
    return None, None, None


async def split_full_names_in_last_name(conn, dry_run=True):
    """Find and split full names stored in last_name field"""
    
    print("🔍 FINDING FULL NAMES IN LAST_NAME FIELD")
    print("=" * 80)
    
    # Find rows where last_name looks like it contains a full name
    # Pattern: Has 3+ words, or has middle initial pattern (LETTER. LETTERS)
    # Also check for cases like "WILLIAM B. FUENTEBELLA" where first_name might be NULL or empty
    candidates = await conn.fetch("""
        SELECT 
            id,
            first_name,
            last_name,
            position,
            province,
            year
        FROM political_dynasties
        WHERE last_name IS NOT NULL 
          AND last_name <> ''
          AND (
            -- Case 1: Has 3 or more words (likely full name)
            (array_length(string_to_array(last_name, ' '), 1) >= 3)
            -- Case 2: Has middle initial pattern (e.g., "WILLIAM B. FUENTEBELLA")
            OR last_name ~* '^[A-Z]+ [A-Z]\\. [A-Z]+'
            OR last_name ~* '^[A-Z]+ [A-Z] [A-Z]+'
          )
          -- Include rows where first_name is missing or very generic/common
          AND (
            first_name IS NULL 
            OR first_name = '' 
            OR first_name IN ('WILLIAM', 'JOHN', 'JUAN', 'JOSE', 'MARIA', 'JOSEPH', 'FRANCIS', 'ANTONIO', 'CARLOS')
            -- Or first_name doesn't match what's in last_name (indicating incorrect split)
            OR first_name NOT IN (SELECT unnest(string_to_array(last_name, ' ')))
          )
        ORDER BY 
            CASE WHEN first_name IS NULL OR first_name = '' THEN 0 ELSE 1 END,
            LENGTH(last_name) DESC
        LIMIT 500
    """)
    
    print(f"📊 Found {len(candidates)} candidates to process\n")
    
    if not candidates:
        print("✅ No candidates found.")
        return
    
    # Show preview
    print("📋 Preview of names to split (first 20):")
    print("-" * 80)
    for row in candidates[:20]:
        print(f"   ID: {row['id']:8} | First: {str(row['first_name'])[:20]:20} | Last: {str(row['last_name'])[:50]}")
    if len(candidates) > 20:
        print(f"   ... and {len(candidates) - 20} more")
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No rows will be updated.")
        print("   Run with --execute flag to actually update the rows.\n")
        return
    
    print("\n🔄 Splitting names...")
    updated = 0
    skipped = 0
    
    for row in candidates:
        full_name = row['last_name']
        existing_first = row['first_name'] if row['first_name'] else ''
        
        # If first_name is already set but is generic, use the full name from last_name
        # Otherwise, split the last_name
        if existing_first and existing_first in ['WILLIAM', 'JOHN', 'JUAN', 'JOSE', 'MARIA', 'JOSEPH', 'FRANCIS', 'ANTONIO', 'CARLOS']:
            # First name is generic - parse the full name from last_name
            first, middle, last = split_full_name(full_name)
        else:
            # No first_name or first_name looks valid - still check if last_name has more info
            # If last_name has 3+ words, it might contain the full name
            if len(full_name.split()) >= 3:
                first, middle, last = split_full_name(full_name)
                # If we already have a first_name and it's not in the parsed result, keep existing
                if existing_first and existing_first not in full_name.upper():
                    # Keep existing first_name, just update middle and last
                    first = existing_first
            else:
                # Keep existing structure, just split if needed
                first, middle, last = split_full_name(full_name)
                if existing_first:
                    first = existing_first
        
        if not first or not last:
            skipped += 1
            continue
        
        try:
            # Update the row
            await conn.execute("""
                UPDATE political_dynasties
                SET 
                    first_name = COALESCE(NULLIF(TRIM($1), ''), first_name),
                    middle_name = COALESCE(NULLIF(TRIM($2), ''), middle_name),
                    last_name = $3
                WHERE id = $4
            """, first, middle, last, row['id'])
            
            updated += 1
            if updated <= 10:  # Show first 10 updates
                old_first = existing_first or '(empty)'
                print(f"   ✅ ID {row['id']:8}: First: '{old_first}' -> '{first}', Middle: '{middle or 'None'}', Last: '{full_name}' -> '{last}'")
        except Exception as e:
            print(f"   ❌ Error updating ID {row['id']}: {e}")
            skipped += 1
    
    print(f"\n✅ Updated {updated} rows")
    print(f"⚠️  Skipped {skipped} rows (could not parse or error)")


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
        await split_full_names_in_last_name(conn, dry_run=dry_run)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

