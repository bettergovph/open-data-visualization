#!/usr/bin/env python3
"""
Export political_dynasties and relationships tables to parquet files
"""

import asyncio
import asyncpg
import pandas as pd
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

async def export_to_parquet():
    """Export dynasty data to parquet files"""
    
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        print("📊 Exporting dynasty data to parquet...")
        
        # Create output directory
        output_dir = Path("data/parquet")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export political_dynasties
        print("📋 Exporting political_dynasties...")
        dynasties = await conn.fetch("""
            SELECT id, first_name, last_name, middle_name, party, region, province, 
                   municipality_city, position, year, fat, nickname
            FROM political_dynasties
            ORDER BY id
        """)
        
        dynasties_df = pd.DataFrame([dict(row) for row in dynasties])
        parquet_path = output_dir / "political_dynasties.parquet"
        dynasties_df.to_parquet(parquet_path, index=False, engine='pyarrow')
        print(f"✅ Exported {len(dynasties_df)} records to {parquet_path}")
        
        # Export relationships
        print("🔗 Exporting relationships...")
        relationships = await conn.fetch("""
            SELECT id, person_id, related_person_id, relationship_type, relationship_description,
                   source_url, normalized_description, confidence_level, created_at, created_by
            FROM relationships
            ORDER BY id
        """)
        
        relationships_df = pd.DataFrame([dict(row) for row in relationships])
        parquet_path = output_dir / "relationships.parquet"
        relationships_df.to_parquet(parquet_path, index=False, engine='pyarrow')
        print(f"✅ Exported {len(relationships_df)} records to {parquet_path}")
        
        # Export connection_types
        print("📋 Exporting connection_types...")
        connection_types = await conn.fetch("""
            SELECT id, code, description
            FROM connection_types
            ORDER BY id
        """)
        
        types_df = pd.DataFrame([dict(row) for row in connection_types])
        parquet_path = output_dir / "connection_types.parquet"
        types_df.to_parquet(parquet_path, index=False, engine='pyarrow')
        print(f"✅ Exported {len(types_df)} records to {parquet_path}")
        
        # Export politician_contractors
        print("👷 Exporting politician_contractors...")
        politician_contractors = await conn.fetch("""
            SELECT id, politician_id, contractor_name, match_confidence, notes, source, created_at, updated_at
            FROM politician_contractors
            ORDER BY id
        """)
        
        contractors_df = pd.DataFrame([dict(row) for row in politician_contractors])
        parquet_path = output_dir / "politician_contractors.parquet"
        contractors_df.to_parquet(parquet_path, index=False, engine='pyarrow')
        print(f"✅ Exported {len(contractors_df)} records to {parquet_path}")
        
        # Export party_list_members
        print("📋 Exporting party_list_members...")
        party_list_members = await conn.fetch("""
            SELECT id, person_id, party_code, party_list_number, party_name, created_at
            FROM party_list_members
            ORDER BY id
        """)
        
        if party_list_members:
            plm_df = pd.DataFrame([dict(row) for row in party_list_members])
            parquet_path = output_dir / "party_list_members.parquet"
            plm_df.to_parquet(parquet_path, index=False, engine='pyarrow')
            print(f"✅ Exported {len(plm_df)} records to {parquet_path}")
        else:
            print("⚠️  No party_list_members found")
        
        print(f"\n✅ All data exported to {output_dir}/")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(export_to_parquet())

