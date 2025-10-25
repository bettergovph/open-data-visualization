#!/usr/bin/env python3
"""
2025 Election Data Import Script - UNIQUE NAMES ONLY
Ensures each person appears only once per year, regardless of precincts
"""

import asyncio
import asyncpg
import csv
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading
from collections import defaultdict

async def main():
    # Database connection
    db_host = 'localhost'
    db_port = 5432
    db_user = 'budget_admin'
    db_password = 'wuQ5gBYCKkZiOGb61chLcByMu'
    db_name = 'dynasty'
    
    print("🚀 Connecting to local dynasty database...")
    
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
    tar_files = list(elections_data_path.glob('*.tar.gz'))
    for tar_file in tar_files:
        print(f"  Extracting {tar_file.name}...")
        import subprocess
        subprocess.run(['tar', '-xf', str(tar_file), '-C', str(tar_file.parent)], check=True)
    
    # Find all CSV files
    csv_files = list(elections_data_path.rglob('*.csv'))
    print(f"📊 Found {len(csv_files)} CSV files to process")
    
    # Collect all candidates data first
    print("📊 Collecting all candidates data...")
    all_candidates = defaultdict(list)  # position -> list of candidates with votes
    
    def process_csv_file(csv_file):
        """Process a single CSV file and return candidates data"""
        file_candidates = []
        
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
                        
                        # Skip party list positions
                        if 'PARTY LIST' in scope or 'PARTY LIST' in contest_name.upper():
                            continue
                        
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
                        
                        if not position:
                            continue
                        
                        # Parse candidate name
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
                        
                        # Create candidate record
                        candidate = {
                            'first_name': first_name,
                            'last_name': last_name,
                            'region': region,
                            'province': province,
                            'municipality_city': municipality_city,
                            'position': position,
                            'votes': votes,
                            'precinct_code': precinct_code
                        }
                        
                        file_candidates.append(candidate)
                        
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
        chunk_candidates = []
        
        for csv_file in chunk_files:
            try:
                file_candidates = process_csv_file(csv_file)
                chunk_candidates.extend(file_candidates)
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
                
                # Add candidates to the main collection
                for candidate in chunk_candidates:
                    position = candidate['position']
                    all_candidates[position].append(candidate)
                    
            except Exception as e:
                chunk_index = future_to_chunk[future]
                print(f"  ⚠️ Error processing chunk {chunk_index}: {e}")
    
    print(f"📊 Collected candidates for {len(all_candidates)} positions")
    
    # Now process each position to determine winners
    total_records = 0
    
    for position, candidates in all_candidates.items():
        print(f"📊 Processing {len(candidates)} candidates for {position}...")
        
        # For national positions (SENATOR, MEMBER HOUSE OF REPRESENTATIVES), 
        # aggregate votes by candidate across all precincts
        if position in ['SENATOR', 'MEMBER, HOUSE OF REPRESENTATIVES']:
            # Aggregate votes by candidate
            candidate_votes = defaultdict(int)
            candidate_info = {}
            
            for candidate in candidates:
                key = f"{candidate['first_name']}|{candidate['last_name']}"
                candidate_votes[key] += candidate['votes']
                candidate_info[key] = candidate  # Store the last candidate info
            
            # Sort by total votes and determine winners
            sorted_candidates = sorted(candidate_votes.items(), key=lambda x: x[1], reverse=True)
            
            # For senators, top 12 are winners
            # For house reps, it depends on the district (we'll use top 1 per district for now)
            if position == 'SENATOR':
                num_winners = 12
            else:
                num_winners = len(sorted_candidates)  # All house reps are winners for now
            
            winners = sorted_candidates[:num_winners]
            winner_votes = {key: votes for key, votes in winners}
            
            # Insert UNIQUE candidates only (one per person per year)
            for key, total_votes in candidate_votes.items():
                candidate = candidate_info[key]
                is_winner = key in winner_votes
                
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
                0,  # fat
                None,  # nickname
                is_winner,  # winner flag
                total_votes  # aggregated votes
                )
                
                total_records += 1
        
        else:
            # For local positions, use precinct-level logic
            # Group by location (province + municipality)
            location_candidates = defaultdict(list)
            
            for candidate in candidates:
                location_key = f"{candidate['province']}|{candidate['municipality_city']}"
                location_candidates[location_key].append(candidate)
            
            # Process each location separately
            for location_key, location_candidates_list in location_candidates.items():
                # Aggregate votes by candidate within this location
                location_candidate_votes = defaultdict(int)
                location_candidate_info = {}
                
                for candidate in location_candidates_list:
                    key = f"{candidate['first_name']}|{candidate['last_name']}"
                    location_candidate_votes[key] += candidate['votes']
                    location_candidate_info[key] = candidate
                
                # Find winner in this location
                winner_key = max(location_candidate_votes.items(), key=lambda x: x[1])[0]
                winner_votes = location_candidate_votes[winner_key]
                
                # Insert UNIQUE candidates only (one per person per location per year)
                for key, total_votes in location_candidate_votes.items():
                    candidate = location_candidate_info[key]
                    is_winner = (key == winner_key)
                    
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
                    0,  # fat
                    None,  # nickname
                    is_winner,  # winner flag
                    total_votes  # aggregated votes
                    )
                    
                    total_records += 1
    
    print(f"✅ Imported {total_records} records from 2025 elections")
    
    # Show final statistics
    final_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE year = 2025")
    winners_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE year = 2025 AND winner = true")
    losers_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE year = 2025 AND winner = false")
    
    print(f"📊 Total 2025 records in database: {final_count}")
    print(f"🏆 Winners: {winners_count}")
    print(f"❌ Losers: {losers_count}")
    
    # Show senator winners
    senator_winners = await conn.fetch("""
        SELECT first_name, last_name, votes 
        FROM political_dynasties 
        WHERE year = 2025 AND position = 'SENATOR' AND winner = true 
        ORDER BY votes DESC
    """)
    
    print(f"📊 Senator winners ({len(senator_winners)}):")
    for senator in senator_winners:
        print(f"  {senator['first_name']} {senator['last_name']}: {senator['votes']:,} votes")
    
    await conn.close()
    print("✅ 2025 elections data import completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
