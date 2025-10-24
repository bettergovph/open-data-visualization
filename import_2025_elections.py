#!/usr/bin/env python3
"""
Import 2025 elections data into dynasty database
"""
import asyncio
import asyncpg
import os
import csv
import glob
import re
from pathlib import Path
from dotenv import load_dotenv

async def import_2025_elections():
    load_dotenv('.env')
    
    # Local database connection
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_port = int(os.getenv('POSTGRES_PORT', 5432))
    db_user = os.getenv('POSTGRES_USER', 'budget_admin')
    db_password = os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu')
    db_name = os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    
    print("🚀 Connecting to local dynasty database...")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        
        print("✅ Connected to local dynasty database")
        
        # Process all CSV files in the elections data
        elections_data_path = Path.home() / 'ph-elections2025' / 'data'
        
        # Extract all tar.gz files first
        print("📦 Extracting election data files...")
        for tar_file in elections_data_path.glob('*.tar.gz'):
            print(f"  Extracting {tar_file.name}...")
            import subprocess
            subprocess.run(['tar', '-xf', str(tar_file), '-C', str(tar_file.parent)], check=True)
        
        # Find all CSV files
        csv_files = list(elections_data_path.rglob('*.csv'))
        print(f"📊 Found {len(csv_files)} CSV files to process")
        
        # Position mapping for dynasty database
        position_mapping = {
            'SENATOR of PHILIPPINES': 'SENATOR',
            'MEMBER, HOUSE OF REPRESENTATIVES': 'MEMBER, HOUSE OF REPRESENTATIVES',
            'GOVERNOR': 'GOVERNOR',
            'VICE-GOVERNOR': 'VICE GOVERNOR',
            'MAYOR': 'MAYOR',
            'VICE-MAYOR': 'VICE MAYOR',
            'MEMBER, SANGGUNIANG PANLUNGSOD': 'COUNCILOR',
            'MEMBER, SANGGUNIANG PANLALAWIGAN': 'PROVINCIAL BOARD MEMBER'
        }
        
        # Process each CSV file
        total_records = 0
        for i, csv_file in enumerate(csv_files):
            if i % 100 == 0:
                print(f"  Processing file {i+1}/{len(csv_files)}: {csv_file.name}")
            
            try:
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    
                    for row in reader:
                        if len(row) >= 8:
                            # Parse the data
                            precinct_code = row[0]
                            location = row[1]
                            voting_center = row[2]
                            scope = row[3]
                            contest_name = row[4]
                            candidate_name = row[5]
                            votes = int(row[6]) if row[6].isdigit() else 0
                            percentage = float(row[7]) if row[7].replace('.', '').isdigit() else 0.0
                            
                            # Extract location information
                            location_parts = location.split(', ')
                            if len(location_parts) >= 3:
                                region = location_parts[0]
                                province = location_parts[1] if len(location_parts) > 1 else None
                                municipality_city = location_parts[2] if len(location_parts) > 2 else None
                            else:
                                region = location
                                province = None
                                municipality_city = None
                            
                            # Map contest to position
                            position = None
                            for key, value in position_mapping.items():
                                if key in scope:
                                    position = value
                                    break
                            
                            if not position:
                                # Try to extract position from scope
                                if 'SENATOR' in scope:
                                    position = 'SENATOR'
                                elif 'REPRESENTATIVES' in scope:
                                    position = 'MEMBER, HOUSE OF REPRESENTATIVES'
                                elif 'GOVERNOR' in scope:
                                    position = 'GOVERNOR'
                                elif 'VICE-GOVERNOR' in scope:
                                    position = 'VICE GOVERNOR'
                                elif 'MAYOR' in scope:
                                    position = 'MAYOR'
                                elif 'VICE-MAYOR' in scope:
                                    position = 'VICE MAYOR'
                                elif 'SANGGUNIANG PANLUNGSOD' in scope:
                                    position = 'COUNCILOR'
                                elif 'SANGGUNIANG PANLALAWIGAN' in scope:
                                    position = 'PROVINCIAL BOARD MEMBER'
                                else:
                                    position = 'OTHER'
                            
                            # Parse candidate name
                            # Remove numbering and party info: "1. ABALOS, BENHUR (PFP)" -> "ABALOS, BENHUR"
                            candidate_clean = re.sub(r'^\d+\.\s*', '', candidate_name)
                            candidate_clean = re.sub(r'\s*\([^)]*\)$', '', candidate_clean)
                            
                            # Split name into first and last
                            name_parts = candidate_clean.split(', ')
                            if len(name_parts) >= 2:
                                last_name = name_parts[0].strip()
                                first_name = name_parts[1].strip()
                            else:
                                # If no comma, try to split by space
                                name_parts = candidate_clean.split()
                                if len(name_parts) >= 2:
                                    first_name = name_parts[0]
                                    last_name = ' '.join(name_parts[1:])
                                else:
                                    first_name = candidate_clean
                                    last_name = ''
                            
                            # Insert into database
                            await conn.execute("""
                                INSERT INTO political_dynasties 
                                (first_name, last_name, party, region, province, municipality_city, position, year, fat, nickname)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                            """, 
                            first_name,
                            last_name,
                            None,  # party - could extract from candidate_name
                            region,
                            province,
                            municipality_city,
                            position,
                            2025,  # year
                            0,  # fat - not applicable for 2025
                            None  # nickname
                            )
                            
                            total_records += 1
                            
            except Exception as e:
                print(f"  ⚠️ Error processing {csv_file}: {e}")
                continue
        
        print(f"✅ Imported {total_records} records from 2025 elections")
        
        # Verify import
        count_2025 = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE year = 2025")
        print(f"📊 Total 2025 records in database: {count_2025}")
        
        await conn.close()
        print("✅ 2025 elections data import completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(import_2025_elections())
