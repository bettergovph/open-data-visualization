#!/usr/bin/env python3
"""
Restore missing BAC records based on the clean list file.
Reads bac_titleholders_clean_list.txt and restores any missing legitimate BAC persons.
"""

import asyncio
import asyncpg
import os
import re
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


async def restore_from_clean_list():
    """Restore BAC records from the clean list"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("RESTORE MISSING BAC RECORDS FROM CLEAN LIST")
        print("=" * 80)
        print()
        
        # Read the clean list file
        clean_list_file = Path(__file__).resolve().parents[2] / 'bac_titleholders_clean_list.txt'
        
        if not clean_list_file.exists():
            print(f"❌ Clean list file not found: {clean_list_file}")
            return
        
        print(f"📄 Reading {clean_list_file.name}...")
        content = clean_list_file.read_text(encoding='utf-8')
        
        # Parse the clean list
        # Format: "   1. JANETTE M. SADIE"
        #         "     Position: BAC Chairman Assistant"
        records_to_restore = []
        
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for name line (e.g., "   1. JANETTE M. SADIE")
            name_match = re.match(r'\d+\.\s+(.+)', line)
            if name_match:
                full_name = name_match.group(1).strip()
                
                # Look for position on next few lines
                position = None
                for j in range(i + 1, min(i + 5, len(lines))):
                    pos_line = lines[j]
                    if 'Position:' in pos_line:
                        position = pos_line.split('Position:', 1)[1].strip()
                        break
                
                if position and 'BAC' in position.upper():
                    # Parse name into first and last
                    name_parts = full_name.split()
                    if len(name_parts) >= 2:
                        # Last name is typically the last part
                        last_name = name_parts[-1]
                        first_name = ' '.join(name_parts[:-1])
                        
                        records_to_restore.append({
                            'first_name': first_name,
                            'last_name': last_name,
                            'position': position,
                        })
            i += 1
        
        print(f"Found {len(records_to_restore)} BAC records in clean list")
        print()
        
        # Check which ones are missing
        missing_records = []
        for record in records_to_restore:
            exists = await conn.fetchval(
                "SELECT COUNT(*) FROM political_dynasties "
                "WHERE UPPER(TRIM(first_name)) = $1 "
                "AND UPPER(TRIM(last_name)) = $2 "
                "AND UPPER(TRIM(position)) = $3",
                record['first_name'].upper().strip(),
                record['last_name'].upper().strip(),
                record['position'].upper().strip()
            )
            
            if exists == 0:
                missing_records.append(record)
        
        print(f"Missing records: {len(missing_records)}")
        print()
        
        if missing_records:
            print("Restoring missing records:")
            print("-" * 80)
            
            restored_count = 0
            for record in missing_records[:50]:  # Show first 50
                try:
                    await conn.execute(
                        "INSERT INTO political_dynasties "
                        "(first_name, last_name, position, year, winner) "
                        "VALUES ($1, $2, $3, $4, $5)",
                        record['first_name'],
                        record['last_name'],
                        record['position'],
                        2025,
                        True
                    )
                    
                    restored_count += 1
                    print(f"{restored_count:3d}. {record['first_name']:30s} {record['last_name']:20s} | {record['position'][:50]}")
                
                except Exception as e:
                    print(f"   ⚠️ Error restoring {record['first_name']} {record['last_name']}: {e}")
            
            if len(missing_records) > 50:
                print(f"     ... and {len(missing_records) - 50} more")
                # Restore the rest silently
                for record in missing_records[50:]:
                    try:
                        await conn.execute(
                            "INSERT INTO political_dynasties "
                            "(first_name, last_name, position, year, winner) "
                            "VALUES ($1, $2, $3, $4, $5)",
                            record['first_name'],
                            record['last_name'],
                            record['position'],
                            2025,
                            True
                        )
                        restored_count += 1
                    except:
                        pass
            
            print()
            print(f"✅ Restored {restored_count} BAC records from clean list")
        else:
            print("✅ All BAC records from clean list already exist")
        
        # Final count
        total_bac = await conn.fetchval(
            "SELECT COUNT(*) FROM political_dynasties WHERE UPPER(position) LIKE '%BAC%'"
        )
        unique_bac = await conn.fetchval(
            "SELECT COUNT(DISTINCT CONCAT(UPPER(TRIM(first_name)), '|', UPPER(TRIM(last_name)))) "
            "FROM political_dynasties WHERE UPPER(position) LIKE '%BAC%'"
        )
        
        print()
        print("=" * 80)
        print(f"Total BAC records: {total_bac} total, {unique_bac} unique persons")
        print(f"Target: 99 unique persons")
        print(f"Remaining: {max(0, 99 - unique_bac)} more needed")
        print("=" * 80)
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(restore_from_clean_list())

