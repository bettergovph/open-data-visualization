#!/usr/bin/env python3
"""
Import Political Dynasties Excel data into PostgreSQL database
Fixed version to import all 86,234 records
"""

import pandas as pd
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def import_dynasty_data():
    print("🚀 Starting Political Dynasties Data Import...")
    
    # Read Excel file
    excel_file = 'database/ASoG-POLITICAL-DYNASTIES-DATASET-V2016.xlsx'
    print(f"📊 Reading Excel file: {excel_file}")
    
    # Read the Data sheet (this has all the records)
    df = pd.read_excel(excel_file, sheet_name='Data')
    print(f"📋 Found {len(df)} records in Excel file")
    print(f"📄 Columns: {list(df.columns)}")
    
    # Show sample data
    print(f"\\n📄 Sample data:")
    print(df.head(3).to_string())
    
    # Check unique provinces
    unique_provinces = df['Province'].nunique()
    print(f"\\n🏛️ Unique provinces in Excel: {unique_provinces}")
    print(f"Provinces: {sorted(df['Province'].unique())}")
    
    # Connect to database
    print(f"\\n🔌 Connecting to database...")
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY_SEC', 'dynasty')
    )
    
    # Drop and recreate table
    print(f"\\n🗑️ Dropping existing table...")
    await conn.execute('DROP TABLE IF EXISTS political_dynasties')
    
    # Create table with proper schema
    print(f"\\n🏗️ Creating new table...")
    await conn.execute('''
        CREATE TABLE political_dynasties (
            id SERIAL PRIMARY KEY,
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            party VARCHAR(255),
            region VARCHAR(255),
            province VARCHAR(255),
            municipality_city VARCHAR(255),
            position VARCHAR(255),
            year INTEGER,
            fat INTEGER
        )
    ''')
    
    # Prepare data for insertion
    print(f"\\n📝 Preparing data for insertion...")
    
    # Convert data types
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce').fillna(0).astype(int)
    df['fat'] = pd.to_numeric(df['fat'], errors='coerce').fillna(0).astype(int)
    
    # Replace NaN values with empty strings
    df = df.fillna('')
    
    # Convert to list of tuples
    records = []
    for _, row in df.iterrows():
        records.append((
            str(row['First Name']),
            str(row['Last Name']),
            str(row['Party']),
            str(row['Region']),
            str(row['Province']),
            str(row['Municipality.City']),
            str(row['Position']),
            int(row['Year']),
            int(row['fat'])
        ))
    
    print(f"📊 Prepared {len(records)} records for insertion")
    
    # Insert data in batches
    print(f"\\n💾 Inserting data in batches...")
    batch_size = 1000
    total_inserted = 0
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        await conn.executemany('''
            INSERT INTO political_dynasties 
            (first_name, last_name, party, region, province, municipality_city, position, year, fat)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ''', batch)
        
        total_inserted += len(batch)
        print(f"  ✅ Inserted {total_inserted}/{len(records)} records ({total_inserted/len(records)*100:.1f}%)")
    
    # Verify import
    print(f"\\n🔍 Verifying import...")
    total_count = await conn.fetchval('SELECT COUNT(*) FROM political_dynasties')
    print(f"📊 Total records in database: {total_count}")
    
    # Check unique provinces
    provinces = await conn.fetch('SELECT province, COUNT(*) as count FROM political_dynasties GROUP BY province ORDER BY count DESC')
    print(f"\\n🏛️ Provinces in database ({len(provinces)}):")
    for province in provinces[:10]:  # Show top 10
        print(f"  {province['province']}: {province['count']} records")
    
    # Check dynasty members (fat=1)
    dynasty_count = await conn.fetchval('SELECT COUNT(*) FROM political_dynasties WHERE fat = 1')
    print(f"\\n👑 Dynasty members (fat=1): {dynasty_count}")
    
    await conn.close()
    print(f"\\n✅ Import completed successfully!")
    print(f"📊 Total records: {total_count}")
    print(f"👑 Dynasty members: {dynasty_count}")
    print(f"🏛️ Unique provinces: {len(provinces)}")

if __name__ == "__main__":
    asyncio.run(import_dynasty_data())
