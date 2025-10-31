#!/usr/bin/env python3
"""
1. Remove "SGD." (signed) prefix from names
2. Delete document fragment entries from BAC positions
3. Generate clean list of legitimate BAC titleholders
"""

import asyncio
import asyncpg
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime


def load_env_from_dotenv() -> None:
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[2]
    env_path = root / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    load_env_from_dotenv()
    load_dotenv()
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


def is_document_fragment(first_name: str, last_name: str, position: str) -> bool:
    """Check if a record is a document fragment"""
    first = (first_name or '').upper().strip()
    last = (last_name or '').upper().strip()
    pos = (position or '').upper().strip()
    
    # Document fragment patterns
    fragment_patterns = [
        # Bridge/structure fragments
        (first.startswith('BACK') or 'BACK' in first) and 'BAC' in pos,
        'STRUCTURE' in first and 'BAC' in pos,
        'BRIDGE' in first and ('BACK' in first or 'BAC' in pos),
        'BEG.' in first or 'BEGINING' in first,
        'FILL' in first and 'BAC' in pos,
        'DIAPHRAGM' in first or 'BACKWALL' in first,
        'DRAIN' in first and 'BAC' in pos,
        
        # Place name fragments (not positions)
        first in ('A', 'L', 'O', 'K', 'EA', 'AIN', 'MTS.', 'N', 'RAIN') and 'BAC' in pos,
        'CALIPAYAN' in first and 'CATAGBAC' in pos,
        'BUYACAOAN' in first and 'BADEO BAC' in pos,
        'SINAIT' in first and 'BALACBAC' in pos,
        'SPIRITU' in first and 'BALACBAC' in pos,
        
        # Technical/construction fragments
        'COMPLETE MANNER' in first,
        'TYHCA' in first,
        'ENGINEERING SECTION' in first or 'NEERING SECTION' in first,
        'INTERSECTIONS' in first,
        'SHADE COMBINATION' in first,
        'COLOR SHADE' in first,
        'HYDRAULIC' in first and 'BAC' in pos,
        'CYCLE COSTS' in first,
        'PHOTO' in first and 'BAC' in pos,
        'ROOM ROOM' in first,
        'CCTV' in first or 'STORAGE RADIO' in pos,
        'DRIVEWAY' in pos and 'BAC' in pos,
        'ELBAC' in pos or 'NORABAC' in pos,
        'ELBAC' in pos or 'ELBAC' in pos,
        'SNOISIVORP' in first or 'RIEHT' in first,
        
        # Common words that indicate fragments
        (len(first.split()) == 1 and len(first) <= 3) and ('BAC' in pos and 'BAC' not in first),
        'TOR' in first and len(first.split()) <= 2,
        'THK' in first,
        'MM' in first and len(first.split()) <= 2,
        
        # Other suspicious patterns
        'MAP' in first and 'BAC' in pos,
        'LOCATION' in first and 'BAC' in pos,
        'NOTES' in first or 'ALSEM' in first,
        'MANUAL ISSION' in first or 'MANUAL MISSION' in first,
        'ING OFFICE' in first,
        
        # Very short or suspicious names
        (first in ('A BRIDGE', 'N BRIDGE', 'MTS. BRIDGE', 'AIN BRIDGE', 'RAIN BRIDGE') and 'BACK OF BAC' in pos),
    ]
    
    return any(fragment_patterns)


async def remove_sgd_prefix(conn):
    """Remove SGD. prefix from names"""
    print("1. Removing 'SGD.' prefix from names...")
    
    # Find records with SGD. prefix
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE UPPER(TRIM(first_name)) LIKE 'SGD.%'
           OR UPPER(TRIM(first_name)) LIKE 'SGD %'
    ''')
    
    print(f"   Found {len(records)} records with SGD. prefix")
    
    updated = 0
    for record in records:
        first = record['first_name'] or ''
        # Remove SGD. or SGD prefix
        cleaned = re.sub(r'^SGD\.?\s*', '', first, flags=re.IGNORECASE).strip()
        
        if cleaned != first:
            await conn.execute('''
                UPDATE political_dynasties
                SET first_name = $1
                WHERE id = $2
            ''', cleaned, record['id'])
            updated += 1
    
    print(f"   ✅ Updated {updated} records")
    return updated


async def delete_bac_fragments(conn):
    """Delete document fragment entries from BAC positions"""
    print("\n2. Deleting document fragments from BAC positions...")
    
    # Get all BAC records
    all_bac = await conn.fetch('''
        SELECT id, first_name, last_name, position
        FROM political_dynasties
        WHERE UPPER(position) LIKE '%BAC%'
    ''')
    
    print(f"   Found {len(all_bac)} BAC-related records to analyze")
    
    fragment_ids = []
    for record in all_bac:
        if is_document_fragment(record['first_name'], record['last_name'], record['position']):
            fragment_ids.append(record['id'])
    
    print(f"   Identified {len(fragment_ids)} document fragments to delete")
    
    if fragment_ids:
        result = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE id = ANY($1::int[])
        ''', fragment_ids)
        
        deleted_num = int(str(result).split()[-1])
        print(f"   ✅ Deleted {deleted_num} document fragments")
        return deleted_num
    
    return 0


