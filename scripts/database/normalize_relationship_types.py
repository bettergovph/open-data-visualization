#!/usr/bin/env python3
"""
Normalize relationship types and descriptions in the database
Adds normalized columns to reduce overhead and ensure consistency
"""

import asyncio
import asyncpg
import os
import re
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


def normalize_relationship_type(type_name):
    """Normalize relationship type name"""
    if not type_name:
        return None
    
    # Convert to uppercase, strip whitespace
    normalized = type_name.strip().upper()
    
    # Remove extra spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Common variations mapping
    variations = {
        'FATHER': 'FATHER',
        'MOTHER': 'MOTHER',
        'SON': 'SON',
        'DAUGHTER': 'DAUGHTER',
        'HUSBAND': 'HUSBAND',
        'WIFE': 'WIFE',
        'SPOUSE': 'SPOUSE',
        'BROTHER': 'BROTHER',
        'SISTER': 'SISTER',
        'SIBLING': 'SIBLING',
        'UNCLE': 'UNCLE',
        'AUNT': 'AUNT',
        'NEPHEW': 'NEPHEW',
        'NIECE': 'NIECE',
        'COUSIN': 'COUSIN',
        'GRANDFATHER': 'GRANDFATHER',
        'GRANDMOTHER': 'GRANDMOTHER',
        'GRANDSON': 'GRANDSON',
        'GRANDDAUGHTER': 'GRANDDAUGHTER',
        'FATHER-IN-LAW': 'FATHER-IN-LAW',
        'MOTHER-IN-LAW': 'MOTHER-IN-LAW',
        'SON-IN-LAW': 'SON-IN-LAW',
        'DAUGHTER-IN-LAW': 'DAUGHTER-IN-LAW',
        'POLITICAL ALLY': 'POLITICAL ALLY',
        'POLITICAL RIVAL': 'POLITICAL RIVAL',
        'SUCCESSOR': 'SUCCESSOR',
        'PREDECESSOR': 'PREDECESSOR',
        'MENTOR': 'MENTOR',
        'PROTEGE': 'PROTEGE',
        'BUSINESS PARTNER': 'BUSINESS PARTNER',
        'BUSINESS RIVAL': 'BUSINESS RIVAL',
        'INVESTOR': 'INVESTOR',
        'CLIENT': 'CLIENT',
        'CONTRACTOR': 'CONTRACTOR',
        'BUSINESS/CONTRACTOR CONNECTION': 'BUSINESS/CONTRACTOR CONNECTION',
        'PARTY-LIST MEMBERSHIP': 'PARTY-LIST MEMBERSHIP'
    }
    
    # Check for exact match first
    if normalized in variations:
        return variations[normalized]
    
    # Check for partial matches
    for key, value in variations.items():
        if key in normalized or normalized in key:
            return value
    
    return normalized


def normalize_relationship_description(description):
    """Normalize relationship description text"""
    if not description:
        return None
    
    # Convert to uppercase, strip whitespace
    normalized = description.strip().upper()
    
    # Remove extra spaces
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Remove common prefixes/suffixes that don't add value
    normalized = re.sub(r'^(CONNECTED VIA|RELATED VIA|LINKED VIA)\s+', '', normalized)
    normalized = re.sub(r'\s+(CONNECTION|RELATIONSHIP|LINK)$', '', normalized)
    
    return normalized if normalized else None


