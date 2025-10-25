#!/usr/bin/env python3
"""
Import dynasty data to production database
"""
import asyncio
import asyncpg
import os
import re
from dotenv import load_dotenv

async def import_dynasty_data():
    # Production database connection
    db_host = '10.27.79.7'
    db_port = 5432
    db_user = 'budget_admin'
    db_password = 'wuQ5gBYCKkZiOGb61chLcByMu'
    db_name = 'dynasty'
    
    print("🚀 Connecting to production database...")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        
        print("✅ Connected to production database")
        
        # Read the local dynasty.sql file
        with open('database/dynasty_local.sql', 'r') as f:
            sql_content = f.read()
        
        # Extract and import connection_types data
        print("📋 Importing connection_types...")
        connection_types_pattern = r'COPY public\.connection_types[^;]+;\n(.*?)\n\\\.'
        match = re.search(connection_types_pattern, sql_content, re.DOTALL)
        if match:
            data_lines = match.group(1).strip().split('\n')
            for line in data_lines:
                if line.strip() and not line.startswith('\\'):
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        await conn.execute("""
                            INSERT INTO connection_types (id, code, name, description) 
                            VALUES ($1, $2, $3, $4)
                        """, int(parts[0]), int(parts[1]), parts[2], parts[3] if parts[3] != 'NULL' else None)
            print(f"✅ Imported {len(data_lines)} connection_types records")
        
        # Extract and import political_dynasties data
        print("📊 Importing political_dynasties...")
        political_dynasties_pattern = r'COPY public\.political_dynasties[^;]+;\n(.*?)\n\\\.'
        match = re.search(political_dynasties_pattern, sql_content, re.DOTALL)
        if match:
            data_lines = match.group(1).strip().split('\n')
            count = 0
            for line in data_lines:
                if line.strip() and not line.startswith('\\'):
                    parts = line.split('\t')
                    if len(parts) >= 11:
                        await conn.execute("""
                            INSERT INTO political_dynasties 
                            (id, first_name, last_name, party, region, province, municipality_city, position, year, fat, nickname) 
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        """, 
                        int(parts[0]),
                        parts[1] if parts[1] != 'NULL' else None,
                        parts[2] if parts[2] != 'NULL' else None,
                        parts[3] if parts[3] != 'NULL' else None,
                        parts[4] if parts[4] != 'NULL' else None,
                        parts[5] if parts[5] != 'NULL' else None,
                        parts[6] if parts[6] != 'NULL' else None,
                        parts[7] if parts[7] != 'NULL' else None,
                        int(parts[8]) if parts[8] != 'NULL' else None,
                        int(parts[9]) if parts[9] != 'NULL' else None,
                        parts[10] if parts[10] != 'NULL' else None
                        )
                        count += 1
                        if count % 1000 == 0:
                            print(f"  Imported {count} records...")
            print(f"✅ Imported {count} political_dynasties records")
        
        # Extract and import relationships data
        print("🔗 Importing relationships...")
        relationships_pattern = r'COPY public\.relationships[^;]+;\n(.*?)\n\\\.'
        match = re.search(relationships_pattern, sql_content, re.DOTALL)
        if match:
            data_lines = match.group(1).strip().split('\n')
            count = 0
            for line in data_lines:
                if line.strip() and not line.startswith('\\'):
                    parts = line.split('\t')
                    if len(parts) >= 5:
                        await conn.execute("""
                            INSERT INTO relationships 
                            (id, person_id, related_person_id, relationship_type, relationship_description) 
                            VALUES ($1, $2, $3, $4, $5)
                        """, 
                        int(parts[0]),
                        int(parts[1]),
                        int(parts[2]),
                        int(parts[3]),
                        parts[4] if parts[4] != 'NULL' else None
                        )
                        count += 1
            print(f"✅ Imported {count} relationships records")
        
        # Verify import
        connection_types_count = await conn.fetchval("SELECT COUNT(*) FROM connection_types")
        political_dynasties_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
        relationships_count = await conn.fetchval("SELECT COUNT(*) FROM relationships")
        
        print(f"📊 Final counts:")
        print(f"  - connection_types: {connection_types_count}")
        print(f"  - political_dynasties: {political_dynasties_count}")
        print(f"  - relationships: {relationships_count}")
        
        await conn.close()
        print("✅ Dynasty database import completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(import_dynasty_data())

