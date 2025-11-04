#!/usr/bin/env python3
"""
Properly fix Marcos and Romualdez names with correct first_name, middle_name, last_name, suffix structure.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv


async def fix_marcos_names_properly():
    load_dotenv('.env')
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    print("=" * 80)
    print("PROPERLY FIXING MARCOS & ROMUALDEZ NAME STRUCTURE")
    print("=" * 80)
    
    # Fix Ferdinand Marcos Jr. - should be: first=FERDINAND, middle=ROMUALDEZ, last=MARCOS, suffix=JR.
    print("\n1️⃣  Fixing FERDINAND MARCOS JR. structure...")
    
    await conn.execute("""
        UPDATE political_dynasties
        SET first_name = 'FERDINAND',
            middle_name = 'ROMUALDEZ',
            last_name = 'MARCOS',
            suffix = 'JR.',
            canonical_name = 'FERDINAND MARCOS JR.'
        WHERE canonical_name = 'FERDINAND MARCOS JR.'
           OR (first_name LIKE '%FERDINAND%' AND (last_name LIKE '%MARCOS%' OR middle_name LIKE '%MARCOS%') 
               AND (last_name LIKE '%JR%' OR middle_name LIKE '%JR%' OR first_name LIKE '%BONGBONG%'))
    """)
    
    count = await conn.fetchval("""
        SELECT COUNT(*) FROM political_dynasties
        WHERE canonical_name = 'FERDINAND MARCOS JR.'
    """)
    print(f"  ✓ Fixed {count} records for Ferdinand Marcos Jr.")
    
    # Fix Imelda Marcos - first=IMELDA, middle=REMEDIOS, last=MARCOS
    print("\n2️⃣  Fixing IMELDA MARCOS structure...")
    
    await conn.execute("""
        UPDATE political_dynasties
        SET first_name = 'IMELDA',
            middle_name = 'REMEDIOS',
            last_name = 'MARCOS',
            suffix = NULL,
            canonical_name = 'IMELDA MARCOS'
        WHERE canonical_name = 'IMELDA MARCOS'
           OR (first_name LIKE '%IMEL%' AND last_name = 'MARCOS' AND middle_name IS NULL)
    """)
    
    count = await conn.fetchval("""
        SELECT COUNT(*) FROM political_dynasties
        WHERE canonical_name = 'IMELDA MARCOS'
    """)
    print(f"  ✓ Fixed {count} records for Imelda Marcos")
    
    # Fix Imee Marcos - first=IMEE, middle=REMEDIOS, last=MARCOS
    print("\n3️⃣  Fixing IMEE MARCOS structure...")
    
    await conn.execute("""
        UPDATE political_dynasties
        SET first_name = 'IMEE',
            middle_name = 'REMEDIOS',
            last_name = 'MARCOS',
            suffix = NULL,
            canonical_name = 'IMEE MARCOS'
        WHERE canonical_name = 'IMEE MARCOS'
           OR (first_name LIKE '%IME%' AND last_name = 'MARCOS')
    """)
    
    count = await conn.fetchval("""
        SELECT COUNT(*) FROM political_dynasties
        WHERE canonical_name = 'IMEE MARCOS'
    """)
    print(f"  ✓ Fixed {count} records for Imee Marcos")
    
    # Fix Ferdinand Martin Romualdez - first=FERDINAND, middle=MARTIN, last=ROMUALDEZ
    print("\n4️⃣  Fixing FERDINAND MARTIN ROMUALDEZ structure...")
    
    await conn.execute("""
        UPDATE political_dynasties
        SET first_name = 'FERDINAND',
            middle_name = 'MARTIN',
            last_name = 'ROMUALDEZ',
            suffix = NULL,
            canonical_name = 'FERDINAND MARTIN ROMUALDEZ'
        WHERE canonical_name = 'FERDINAND MARTIN ROMUALDEZ'
           OR (first_name LIKE '%FERDINAND%' AND last_name = 'ROMUALDEZ')
    """)
    
    count = await conn.fetchval("""
        SELECT COUNT(*) FROM political_dynasties
        WHERE canonical_name = 'FERDINAND MARTIN ROMUALDEZ'
    """)
    print(f"  ✓ Fixed {count} records for Ferdinand Martin Romualdez")
    
    # Verify the fixes
    print("\n" + "=" * 80)
    print("VERIFICATION OF CORRECTED NAMES:")
    print("=" * 80)
    
    names_to_check = [
        'FERDINAND MARCOS JR.',
        'FERDINAND MARCOS SR.',
        'IMELDA MARCOS',
        'IMEE MARCOS',
        'FERDINAND MARTIN ROMUALDEZ'
    ]
    
    for canonical in names_to_check:
        records = await conn.fetch("""
            SELECT id, first_name, middle_name, last_name, suffix, position, province, year
            FROM political_dynasties
            WHERE canonical_name = $1
            ORDER BY year NULLS LAST
            LIMIT 3
        """, canonical)
        
        print(f"\n{canonical}:")
        if records:
            for r in records:
                name_parts = [r['first_name'], r['middle_name'], r['last_name'], r['suffix']]
                full_name = ' '.join([p for p in name_parts if p])
                print(f"  ✓ ID {r['id']:7}: {full_name:40} ({r['position'] or 'N/A'}, {r['year'] or 'N/A'})")
        else:
            print(f"  ⚠️ No records found!")
    
    await conn.close()
    print("\n" + "=" * 80)
    print("✅ NAME STRUCTURE CORRECTIONS COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(fix_marcos_names_properly())




