#!/usr/bin/env python3
"""
Analyze database for document text that looks like names or positions.

This identifies rows where:
- first_name or last_name contain document text
- position contains document text (may have been missed)
- Other fields contain suspicious content
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import re


async def analyze_document_text(conn):
    """Analyze database for document text masquerading as names/positions"""
    
    # Patterns that indicate document text rather than actual names/positions
    document_text_patterns = [
        # Technical/specification phrases
        r'SHALL BE',
        r'WILL BE',
        r'AS DIRECTED BY',
        r'APPROVED BY',
        r'AS STAKED BY',
        r'AS SHOWN',
        r'SUBMIT IN',
        r'INDICATED ON',
        r'CONTRACTOR',
        r'THE ENGINEER',
        r'THIS ITEM',
        r'THIS SPECIFICATION',
        r'CONSIST OF',
        r'FURNISHING',
        r'INSTALLATION',
        r'CONSTRUCTION',
        r'PROVIDE',
        r'REQUIRED',
        r'SPECIFIED',
        r'DIRECTED',
        r'PERFORMED',
        r'EXECUTED',
        
        # Project/contract phrases
        r'CONTRACT',
        r'PROJECT',
        r'APPROVED BUDGET',
        r'BID',
        r'PROPOSAL',
        r'PLAN',
        r'DESIGN',
        r'SECTION',
        r'ITEM',
        r'WORK',
        
        # Location/address-like text
        r'ROAD',
        r'STREET',
        r'AVENUE',
        r'BARANGAY',
        r'CITY',
        r'MUNICIPALITY',
        r'PROVINCE',
        r'REGION',
        r'DISTRICT',
        
        # Technical terms that shouldn't be names
        r'CONCRETE',
        r'STEEL',
        r'ASPHALT',
        r'MATERIAL',
        r'EQUIPMENT',
        r'TOOL',
        r'MACHINE',
        r'STRUCTURE',
        r'BUILDING',
        
        # Engineering terms
        r'EXCAVATION',
        r'EMBANKMENT',
        r'FOUNDATION',
        r'REINFORCEMENT',
        r'DRAINAGE',
        r'CULVERT',
        r'BRIDGE',
        
        # Date/time phrases
        r'DATE',
        r'YEAR',
        r'MONTH',
        r'DAY',
        r'TIME',
        
        # Measurement/quantity phrases
        r'QUANTITY',
        r'LENGTH',
        r'WIDTH',
        r'HEIGHT',
        r'DEPTH',
        r'AREA',
        r'VOLUME',
        
        # Action verbs (unlikely to be names)
        r'LAYING',
        r'FILLING',
        r'REMOVAL',
        r'DISPOSAL',
        r'LOAD',
        r'UNLOAD',
        r'PLACE',
        r'INSTALL',
        r'CONSTRUCT',
        r'BUILD',
        
        # Common document words
        r'ACCORDANCE',
        r'REFERENCE',
        r'DETAIL',
        r'DRAWING',
        r'SPECIFICATION',
        r'STANDARD',
        r'CODE',
        r'REGULATION',
        r'REQUIREMENT',
    ]
    
    print("🔍 ANALYZING DATABASE FOR DOCUMENT TEXT")
    print("=" * 80)
    
    # Build pattern conditions for SQL
    pattern_conditions = []
    for pattern in document_text_patterns:
        escaped = pattern.replace('%', '%%').replace('_', '__')
        pattern_conditions.append(f"'{escaped}'")
    
    # 1. Check first_name for document text
    print("\n1️⃣  CHECKING FIRST_NAME FIELD")
    print("-" * 80)
    
    first_name_issues = await conn.fetch("""
        SELECT 
            id,
            first_name,
            last_name,
            position,
            province,
            year,
            CASE 
                WHEN LENGTH(first_name) > 50 THEN 'Too Long'
                WHEN first_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*' THEN 'Contains Document Text'
                ELSE 'Unknown'
            END as issue_type
        FROM political_dynasties
        WHERE first_name IS NOT NULL 
          AND first_name <> ''
          AND (
            LENGTH(first_name) > 50
            OR first_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
        ORDER BY LENGTH(first_name) DESC, first_name
        LIMIT 100
    """)
    
    first_name_count = await conn.fetchval("""
        SELECT COUNT(*)
        FROM political_dynasties
        WHERE first_name IS NOT NULL 
          AND first_name <> ''
          AND (
            LENGTH(first_name) > 50
            OR first_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
    """)
    
    print(f"   Total rows with suspicious first_name: {first_name_count:,}")
    if first_name_issues:
        print(f"\n   Sample rows (showing first 20):")
        for row in first_name_issues[:20]:
            print(f"   ID: {row['id']:8} | First: {str(row['first_name'])[:40]:40} | Last: {str(row['last_name'])[:30]:30} | Issue: {row['issue_type']}")
    
    # 2. Check last_name for document text
    print("\n2️⃣  CHECKING LAST_NAME FIELD")
    print("-" * 80)
    
    last_name_issues = await conn.fetch("""
        SELECT 
            id,
            first_name,
            last_name,
            position,
            province,
            year,
            CASE 
                WHEN LENGTH(last_name) > 50 THEN 'Too Long'
                WHEN last_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*' THEN 'Contains Document Text'
                ELSE 'Unknown'
            END as issue_type
        FROM political_dynasties
        WHERE last_name IS NOT NULL 
          AND last_name <> ''
          AND (
            LENGTH(last_name) > 50
            OR last_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
        ORDER BY LENGTH(last_name) DESC, last_name
        LIMIT 100
    """)
    
    last_name_count = await conn.fetchval("""
        SELECT COUNT(*)
        FROM political_dynasties
        WHERE last_name IS NOT NULL 
          AND last_name <> ''
          AND (
            LENGTH(last_name) > 50
            OR last_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
    """)
    
    print(f"   Total rows with suspicious last_name: {last_name_count:,}")
    if last_name_issues:
        print(f"\n   Sample rows (showing first 20):")
        for row in last_name_issues[:20]:
            print(f"   ID: {row['id']:8} | First: {str(row['first_name'])[:30]:30} | Last: {str(row['last_name'])[:40]:40} | Issue: {row['issue_type']}")
    
    # 3. Check position for remaining document text
    print("\n3️⃣  CHECKING POSITION FIELD (remaining issues)")
    print("-" * 80)
    
    position_issues = await conn.fetch("""
        SELECT 
            id,
            first_name,
            last_name,
            position,
            province,
            year,
            CASE 
                WHEN LENGTH(position) > 100 THEN 'Too Long'
                WHEN position ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*' THEN 'Contains Document Text'
                ELSE 'Unknown'
            END as issue_type
        FROM political_dynasties
        WHERE position IS NOT NULL 
          AND position <> ''
          AND (
            LENGTH(position) > 100
            OR position ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
        ORDER BY LENGTH(position) DESC, position
        LIMIT 100
    """)
    
    position_count = await conn.fetchval("""
        SELECT COUNT(*)
        FROM political_dynasties
        WHERE position IS NOT NULL 
          AND position <> ''
          AND (
            LENGTH(position) > 100
            OR position ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
    """)
    
    print(f"   Total rows with suspicious position: {position_count:,}")
    if position_issues:
        print(f"\n   Sample rows (showing first 20):")
        for row in position_issues[:20]:
            print(f"   ID: {row['id']:8} | {str(row['first_name'])[:20]:20} {str(row['last_name'])[:20]:20} | Pos: {str(row['position'])[:50]:50} | Issue: {row['issue_type']}")
    
    # 4. Check for rows where both first and last name are suspicious
    print("\n4️⃣  ROWS WHERE BOTH FIRST AND LAST NAMES ARE SUSPICIOUS")
    print("-" * 80)
    
    both_suspicious = await conn.fetchval("""
        SELECT COUNT(*)
        FROM political_dynasties
        WHERE first_name IS NOT NULL 
          AND first_name <> ''
          AND last_name IS NOT NULL 
          AND last_name <> ''
          AND (
            LENGTH(first_name) > 50
            OR first_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
          AND (
            LENGTH(last_name) > 50
            OR last_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
          )
    """)
    
    print(f"   Total rows where both names are suspicious: {both_suspicious:,}")
    
    # 5. Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"   Rows with suspicious first_name:  {first_name_count:>8,}")
    print(f"   Rows with suspicious last_name:   {last_name_count:>8,}")
    print(f"   Rows with suspicious position:    {position_count:>8,}")
    print(f"   Rows where both names suspicious: {both_suspicious:>8,}")
    
    # Calculate total unique rows that should be deleted (union of all issues)
    total_to_delete = await conn.fetchval("""
        SELECT COUNT(DISTINCT id)
        FROM political_dynasties
        WHERE (
            (first_name IS NOT NULL AND first_name <> '' AND (
                LENGTH(first_name) > 50
                OR first_name ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
            ))
            OR (last_name IS NOT NULL AND last_name <> '' AND (
                LENGTH(last_name) > 50
                OR (
                    last_name ~* '.*(SHALL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|STANDARD|CODE|REQUIREMENT).*'
                    AND NOT last_name ~* '^[A-Z][A-Z ]+[A-Z]\\.? [A-Z]'
                    AND NOT last_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z]'
                    AND NOT last_name ~* '^[A-Z][A-Z]+-[A-Z][A-Z]+'
                )
                AND NOT (
                    last_name ~* '^[A-Z][A-Z ]+ [A-Z]\\. [A-Z]' OR
                    last_name ~* '^[A-Z][a-z]+ [A-Z]\\. [A-Z][a-z]+' OR
                    (LENGTH(last_name) < 80 AND last_name ~* '^[A-Z]+ [A-Z]+ [A-Z]+')
                )
            ))
            OR (position IS NOT NULL AND position <> '' AND (
                LENGTH(position) > 100
                OR position ~* '.*(SHALL|WILL|DIRECTED|APPROVED|CONTRACT|PROJECT|CONSTRUCTION|INSTALLATION|PROVIDE|REQUIRED|SPECIFIED|LAYING|FILLING|REMOVAL|LOAD|PLACE|CONCRETE|STEEL|ASPHALT|MATERIAL|EQUIPMENT|EXCAVATION|EMBANKMENT|FOUNDATION|DRAINAGE|CULVERT|ROAD|STREET|BARANGAY|CITY|PROVINCE|REGION|DISTRICT|DATE|YEAR|QUANTITY|LENGTH|WIDTH|AREA|VOLUME|ACCORDANCE|REFERENCE|DETAIL|DRAWING|SPECIFICATION|STANDARD|CODE|REQUIREMENT).*'
            ))
        )
    """)
    
    print(f"\n   ⚠️  TOTAL UNIQUE ROWS TO DELETE:    {total_to_delete:>8,}")
    print("\n   Run with --execute to delete these rows.")


async def main():
    load_dotenv()
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        await analyze_document_text(conn)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

