#!/usr/bin/env python3
"""
Create party_memberships table to track political party affiliations over time.

This allows us to:
1. Track one-to-many relationship (person can belong to multiple parties over time)
2. Identify political allies based on shared party membership during overlapping periods
3. Track party changes based on presidential administrations
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv


async def create_party_tables():
    """Create political_parties and party_memberships tables"""
    load_dotenv()
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("🏗️ Creating political party tables...")
        
        # 1. Create political_parties table (master list of parties)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS political_parties (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                abbreviation VARCHAR(50),
                description TEXT,
                founded_year INTEGER,
                ideology VARCHAR(100),  -- e.g., 'Liberal', 'Conservative', 'Nationalist', 'Socialist'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Created political_parties table")
        
        # 2. Create party_memberships table (one-to-many: person -> parties over time)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS party_memberships (
                id SERIAL PRIMARY KEY,
                person_id INTEGER NOT NULL REFERENCES political_dynasties(id) ON DELETE CASCADE,
                party_id INTEGER NOT NULL REFERENCES political_parties(id) ON DELETE CASCADE,
                joined_date DATE,  -- When they joined this party
                left_date DATE,    -- When they left this party (NULL if still current)
                is_current BOOLEAN DEFAULT TRUE,  -- Currently active member
                position_in_party VARCHAR(255),  -- e.g., 'President', 'Secretary', 'Member'
                source_url TEXT,   -- Source for this membership info
                confidence_level INTEGER CHECK (confidence_level >= 1 AND confidence_level <= 10),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, party_id, joined_date)  -- Prevent duplicate memberships
            )
        """)
        print("✅ Created party_memberships table")
        
        # 3. Create indexes for performance
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_party_memberships_person_id 
            ON party_memberships(person_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_party_memberships_party_id 
            ON party_memberships(party_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_party_memberships_dates 
            ON party_memberships(joined_date, left_date)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_party_memberships_current 
            ON party_memberships(is_current) WHERE is_current = TRUE
        """)
        print("✅ Created indexes")
        
        # 4. Migrate existing party data from political_dynasties.party if it exists
        print("\n📊 Checking for existing party data in political_dynasties...")
        party_data = await conn.fetch("""
            SELECT DISTINCT party, year, COUNT(*) as count
            FROM political_dynasties
            WHERE party IS NOT NULL AND party <> ''
            GROUP BY party, year
            ORDER BY year DESC, count DESC
            LIMIT 20
        """)
        
        if party_data:
            print(f"📋 Found party data in {len(party_data)} party-year combinations")
            print("\nTop parties found:")
            for row in party_data[:10]:
                print(f"   - {row['party']} ({row['year']}): {row['count']} records")
            
            # Insert unique party names into political_parties
            unique_parties = await conn.fetch("""
                SELECT DISTINCT party
                FROM political_dynasties
                WHERE party IS NOT NULL AND party <> ''
            """)
            
            inserted_parties = 0
            for party_row in unique_parties:
                party_name = party_row['party'].strip()
                if party_name:
                    await conn.execute("""
                        INSERT INTO political_parties (name)
                        VALUES ($1)
                        ON CONFLICT (name) DO NOTHING
                    """, party_name)
                    inserted_parties += 1
            
            print(f"\n✅ Inserted {inserted_parties} unique parties into political_parties table")
            
            # Create a function to help migrate party data (optional - can be run separately)
            print("\n💡 Tip: You can migrate existing party data using:")
            print("   python3 migrate_existing_party_data.py")
        
        else:
            print("ℹ️  No existing party data found in political_dynasties table")
        
        # 5. Create view for easy querying of current party memberships
        await conn.execute("""
            CREATE OR REPLACE VIEW current_party_memberships AS
            SELECT 
                pm.id,
                pd.id as person_id,
                CONCAT(pd.first_name, ' ', pd.last_name) as person_name,
                pp.id as party_id,
                pp.name as party_name,
                pp.abbreviation as party_abbreviation,
                pm.joined_date,
                pm.position_in_party,
                pm.is_current
            FROM party_memberships pm
            JOIN political_dynasties pd ON pm.person_id = pd.id
            JOIN political_parties pp ON pm.party_id = pp.id
            WHERE pm.is_current = TRUE
            ORDER BY pd.last_name, pd.first_name
        """)
        print("✅ Created current_party_memberships view")
        
        # 6. Create view for finding political allies (shared party memberships during overlapping periods)
        await conn.execute("""
            CREATE OR REPLACE VIEW potential_political_allies AS
            SELECT DISTINCT
                pd1.id as person1_id,
                CONCAT(pd1.first_name, ' ', pd1.last_name) as person1_name,
                pd2.id as person2_id,
                CONCAT(pd2.first_name, ' ', pd2.last_name) as person2_name,
                pp.id as party_id,
                pp.name as party_name,
                GREATEST(
                    COALESCE(pm1.joined_date, '1900-01-01'::date),
                    COALESCE(pm2.joined_date, '1900-01-01'::date)
                ) as overlap_start,
                LEAST(
                    COALESCE(pm1.left_date, CURRENT_DATE),
                    COALESCE(pm2.left_date, CURRENT_DATE)
                ) as overlap_end,
                CASE 
                    WHEN GREATEST(
                        COALESCE(pm1.joined_date, '1900-01-01'::date),
                        COALESCE(pm2.joined_date, '1900-01-01'::date)
                    ) <= LEAST(
                        COALESCE(pm1.left_date, CURRENT_DATE),
                        COALESCE(pm2.left_date, CURRENT_DATE)
                    )
                    THEN TRUE
                    ELSE FALSE
                END as had_overlap
            FROM party_memberships pm1
            JOIN party_memberships pm2 ON pm1.party_id = pm2.party_id AND pm1.person_id < pm2.person_id
            JOIN political_dynasties pd1 ON pm1.person_id = pd1.id
            JOIN political_dynasties pd2 ON pm2.person_id = pd2.id
            JOIN political_parties pp ON pm1.party_id = pp.id
            WHERE pm1.is_current = TRUE OR pm2.is_current = TRUE
            ORDER BY person1_name, person2_name
        """)
        print("✅ Created potential_political_allies view")
        
        print("\n✅ All party tables and views created successfully!")
        print("\n📋 Next steps:")
        print("   1. Use Perplexity to gather party membership data for senators")
        print("   2. Insert party names into political_parties table")
        print("   3. Insert party memberships into party_memberships table with dates")
        print("   4. Query potential_political_allies view to identify political relationships")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(create_party_tables())