async def generate_clean_bac_list(conn):
    """Generate clean list of legitimate BAC titleholders"""
    print("\n3. Generating clean list of legitimate BAC titleholders...")
    
    records = await conn.fetch('''
        SELECT 
            id,
            first_name,
            last_name,
            position,
            province,
            municipality_city,
            region,
            year,
            party
        FROM political_dynasties
        WHERE UPPER(position) LIKE '%BAC%'
        ORDER BY 
            CASE 
                WHEN UPPER(position) LIKE '%CHAIRMAN%' OR UPPER(position) LIKE '%CHAIRPERSON%' THEN 1
                WHEN UPPER(position) LIKE '%MEMBER%' THEN 2
                WHEN UPPER(position) LIKE '%SECRETARIAT%' THEN 3
                WHEN UPPER(position) LIKE '%HEAD%' OR UPPER(position) LIKE '%DIRECTOR%' THEN 4
                WHEN UPPER(position) LIKE '%CHIEF%' THEN 5
                WHEN UPPER(position) LIKE '%ENGINEER%' THEN 6
                ELSE 7
            END,
            last_name,
            first_name
    ''')
    
    # Group by unique name+position
    unique_combos = {}
    for record in records:
        name = f"{record['first_name']} {record['last_name']}".strip()
        pos = record['position'] or ''
        key = (name.upper(), pos.upper())
        
        if key not in unique_combos:
            unique_combos[key] = {
                'name': name,
                'position': pos,
                'province': record['province'] or '',
                'municipality': record['municipality_city'] or '',
                'region': record['region'] or '',
                'year': record['year'],
                'count': 0,
                'ids': []
            }
        unique_combos[key]['count'] += 1
        unique_combos[key]['ids'].append(record['id'])
    
    # Sort by position category then name
    sorted_combos = sorted(unique_combos.values(), key=lambda x: (
        x['position'].upper().startswith('BAC CHAIR') and 1 or
        x['position'].upper().startswith('BAC SECRETARIAT') and 2 or
        x['position'].upper().startswith('HEAD') and 3 or
        x['position'].upper().startswith('CHIEF') and 4 or
        x['position'].upper().startswith('ENGINEER') and 5 or 6,
        x['position'],
        x['name']
    ))
    
    # Print to console
    print(f"\n{'='*80}")
    print(f"COMPLETE LIST OF LEGITIMATE BAC TITLEHOLDERS")
    print(f"{'='*80}")
    print(f"\nTotal: {len(sorted_combos)} unique name+position combinations\n")
    
    print(f"{'#':<5} {'Name':<50} {'Position':<60} {'Location':<30}")
    print("-" * 145)
    
    for i, combo in enumerate(sorted_combos, 1):
        name = combo['name'][:48]
        position = combo['position'][:58]
        location = combo['province'] or combo['municipality'] or combo['region'] or 'N/A'
        location = location[:28]
        print(f"{i:<5} {name:<50} {position:<60} {location:<30}")
    
    # Save to file
    output_file = 'bac_titleholders_clean_list.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("COMPLETE LIST OF LEGITIMATE BAC TITLEHOLDERS\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Total: {len(sorted_combos)} unique name+position combinations\n\n")
        
        for i, combo in enumerate(sorted_combos, 1):
            f.write(f"{i:4d}. {combo['name']}\n")
            f.write(f"     Position: {combo['position']}\n")
            
            location_parts = []
            if combo['municipality']:
                location_parts.append(combo['municipality'])
            if combo['province']:
                location_parts.append(combo['province'])
            if combo['region']:
                location_parts.append(f"({combo['region']})")
            
            if location_parts:
                f.write(f"     Location: {', '.join(location_parts)}\n")
            
            if combo['year']:
                f.write(f"     Year: {combo['year']}\n")
            
            f.write(f"     Records: {combo['count']}\n")
            f.write(f"     IDs: {', '.join(map(str, combo['ids']))}\n")
            f.write("\n")
    
    print(f"\n✅ Clean list saved to: {output_file}")
    return len(sorted_combos)


async def main():
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("CLEAN BAC RECORDS AND GENERATE COMPLETE LIST")
        print("=" * 80)
        print()
        
        # Step 1: Remove SGD. prefix
        await remove_sgd_prefix(conn)
        
        # Step 2: Delete document fragments
        await delete_bac_fragments(conn)
        
        # Step 3: Generate clean list
        await generate_clean_bac_list(conn)
        
        print("\n" + "=" * 80)
        print("✅ BAC records cleaned and complete list generated!")
        print("=" * 80)
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

