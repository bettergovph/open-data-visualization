#!/usr/bin/env python3
"""
Investigate Bernadette Herrera's contractor relationships and their sources.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def investigate_herrera():
    """Query database for Bernadette Herrera's contractor relationships."""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("🔍 Investigating Bernadette Herrera's contractor relationships...\n")
        
        # First, find Bernadette Herrera in political_dynasties
        herrera_records = await conn.fetch("""
            SELECT id, first_name, last_name, middle_name, party, position, year, normalized_name
            FROM political_dynasties
            WHERE LOWER(first_name) LIKE '%bernadette%' 
               OR LOWER(last_name) LIKE '%herrera%'
            ORDER BY year DESC
        """)
        
        print(f"📋 Found {len(herrera_records)} Bernadette Herrera records:")
        for record in herrera_records:
            print(f"   ID: {record['id']}, Name: {record['first_name']} {record['last_name']}, "
                  f"Party: {record['party']}, Position: {record['position']}, Year: {record['year']}, "
                  f"Normalized: {record['normalized_name']}")
        
        if not herrera_records:
            print("❌ No Bernadette Herrera found in political_dynasties")
            return
        
        # Get all contractor relationships for all Herrera IDs
        herrera_ids = [r['id'] for r in herrera_records]
        
        contractor_relationships = await conn.fetch("""
            SELECT 
                pc.id,
                pc.politician_id,
                pc.contractor_name,
                pc.match_confidence,
                pc.notes,
                pc.source,
                pd.first_name,
                pd.last_name,
                pd.party,
                pd.position,
                pd.year
            FROM politician_contractors pc
            JOIN political_dynasties pd ON pc.politician_id = pd.id
            WHERE pc.politician_id = ANY($1)
            ORDER BY pc.contractor_name, pd.year DESC
        """, herrera_ids)
        
        print(f"\n🔗 Found {len(contractor_relationships)} contractor relationships:\n")
        
        # Group by contractor to see patterns
        contractors = {}
        for rel in contractor_relationships:
            contractor = rel['contractor_name']
            if contractor not in contractors:
                contractors[contractor] = []
            contractors[contractor].append({
                'id': rel['id'],
                'politician_id': rel['politician_id'],
                'name': f"{rel['first_name']} {rel['last_name']}",
                'party': rel['party'],
                'position': rel['position'],
                'year': rel['year'],
                'match_confidence': rel['match_confidence'],
                'notes': rel['notes'],
                'source': rel['source']
            })
        
        print(f"📊 Summary: {len(contractors)} unique contractors linked to Bernadette Herrera\n")
        
        # Show contractors with sources
        print("=" * 80)
        print("CONTRACTOR RELATIONSHIPS WITH SOURCES:")
        print("=" * 80)
        
        for contractor, relationships in sorted(contractors.items()):
            print(f"\n🏢 {contractor}")
            print(f"   Linked {len(relationships)} time(s)")
            
            sources = set()
            for rel in relationships:
                if rel['source']:
                    sources.add(rel['source'])
                if rel['notes']:
                    print(f"   Notes: {rel['notes']}")
            
            if sources:
                print(f"   Sources: {', '.join(sorted(sources))}")
            else:
                print(f"   ⚠️  NO SOURCE SPECIFIED")
            
            # Show which politician records this contractor is linked to
            for rel in relationships:
                print(f"   - Linked to: {rel['name']} ({rel['party']}, {rel['position']}, {rel['year']}) "
                      f"[ID: {rel['politician_id']}]")
                if rel['match_confidence']:
                    print(f"     Match confidence: {rel['match_confidence']}")
        
        # Check if there are any DIME-based relationships (which might be automatic)
        print("\n" + "=" * 80)
        print("CHECKING FOR DIME-BASED RELATIONSHIPS:")
        print("=" * 80)
        
        dime_relationships = await conn.fetch("""
            SELECT 
                pc.contractor_name,
                COUNT(*) as count,
                STRING_AGG(DISTINCT pc.source, ', ') as sources
            FROM politician_contractors pc
            WHERE pc.politician_id = ANY($1)
            GROUP BY pc.contractor_name
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """, herrera_ids)
        
        if dime_relationships:
            print(f"\n⚠️  Found {len(dime_relationships)} contractors with multiple relationships")
            print("   (This might indicate automatic/programmatic linking)\n")
            for rel in dime_relationships[:10]:  # Show top 10
                print(f"   {rel['contractor_name']}: {rel['count']} links, Sources: {rel['sources']}")
        
        # Check contractor_dynasty_matches table (used by constellation cache)
        print("\n" + "=" * 80)
        print("CHECKING contractor_dynasty_matches TABLE:")
        print("=" * 80)
        
        dynasty_matches = await conn.fetch("""
            SELECT 
                cdm.company_name,
                cdm.person_name,
                cdm.role,
                cdm.dynasty_full_name,
                cdm.dynasty_first_name,
                cdm.dynasty_last_name,
                cdm.source_csv_file,
                cdm.matched_at
            FROM contractor_dynasty_matches cdm
            WHERE UPPER(cdm.dynasty_full_name) LIKE '%BERNADETTE%HERRERA%'
               OR UPPER(cdm.dynasty_first_name) LIKE '%BERNADETTE%'
               OR UPPER(cdm.dynasty_last_name) LIKE '%HERRERA%'
            ORDER BY cdm.company_name
        """)
        
        if dynasty_matches:
            print(f"\n⚠️  Found {len(dynasty_matches)} entries in contractor_dynasty_matches:")
            for match in dynasty_matches:
                print(f"\n   🏢 Company: {match['company_name']}")
                print(f"      Person: {match['person_name']}")
                print(f"      Dynasty: {match['dynasty_full_name']} ({match['dynasty_first_name']} {match['dynasty_last_name']})")
                print(f"      Role: {match['role']}")
                print(f"      Source: {match['source_csv_file']}")
                print(f"      Matched at: {match['matched_at']}")
        else:
            print("\n   No entries found in contractor_dynasty_matches")
        
        # Check sources.csv for any Herrera-related sources
        print("\n" + "=" * 80)
        print("CHECKING SOURCES.CSV FOR HERRERA-RELATED SOURCES:")
        print("=" * 80)
        
        # Read sources.csv
        sources_file = "database/sources.csv"
        if os.path.exists(sources_file):
            with open(sources_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                herrera_sources = []
                for line in lines:
                    if 'herrera' in line.lower():
                        herrera_sources.append(line.strip())
                
                if herrera_sources:
                    print(f"\n📰 Found {len(herrera_sources)} Herrera-related sources in sources.csv:")
                    for source in herrera_sources:
                        print(f"   {source}")
                else:
                    print("\n   No Herrera-specific sources found in sources.csv")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(investigate_herrera())

