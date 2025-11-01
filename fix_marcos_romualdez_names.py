#!/usr/bin/env python3
"""
Fix Marcos and Romualdez family name variations and standardize them.

Corrections:
- ferdinand marcos, bongbong marcos, ferdinand jr marcos → Ferdinand Marcos Jr.
- ferdinand romualdez → Ferdinand Martin Romualdez  
- imeelda marcos → Imelda Marcos
- ime marcos → Imee Marcos
- Create entry for Ferdinand Marcos Sr. (father)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv


# Name correction mappings
NAME_CORRECTIONS = {
    # Marcos family
    'FERDINAND MARCOS JR.': [
        'FERDINAND MARCOS',
        'BONGBONG MARCOS',
        'FERDINAND JR MARCOS',
        'FERDINAND JR. MARCOS',
        'FERDINAND R. MARCOS JR.',
        'FERDINAND ROMUALDEZ MARCOS JR.'
    ],
    'IMELDA MARCOS': [
        'IMEELDA MARCOS',
        'IMELDA R MARCOS',
        'IMELDA R. MARCOS'
    ],
    'IMEE MARCOS': [
        'IME MARCOS',
        'IMEE R MARCOS',
        'IMEE R. MARCOS'
    ],
    # Romualdez family  
    'FERDINAND MARTIN ROMUALDEZ': [
        'FERDINAND ROMUALDEZ',
        'FERDINAND ROMULADEZ',
        'MARTIN ROMUALDEZ'
    ]
}

# Pattern to save for review
NAME_VARIATION_PATTERNS = [
    "Nickname variations (Bongbong → Ferdinand Jr.)",
    "Middle initial variations (Ferdinand R. Marcos → Ferdinand Marcos)",
    "Jr./Sr. suffix inconsistencies",
    "Misspellings (Imeelda → Imelda)",
    "Shortened versions (Ime → Imee)"
]


async def fix_marcos_romualdez_names():
    load_dotenv('.env')
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    print("=" * 80)
    print("MARCOS & ROMUALDEZ NAME CORRECTIONS")
    print("=" * 80)
    
    total_updated = 0
    
    # Process each correction
    for correct_name, variations in NAME_CORRECTIONS.items():
        print(f"\n✏️  Standardizing to: {correct_name}")
        
        # Split correct name into parts
        parts = correct_name.split()
        if len(parts) >= 2:
            correct_first = parts[0]
            correct_last = parts[-1]
            correct_middle = ' '.join(parts[1:-1]) if len(parts) > 2 else None
        else:
            continue
        
        for variant in variations:
            # Find records matching this variation
            matches = await conn.fetch("""
                SELECT id, first_name, middle_name, last_name, position, province, year
                FROM political_dynasties
                WHERE UPPER(CONCAT(first_name, ' ', COALESCE(middle_name, ''), ' ', last_name)) 
                      LIKE '%' || $1 || '%'
                   OR UPPER(CONCAT(first_name, ' ', last_name)) = $1
            """, variant.upper())
            
            if matches:
                print(f"  Found {len(matches)} records for variant: {variant}")
                
                for match in matches:
                    # Update the name
                    await conn.execute("""
                        UPDATE political_dynasties
                        SET first_name = $1,
                            middle_name = $2,
                            last_name = $3,
                            canonical_name = $4
                        WHERE id = $5
                    """, correct_first, correct_middle, correct_last, 
                         correct_name, match['id'])
                    
                    print(f"    ✓ Updated ID {match['id']}: "
                          f"{match['first_name']} {match['last_name']} → {correct_name} "
                          f"({match['position']}, {match['province']}, {match['year']})")
                    
                    total_updated += 1
    
    # Create Ferdinand Marcos Sr. entry if it doesn't exist
    print(f"\n👴 Creating Ferdinand Marcos Sr. (father) entry...")
    
    # Check if Ferdinand Marcos Sr. exists
    sr_exists = await conn.fetchval("""
        SELECT COUNT(*) FROM political_dynasties
        WHERE canonical_name = 'FERDINAND MARCOS SR.'
           OR (first_name = 'FERDINAND' AND last_name = 'MARCOS' AND suffix = 'SR.')
    """)
    
    if sr_exists == 0:
        # Create a representative entry for Ferdinand Marcos Sr.
        await conn.execute("""
            INSERT INTO political_dynasties (
                first_name, middle_name, last_name, suffix,
                position, region, province, year, 
                party, canonical_name, fat, winner
            ) VALUES (
                'FERDINAND', 'EDRALIN', 'MARCOS', 'SR.',
                'PRESIDENT', 'NATIONAL', 'NATIONAL', 1965,
                'KBL', 'FERDINAND MARCOS SR.', 1, true
            )
        """)
        print("  ✓ Created Ferdinand Marcos Sr. entry (President, 1965)")
        total_updated += 1
    else:
        print(f"  ⚠️  Ferdinand Marcos Sr. already exists ({sr_exists} records)")
    
    # Summary
    print("\n" + "=" * 80)
    print(f"✅ COMPLETED: Updated {total_updated} records")
    print("=" * 80)
    
    # Show final Marcos/Romualdez family members
    print("\n📊 Current Marcos & Romualdez Family Members:")
    
    family_members = await conn.fetch("""
        SELECT DISTINCT first_name, middle_name, last_name, suffix, canonical_name, COUNT(*) as records
        FROM political_dynasties
        WHERE UPPER(last_name) IN ('MARCOS', 'ROMUALDEZ')
          AND first_name IS NOT NULL
        GROUP BY first_name, middle_name, last_name, suffix, canonical_name
        ORDER BY last_name, first_name
    """)
    
    for member in family_members:
        name = f"{member['first_name']} {member['middle_name'] or ''} {member['last_name']} {member['suffix'] or ''}".strip()
        canonical = member['canonical_name'] or 'N/A'
        print(f"  • {name:40} → {canonical:40} ({member['records']} records)")
    
    # Save pattern for review
    print("\n📝 Name Variation Patterns to Watch For:")
    for pattern in NAME_VARIATION_PATTERNS:
        print(f"  • {pattern}")
    
    # Create a review pattern file
    with open('name_variation_patterns_for_review.txt', 'w') as f:
        f.write("NAME VARIATION PATTERNS FOR REVIEW\n")
        f.write("=" * 80 + "\n\n")
        f.write("Based on Marcos/Romualdez corrections, watch for:\n\n")
        for pattern in NAME_VARIATION_PATTERNS:
            f.write(f"  • {pattern}\n")
        f.write("\n\nSQL Query to Find Similar Issues:\n\n")
        f.write("""
-- Find names with Jr. but no Sr.
SELECT last_name, COUNT(*) as jr_count
FROM political_dynasties
WHERE suffix = 'JR.' OR first_name LIKE '%JR%' OR last_name LIKE '%JR%'
GROUP BY last_name
HAVING COUNT(*) > 1;

-- Find names with nickname variations (common Filipino nicknames)
SELECT first_name, last_name, COUNT(*) as count
FROM political_dynasties  
WHERE first_name IN ('BONGBONG', 'BONG', 'NOYNOY', 'NENE', 'BING', 'JUN', 'BOY')
GROUP BY first_name, last_name
HAVING COUNT(*) > 0;

-- Find potential misspellings (very similar names)
SELECT p1.first_name as name1, p2.first_name as name2, p1.last_name
FROM political_dynasties p1
JOIN political_dynasties p2 ON p1.last_name = p2.last_name 
WHERE p1.id < p2.id
  AND levenshtein(p1.first_name, p2.first_name) <= 2
  AND p1.first_name != p2.first_name
LIMIT 50;
""")
    
    print("\n✅ Saved review patterns to: name_variation_patterns_for_review.txt")
    
    await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_marcos_romualdez_names())

