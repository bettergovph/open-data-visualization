#!/usr/bin/env python3
"""
Migrate SEC data to its own database
1. Create 'sec' database
2. Copy philgeps.contractors table to sec.contractors
3. Drop philgeps.contractors table
4. Recreate philgeps.contractors as cleaned version of project_contractors
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from sync_flood_contractors import split_joint_venture, is_valid_contractor_name

load_dotenv('.env')

async def main():
    print("🚀 Starting SEC database migration...\n")
    
    # Connect to postgres database to create new database
    postgres_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='postgres'
    )
    
    # Step 1: Create SEC database
    print("📊 Step 1: Creating 'sec' database...")
    try:
        await postgres_conn.execute('CREATE DATABASE sec')
        print("✅ Created 'sec' database\n")
    except Exception as e:
        if 'already exists' in str(e):
            print("✅ 'sec' database already exists\n")
        else:
            print(f"❌ Error creating database: {e}")
            await postgres_conn.close()
            return
    
    await postgres_conn.close()
    
    # Connect to philgeps database
    philgeps_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='philgeps'
    )
    
    # Connect to sec database
    sec_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Step 2: Copy contractors table schema to sec database
    print("📊 Step 2: Creating contractors table in 'sec' database...")
    
    await sec_conn.execute('''
        CREATE TABLE IF NOT EXISTS contractors (
            id SERIAL PRIMARY KEY,
            contractor_name TEXT NOT NULL,
            sec_number VARCHAR(255),
            date_registered DATE,
            status VARCHAR(50),
            address TEXT,
            secondary_licenses TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            project_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'unknown',
            former_id INTEGER REFERENCES contractors(id)
        )
    ''')
    
    # Create unique index on sec_number
    await sec_conn.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS contractors_sec_number_unique 
        ON contractors (sec_number) 
        WHERE sec_number IS NOT NULL
    ''')
    
    print("✅ Created contractors table in 'sec' database\n")
    
    # Step 3: Copy data from philgeps.contractors to sec.contractors
    print("📊 Step 3: Copying data from philgeps.contractors to sec.contractors...")
    
    contractors = await philgeps_conn.fetch('SELECT * FROM contractors')
    print(f"   Found {len(contractors)} contractors to copy")
    
    copied = 0
    for contractor in contractors:
        try:
            await sec_conn.execute('''
                INSERT INTO contractors (
                    id, contractor_name, sec_number, date_registered, status, 
                    address, secondary_licenses, created_at, updated_at, 
                    project_count, source, former_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ''', 
                contractor['id'],
                contractor['contractor_name'],
                contractor['sec_number'],
                contractor['date_registered'],
                contractor['status'],
                contractor['address'],
                contractor.get('secondary_licenses'),
                contractor['created_at'],
                contractor['updated_at'],
                contractor.get('project_count', 0),
                contractor.get('source', 'unknown'),
                contractor.get('former_id')
            )
            copied += 1
            if copied % 1000 == 0:
                print(f"   Progress: {copied}/{len(contractors)}...")
        except Exception as e:
            print(f"⚠️  Error copying contractor {contractor['id']}: {e}")
    
    print(f"✅ Copied {copied} contractors to sec.contractors\n")
    
    # Step 4: Drop old philgeps.contractors table
    print("📊 Step 4: Dropping old philgeps.contractors table...")
    await philgeps_conn.execute('DROP TABLE IF EXISTS contractors CASCADE')
    print("✅ Dropped philgeps.contractors\n")
    
    # Step 5: Create new philgeps.contractors from cleaned project_contractors
    print("📊 Step 5: Creating new philgeps.contractors from project_contractors...")
    
    await philgeps_conn.execute('''
        CREATE TABLE contractors (
            id SERIAL PRIMARY KEY,
            contractor_name TEXT NOT NULL UNIQUE,
            project_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'project_contractors',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    print("✅ Created new philgeps.contractors table\n")
    
    # Step 6: Extract and clean contractors from project_contractors
    print("📊 Step 6: Extracting and cleaning contractors from project_contractors...")
    
    raw_contractors = await philgeps_conn.fetch('''
        SELECT DISTINCT contractor_name 
        FROM project_contractors
        WHERE contractor_name IS NOT NULL
    ''')
    
    print(f"   Found {len(raw_contractors)} raw contractor names")
    
    # Clean and split contractors
    all_individual_contractors = set()
    for row in raw_contractors:
        contractor_name = row['contractor_name']
        
        # Split using same logic as flood sync
        individual_contractors = split_joint_venture(contractor_name)
        
        for contractor_data in individual_contractors:
            contractor = contractor_data['name']
            if contractor and contractor.strip() and is_valid_contractor_name(contractor):
                all_individual_contractors.add(contractor.strip())
    
    print(f"   After cleaning and splitting: {len(all_individual_contractors)} unique contractors\n")
    
    # Insert into new philgeps.contractors
    print("📊 Step 7: Inserting cleaned contractors into philgeps.contractors...")
    
    inserted = 0
    for contractor_name in sorted(all_individual_contractors):
        try:
            await philgeps_conn.execute('''
                INSERT INTO contractors (contractor_name, source)
                VALUES ($1, $2)
            ''', contractor_name, 'project_contractors')
            inserted += 1
            if inserted % 100 == 0:
                print(f"   Progress: {inserted}/{len(all_individual_contractors)}...")
        except Exception as e:
            print(f"⚠️  Error inserting '{contractor_name}': {e}")
    
    print(f"✅ Inserted {inserted} cleaned contractors into philgeps.contractors\n")
    
    await philgeps_conn.close()
    await sec_conn.close()
    
    print("✅ Migration completed!")
    print("\nSummary:")
    print(f"   • Created 'sec' database with {copied} contractors (SEC data)")
    print(f"   • Created new philgeps.contractors with {inserted} cleaned contractors")
    print(f"   • Source: project_contractors (cleaned and split)")

if __name__ == '__main__':
    asyncio.run(main())

