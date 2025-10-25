#!/usr/bin/env python3
"""
Expand Dynasty Database to Include All Government Positions
SC Justices, Department Secretaries, and other government officials
"""

import asyncio
import asyncpg
from typing import List, Dict

class DynastyDatabaseExpander:
    def __init__(self):
        self.db_conn = None
        
    async def connect(self):
        """Connect to the dynasty database"""
        self.db_conn = await asyncpg.connect(
            host='localhost',
            port='5432',
            user='budget_admin',
            password='wuQ5gBYCKkZiOGb61chLcByMu',
            database='dynasty'
        )
        print("✅ Connected to dynasty database")
        
    async def close(self):
        """Close database connection"""
        if self.db_conn:
            await self.db_conn.close()
            print("✅ Database connection closed")
    
    async def analyze_current_structure(self):
        """Analyze current database structure"""
        print("📊 ANALYZING CURRENT DATABASE STRUCTURE")
        print("=" * 60)
        
        # Check table structure
        columns = await self.db_conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'political_dynasties'
            ORDER BY ordinal_position
        """)
        
        print("Current table structure:")
        for col in columns:
            print(f"   {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
        
        # Check current position types
        positions = await self.db_conn.fetch("""
            SELECT 
                position,
                COUNT(*) as count
            FROM political_dynasties 
            WHERE position IS NOT NULL AND position != ''
            GROUP BY position
            ORDER BY count DESC
            LIMIT 20
        """)
        
        print(f"\nCurrent position types ({len(positions)} total):")
        for pos in positions:
            print(f"   {pos['count']:>4} - {pos['position']}")
    
    async def create_government_positions_table(self):
        """Create a comprehensive government positions reference table"""
        print("\n🔨 CREATING GOVERNMENT POSITIONS REFERENCE TABLE")
        print("=" * 60)
        
        # Create government positions table
        await self.db_conn.execute("""
            CREATE TABLE IF NOT EXISTS government_positions (
                id SERIAL PRIMARY KEY,
                position_name VARCHAR(200) NOT NULL,
                position_category VARCHAR(100) NOT NULL,
                government_branch VARCHAR(50) NOT NULL,
                level VARCHAR(50) NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        print("✅ Government positions table created")
    
    async def populate_government_positions(self):
        """Populate the government positions table"""
        print("\n📋 POPULATING GOVERNMENT POSITIONS")
        print("=" * 60)
        
        # Comprehensive list of government positions
        positions = [
            # Judiciary
            ("CHIEF JUSTICE", "Judiciary", "Supreme Court", "National", "Head of the Supreme Court"),
            ("ASSOCIATE JUSTICE", "Judiciary", "Supreme Court", "National", "Supreme Court Associate Justice"),
            ("COURT OF APPEALS JUSTICE", "Judiciary", "Court of Appeals", "National", "Court of Appeals Justice"),
            ("REGIONAL TRIAL COURT JUDGE", "Judiciary", "Regional Trial Court", "Regional", "RTC Judge"),
            ("METROPOLITAN TRIAL COURT JUDGE", "Judiciary", "Metropolitan Trial Court", "Local", "MTC Judge"),
            ("MUNICIPAL TRIAL COURT JUDGE", "Judiciary", "Municipal Trial Court", "Local", "Municipal Judge"),
            
            # Executive Department - Cabinet Secretaries
            ("SECRETARY OF AGRICULTURE", "Executive", "Department of Agriculture", "National", "DA Secretary"),
            ("SECRETARY OF EDUCATION", "Executive", "Department of Education", "National", "DepEd Secretary"),
            ("SECRETARY OF HEALTH", "Executive", "Department of Health", "National", "DOH Secretary"),
            ("SECRETARY OF FINANCE", "Executive", "Department of Finance", "National", "DOF Secretary"),
            ("SECRETARY OF INTERIOR AND LOCAL GOVERNMENT", "Executive", "DILG", "National", "DILG Secretary"),
            ("SECRETARY OF NATIONAL DEFENSE", "Executive", "Department of National Defense", "National", "DND Secretary"),
            ("SECRETARY OF PUBLIC WORKS AND HIGHWAYS", "Executive", "DPWH", "National", "DPWH Secretary"),
            ("SECRETARY OF TRANSPORTATION", "Executive", "DOTr", "National", "DOTr Secretary"),
            ("SECRETARY OF TOURISM", "Executive", "DOT", "National", "DOT Secretary"),
            ("SECRETARY OF TRADE AND INDUSTRY", "Executive", "DTI", "National", "DTI Secretary"),
            ("SECRETARY OF LABOR AND EMPLOYMENT", "Executive", "DOLE", "National", "DOLE Secretary"),
            ("SECRETARY OF SOCIAL WELFARE AND DEVELOPMENT", "Executive", "DSWD", "National", "DSWD Secretary"),
            ("SECRETARY OF ENVIRONMENT AND NATURAL RESOURCES", "Executive", "DENR", "National", "DENR Secretary"),
            ("SECRETARY OF ENERGY", "Executive", "DOE", "National", "DOE Secretary"),
            ("SECRETARY OF SCIENCE AND TECHNOLOGY", "Executive", "DOST", "National", "DOST Secretary"),
            ("SECRETARY OF INFORMATION AND COMMUNICATIONS TECHNOLOGY", "Executive", "DICT", "National", "DICT Secretary"),
            ("SECRETARY OF FOREIGN AFFAIRS", "Executive", "DFA", "National", "DFA Secretary"),
            ("SECRETARY OF JUSTICE", "Executive", "DOJ", "National", "DOJ Secretary"),
            ("SECRETARY OF BUDGET AND MANAGEMENT", "Executive", "DBM", "National", "DBM Secretary"),
            ("SECRETARY OF AGRARIAN REFORM", "Executive", "DAR", "National", "DAR Secretary"),
            ("SECRETARY OF AGRICULTURE", "Executive", "DA", "National", "DA Secretary"),
            
            # Executive Department - Other High Positions
            ("EXECUTIVE SECRETARY", "Executive", "Office of the President", "National", "Executive Secretary"),
            ("PRESIDENTIAL SPOKESPERSON", "Executive", "Office of the President", "National", "Presidential Spokesperson"),
            ("NATIONAL SECURITY ADVISER", "Executive", "Office of the President", "National", "NSA"),
            ("CHIEF OF STAFF", "Executive", "Office of the President", "National", "Chief of Staff"),
            ("SPECIAL ASSISTANT TO THE PRESIDENT", "Executive", "Office of the President", "National", "SAP"),
            
            # Constitutional Commissions
            ("CHAIRMAN, COMMISSION ON ELECTIONS", "Constitutional Commission", "COMELEC", "National", "COMELEC Chairman"),
            ("COMMISSIONER, COMMISSION ON ELECTIONS", "Constitutional Commission", "COMELEC", "National", "COMELEC Commissioner"),
            ("CHAIRMAN, COMMISSION ON AUDIT", "Constitutional Commission", "COA", "National", "COA Chairman"),
            ("COMMISSIONER, COMMISSION ON AUDIT", "Constitutional Commission", "COA", "National", "COA Commissioner"),
            ("CHAIRMAN, CIVIL SERVICE COMMISSION", "Constitutional Commission", "CSC", "National", "CSC Chairman"),
            ("COMMISSIONER, CIVIL SERVICE COMMISSION", "Constitutional Commission", "CSC", "National", "CSC Commissioner"),
            
            # Government-Owned and Controlled Corporations
            ("PRESIDENT, GOVERNMENT SERVICE INSURANCE SYSTEM", "GOCC", "GSIS", "National", "GSIS President"),
            ("PRESIDENT, SOCIAL SECURITY SYSTEM", "GOCC", "SSS", "National", "SSS President"),
            ("PRESIDENT, PHILIPPINE HEALTH INSURANCE CORPORATION", "GOCC", "PhilHealth", "National", "PhilHealth President"),
            ("PRESIDENT, DEVELOPMENT BANK OF THE PHILIPPINES", "GOCC", "DBP", "National", "DBP President"),
            ("PRESIDENT, LAND BANK OF THE PHILIPPINES", "GOCC", "LBP", "National", "LBP President"),
            
            # Military and Police
            ("CHIEF OF STAFF, ARMED FORCES OF THE PHILIPPINES", "Military", "AFP", "National", "AFP Chief of Staff"),
            ("COMMANDING GENERAL, PHILIPPINE ARMY", "Military", "PA", "National", "PA Commanding General"),
            ("FLAG OFFICER IN COMMAND, PHILIPPINE NAVY", "Military", "PN", "National", "PN Flag Officer"),
            ("COMMANDING GENERAL, PHILIPPINE AIR FORCE", "Military", "PAF", "National", "PAF Commanding General"),
            ("CHIEF, PHILIPPINE NATIONAL POLICE", "Police", "PNP", "National", "PNP Chief"),
            ("DIRECTOR GENERAL, PHILIPPINE NATIONAL POLICE", "Police", "PNP", "National", "PNP Director General"),
            
            # Existing positions (keep current ones)
            ("SENATOR", "Legislative", "Senate", "National", "Senator"),
            ("MEMBER, HOUSE OF REPRESENTATIVES", "Legislative", "House of Representatives", "National", "Congressman/Congresswoman"),
            ("GOVERNOR", "Executive", "Provincial Government", "Provincial", "Provincial Governor"),
            ("VICE GOVERNOR", "Executive", "Provincial Government", "Provincial", "Provincial Vice Governor"),
            ("MAYOR", "Executive", "City/Municipal Government", "Local", "City/Municipal Mayor"),
            ("VICE MAYOR", "Executive", "City/Municipal Government", "Local", "City/Municipal Vice Mayor"),
            ("COUNCILOR", "Legislative", "City/Municipal Council", "Local", "City/Municipal Councilor"),
            ("PROVINCIAL BOARD MEMBER", "Legislative", "Provincial Board", "Provincial", "Provincial Board Member"),
        ]
        
        # Insert positions
        for position in positions:
            try:
                await self.db_conn.execute("""
                    INSERT INTO government_positions 
                    (position_name, position_category, government_branch, level, description)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT DO NOTHING
                """, *position)
            except Exception as e:
                print(f"   ⚠️  Error inserting {position[0]}: {e}")
        
        print(f"✅ Populated {len(positions)} government positions")
    
    async def create_position_standardization_script(self):
        """Create a script to standardize existing positions"""
        print("\n🔧 CREATING POSITION STANDARDIZATION SCRIPT")
        print("=" * 60)
        
        standardization_script = """
# Position Standardization Script
# This script standardizes position names in the political_dynasties table

UPDATE political_dynasties 
SET position = 'CHIEF JUSTICE' 
WHERE position ILIKE '%CHIEF JUSTICE%' OR position ILIKE '%SUPREME COURT CHIEF%';

UPDATE political_dynasties 
SET position = 'ASSOCIATE JUSTICE' 
WHERE position ILIKE '%ASSOCIATE JUSTICE%' OR position ILIKE '%SUPREME COURT JUSTICE%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF EDUCATION' 
WHERE position ILIKE '%SECRETARY%EDUCATION%' OR position ILIKE '%DEPED SECRETARY%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF HEALTH' 
WHERE position ILIKE '%SECRETARY%HEALTH%' OR position ILIKE '%DOH SECRETARY%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF FINANCE' 
WHERE position ILIKE '%SECRETARY%FINANCE%' OR position ILIKE '%DOF SECRETARY%';

UPDATE political_dynasties 
SET position = 'SECRETARY OF INTERIOR AND LOCAL GOVERNMENT' 
WHERE position ILIKE '%SECRETARY%INTERIOR%' OR position ILIKE '%DILG SECRETARY%';

UPDATE political_dynasties 
SET position = 'CHAIRMAN, COMMISSION ON ELECTIONS' 
WHERE position ILIKE '%COMELEC%CHAIRMAN%' OR position ILIKE '%ELECTIONS%CHAIRMAN%';

UPDATE political_dynasties 
SET position = 'COMMISSIONER, COMMISSION ON ELECTIONS' 
WHERE position ILIKE '%COMELEC%COMMISSIONER%' OR position ILIKE '%ELECTIONS%COMMISSIONER%';

-- Standardize existing positions
UPDATE political_dynasties 
SET position = 'SENATOR' 
WHERE position ILIKE '%SENATOR%';

UPDATE political_dynasties 
SET position = 'MEMBER, HOUSE OF REPRESENTATIVES' 
WHERE position ILIKE '%REPRESENTATIVE%' OR position ILIKE '%CONGRESS%';

UPDATE political_dynasties 
SET position = 'GOVERNOR' 
WHERE position ILIKE '%GOVERNOR%' AND position NOT ILIKE '%VICE%';

UPDATE political_dynasties 
SET position = 'VICE GOVERNOR' 
WHERE position ILIKE '%VICE GOVERNOR%';

UPDATE political_dynasties 
SET position = 'MAYOR' 
WHERE position ILIKE '%MAYOR%' AND position NOT ILIKE '%VICE%';

UPDATE political_dynasties 
SET position = 'VICE MAYOR' 
WHERE position ILIKE '%VICE MAYOR%';

UPDATE political_dynasties 
SET position = 'COUNCILOR' 
WHERE position ILIKE '%COUNCILOR%';
"""
        
        with open('standardize_positions.sql', 'w') as f:
            f.write(standardization_script)
        
        print("✅ Created standardize_positions.sql")
    
    async def show_expansion_summary(self):
        """Show summary of database expansion"""
        print("\n📊 DATABASE EXPANSION SUMMARY")
        print("=" * 60)
        
        # Count positions by category
        categories = await self.db_conn.fetch("""
            SELECT 
                position_category,
                COUNT(*) as count
            FROM government_positions 
            GROUP BY position_category
            ORDER BY count DESC
        """)
        
        print("Government position categories:")
        for cat in categories:
            print(f"   {cat['count']:>3} - {cat['position_category']}")
        
        # Show sample positions
        sample_positions = await self.db_conn.fetch("""
            SELECT position_name, position_category, government_branch
            FROM government_positions 
            ORDER BY position_category, position_name
            LIMIT 20
        """)
        
        print(f"\nSample positions:")
        for pos in sample_positions:
            print(f"   {pos['position_name']} ({pos['position_category']} - {pos['government_branch']})")

async def main():
    """Main function to expand the dynasty database"""
    expander = DynastyDatabaseExpander()
    
    try:
        await expander.connect()
        await expander.analyze_current_structure()
        await expander.create_government_positions_table()
        await expander.populate_government_positions()
        await expander.create_position_standardization_script()
        await expander.show_expansion_summary()
        
    finally:
        await expander.close()

if __name__ == "__main__":
    asyncio.run(main())
