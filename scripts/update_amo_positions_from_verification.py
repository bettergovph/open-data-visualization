#!/usr/bin/env python3
"""
Update AMO positions in database based on Perplexity verification results.
Moves past positions and non-elected officials to indirect or removes them.
"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

# Based on Perplexity verification:
# Current 2025 positions (keep as direct):
CURRENT_2025 = [
    "JOSEPH JEREMY DE GUZMAN LARA",  # Mayor, Solsona, Ilocos Norte
    "GIAN NICOLETTE GUILLEN CHUA",  # Councilor, Piddig, Ilocos Norte
    "GLENN CARLO LIM TAN",  # Councilor, Paranas, Samar
    "ROMEO C. RIVERA",  # Councilor, Baao, Camarines Sur
]

# Not elected officials (remove from direct, move to indirect if they have relationships):
NOT_ELECTED = [
    "FERDINAND L. BELTRAN",  # Not a party-list representative
    "CARLOS ANDES LORIA",  # Not a congressman
    "MA. CONSUELO C. ROQUE",  # Not DTI Secretary
]

# Past positions only (move to indirect if they have relationships to current elected):
PAST_POSITIONS = [
    "CHINGBE A. GILBOR",  # 2016 Councilor - past
    "ARTURO B. UY",  # 2004 Councilor - past
    "ROMANITO DEL ROSARIO JUATCO",  # 2010 Provincial Board - past
    "FAROUK M. MACARAMBON",  # 2016 Provincial Board - past
    "ROLANDO Y. DOMINGO",  # 2004 Councilor - past
    "MA. CHARLOTA C. ADLAWAN",  # 2013 Councilor - past
    "ISARME AMARILLO BOSQUE",  # 2004 Mayor - past
    "NOLI A. VENZON",  # 2004 Mayor - past
    "PERFECTO P. CEZAR",  # 2004 Councilor - past
    "NELSON NESIA YU",  # 2010 Mayor - past
    "CHRISTIAN EMMANUEL R. PERALTA",  # 2004 Councilor - past
    "ERIC GO ONG",  # 2007 Councilor - past
    "MARTIN GERARD S. TAN",  # 2007 Councilor - past
    "ROGELIO B. YAP",  # 2004 Mayor - past
    "DOMINGO QUE TAN",  # 2004 Mayor - past
    "BILLY M. ACERON",  # 2016 Mayor - past
    "LARRY REY VILLANUEVA",  # 2007 Councilor - past
    "JOSE CABARAL TIU",  # 2007 Mayor - past
    "DANIEL SALONGA PAMINTUAN",  # 2004 Councilor - past
    "MA. CORAZON R. AGUILAR",  # 2004 Mayor - past
    "ERLINDA WEE ENG GO",  # 2004 Councilor - past
    "MARTIN JUNBOY CALDERON TAN",  # 2007 Councilor - past
    "MARCIAL R. VARGAS",  # 2004 Mayor - past
]


async def update_positions():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='dynasty'
    )
    
    print("=" * 80)
    print("UPDATING AMO POSITIONS BASED ON PERPLEXITY VERIFICATION")
    print("=" * 80)
    print()
    
    updates = []
    
    # Handle NOT_ELECTED - change to Contractor/Corporate Officer
    print("📋 Updating NOT ELECTED officials...")
    for name in NOT_ELECTED:
        name_parts = name.split()
        if len(name_parts) >= 2:
            first = name_parts[0].upper()
            last = name_parts[-1].upper()
            
            rows = await conn.fetch("""
                SELECT id, first_name, last_name, position
                FROM political_dynasties
                WHERE UPPER(first_name) = $1 
                  AND UPPER(last_name) = $2
                  AND position_category IN ('Elected Officials', 'Elected Official', 'Representative')
                LIMIT 5
            """, first, last)
            
            for row in rows:
                await conn.execute("""
                    UPDATE political_dynasties
                    SET position_category = 'Contractor/Corporate Officer',
                        position = NULL,
                        government_branch = 'Private Sector'
                    WHERE id = $1
                """, row['id'])
                updates.append(f"✅ {row['first_name']} {row['last_name']}: Changed to Contractor (not elected)")
                print(f"✅ {row['first_name']} {row['last_name']} (ID: {row['id']}): Changed to Contractor")
    
    # Handle PAST_POSITIONS - check for relationships to current elected, if none, change to Contractor
    print(f"\n📋 Checking PAST POSITIONS ({len(PAST_POSITIONS)} names)...")
    for name in PAST_POSITIONS:
        name_parts = name.split()
        if len(name_parts) >= 2:
            first = name_parts[0].upper()
            last = name_parts[-1].upper()
            
            person = await conn.fetchrow("""
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE UPPER(first_name) = $1 
                  AND UPPER(last_name) = $2
                  AND position_category IN ('Elected Officials', 'Elected Official')
                ORDER BY year DESC NULLS LAST
                LIMIT 1
            """, first, last)
            
            if person:
                # Check for relationships to current elected officials (2020+)
                rels = await conn.fetch("""
                    SELECT r.related_person_id, ct.name as rel_name,
                           p.first_name, p.last_name, p.position, p.year
                    FROM relationships r
                    JOIN connection_types ct ON r.relationship_type = ct.id
                    JOIN political_dynasties p ON r.related_person_id = p.id
                    WHERE r.person_id = $1
                      AND p.year >= 2020
                      AND (
                          p.position_category IN ('Elected Officials', 'Elected Official', 'Representative')
                          OR p.government_branch IN ('Legislative', 'Executive')
                      )
                    LIMIT 1
                """, person['id'])
                
                if not rels:
                    # No current relationships - change to Contractor
                    await conn.execute("""
                        UPDATE political_dynasties
                        SET position_category = 'Contractor/Corporate Officer',
                            position = NULL,
                            government_branch = 'Private Sector'
                        WHERE id = $1
                    """, person['id'])
                    updates.append(f"✅ {person['first_name']} {person['last_name']}: Changed to Contractor (past position, no current relationships)")
                    print(f"✅ {person['first_name']} {person['last_name']} (ID: {person['id']}): Changed to Contractor (past position)")
                else:
                    # Has relationships - keep as is (will show in indirect)
                    print(f"ℹ️  {person['first_name']} {person['last_name']}: Past position but has relationships to current elected - keeping")
    
    print(f"\n✅ Made {len(updates)} updates")
    print("\nSummary:")
    for update in updates:
        print(f"  {update}")
    
    await conn.close()
    
    print("\n" + "=" * 80)
    print("✅ UPDATES COMPLETE")
    print("=" * 80)
    print("\nNext steps:")
    print("1. Run: python3 scripts/generate_philgeps_amo_cache.py")
    print("2. Review the updated cache")


if __name__ == '__main__':
    asyncio.run(update_positions())

