#!/usr/bin/env python3
"""Export dynasty data (congressmen, districts, contractors) from PostgreSQL to DuckDB for faster access."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import asyncpg
import duckdb
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
PARQUET_DIR = DATA_DIR / "parquet"
DUCKDB_PATH = PARQUET_DIR / "dynasty_data.duckdb"


async def _connect_postgres() -> asyncpg.Connection:
    """Connect to PostgreSQL database"""
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        user=os.getenv("POSTGRES_USER", "budget_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    )
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    return conn


def _normalize_entries(rows: List[asyncpg.Record]) -> List[Dict[str, Any]]:
    """Normalize congressmen entries"""
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        entry: Dict[str, Any] = {
            "id": row["id"],
            "first_name_pattern": row["first_name_pattern"],
            "last_name_pattern": row["last_name_pattern"],
            "display_name": row["display_name"],
            "province": row["province"],
            "district_number": row["district_number"],
            "is_city_district": row["is_city_district"],
            "terms": json.dumps(row["terms"] or []) if row["terms"] else "[]",
        }

        barangays_list = row["barangays"] or []
        if barangays_list or not row["is_city_district"] or row["barangays_file"] is None:
            entry["barangays"] = json.dumps(barangays_list) if barangays_list else "[]"

        if row["full_name"] is not None:
            entry["full_name"] = row["full_name"]
        if row["is_partylist"]:
            entry["is_partylist"] = True
        if row["family_connections"] is not None:
            entry["family_connections"] = json.dumps(row["family_connections"])
        if row["previous_positions"] is not None:
            entry["previous_positions"] = json.dumps(row["previous_positions"])
        if row["barangays_file"] is not None:
            entry["barangays_file"] = row["barangays_file"]

        normalized.append(entry)
    return normalized


async def export_to_duckdb():
    """Export all dynasty data from PostgreSQL to DuckDB"""
    print("🚀 Exporting dynasty data to DuckDB...")
    
    # Ensure directories exist
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    
    # Connect to PostgreSQL
    pg_conn = await _connect_postgres()
    
    try:
        # Connect to DuckDB
        duckdb_conn = duckdb.connect(str(DUCKDB_PATH))
        
        # Track statistics
        stats = {
            'congressmen_count': 0,
            'districts_count': 0,
            'municipalities_count': 0,
            'barangays_count': 0,
            'contractors_count': 0,
            'party_members_count': 0,
            'dynasty_records_count': 0
        }
        
        try:
            # 1. Export congressmen config - normalized for fast lookups
            print("📊 Exporting congressmen config...")
            config_rows = await pg_conn.fetch(
                """
                SELECT id, first_name_pattern, last_name_pattern, display_name, full_name,
                       province, district_number, is_city_district, is_partylist,
                       barangays, terms, family_connections, previous_positions, barangays_file
                FROM dynasty_projects_congressmen_config
                ORDER BY id
                """
            )
            config_metadata_row = await pg_conn.fetchrow(
                "SELECT metadata, verified_contractors FROM dynasty_projects_config_metadata WHERE id = 1"
            )
            
            # Create normalized congressmen table
            duckdb_conn.execute("DROP TABLE IF EXISTS congressmen")
            duckdb_conn.execute("""
                CREATE TABLE congressmen (
                    id INTEGER,
                    first_name_pattern VARCHAR,
                    last_name_pattern VARCHAR,
                    display_name VARCHAR,
                    full_name VARCHAR,
                    province VARCHAR,
                    district_number VARCHAR,
                    district_key VARCHAR,
                    is_city_district BOOLEAN,
                    is_partylist BOOLEAN,
                    terms VARCHAR,
                    family_connections VARCHAR,
                    previous_positions VARCHAR,
                    barangays_file VARCHAR
                )
            """)
            
            # Also create congressmen_barangays table for city districts
            duckdb_conn.execute("DROP TABLE IF EXISTS congressmen_barangays")
            duckdb_conn.execute("""
                CREATE TABLE congressmen_barangays (
                    congressman_id INTEGER,
                    district_key VARCHAR,
                    barangay VARCHAR
                )
            """)
            
            # Keep original config table for backward compatibility
            duckdb_conn.execute("DROP TABLE IF EXISTS congressmen_config")
            duckdb_conn.execute("""
                CREATE TABLE congressmen_config (
                    id INTEGER,
                    first_name_pattern VARCHAR,
                    last_name_pattern VARCHAR,
                    display_name VARCHAR,
                    province VARCHAR,
                    district_number VARCHAR,
                    is_city_district BOOLEAN,
                    terms VARCHAR,
                    barangays VARCHAR,
                    full_name VARCHAR,
                    is_partylist BOOLEAN,
                    family_connections VARCHAR,
                    previous_positions VARCHAR,
                    barangays_file VARCHAR
                )
            """)
            
            total_barangays = 0
            
            for row in config_rows:
                # Build district key
                province = row["province"] or ""
                district_number = row["district_number"] or ""
                district_key = f"{province} {district_number} District" if province and district_number else None
                
                # Normalize entry
                entry = _normalize_entries([row])[0]
                
                # Insert into congressmen table
                duckdb_conn.execute("""
                    INSERT INTO congressmen VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    entry.get("id"),
                    entry.get("first_name_pattern"),
                    entry.get("last_name_pattern"),
                    entry.get("display_name"),
                    entry.get("full_name"),
                    entry.get("province"),
                    entry.get("district_number"),
                    district_key,
                    entry.get("is_city_district", False),
                    entry.get("is_partylist", False),
                    entry.get("terms", "[]"),
                    entry.get("family_connections"),
                    entry.get("previous_positions"),
                    entry.get("barangays_file")
                ])
                
                # Insert into config table (backward compatibility)
                duckdb_conn.execute("""
                    INSERT INTO congressmen_config VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    entry.get("id"),
                    entry.get("first_name_pattern"),
                    entry.get("last_name_pattern"),
                    entry.get("display_name"),
                    entry.get("province"),
                    entry.get("district_number"),
                    entry.get("is_city_district", False),
                    entry.get("terms", "[]"),
                    entry.get("barangays", "[]"),
                    entry.get("full_name"),
                    entry.get("is_partylist", False),
                    entry.get("family_connections"),
                    entry.get("previous_positions"),
                    entry.get("barangays_file")
                ])
                
                # Extract barangays for city districts
                if row["is_city_district"] and row["barangays"]:
                    barangays_list = row["barangays"]
                    if isinstance(barangays_list, list):
                        for barangay in barangays_list:
                            if barangay and district_key:
                                brgy_clean = str(barangay).upper().strip()
                                duckdb_conn.execute("""
                                    INSERT INTO congressmen_barangays VALUES (?, ?, ?)
                                """, [row["id"], district_key, brgy_clean])
                                # Also add without "BRGY" prefix
                                brgy_no_prefix = brgy_clean.replace("BRGY.", "").replace("BRGY", "").replace("BARANGAY", "").strip()
                                if brgy_no_prefix and brgy_no_prefix != brgy_clean:
                                    duckdb_conn.execute("""
                                        INSERT INTO congressmen_barangays VALUES (?, ?, ?)
                                    """, [row["id"], district_key, brgy_no_prefix])
                                total_barangays += 1
            
            # Store metadata
            duckdb_conn.execute("DROP TABLE IF EXISTS config_metadata")
            duckdb_conn.execute("""
                CREATE TABLE config_metadata (
                    id INTEGER,
                    metadata VARCHAR,
                    verified_contractors VARCHAR
                )
            """)
            if config_metadata_row:
                duckdb_conn.execute("""
                    INSERT INTO config_metadata VALUES (?, ?, ?)
                """, [
                    1,
                    json.dumps(config_metadata_row["metadata"]) if config_metadata_row["metadata"] else "{}",
                    json.dumps(config_metadata_row["verified_contractors"]) if config_metadata_row.get("verified_contractors") else "{}"
                ])
            
            stats['congressmen_count'] = len(config_rows)
            stats['barangays_count'] += total_barangays
            print(f"✅ Exported {len(config_rows)} congressmen")
            print(f"   - {total_barangays} barangays from congressmen config")
            
            # 2. Export districts data - normalized for fast lookups
            print("📊 Exporting districts data...")
            district_rows = await pg_conn.fetch(
                "SELECT name, entity_type, data FROM district_entries ORDER BY name"
            )
            district_metadata_row = await pg_conn.fetchrow(
                "SELECT metadata, key_findings, validation, notes FROM district_dataset_metadata WHERE id = 1"
            )
            
            # Create normalized district tables
            duckdb_conn.execute("DROP TABLE IF EXISTS districts")
            duckdb_conn.execute("""
                CREATE TABLE districts (
                    province_name VARCHAR,
                    district_number VARCHAR,
                    district_key VARCHAR,
                    is_city BOOLEAN
                )
            """)
            
            duckdb_conn.execute("DROP TABLE IF EXISTS district_municipalities")
            duckdb_conn.execute("""
                CREATE TABLE district_municipalities (
                    district_key VARCHAR,
                    municipality VARCHAR,
                    province_name VARCHAR
                )
            """)
            
            duckdb_conn.execute("DROP TABLE IF EXISTS district_barangays")
            duckdb_conn.execute("""
                CREATE TABLE district_barangays (
                    district_key VARCHAR,
                    barangay VARCHAR,
                    province_name VARCHAR
                )
            """)
            
            # Also keep raw district_entries for backward compatibility
            duckdb_conn.execute("DROP TABLE IF EXISTS district_entries")
            duckdb_conn.execute("""
                CREATE TABLE district_entries (
                    name VARCHAR,
                    entity_type VARCHAR,
                    data VARCHAR
                )
            """)
            
            total_municipalities = 0
            total_barangays = 0
            districts_added = set()
            
            for row in district_rows:
                data = row["data"]
                if isinstance(data, str):
                    data_dict = json.loads(data)
                else:
                    data_dict = data
                
                # Store raw entry
                data_str = json.dumps(data_dict) if not isinstance(data, str) else data
                duckdb_conn.execute("""
                    INSERT INTO district_entries VALUES (?, ?, ?)
                """, [row["name"], row["entity_type"], data_str])
                
                # Extract municipalities
                municipalities_map = data_dict.get("municipalities", {})
                if isinstance(municipalities_map, dict):
                    for mun_name, mun_district in municipalities_map.items():
                        # Create district key: "Province District Number"
                        district_key = f"{row['name']} {mun_district}"
                        if district_key not in districts_added:
                            # Determine if city district (check if name contains "City" or entity_type)
                            is_city = "CITY" in row["name"].upper() or row["entity_type"] == "city"
                            duckdb_conn.execute("""
                                INSERT INTO districts VALUES (?, ?, ?, ?)
                            """, [row["name"], mun_district, district_key, is_city])
                            districts_added.add(district_key)
                        
                        duckdb_conn.execute("""
                            INSERT INTO district_municipalities VALUES (?, ?, ?)
                        """, [district_key, mun_name.upper(), row["name"]])
                        total_municipalities += 1
                
                # Extract barangays (for city districts)
                barangays_map = data_dict.get("barangays", {})
                if isinstance(barangays_map, dict):
                    for district_num, barangay_list in barangays_map.items():
                        if isinstance(barangay_list, list):
                            district_key = f"{row['name']} {district_num}"
                            if district_key not in districts_added:
                                duckdb_conn.execute("""
                                    INSERT INTO districts VALUES (?, ?, ?, ?)
                                """, [row["name"], district_num, district_key, True])
                                districts_added.add(district_key)
                            
                            for barangay in barangay_list:
                                if barangay:
                                    # Clean barangay name
                                    brgy_clean = str(barangay).upper().strip()
                                    # Also add without "BRGY" prefix
                                    brgy_no_prefix = brgy_clean.replace("BRGY.", "").replace("BRGY", "").replace("BARANGAY", "").strip()
                                    
                                    duckdb_conn.execute("""
                                        INSERT INTO district_barangays VALUES (?, ?, ?)
                                    """, [district_key, brgy_clean, row["name"]])
                                    if brgy_no_prefix and brgy_no_prefix != brgy_clean:
                                        duckdb_conn.execute("""
                                            INSERT INTO district_barangays VALUES (?, ?, ?)
                                        """, [district_key, brgy_no_prefix, row["name"]])
                                    total_barangays += 1
            
            # Store district metadata
            duckdb_conn.execute("DROP TABLE IF EXISTS district_metadata")
            duckdb_conn.execute("""
                CREATE TABLE district_metadata (
                    id INTEGER,
                    metadata VARCHAR,
                    key_findings VARCHAR,
                    validation VARCHAR,
                    notes VARCHAR
                )
            """)
            if district_metadata_row:
                duckdb_conn.execute("""
                    INSERT INTO district_metadata VALUES (?, ?, ?, ?, ?)
                """, [
                    1,
                    json.dumps(district_metadata_row["metadata"]) if district_metadata_row["metadata"] else "{}",
                    json.dumps(district_metadata_row["key_findings"]) if district_metadata_row.get("key_findings") else "{}",
                    json.dumps(district_metadata_row["validation"]) if district_metadata_row.get("validation") else "{}",
                    json.dumps(district_metadata_row["notes"]) if district_metadata_row.get("notes") else "{}"
                ])
            
            stats['districts_count'] = len(districts_added)
            stats['municipalities_count'] = total_municipalities
            stats['barangays_count'] += total_barangays
            print(f"✅ Exported {len(district_rows)} districts")
            print(f"   - {len(districts_added)} unique districts")
            print(f"   - {total_municipalities} municipalities")
            print(f"   - {total_barangays} barangays")
            
            # 3. Export contractor matches
            print("📊 Exporting contractor matches...")
            contractor_rows = await pg_conn.fetch(
                """
                SELECT dynasty_first_name, dynasty_last_name, company_name, role
                FROM contractor_dynasty_matches
                """
            )
            
            duckdb_conn.execute("DROP TABLE IF EXISTS contractor_dynasty_matches")
            duckdb_conn.execute("""
                CREATE TABLE contractor_dynasty_matches (
                    dynasty_first_name VARCHAR,
                    dynasty_last_name VARCHAR,
                    company_name VARCHAR,
                    role VARCHAR
                )
            """)
            
            for row in contractor_rows:
                duckdb_conn.execute("""
                    INSERT INTO contractor_dynasty_matches VALUES (?, ?, ?, ?)
                """, [
                    row["dynasty_first_name"],
                    row["dynasty_last_name"],
                    row["company_name"],
                    row["role"]
                ])
            
            stats['contractors_count'] = len(contractor_rows)
            print(f"✅ Exported {len(contractor_rows)} contractor matches")
            
            # 4. Export party list members (if political_dynasties table exists)
            try:
                party_rows = await pg_conn.fetch(
                    """
                    SELECT plm.person_id, plm.party_list_number, pd.first_name, pd.last_name
                    FROM party_list_members plm
                    JOIN political_dynasties pd ON plm.person_id = pd.id
                    """
                )
                
                duckdb_conn.execute("DROP TABLE IF EXISTS party_list_members")
                duckdb_conn.execute("""
                    CREATE TABLE party_list_members (
                        person_id INTEGER,
                        party_list_number INTEGER,
                        first_name VARCHAR,
                        last_name VARCHAR
                    )
                """)
                
                for row in party_rows:
                    duckdb_conn.execute("""
                        INSERT INTO party_list_members VALUES (?, ?, ?, ?)
                    """, [
                        row["person_id"],
                        row["party_list_number"],
                        row["first_name"],
                        row["last_name"]
                    ])
                
                stats['party_members_count'] = len(party_rows)
                print(f"✅ Exported {len(party_rows)} party list members")
            except Exception as e:
                print(f"⚠️  Could not export party list members: {e}")
            
            # 5. Export political_dynasties (for congressmen lookup)
            try:
                dynasty_rows = await pg_conn.fetch(
                    """
                    SELECT id, first_name, last_name, middle_name, province, municipality_city, region, party, position
                    FROM political_dynasties
                    WHERE (
                        UPPER(position) LIKE '%CONGRESSMAN%' 
                        OR UPPER(position) LIKE '%CONGRESSMEN%' 
                        OR UPPER(position) LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%'
                        OR UPPER(position) LIKE '%REPRESENTATIVE%PARTY-LIST%'
                        OR UPPER(position) LIKE '%REPRESENTATIVE, %PARTY-LIST%'
                        OR UPPER(position) LIKE '%PARTY-LIST%REPRESENTATIVE%'
                        OR UPPER(position) LIKE '%DEPUTY SPEAKER%'
                        OR UPPER(position) LIKE '%SPEAKER%'
                    )
                    """
                )
                
                duckdb_conn.execute("DROP TABLE IF EXISTS political_dynasties_congressmen")
                duckdb_conn.execute("""
                    CREATE TABLE political_dynasties_congressmen (
                        id INTEGER,
                        first_name VARCHAR,
                        last_name VARCHAR,
                        middle_name VARCHAR,
                        province VARCHAR,
                        municipality_city VARCHAR,
                        region VARCHAR,
                        party VARCHAR,
                        position VARCHAR
                    )
                """)
                
                for row in dynasty_rows:
                    duckdb_conn.execute("""
                        INSERT INTO political_dynasties_congressmen VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, [
                        row["id"],
                        row["first_name"],
                        row["last_name"],
                        row["middle_name"],
                        row["province"],
                        row["municipality_city"],
                        row["region"],
                        row["party"],
                        row["position"]
                    ])
                
                stats['dynasty_records_count'] = len(dynasty_rows)
                print(f"✅ Exported {len(dynasty_rows)} political dynasty congressmen records")
            except Exception as e:
                print(f"⚠️  Could not export political_dynasties: {e}")
            
            # Create indexes for faster lookups
            print("📊 Creating indexes for faster lookups...")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_districts_key ON districts(district_key)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_districts_province ON districts(province_name)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_district_municipalities_key ON district_municipalities(district_key)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_district_municipalities_name ON district_municipalities(municipality)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_district_barangays_key ON district_barangays(district_key)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_district_barangays_name ON district_barangays(barangay)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_congressmen_key ON congressmen(district_key)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_congressmen_province ON congressmen(province)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_congressmen_barangays_key ON congressmen_barangays(district_key)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_congressmen_barangays_name ON congressmen_barangays(barangay)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_contractor_name ON contractor_dynasty_matches(company_name)")
            duckdb_conn.execute("CREATE INDEX IF NOT EXISTS idx_contractor_names ON contractor_dynasty_matches(dynasty_first_name, dynasty_last_name)")
            
            duckdb_conn.commit()
            
            # Print summary
            print("\n📊 Export Summary:")
            print(f"   ✅ Congressmen: {stats['congressmen_count']}")
            print(f"   ✅ Districts: {stats['districts_count']} unique districts")
            print(f"   ✅ Municipalities: {stats['municipalities_count']}")
            print(f"   ✅ Barangays: {stats['barangays_count']}")
            print(f"   ✅ Contractor matches: {stats['contractors_count']}")
            if stats['party_members_count'] > 0:
                print(f"   ✅ Party list members: {stats['party_members_count']}")
            if stats['dynasty_records_count'] > 0:
                print(f"   ✅ Political dynasty records: {stats['dynasty_records_count']}")
            print(f"   ✅ DuckDB file: {DUCKDB_PATH}")
            print(f"   ✅ All data exported successfully!")
            
        finally:
            duckdb_conn.close()
    
    finally:
        await pg_conn.close()


if __name__ == "__main__":
    asyncio.run(export_to_duckdb())

