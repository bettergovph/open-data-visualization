#!/usr/bin/env python3
"""
List all persons holding BAC (Bids and Awards Committee) titles/positions.
Outputs a comprehensive report to both console and a text file.
"""

import asyncio
import asyncpg
import os
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


async def get_bac_titleholders():
    """Get all persons with BAC positions"""
    conn = await get_dynasty_conn()
    
    try:
        # Get all records with BAC in position
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
                government_level,
                department,
                party
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%BAC%'
            ORDER BY 
                CASE 
                    WHEN UPPER(position) LIKE '%CHAIRMAN%' OR UPPER(position) LIKE '%CHAIRPERSON%' THEN 1
                    WHEN UPPER(position) LIKE '%MEMBER%' THEN 2
                    WHEN UPPER(position) LIKE '%SECRETARIAT%' THEN 3
                    WHEN UPPER(position) LIKE '%HEAD%' THEN 4
                    ELSE 5
                END,
                last_name,
                first_name
        ''')
        
        return records
        
    finally:
        await conn.close()


async def categorize_bac_positions(records):
    """Categorize BAC positions by type"""
    categories = {
        'BAC Chairman/Chairperson': [],
        'BAC Member': [],
        'BAC Secretariat': [],
        'BAC Head/Director': [],
        'Engineer (BAC-related)': [],
        'Other BAC positions': []
    }
    
    for record in records:
        pos = (record['position'] or '').upper()
        name = f"{record['first_name']} {record['last_name']}"
        
        if 'CHAIRMAN' in pos or 'CHAIRPERSON' in pos:
            categories['BAC Chairman/Chairperson'].append((name, record))
        elif 'MEMBER' in pos:
            categories['BAC Member'].append((name, record))
        elif 'SECRETARIAT' in pos:
            categories['BAC Secretariat'].append((name, record))
        elif 'HEAD' in pos or 'DIRECTOR' in pos:
            categories['BAC Head/Director'].append((name, record))
        elif 'ENGINEER' in pos:
            categories['Engineer (BAC-related)'].append((name, record))
        else:
            categories['Other BAC positions'].append((name, record))
    
    return categories


async def main():
    print("=" * 80)
    print("BAC (BIDS AND AWARDS COMMITTEE) TITLEHOLDERS REPORT")
    print("=" * 80)
    print()
    
    records = await get_bac_titleholders()
    total = len(records)
    
    print(f"Total records with BAC positions: {total:,}")
    print()
    
    # Categorize
    categories = await categorize_bac_positions(records)
    
    # Print summary by category
    print("SUMMARY BY CATEGORY:")
    print("-" * 80)
    for category, items in categories.items():
        print(f"{category:30s}: {len(items):,} records")
    print()
    
    # Print detailed list
    print("=" * 80)
    print("DETAILED LIST - ALL BAC TITLEHOLDERS")
    print("=" * 80)
    print()
    
    # Group by unique name+position
    unique_combos = {}
    for record in records:
        name = f"{record['first_name']} {record['last_name']}"
        pos = record['position'] or ''
        province = record['province'] or 'N/A'
        key = (name.upper(), pos.upper())
        
        if key not in unique_combos:
            unique_combos[key] = {
                'name': name,
                'position': pos,
                'province': province,
                'municipality': record['municipality_city'] or '',
                'region': record['region'] or '',
                'year': record['year'],
                'count': 0,
                'ids': []
            }
        unique_combos[key]['count'] += 1
        unique_combos[key]['ids'].append(record['id'])
    
    # Sort by position then name
    sorted_combos = sorted(unique_combos.values(), key=lambda x: (x['position'], x['name']))
    
    print(f"{'#':<5} {'Name':<50} {'Position':<50} {'Province':<25} {'Count':<8}")
    print("-" * 140)
    
    for i, combo in enumerate(sorted_combos, 1):
        name = combo['name'][:48]
        position = combo['position'][:48]
        province = combo['province'][:23]
        count = combo['count']
        print(f"{i:<5} {name:<50} {position:<50} {province:<25} {count:<8}")
    
    # Save to file
    output_file = 'bac_titleholders_report.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("BAC (BIDS AND AWARDS COMMITTEE) TITLEHOLDERS REPORT\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"Total records with BAC positions: {total:,}\n\n")
        
        f.write("SUMMARY BY CATEGORY:\n")
        f.write("-" * 80 + "\n")
        for category, items in categories.items():
            f.write(f"{category:30s}: {len(items):,} records\n")
        f.write("\n")
        
        f.write("=" * 80 + "\n")
        f.write("DETAILED LIST - ALL BAC TITLEHOLDERS\n")
        f.write("=" * 80 + "\n\n")
        
        for i, combo in enumerate(sorted_combos, 1):
            f.write(f"{i:4d}. {combo['name']}\n")
            f.write(f"     Position: {combo['position']}\n")
            f.write(f"     Location: {combo['province']}")
            if combo['municipality']:
                f.write(f", {combo['municipality']}")
            if combo['region']:
                f.write(f" ({combo['region']})")
            f.write(f"\n")
            f.write(f"     Year: {combo['year'] or 'N/A'}\n")
            f.write(f"     Records: {combo['count']}\n")
            f.write(f"     IDs: {', '.join(map(str, combo['ids']))}\n")
            f.write("\n")
    
    print()
    print(f"✅ Report saved to: {output_file}")
    print(f"   Total unique name+position combinations: {len(sorted_combos)}")


if __name__ == '__main__':
    asyncio.run(main())

