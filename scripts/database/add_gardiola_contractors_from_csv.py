#!/usr/bin/env python3
"""Parse gardiola_contractors.csv and add politician-contractor relationships to the database.
This script handles:
- Edwin Gardiola (CWS) -> Newington Builders Inc, Lourel Corp, S-Ang General Construction
- James Ang Jr. (Uswag Ilonggo) -> IBC International Corp, Allencon Corp
- Jernie Nisay (Pusong Pinoy) -> JVN Construction and Trading
- Augustina Pancho (Bulacan 3rd) -> C.M. Pancho Construction Inc.
- Joseph Lara (Cagayan 3rd) -> JLL Pulsar Construction
- Francisco Matugas (Surigao del Norte 1st) -> Boometrix Development Corp.
- Noel Rivera (Tarlac 3rd) -> Tarlac3-G and Development
- Zaldy Co (former Ako Bicol) -> FS Co Builders and Supply
"""

import asyncio
import asyncpg
import csv
import os
from dotenv import load_dotenv

load_dotenv()

def normalize_name(name):
    """Normalize name for database matching"""
    return name.strip().upper()

def parse_contractors(contractor_str):
    """Parse comma-separated contractor names"""
    if not contractor_str:
        return []
    return [c.strip() for c in contractor_str.split(',') if c.strip()]

async def find_or_create_politician(conn, name, district_party, source_url):
    """Find existing politician or create new one, handling name normalization"""
    # Try various name patterns
    name_parts = name.split()
    first_name = name_parts[0] if name_parts else name
    last_name = name_parts[-1] if len(name_parts) > 1 else ""
    middle_name = " ".join(name_parts[1:-1]) if len(name_parts) > 2 else ""
    
    # Handle special cases
    if "(former)" in name.lower():
        name = name.replace("(former)", "").replace("(Former)", "").strip()
        name_parts = name.split()
        first_name = name_parts[0] if name_parts else name
        last_name = name_parts[-1] if len(name_parts) > 1 else ""
    
    # Try to find existing politician
    # Search by first and last name
    politician = await conn.fetchrow('''
        SELECT id, first_name, last_name, position, normalized_name
        FROM political_dynasties
        WHERE UPPER(first_name) LIKE $1
          AND UPPER(last_name) LIKE $2
        ORDER BY id DESC
        LIMIT 1
    ''', f"%{first_name.upper()}%", f"%{last_name.upper()}%")
    
    if politician:
        print(f"✅ Found existing: {politician['first_name']} {politician['last_name']} (ID: {politician['id']})")
        return politician['id']
    
    # Create new politician
    # Determine position from district/party
    position = "CONGRESSMAN"
    if "Party" in district_party or "party" in district_party:
        position = f"PARTY-LIST REPRESENTATIVE ({district_party})"
    elif "District" in district_party or "district" in district_party or any(char.isdigit() for char in district_party):
        position = f"CONGRESSMAN ({district_party})"
    
    # Extract province if possible
    province = None
    if "Bulacan" in district_party:
        province = "BULACAN"
    elif "Cagayan" in district_party:
        province = "CAGAYAN"
    elif "Surigao" in district_party:
        province = "SURIGAO DEL NORTE"
    elif "Tarlac" in district_party:
        province = "TARLAC"
    elif "Bicol" in district_party or "BICOL" in district_party:
        province = "ALBAY"  # Ako Bicol is typically Albay-based
    
    normalized_name = normalize_name(f"{first_name} {last_name}")
    
    politician_id = await conn.fetchval('''
        INSERT INTO political_dynasties (first_name, last_name, position, province, normalized_name, year)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
    ''', first_name.upper(), last_name.upper(), position, province, normalized_name, 2025)
    
    print(f"✅ Created new: {first_name.upper()} {last_name.upper()} (ID: {politician_id}, Position: {position})")
    return politician_id

async def add_contractor_connection(conn, politician_id, contractor_name, source_url):
    """Add or update politician-contractor connection"""
    contractor_name_upper = contractor_name.upper().strip()
    
    # Check if connection already exists
    existing = await conn.fetchrow('''
        SELECT id FROM politician_contractors
        WHERE politician_id = $1 AND contractor_name = $2
    ''', politician_id, contractor_name_upper)
    
    if existing:
        print(f"   ⚠️  Connection already exists: {contractor_name_upper}")
        return False
    
    # Insert new connection
    await conn.execute('''
        INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
        VALUES ($1, $2, $3, $4, $5)
    ''', politician_id, contractor_name_upper, 10,
        f"Contractor linked to congressman/party-list representative. Source: Philippine Star article on plunder/graft cases", 
        source_url)
    
    print(f"   ✅ Added contractor: {contractor_name_upper}")
    return True

async def main():
    csv_path = "database/gardiola_contractors.csv"
    
    if not os.path.exists(csv_path):
        print(f"❌ CSV file not found: {csv_path}")
        return
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        source_url = "https://www.philstar.com/headlines/2025/11/27/2490186/co-7-lawmakers-face-plunder-graft-cases"
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            total_added = 0
            
            for row in reader:
                congressman = row.get('Congressman', '').strip()
                district_party = row.get('District/Party', '').strip()
                contractors_str = row.get('Contractor(s)', '').strip()
                source = row.get('Source', source_url).strip()
                
                if not congressman:
                    continue
                
                print(f"\n📋 Processing: {congressman} ({district_party})")
                
                # Find or create politician
                politician_id = await find_or_create_politician(conn, congressman, district_party, source)
                
                # Parse and add contractors
                contractors = parse_contractors(contractors_str)
                for contractor in contractors:
                    if await add_contractor_connection(conn, politician_id, contractor, source):
                        total_added += 1
        
        print(f"\n✅ Done! Added {total_added} new contractor connections")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