async def normalize_relationship_types():
    """Add normalized columns and populate them"""
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
        # 1. Add normalized_name to connection_types table
        print("🔧 Step 1: Normalizing connection_types table...")
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'connection_types' AND column_name = 'normalized_name'
        """)
        
        if not columns:
            await conn.execute("""
                ALTER TABLE connection_types 
                ADD COLUMN normalized_name VARCHAR(200)
            """)
            print("✅ Added 'normalized_name' column to connection_types")
        else:
            print("✅ Column 'normalized_name' already exists in connection_types")
        
        # Populate normalized_name for connection_types
        print("📝 Populating normalized_name for connection_types...")
        types = await conn.fetch("""
            SELECT id, name, COALESCE(normalized_name, '') as current_normalized
            FROM connection_types
            WHERE normalized_name IS NULL OR normalized_name = ''
        """)
        
        updated_types = 0
        for type_row in types:
            normalized = normalize_relationship_type(type_row['name'])
            if normalized:
                await conn.execute("""
                    UPDATE connection_types 
                    SET normalized_name = $1 
                    WHERE id = $2
                """, normalized, type_row['id'])
                updated_types += 1
        
        print(f"✅ Updated {updated_types} connection types with normalized_name")
        
        # Create index
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_connection_types_normalized_name 
                ON connection_types(normalized_name)
            """)
            print("✅ Index created on connection_types.normalized_name")
        except Exception as e:
            print(f"⚠️  Index creation: {e}")
        
        # 2. Add normalized_description to relationships table
        print("\n🔧 Step 2: Normalizing relationships table...")
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'relationships' AND column_name = 'normalized_description'
        """)
        
        if not columns:
            await conn.execute("""
                ALTER TABLE relationships 
                ADD COLUMN normalized_description VARCHAR(500)
            """)
            print("✅ Added 'normalized_description' column to relationships")
        else:
            print("✅ Column 'normalized_description' already exists in relationships")
        
        # Populate normalized_description for relationships
        print("📝 Populating normalized_description for relationships...")
        relationships = await conn.fetch("""
            SELECT id, relationship_description, COALESCE(normalized_description, '') as current_normalized
            FROM relationships
            WHERE (normalized_description IS NULL OR normalized_description = '')
              AND relationship_description IS NOT NULL
        """)
        
        updated_rels = 0
        for rel in relationships:
            normalized = normalize_relationship_description(rel['relationship_description'])
            if normalized:
                await conn.execute("""
                    UPDATE relationships 
                    SET normalized_description = $1 
                    WHERE id = $2
                """, normalized, rel['id'])
                updated_rels += 1
                
                if updated_rels % 1000 == 0:
                    print(f"   Updated {updated_rels}/{len(relationships)} relationships...")
        
        print(f"✅ Updated {updated_rels} relationships with normalized_description")
        
        # Create index
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_normalized_description 
                ON relationships(normalized_description)
            """)
            print("✅ Index created on relationships.normalized_description")
        except Exception as e:
            print(f"⚠️  Index creation: {e}")
        
        # 3. Also add normalized_relationship_type to relationships (from connection_types)
        print("\n🔧 Step 3: Adding normalized_relationship_type to relationships...")
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'relationships' AND column_name = 'normalized_relationship_type'
        """)
        
        if not columns:
            await conn.execute("""
                ALTER TABLE relationships 
                ADD COLUMN normalized_relationship_type VARCHAR(200)
            """)
            print("✅ Added 'normalized_relationship_type' column to relationships")
        else:
            print("✅ Column 'normalized_relationship_type' already exists in relationships")
        
        # Populate normalized_relationship_type from connection_types
        print("📝 Populating normalized_relationship_type for relationships...")
        await conn.execute("""
            UPDATE relationships r
            SET normalized_relationship_type = ct.normalized_name
            FROM connection_types ct
            WHERE r.relationship_type = ct.id
              AND (r.normalized_relationship_type IS NULL OR r.normalized_relationship_type = '')
              AND ct.normalized_name IS NOT NULL
        """)
        
        updated_count = await conn.fetchval("""
            SELECT COUNT(*) FROM relationships 
            WHERE normalized_relationship_type IS NOT NULL AND normalized_relationship_type != ''
        """)
        print(f"✅ Updated {updated_count} relationships with normalized_relationship_type")
        
        # Create index
        try:
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_normalized_type 
                ON relationships(normalized_relationship_type)
            """)
            print("✅ Index created on relationships.normalized_relationship_type")
        except Exception as e:
            print(f"⚠️  Index creation: {e}")
        
        # Summary
        total_types = await conn.fetchval("SELECT COUNT(*) FROM connection_types")
        types_with_normalized = await conn.fetchval("""
            SELECT COUNT(*) FROM connection_types 
            WHERE normalized_name IS NOT NULL AND normalized_name != ''
        """)
        
        total_rels = await conn.fetchval("SELECT COUNT(*) FROM relationships")
        rels_with_normalized_desc = await conn.fetchval("""
            SELECT COUNT(*) FROM relationships 
            WHERE normalized_description IS NOT NULL AND normalized_description != ''
        """)
        rels_with_normalized_type = await conn.fetchval("""
            SELECT COUNT(*) FROM relationships 
            WHERE normalized_relationship_type IS NOT NULL AND normalized_relationship_type != ''
        """)
        
        print(f"\n📊 Summary:")
        print(f"   Connection Types: {types_with_normalized}/{total_types} normalized ({types_with_normalized/total_types*100:.1f}%)")
        print(f"   Relationships with normalized_description: {rels_with_normalized_desc}/{total_rels} ({rels_with_normalized_desc/total_rels*100:.1f}%)")
        print(f"   Relationships with normalized_relationship_type: {rels_with_normalized_type}/{total_rels} ({rels_with_normalized_type/total_rels*100:.1f}%)")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(normalize_relationship_types())

