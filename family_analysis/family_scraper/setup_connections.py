#!/usr/bin/env python3
"""
Setup connection system for political dynasties
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('visualization.env')

async def setup_connections():
    """Setup the connection system"""
    
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port='5432',
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        print("🔗 Setting up political dynasty connections...")
        
        # Clear existing connection data
        await conn.execute("""
            UPDATE political_dynasties 
            SET connection_type = NULL, connection_id = NULL, connection = NULL
        """)
        
        # Find COEFREDO UY (father of Stephany)
        coefredo_uy = await conn.fetchrow("""
            SELECT id, first_name, last_name, position, year 
            FROM political_dynasties 
            WHERE first_name = 'COEFREDO' AND last_name = 'UY' AND province = 'SAMAR'
            ORDER BY year DESC LIMIT 1
        """)
        
        if coefredo_uy:
            print(f"✅ Found COEFREDO UY: {coefredo_uy['first_name']} {coefredo_uy['last_name']} (ID: {coefredo_uy['id']})")
            
            # Find STEPHANY TAN (married to Stephen James Tan)
            stephany_tan = await conn.fetchrow("""
                SELECT id, first_name, last_name, position, year 
                FROM political_dynasties 
                WHERE first_name = 'STEPHANY' AND last_name = 'TAN' AND province = 'SAMAR'
                ORDER BY year DESC LIMIT 1
            """)
            
            if stephany_tan:
                print(f"✅ Found STEPHANY TAN: {stephany_tan['first_name']} {stephany_tan['last_name']} (ID: {stephany_tan['id']})")
                
                # Set up the connections:
                # 1. COEFREDO UY is father of STEPHANY TAN (connection_type = 1, connection_id = stephany_tan.id)
                await conn.execute("""
                    UPDATE political_dynasties 
                    SET connection_type = 1, connection_id = $1, connection = 'Father of Stephany Uy-Tan'
                    WHERE id = $2
                """, stephany_tan['id'], coefredo_uy['id'])
                
                # 2. STEPHANY TAN is daughter of COEFREDO UY (connection_type = 4, connection_id = coefredo_uy.id)
                await conn.execute("""
                    UPDATE political_dynasties 
                    SET connection_type = 4, connection_id = $1, connection = 'Daughter of Coefredo Uy'
                    WHERE id = $2
                """, coefredo_uy['id'], stephany_tan['id'])
                
                print("✅ Set up UY-TAN family connections:")
                print(f"   - COEFREDO UY (ID: {coefredo_uy['id']}) → Father of STEPHANY TAN (ID: {stephany_tan['id']})")
                print(f"   - STEPHANY TAN (ID: {stephany_tan['id']}) → Daughter of COEFREDO UY (ID: {coefredo_uy['id']})")
            else:
                print("❌ STEPHANY TAN not found in database")
        else:
            print("❌ COEFREDO UY not found in database")
        
        # Show connection types
        print("\n📋 Available connection types:")
        connection_types = await conn.fetch("SELECT code, name FROM connection_types ORDER BY code")
        for ct in connection_types:
            print(f"   {ct['code']}: {ct['name']}")
        
        # Show some examples of connections
        print("\n🔗 Current connections in database:")
        connections = await conn.fetch("""
            SELECT 
                p1.first_name || ' ' || p1.last_name as person1,
                ct.name as relationship,
                p2.first_name || ' ' || p2.last_name as person2,
                p1.connection as description
            FROM political_dynasties p1
            JOIN connection_types ct ON p1.connection_type = ct.code
            JOIN political_dynasties p2 ON p1.connection_id = p2.id
            WHERE p1.connection_type IS NOT NULL
            ORDER BY p1.first_name, p1.last_name
        """)
        
        for conn_row in connections:
            print(f"   {conn_row['person1']} → {conn_row['relationship']} → {conn_row['person2']}")
            print(f"      Description: {conn_row['description']}")
        
        print(f"\n✅ Connection system setup complete! Found {len(connections)} connections.")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(setup_connections())
