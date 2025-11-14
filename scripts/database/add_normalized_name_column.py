#!/usr/bin/env python3
"""
Add normalized_name column to political_dynasties table and populate it
This reduces overhead by pre-computing normalized names in the database
"""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path
from dotenv import load_dotenv


def load_env_from_dotenv():
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


def normalize_person_name(first_name, last_name, suffix=None):
    """Normalize person name for consistent indexing"""
    name_parts = []
    if first_name:
        name_parts.append(first_name.strip().upper())
    if last_name:
        name_parts.append(last_name.strip().upper())
    if suffix:
        name_parts.append(suffix.strip().upper())
    return ' '.join(name_parts) if name_parts else None


async def add_normalized_name_column():
    """Add normalized_name column and populate it"""
    load_env_from_dotenv()
    load_dotenv()
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Check if column already exists
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'political_dynasties' AND column_name = 'normalized_name'
        """)
        
        if columns:
            print("✅ Column 'normalized_name' already exists")
        else:
            # Add column
            await conn.execute("""
                ALTER TABLE political_dynasties 
                ADD COLUMN normalized_name VARCHAR(500)
            """)
            print("✅ Added 'normalized_name' column")
        
        # Populate normalized_name for all rows
        print("📝 Populating normalized_name for all rows...")
        
        rows = await conn.fetch("""
            SELECT id, first_name, last_name, suffix 
            FROM political_dynasties 
            WHERE normalized_name IS NULL OR normalized_name = ''
        """)
        
        print(f"   Found {len(rows)} rows to update")
        
        updated = 0
        for row in rows:
            normalized = normalize_person_name(
                row['first_name'],
                row['last_name'],
                row['suffix']
            )
            
            if normalized:
                await conn.execute("""
                    UPDATE political_dynasties 
                    SET normalized_name = $1 
                    WHERE id = $2
                """, normalized, row['id'])
                updated += 1
                
                if updated % 1000 == 0:
                    print(f"   Updated {updated}/{len(rows)} rows...")
        
        print(f"✅ Updated {updated} rows with normalized_name")
        
        # Create index for faster lookups
        print("📊 Creating index on normalized_name...")
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_political_dynasties_normalized_name 
                ON political_dynasties(normalized_name)
            """)
            print("✅ Index created")
        except Exception as e:
            print(f"⚠️  Index creation: {e}")
        
        # Verify
        total = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
        with_normalized = await conn.fetchval("""
            SELECT COUNT(*) FROM political_dynasties WHERE normalized_name IS NOT NULL AND normalized_name != ''
        """)
        
        print(f"\n📊 Summary:")
        print(f"   Total rows: {total}")
        print(f"   With normalized_name: {with_normalized}")
        print(f"   Coverage: {with_normalized/total*100:.1f}%")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(add_normalized_name_column())

