#!/usr/bin/env python3
"""
Restore deleted BAC records from DPWH JSON source files.
Reads from dpwh_intermediary_output_filtered.json and restores legitimate BAC positions.
"""

import asyncio
import asyncpg
import json
import os
from pathlib import Path
from dotenv import load_dotenv


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


def is_legitimate_bac_position(position: str) -> bool:
    """Check if position is a legitimate BAC position"""
    if not position:
        return False
    
    pos_upper = position.upper().strip()
    
    # Legitimate BAC position patterns (strings to search for)
    legitimate_patterns = [
        'BAC CHAIRMAN',
        'BAC CHAIRPERSON',
        'BAC SECRETARIAT',
        'HEAD, BAC',
        'HEAD BAC',
        'BAC,',  # BAC with comma
        'BAC CHAIRMAN HEAD',
        'BAC SECRETARIAT HEAD',
    ]
    
    # Check for string patterns
    if any(pattern in pos_upper for pattern in legitimate_patterns):
        return True
    
    # Check for combined patterns
    if 'CHIEF' in pos_upper and 'BAC' in pos_upper:
        return True
    if 'ENGINEER' in pos_upper and 'BAC' in pos_upper:
        return True
    
    return False


async def restore_bac_records():
    """Restore BAC records from DPWH JSON"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("RESTORE BAC RECORDS FROM DPWH JSON")
        print("=" * 80)
        print()
        
        # Load DPWH JSON files (try multiple sources)
        dpwh_archive_dir = Path(__file__).resolve().parents[2] / 'dpwh_archive'
        
        json_files = [
            dpwh_archive_dir / 'dpwh_main_parser_output.json',  # Has 1122 BAC records
            dpwh_archive_dir / 'dpwh_intermediary_output_filtered.json',  # Has 437 BAC records
        ]
        
        all_records = []
        for json_file in json_files:
            if not json_file.exists():
                print(f"⚠️  JSON file not found: {json_file.name}")
                continue
            
            print(f"📄 Loading {json_file.name}...")
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, dict):
                if 'dynasty_records' in data:
                    records = data['dynasty_records']
                elif 'recovered_records' in data:
                    records = data['recovered_records']
                else:
                    records = list(data.values()) if data else []
            elif isinstance(data, list):
                records = data
            else:
                print(f"⚠️  Unexpected JSON structure in {json_file.name}: {type(data)}")
                continue
            
            print(f"   Loaded {len(records)} records from {json_file.name}")
            all_records.extend(records)
        
        print(f"\n📊 Total records from all files: {len(all_records)}")
        print()
        
        data = all_records
        
        # Filter for legitimate BAC positions
        bac_records_to_restore = []
        seen = set()
        
        for record in data:
            if not isinstance(record, dict):
                continue
                
            position = record.get('position', '') or ''
            first_name = record.get('first_name', '') or ''
            last_name = record.get('last_name', '') or ''
            
            if not is_legitimate_bac_position(position):
                continue
            
            # Skip if name or position is too long (database constraint)
            if len(first_name.strip()) > 255 or len(last_name.strip()) > 255 or len(position.strip()) > 255:
                continue
            
            # Skip obviously bad names (document fragments)
            first_upper = first_name.upper().strip()
            last_upper = last_name.upper().strip()
            if not first_upper or not last_upper:
                continue
            
            # Skip single-letter names
            if len(first_upper) <= 1 or len(last_upper) <= 1:
                continue
            
            # Skip common document fragments (exact matches or contains)
            bad_first_names = ['FOR', 'TO', 'THE', 'ING', 'CERNING', 'MANUAL', 'BAC', 'MATION', 
                             'EXCAVATION', 'CONTRACT', 'DOCUMENT', 'BID', 'SUBMISSION',
                             'RECEIVED', 'CONSTRUCTION', 'LOCATION', 'FIGURE', 'PESOS',
                             'FOLLOWING', 'ON', 'BY', 'IN', 'OF', 'AND', 'OR']
            if first_upper in bad_first_names:
                continue
            
            bad_last_names = ['TO', 'FOLLOWING', 'ON', 'BY', 'IN', 'OF', 'AND', 'OR',
                            'EXCAVATION', 'CONTRACT', 'DOCUMENT', 'BID', 'SUBMISSION',
                            'RECEIVED', 'CONSTRUCTION', 'LOCATION', 'FIGURE', 'PESOS']
            if last_upper in bad_last_names:
                continue
            
            # Skip if name looks like a document fragment (contains common document words)
            if any(word in first_upper for word in ['EXCAVATION', 'CONTRACT', 'DOCUMENT', 'BID', 'SUBMISSION']):
                continue
            if any(word in last_upper for word in ['EXCAVATION', 'CONTRACT', 'DOCUMENT', 'BID', 'SUBMISSION']):
                continue
            
            # Check if record already exists (by name+position, but allow same person with different positions)
            key = (first_name.upper().strip(), last_name.upper().strip(), position.upper().strip())
            if key in seen:
                continue
            seen.add(key)
            
            # Extract region/province from organization if available
            organization = record.get('organization', '') or ''
            province = record.get('province', '') or ''
            region = record.get('region', '') or ''
            municipality_city = record.get('municipality_city', '') or ''
            
            # Try to extract from organization string
            if not province and 'REGION' in organization.upper():
                # Organization might contain region info
                pass
            
            bac_records_to_restore.append({
                'first_name': first_name.strip(),
                'last_name': last_name.strip(),
                'position': position.strip(),
                'province': province,
                'region': region,
                'municipality_city': municipality_city,
                'year': record.get('year', 2025) or 2025,
                'party': record.get('party', '') or '',
            })
        
        print(f"Found {len(bac_records_to_restore)} unique legitimate BAC records to restore")
        print()
        
        # Check which ones don't exist in database
        records_to_insert = []
        
        for record in bac_records_to_restore:
            exists = await conn.fetchval('''
                SELECT COUNT(*)
                FROM political_dynasties
                WHERE UPPER(TRIM(first_name)) = $1
                  AND UPPER(TRIM(last_name)) = $2
                  AND UPPER(TRIM(position)) = $3
            ''', record['first_name'].upper().strip(),
                record['last_name'].upper().strip(),
                record['position'].upper().strip())
            
            if exists == 0:
                records_to_insert.append(record)
        
        print(f"Records to restore: {len(records_to_insert)}")
        print()
        
        if records_to_insert:
            print("Restoring records:")
            print("-" * 80)
            
            restored_count = 0
            for record in records_to_insert:
                try:
                    await conn.execute('''
                        INSERT INTO political_dynasties (
                            first_name, last_name, position,
                            province, region, municipality_city,
                            year, party, winner
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ''',
                        record['first_name'],
                        record['last_name'],
                        record['position'],
                        record['province'] or None,
                        record['region'] or None,
                        record['municipality_city'] or None,
                        record['year'],
                        record['party'] or None,
                        True
                    )
                    
                    restored_count += 1
                    if restored_count <= 20:  # Show first 20
                        print(f"{restored_count:3d}. {record['first_name']:30s} {record['last_name']:20s} | {record['position'][:50]}")
                
                except Exception as e:
                    print(f"   ⚠️ Error restoring {record['first_name']} {record['last_name']}: {e}")
            
            if restored_count > 20:
                print(f"     ... and {restored_count - 20} more")
            
            print()
            print(f"✅ Restored {restored_count} BAC records")
        else:
            print("✅ All BAC records already exist in database")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(restore_bac_records())

