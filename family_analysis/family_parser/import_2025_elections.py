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
from concurrent.futures import ThreadPoolExecutor
import threading

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
        
        # Clear existing 2025 data to re-import with correct winner identification
        print("🗑️ Clearing existing 2025 data...")
        deleted_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE year = 2025")
        if deleted_count > 0:
            await conn.execute("DELETE FROM political_dynasties WHERE year = 2025")
            print(f"✅ Cleared {deleted_count} existing 2025 records")
        else:
            print("ℹ️ No existing 2025 records to clear")
        
        # Mark all existing records as winners (since they represent people who held positions)
        print("🏆 Marking all existing records as winners...")
        existing_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE year != 2025")
        if existing_count > 0:
            await conn.execute("UPDATE political_dynasties SET winner = TRUE WHERE year != 2025")
            print(f"✅ Marked {existing_count} existing records as winners")
        else:
            print("ℹ️ No existing records to mark as winners")
        
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
        
        # Process each CSV file to import all candidates and identify winners
        total_records = 0
        candidates_by_position = {}  # Store all candidates by position and location
        candidates_lock = threading.Lock()  # Thread-safe access to shared data
        
        def process_csv_file(csv_file):
            """Process a single CSV file and return candidates data"""
            file_candidates = {}
            
            try:
                print(f"DEBUG: Opening {csv_file.name}")
                with open(csv_file, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    header = next(reader)
                    print(f"DEBUG: Processing {csv_file.name}, header: {header}")
                    
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
                            
                            # Map contest to position based on scope and contest_name
                            position = None
                            
                            # First try to extract from contest_name (more reliable)
                            contest_name_upper = contest_name.upper()
                            if 'SENATOR' in contest_name_upper:
                                position = 'SENATOR'
                            elif 'REPRESENTATIVES' in contest_name_upper or 'HOUSE OF REPRESENTATIVES' in contest_name_upper:
                                position = 'MEMBER, HOUSE OF REPRESENTATIVES'
                            elif 'PROVINCIAL GOVERNOR' in contest_name_upper:
                                position = 'GOVERNOR'
                            elif 'PROVINCIAL VICE-GOVERNOR' in contest_name_upper:
                                position = 'VICE GOVERNOR'
                            elif 'MAYOR' in contest_name_upper:
                                position = 'MAYOR'
                            elif 'VICE-MAYOR' in contest_name_upper:
                                position = 'VICE MAYOR'
                            elif 'SANGGUNIANG PANLUNGSOD' in contest_name_upper or 'SANGGUNIANG BAYAN' in contest_name_upper:
                                position = 'COUNCILOR'
                            elif 'SANGGUNIANG PANLALAWIGAN' in contest_name_upper:
                                position = 'PROVINCIAL BOARD MEMBER'
                            
                            
                            # If not found in contest_name, try scope
                            if not position:
                                scope_upper = scope.upper()
                                if 'SENATOR' in scope_upper:
                                    position = 'SENATOR'
                                elif 'REPRESENTATIVES' in scope_upper:
                                    position = 'MEMBER, HOUSE OF REPRESENTATIVES'
                                elif 'GOVERNOR' in scope_upper:
                                    position = 'GOVERNOR'
                                elif 'VICE-GOVERNOR' in scope_upper:
                                    position = 'VICE GOVERNOR'
                                elif 'MAYOR' in scope_upper:
                                    position = 'MAYOR'
                                elif 'VICE-MAYOR' in scope_upper:
                                    position = 'VICE MAYOR'
                                elif 'SANGGUNIANG PANLUNGSOD' in scope_upper:
                                    position = 'COUNCILOR'
                                elif 'SANGGUNIANG PANLALAWIGAN' in scope_upper:
                                    position = 'PROVINCIAL BOARD MEMBER'
                                else:
                                    position = 'OTHER'
                            
                            # Skip party-list positions only
                            if 'PARTY LIST' in scope or 'PARTY LIST' in contest_name.upper():
                                continue
                            
                            # Debug: Print first few positions to see what's happening
                            if total_records < 3:
                                print(f"DEBUG: contest_name='{contest_name}', position='{position}'")
                            
                            
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
                            
                            # Create unique key for position and location
                            position_key = f"{position}_{region}_{province}_{municipality_city}"
                            
                            # Store candidate data
                            if position_key not in file_candidates:
                                file_candidates[position_key] = []
                            
                            file_candidates[position_key].append({
                                'first_name': first_name,
                                'last_name': last_name,
                                'votes': votes,
                                'position': position,
                                'region': region,
                                'province': province,
                                'municipality_city': municipality_city,
                                'scope': scope
                            })
                            
            except Exception as e:
                print(f"  ⚠️ Error processing {csv_file}: {e}")
            
            return file_candidates
        
        # Process CSV files with 20 threads
        print(f"🚀 Processing {len(csv_files)} CSV files with 20 threads...")
        
        # Partition CSV files into chunks for each thread
        chunk_size = len(csv_files) // 20
        if chunk_size == 0:
            chunk_size = 1
        
        csv_chunks = []
        for i in range(0, len(csv_files), chunk_size):
            chunk = csv_files[i:i + chunk_size]
            csv_chunks.append(chunk)
        
        print(f"📊 Split {len(csv_files)} files into {len(csv_chunks)} chunks for {20} threads")
        
        def process_csv_chunk(chunk_files):
            """Process a chunk of CSV files and return all candidates data"""
            chunk_candidates = {}
            
            for csv_file in chunk_files:
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
                                
                                # Map contest to position based on scope and contest_name
                                position = None
                                
                                # First try to extract from contest_name (more reliable)
                                contest_name_upper = contest_name.upper()
                                if 'SENATOR' in contest_name_upper:
                                    position = 'SENATOR'
                                elif 'REPRESENTATIVES' in contest_name_upper or 'HOUSE OF REPRESENTATIVES' in contest_name_upper:
                                    position = 'MEMBER, HOUSE OF REPRESENTATIVES'
                                elif 'PROVINCIAL GOVERNOR' in contest_name_upper:
                                    position = 'GOVERNOR'
                                elif 'PROVINCIAL VICE-GOVERNOR' in contest_name_upper:
                                    position = 'VICE GOVERNOR'
                                elif 'MAYOR' in contest_name_upper:
                                    position = 'MAYOR'
                                elif 'VICE-MAYOR' in contest_name_upper:
                                    position = 'VICE MAYOR'
                                elif 'SANGGUNIANG PANLUNGSOD' in contest_name_upper or 'SANGGUNIANG BAYAN' in contest_name_upper:
                                    position = 'COUNCILOR'
                                elif 'SANGGUNIANG PANLALAWIGAN' in contest_name_upper:
                                    position = 'PROVINCIAL BOARD MEMBER'
                                
                                # If not found in contest_name, try scope
                                if not position:
                                    scope_upper = scope.upper()
                                    if 'SENATOR' in scope_upper:
                                        position = 'SENATOR'
                                    elif 'REPRESENTATIVES' in scope_upper:
                                        position = 'MEMBER, HOUSE OF REPRESENTATIVES'
                                    elif 'GOVERNOR' in scope_upper:
                                        position = 'GOVERNOR'
                                    elif 'VICE-GOVERNOR' in scope_upper:
                                        position = 'VICE GOVERNOR'
                                    elif 'MAYOR' in scope_upper:
                                        position = 'MAYOR'
                                    elif 'VICE-MAYOR' in scope_upper:
                                        position = 'VICE MAYOR'
                                    elif 'SANGGUNIANG PANLUNGSOD' in scope_upper:
                                        position = 'COUNCILOR'
                                    elif 'SANGGUNIANG PANLALAWIGAN' in scope_upper:
                                        position = 'PROVINCIAL BOARD MEMBER'
                                    else:
                                        position = 'OTHER'
                                
                                # Skip party-list positions only
                                if 'PARTY LIST' in scope or 'PARTY LIST' in contest_name.upper():
                                    continue
                                
                                
                                # Skip party-list and other non-dynasty positions
                                if position == 'OTHER' or 'PARTY LIST' in scope:
                                    continue
                                
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
                                
                                # Create unique key for position and location
                                position_key = f"{position}_{region}_{province}_{municipality_city}"
                                
                                # Store candidate data
                                if position_key not in chunk_candidates:
                                    chunk_candidates[position_key] = []
                                
                                chunk_candidates[position_key].append({
                                    'first_name': first_name,
                                    'last_name': last_name,
                                    'votes': votes,
                                    'position': position,
                                    'region': region,
                                    'province': province,
                                    'municipality_city': municipality_city,
                                    'scope': scope
                                })
                                
                except Exception as e:
                    print(f"  ⚠️ Error processing {csv_file}: {e}")
            
            return chunk_candidates
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Submit each chunk to a separate thread
            future_to_chunk = {executor.submit(process_csv_chunk, chunk): i for i, chunk in enumerate(csv_chunks)}
            
            # Collect results as they complete
            completed_chunks = 0
            for future in future_to_chunk:
                try:
                    chunk_candidates = future.result()
                    completed_chunks += 1
                    
                    if completed_chunks % 5 == 0:
                        print(f"  Completed {completed_chunks}/{len(csv_chunks)} chunks")
                    
                    # Merge results into main candidates_by_position
                    with candidates_lock:
                        for position_key, candidates in chunk_candidates.items():
                            if position_key not in candidates_by_position:
                                candidates_by_position[position_key] = []
                            candidates_by_position[position_key].extend(candidates)
                            
                except Exception as e:
                    chunk_index = future_to_chunk[future]
                    print(f"  ⚠️ Error processing chunk {chunk_index}: {e}")
        
        # Insert all candidates and mark winners
        print(f"📊 Processing {len(candidates_by_position)} positions")
        
        for position_key, candidates in candidates_by_position.items():
            # Find the winner (highest votes)
            winner = max(candidates, key=lambda x: x['votes'])
            
            # Insert all candidates for this position
            for candidate in candidates:
                is_winner = (candidate['votes'] == winner['votes'])
                
                # Insert the candidate with winner flag
                await conn.execute("""
                    INSERT INTO political_dynasties 
                    (first_name, last_name, party, region, province, municipality_city, position, year, fat, nickname, winner, votes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """, 
                candidate['first_name'],
                candidate['last_name'],
                None,  # party
                candidate['region'],
                candidate['province'],
                candidate['municipality_city'],
                candidate['position'],
                2025,  # year
                0,  # fat - not applicable for 2025
                None,  # nickname
                is_winner,  # winner flag
                candidate['votes']  # votes
                )
                
                total_records += 1
        
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
