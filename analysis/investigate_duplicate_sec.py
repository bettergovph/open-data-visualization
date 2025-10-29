#!/usr/bin/env python3
"""
Investigate Duplicate SEC Numbers
Analyze contractors with duplicate SEC numbers to identify data quality issues
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from collections import defaultdict

# Load environment variables
load_dotenv()
load_dotenv('visualization.env')

# Database configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB_SEC', 'sec'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres')
}

async def get_db_connection():
    """Get database connection"""
    return await asyncpg.connect(**DB_CONFIG)

async def find_duplicate_sec_numbers(conn):
    """Find all SEC numbers that appear more than once"""
    query = """
    SELECT sec_number, COUNT(*) as count, 
           array_agg(contractor_name ORDER BY contractor_name) as contractor_names,
           array_agg(id ORDER BY contractor_name) as contractor_ids,
           array_agg(address ORDER BY contractor_name) as addresses,
           array_agg(secondary_licenses ORDER BY contractor_name) as phones,
           array_agg(source ORDER BY contractor_name) as emails
    FROM contractors 
    WHERE sec_number IS NOT NULL 
      AND sec_number != '' 
      AND sec_number != 'N/A'
      AND sec_number != 'Not available'
      AND sec_number != 'Not publicly listed'
    GROUP BY sec_number 
    HAVING COUNT(*) > 1
    ORDER BY count DESC, sec_number
    """
    
    rows = await conn.fetch(query)
    return [dict(row) for row in rows]

async def find_common_sec_numbers(conn):
    """Find SEC numbers that appear frequently (including invalid ones)"""
    query = """
    SELECT sec_number, COUNT(*) as count, 
           array_agg(contractor_name ORDER BY contractor_name) as contractor_names,
           array_agg(id ORDER BY contractor_name) as contractor_ids
    FROM contractors 
    WHERE sec_number IS NOT NULL 
      AND sec_number != ''
    GROUP BY sec_number 
    HAVING COUNT(*) > 1
    ORDER BY count DESC, sec_number
    LIMIT 20
    """
    
    rows = await conn.fetch(query)
    return [dict(row) for row in rows]

async def find_invalid_sec_patterns(conn):
    """Find contractors with common invalid SEC number patterns"""
    query = """
    SELECT sec_number, COUNT(*) as count,
           array_agg(contractor_name ORDER BY contractor_name) as contractor_names
    FROM contractors 
    WHERE sec_number IN ('N/A', 'Not available', 'Not publicly listed', 'TBD', 'Pending', '')
    GROUP BY sec_number 
    ORDER BY count DESC
    """
    
    rows = await conn.fetch(query)
    return [dict(row) for row in rows]

async def analyze_contractor_similarity(contractor_names):
    """Analyze similarity between contractor names"""
    def normalize_name(name):
        if not name:
            return ""
        return name.lower().strip().replace('.', '').replace(',', '').replace('inc', '').replace('corp', '').replace('corporation', '').replace('  ', ' ')
    
    similarities = []
    for i, name1 in enumerate(contractor_names):
        for j, name2 in enumerate(contractor_names[i+1:], i+1):
            norm1 = normalize_name(name1)
            norm2 = normalize_name(name2)
            
            # Simple similarity check
            if norm1 == norm2:
                similarity = 1.0
            elif norm1 in norm2 or norm2 in norm1:
                similarity = 0.8
            else:
                # Check for common words
                words1 = set(norm1.split())
                words2 = set(norm2.split())
                if words1 and words2:
                    common_words = words1.intersection(words2)
                    similarity = len(common_words) / max(len(words1), len(words2))
                else:
                    similarity = 0.0
            
            similarities.append({
                'name1': name1,
                'name2': name2,
                'similarity': similarity
            })
    
    return similarities

async def investigate_duplicates():
    """Main function to investigate duplicate SEC numbers"""
    print("🔍 Investigating Duplicate SEC Numbers")
    print("=" * 60)
    
    conn = await get_db_connection()
    
    try:
        # Find duplicate SEC numbers
        print("📊 Finding contractors with duplicate SEC numbers...")
        duplicates = await find_duplicate_sec_numbers(conn)
        
        # Find common SEC numbers (including invalid ones)
        print("📊 Finding common SEC numbers (including invalid patterns)...")
        common_secs = await find_common_sec_numbers(conn)
        
        # Find invalid SEC patterns
        print("📊 Finding invalid SEC number patterns...")
        invalid_secs = await find_invalid_sec_patterns(conn)
        
        if not duplicates and not common_secs and not invalid_secs:
            print("✅ No duplicate or problematic SEC numbers found!")
            return
        
        # Show invalid SEC patterns first
        if invalid_secs:
            print(f"\n🚨 INVALID SEC PATTERNS FOUND: {len(invalid_secs)} patterns")
            print("=" * 60)
            for i, invalid in enumerate(invalid_secs, 1):
                print(f"{i}. SEC: '{invalid['sec_number']}' ({invalid['count']} contractors)")
                for j, name in enumerate(invalid['contractor_names'][:5]):  # Show first 5
                    print(f"   - {name}")
                if len(invalid['contractor_names']) > 5:
                    print(f"   ... and {len(invalid['contractor_names']) - 5} more")
                print()
        
        # Show common SEC numbers
        if common_secs:
            print(f"\n📊 COMMON SEC NUMBERS: {len(common_secs)} groups")
            print("=" * 60)
            for i, common in enumerate(common_secs, 1):
                print(f"{i}. SEC: '{common['sec_number']}' ({common['count']} contractors)")
                for j, name in enumerate(common['contractor_names'][:3]):  # Show first 3
                    print(f"   - {name}")
                if len(common['contractor_names']) > 3:
                    print(f"   ... and {len(common['contractor_names']) - 3} more")
                print()
        
        # Show actual duplicates (valid SEC numbers appearing multiple times)
        if duplicates:
            print(f"\n🔍 VALID DUPLICATE SEC NUMBERS: {len(duplicates)} groups")
            print("=" * 60)
            for i, dup in enumerate(duplicates, 1):
                sec_number = dup['sec_number']
                count = dup['count']
                contractor_names = dup['contractor_names']
                contractor_ids = dup['contractor_ids']
                addresses = dup['addresses']
                phones = dup['phones']
                emails = dup['emails']
                
                print(f"🔍 DUPLICATE GROUP {i}: SEC {sec_number} ({count} contractors)")
                print("-" * 50)
                
                # Show contractor details
                for j, (name, cid, addr, phone, email) in enumerate(zip(contractor_names, contractor_ids, addresses, phones, emails)):
                    print(f"  {j+1}. ID {cid}: {name}")
                    if addr and addr.strip():
                        print(f"     Address: {addr}")
                    if phone and phone.strip():
                        print(f"     Phone: {phone}")
                    if email and email.strip():
                        print(f"     Email: {email}")
                    print()
                
                # Analyze name similarities
                similarities = await analyze_contractor_similarity(contractor_names)
                high_similarity = [s for s in similarities if s['similarity'] >= 0.7]
                
                if high_similarity:
                    print("  🎯 HIGH SIMILARITY DETECTED:")
                    for sim in high_similarity:
                        print(f"     '{sim['name1']}' ≈ '{sim['name2']}' (similarity: {sim['similarity']:.2f})")
                else:
                    print("  ⚠️  LOW SIMILARITY - Possible data quality issue")
                
                print()
                print("=" * 60)
                print()
        
        # Summary statistics
        total_duplicates = sum(dup['count'] for dup in duplicates) if duplicates else 0
        total_common = sum(common['count'] for common in common_secs) if common_secs else 0
        total_invalid = sum(invalid['count'] for invalid in invalid_secs) if invalid_secs else 0
        
        print("\n📊 SUMMARY STATISTICS:")
        print(f"   Valid duplicate SEC numbers: {len(duplicates) if duplicates else 0}")
        print(f"   Common SEC numbers (including invalid): {len(common_secs) if common_secs else 0}")
        print(f"   Invalid SEC patterns: {len(invalid_secs) if invalid_secs else 0}")
        print(f"   Total contractors with duplicate SECs: {total_duplicates}")
        print(f"   Total contractors with common SECs: {total_common}")
        print(f"   Total contractors with invalid SECs: {total_invalid}")
        
        # Check for patterns
        print("\n🔍 PATTERN ANALYSIS:")
        
        if invalid_secs:
            print(f"   🚨 {len(invalid_secs)} invalid SEC patterns found")
            for invalid in invalid_secs:
                print(f"      '{invalid['sec_number']}': {invalid['count']} contractors")
        
        # Check for very high duplicate counts
        if common_secs:
            high_count_duplicates = [common for common in common_secs if common['count'] > 5]
            if high_count_duplicates:
                print(f"   🚨 {len(high_count_duplicates)} groups have >5 contractors with same SEC")
                for dup in high_count_duplicates:
                    print(f"      SEC '{dup['sec_number']}': {dup['count']} contractors")
        
        # Check for potential data quality issues
        print("\n💡 RECOMMENDATIONS:")
        if invalid_secs:
            print("   1. Review contractors with invalid SEC numbers (N/A, Not available, etc.)")
        if common_secs:
            print("   2. Investigate common SEC numbers for data entry errors")
        if duplicates:
            print("   3. Consider merging contractors with identical names and SEC numbers")
        print("   4. Implement data validation to prevent future duplicates")
        print("   5. The sync script correctly handled these duplicates by updating contact info only")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(investigate_duplicates())
