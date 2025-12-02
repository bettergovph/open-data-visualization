#!/usr/bin/env python3
"""Normalize Sara Duterte entries to appear as one in autocomplete while preserving historical positions"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def normalize_sara_duterte():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Check Sara Duterte records
        sara_records = await conn.fetch('''
            SELECT id, first_name, last_name, position, province, year, normalized_name
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%SARA%' 
              AND UPPER(last_name) LIKE '%DUTERTE%'
            ORDER BY id
        ''')
        
        print(f"Found {len(sara_records)} Sara Duterte records:")
        for r in sara_records:
            print(f"  ID: {r['id']}, Name: {r['first_name']} {r['last_name']}, Position: {r['position']}, Year: {r['year']}, Normalized: {r['normalized_name']}")
        
        if len(sara_records) < 2:
            print("\n✅ Only one record found, no normalization needed")
            return
        
        # Determine which is the primary record (the one with more relationships or more recent)
        # Check relationship counts
        rel_counts = {}
        for r in sara_records:
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM relationships
                WHERE person_id = $1 OR related_person_id = $1
            ''', r['id'])
            rel_counts[r['id']] = count
            print(f"  ID {r['id']} has {count} relationships")
        
        # Use the record with more relationships as primary, or the one with VICE PRESIDENT
        primary_id = None
        for r in sara_records:
            if 'VICE PRESIDENT' in (r['position'] or '').upper():
                primary_id = r['id']
                break
        
        if not primary_id:
            # Use the one with more relationships
            primary_id = max(rel_counts.items(), key=lambda x: x[1])[0]
        
        primary_record = next(r for r in sara_records if r['id'] == primary_id)
        other_records = [r for r in sara_records if r['id'] != primary_id]
        
        print(f"\n📌 Using ID {primary_id} as primary record")
        
        # Normalize all to use the same normalized_name
        # Use "SARA DUTERTE" as the normalized name (without CARPIO to match both)
        normalized_name = "SARA DUTERTE"
        
        # Update normalized_name for all records
        for r in sara_records:
            await conn.execute('''
                UPDATE political_dynasties
                SET normalized_name = $1
                WHERE id = $2
            ''', normalized_name, r['id'])
            print(f"✅ Updated ID {r['id']} normalized_name to '{normalized_name}'")
        
        # For the primary record, update position to include both if they're different
        if len(other_records) > 0:
            other_positions = [r['position'] for r in other_records if r['position'] and r['position'] != primary_record['position']]
            if other_positions:
                # Combine positions: "VICE PRESIDENT OF THE PHILIPPINES (Former: MAYOR, Davao City)"
                combined_position = primary_record['position']
                if other_positions:
                    combined_position += f" (Former: {', '.join(set(other_positions))})"
                
                await conn.execute('''
                    UPDATE political_dynasties
                    SET position = $1
                    WHERE id = $2
                ''', combined_position, primary_id)
                print(f"✅ Updated primary record position to include historical: '{combined_position}'")
        
        # Migrate relationships from other records to primary if needed
        for other_record in other_records:
            # Check if there are relationships pointing to the other record
            rels_to_migrate = await conn.fetch('''
                SELECT id, person_id, related_person_id, relationship_type, relationship_description, source_url
                FROM relationships
                WHERE person_id = $1 OR related_person_id = $1
            ''', other_record['id'])
            
            migrated = 0
            for rel in rels_to_migrate:
                # Check if equivalent relationship already exists for primary
                if rel['person_id'] == other_record['id']:
                    existing = await conn.fetchrow('''
                        SELECT id FROM relationships
                        WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                    ''', primary_id, rel['related_person_id'], rel['relationship_type'])
                    if not existing:
                        await conn.execute('''
                            INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                            VALUES ($1, $2, $3, $4, $5)
                        ''', primary_id, rel['related_person_id'], rel['relationship_type'], rel['relationship_description'], rel['source_url'])
                        migrated += 1
                elif rel['related_person_id'] == other_record['id']:
                    existing = await conn.fetchrow('''
                        SELECT id FROM relationships
                        WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                    ''', rel['person_id'], primary_id, rel['relationship_type'])
                    if not existing:
                        await conn.execute('''
                            INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                            VALUES ($1, $2, $3, $4, $5)
                        ''', rel['person_id'], primary_id, rel['relationship_type'], rel['relationship_description'], rel['source_url'])
                        migrated += 1
            
            if migrated > 0:
                print(f"✅ Migrated {migrated} relationships from ID {other_record['id']} to primary ID {primary_id}")
        
        print("\n✅ Normalization complete! Both records now use 'SARA DUTERTE' as normalized_name")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(normalize_sara_duterte())





















