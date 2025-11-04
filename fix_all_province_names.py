#!/usr/bin/env python3
import asyncio
import asyncpg
import os
import re
from dotenv import load_dotenv
from fix_province_names_proper import parse_name_with_middle

load_dotenv()

async def fix_all_entries():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database='dynasty'
    )
    
    print("=" * 80)
    print("FIXING ALL ENTRIES WITH PROVINCE NAMES AND NAME PARSING ISSUES")
    print("=" * 80)
    
    # 1. DELETE entries where name is just a province name
    print("\n1. Deleting entries where name is just a province name...")
    delete_query = '''
        DELETE FROM political_dynasties
        WHERE id IN (
            SELECT p.id
            FROM political_dynasties p
            WHERE (
                (UPPER(p.first_name) = 'ILOCOS' AND UPPER(p.last_name) = 'NORTE')
                OR (UPPER(p.first_name) = 'ILOCOS' AND UPPER(p.last_name) = 'SUR')
                OR (UPPER(p.first_name) = 'LA' AND UPPER(p.last_name) = 'UNION')
                OR (UPPER(p.first_name) = 'NEGROS' AND UPPER(p.last_name) = 'OCCIDENTAL')
                OR (UPPER(p.first_name) = 'MISAMIS' AND UPPER(p.last_name) = 'OCCIDENTAL')
                OR (UPPER(p.first_name) = 'MISAMIS' AND UPPER(p.last_name) = 'ORIENTAL')
                OR (UPPER(p.first_name) = 'DAVAO DEL' AND UPPER(p.last_name) = 'NORTE')
                OR (UPPER(p.first_name) = 'SOUTHERN' AND UPPER(p.last_name) = 'LEYTE')
                OR (UPPER(p.first_name) = 'CAMARINES' AND UPPER(p.last_name) = 'SUR')
                OR (UPPER(p.first_name) = 'CAMARINES' AND UPPER(p.last_name) = 'NORTE')
            )
            AND p.id != 4041737  -- Exclude already fixed
        )
    '''
    deleted = await conn.execute(delete_query)
    print(f"   ✓ Deleted {deleted.split()[-1]} entries")
    
    # 2. FIX entries with province prefixes
    print("\n2. Fixing entries with province prefixes...")
    result1 = await conn.fetch('''
        SELECT p.id, p.first_name, p.last_name, p.middle_name, p.suffix, p.position
        FROM political_dynasties p
        WHERE (UPPER(p.first_name) LIKE 'LAGUNA %'
               OR UPPER(p.first_name) LIKE 'BATANGAS %'
               OR UPPER(p.first_name) LIKE 'BULACAN %'
               OR UPPER(p.first_name) LIKE 'PAMPANGA %'
               OR UPPER(p.first_name) LIKE 'CAVITE %'
               OR UPPER(p.first_name) LIKE 'QUEZON %'
               OR UPPER(p.first_name) LIKE 'CAMARINES NORTE %'
               OR UPPER(p.first_name) LIKE 'CAMARINES SUR %'
               OR UPPER(p.first_name) LIKE 'NEGROS OCCIDENTAL %'
               OR UPPER(p.first_name) LIKE 'NEGROS ORIENTAL %')
               AND p.id NOT IN (4041737, 4041714, 4041817, 4055492, 4056971)
    ''')
    
    fixed1 = 0
    for r in result1:
        full_name = f"{r['first_name']} {r['last_name']}".strip()
        new_first, new_middle, new_last, new_suffix = parse_name_with_middle(full_name)
        
        await conn.execute('''
            UPDATE political_dynasties
            SET first_name = $1, middle_name = NULLIF($2, ''), last_name = $3, suffix = NULLIF($4, '')
            WHERE id = $5
        ''', new_first, new_middle, new_last, new_suffix, r['id'])
        fixed1 += 1
    
    print(f"   ✓ Fixed {fixed1} entries")
    
    # 3. FIX entries where last_name starts with middle initial
    print("\n3. Fixing entries where last_name starts with middle initial...")
    result2 = await conn.fetch('''
        SELECT p.id, p.first_name, p.last_name, p.middle_name, p.suffix, p.position
        FROM political_dynasties p
        WHERE p.last_name ~ '^[A-Z]\. '
           AND (p.middle_name IS NULL OR p.middle_name = '')
           AND p.first_name IS NOT NULL
           AND p.last_name IS NOT NULL
    ''')
    
    fixed2 = 0
    for r in result2:
        full_name = f"{r['first_name']} {r['last_name']}".strip()
        new_first, new_middle, new_last, new_suffix = parse_name_with_middle(full_name)
        
        await conn.execute('''
            UPDATE political_dynasties
            SET first_name = $1, middle_name = NULLIF($2, ''), last_name = $3, suffix = NULLIF($4, '')
            WHERE id = $5
        ''', new_first, new_middle, new_last, new_suffix, r['id'])
        fixed2 += 1
    
    print(f"   ✓ Fixed {fixed2} entries")
    
    # 4. FIX entries where suffix is embedded in last_name
    print("\n4. Fixing entries where suffix is embedded in last_name...")
    result3 = await conn.fetch('''
        SELECT p.id, p.first_name, p.last_name, p.middle_name, p.suffix, p.position
        FROM political_dynasties p
        WHERE (p.last_name LIKE '% JR' OR p.last_name LIKE '% SR' 
               OR p.last_name LIKE '% II' OR p.last_name LIKE '% III'
               OR p.last_name LIKE '% IV')
           AND (p.suffix IS NULL OR p.suffix = '')
           AND p.first_name IS NOT NULL
           AND p.last_name IS NOT NULL
    ''')
    
    fixed3 = 0
    for r in result3:
        new_first, new_middle, new_last, new_suffix = parse_name_with_middle(
            f"{r['first_name']} {r['last_name']}".strip(),
            r['first_name'],
            r['last_name']
        )
        
        await conn.execute('''
            UPDATE political_dynasties
            SET first_name = $1, middle_name = NULLIF($2, ''), last_name = $3, suffix = NULLIF($4, '')
            WHERE id = $5
        ''', new_first, new_middle, new_last, new_suffix, r['id'])
        fixed3 += 1
    
    print(f"   ✓ Fixed {fixed3} entries")
    
    # 5. FIX entries where last_name is only a suffix
    print("\n5. Fixing entries where last_name is only a suffix...")
    result4 = await conn.fetch('''
        SELECT p.id, p.first_name, p.last_name, p.suffix, p.position
        FROM political_dynasties p
        WHERE UPPER(p.last_name) IN ('JR', 'SR', 'JR.', 'SR.', 'II', 'III', 'IV', 'V', 'VI')
           AND p.first_name IS NOT NULL
           AND (p.suffix IS NULL OR p.suffix = '')
    ''')
    
    fixed4 = 0
    for r in result4:
        new_first, new_middle, new_last, new_suffix = parse_name_with_middle(
            f"{r['first_name']} {r['last_name']}".strip(),
            r['first_name'],
            r['last_name']
        )
        
        await conn.execute('''
            UPDATE political_dynasties
            SET first_name = $1, middle_name = NULLIF($2, ''), last_name = $3, suffix = NULLIF($4, '')
            WHERE id = $5
        ''', new_first, new_middle, new_last, new_suffix, r['id'])
        fixed4 += 1
    
    print(f"   ✓ Fixed {fixed4} entries")
    
    await conn.close()
    
    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"  - Deleted entries: {deleted.split()[-1]}")
    print(f"  - Fixed entries with province prefixes: {fixed1}")
    print(f"  - Fixed entries with middle name in last_name: {fixed2}")
    print(f"  - Fixed entries with suffix in last_name: {fixed3}")
    print(f"  - Fixed entries with suffix-only last_name: {fixed4}")
    print(f"  - Total fixed: {fixed1 + fixed2 + fixed3 + fixed4}")
    print("=" * 80)
    print("\n✓ All fixes completed!")

if __name__ == '__main__':
    asyncio.run(fix_all_entries())

