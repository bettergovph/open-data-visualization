#!/usr/bin/env python3
"""
Survey Engineer Positions and Names - Analyze engineer positions and the people holding them
to find unusual patterns (document fragments, parsing errors, etc.)
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv
from collections import Counter, defaultdict
from datetime import datetime


def load_env_from_dotenv() -> None:
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[2]
    env_path = root / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def survey_engineer_positions_and_names():
    """Survey engineer positions and names to find unusual patterns"""
    load_env_from_dotenv()
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("=" * 100)
        print("ENGINEER POSITIONS AND NAMES SURVEY - UNUSUAL PATTERNS ANALYSIS")
        print("=" * 100)
        print()
        
        # Get all engineer positions with their holders
        engineer_records = await conn.fetch('''
            SELECT 
                id,
                first_name,
                last_name,
                position,
                province,
                municipality_city,
                region,
                year
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
            ORDER BY position, last_name, first_name
        ''')
        
        print(f"📊 Total records with engineer positions: {len(engineer_records)}")
        print()
        
        # Group by position
        positions_map = defaultdict(list)
        for record in engineer_records:
            positions_map[record['position']].append(record)
        
        print(f"📊 Total unique engineer positions: {len(positions_map)}")
        print()
        
        # 1. Analyze positions that look suspicious
        print("=" * 100)
        print("1. SUSPICIOUS POSITIONS (Document Fragments)")
        print("=" * 100)
        print()
        
        suspicious_positions = []
        document_word_positions = []
        number_positions = []
        
        for position, records in positions_map.items():
            pos_upper = position.upper()
            suspicious = False
            reasons = []
            
            # Check for document fragments
            document_words = ['TO', 'ON', 'OF', 'AT', 'AS', 'OR', 'AND', 'THE', 'BUT', 'FOR', 'IN', 'IS', 'THAT', 'ARE', 'WHEN', 'WHERE', 'WITHIN', 'WITHOUT', 'THROUGH', 'EXCEPT', 'ALL', 'CAN', 'FROM', 'THREE', 'PART', 'TOTAL', 'TYPICAL', 'SCHEDULE', 'FLOOR', 'PROVISION', 'BONDED', 'DIRECT', 'IMMEDIATELY']
            
            words = pos_upper.split()
            has_doc_words = any(word in document_words for word in words if word != 'ENGINEER' and word not in ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X'])
            
            if has_doc_words:
                suspicious = True
                document_word_positions.append((position, len(records)))
                reasons.append("Contains document words")
            
            # Check for numbers (some are valid like ENGINEER II, but many are not)
            if any(char.isdigit() for char in position):
                # Check if it's a valid Roman numeral or suffix
                if not any(pattern in pos_upper for pattern in ['ENGINEER I', 'ENGINEER II', 'ENGINEER III', 'ENGINEER IV']):
                    suspicious = True
                    number_positions.append((position, len(records)))
                    reasons.append("Contains unusual numbers")
            
            # Very short positions
            if len(position.strip()) < 8:
                suspicious = True
                reasons.append("Very short")
            
            if suspicious:
                suspicious_positions.append({
                    'position': position,
                    'count': len(records),
                    'reasons': reasons,
                    'records': records[:5]  # Sample records
                })
        
        # Sort by count (descending)
        suspicious_positions.sort(key=lambda x: x['count'], reverse=True)
        
        print(f"Found {len(suspicious_positions)} suspicious positions:")
        print()
        
        for item in suspicious_positions[:50]:  # Top 50
            print(f"  {item['position']:60s} | {item['count']:5d} records | {', '.join(item['reasons'])}")
            # Show sample names
            print("    Sample names:")
            for r in item['records'][:3]:
                print(f"      - {r['first_name']:30s} {r['last_name']:30s} | {r['province'] or 'N/A'}")
            print()
        
        print()
        
        # 2. Analyze names that look suspicious
        print("=" * 100)
        print("2. SUSPICIOUS NAMES HOLDING ENGINEER POSITIONS")
        print("=" * 100)
        print()
        
        suspicious_names = []
        document_fragment_names = []
        
        # Common document fragment patterns
        bad_first_names = ['TO', 'ON', 'OF', 'AT', 'AS', 'OR', 'AND', 'THE', 'BUT', 'FOR', 'IN', 'IS', 'THAT', 'ARE', 'WHEN', 'WHERE', 'WITHIN', 'WITHOUT', 'THROUGH', 'EXCEPT', 'ALL', 'CAN', 'FROM', 'ENGINEER', 'ENGINEERING']
        bad_last_names = ['TO', 'ON', 'OF', 'AT', 'AS', 'OR', 'AND', 'THE', 'BUT', 'FOR', 'IN', 'IS', 'THAT', 'ARE', 'ENGINEER', 'ENGINEERING', 'SECTION', 'UNIT', 'OFFICE']
        
        seen_suspicious = set()
        
        for record in engineer_records:
            first = (record['first_name'] or '').strip().upper()
            last = (record['last_name'] or '').strip().upper()
            pos = record['position']
            
            suspicious = False
            reasons = []
            
            # Check for document fragments in names
            if first in bad_first_names or last in bad_last_names:
                suspicious = True
                reasons.append("Document fragment name")
                key = (first, last, pos)
                if key not in seen_suspicious:
                    document_fragment_names.append(record)
                    seen_suspicious.add(key)
            
            # Very short names
            if first and len(first) <= 1:
                suspicious = True
                reasons.append("Single-letter first name")
            
            if last and len(last) <= 1:
                suspicious = True
                reasons.append("Single-letter last name")
            
            # Names containing "ENGINEER" (likely parsing errors)
            if 'ENGINEER' in first or 'ENGINEER' in last:
                suspicious = True
                reasons.append("Name contains 'ENGINEER'")
            
            # Names that look like positions or technical terms
            if any(word in first or word in last for word in ['SECTION', 'OFFICE', 'UNIT', 'DISTRICT', 'PROVINCE', 'CITY']):
                suspicious = True
                reasons.append("Name contains position words")
            
            if suspicious:
                key = (first, last)
                if key not in seen_suspicious:
                    suspicious_names.append({
                        'first_name': record['first_name'],
                        'last_name': record['last_name'],
                        'position': pos,
                        'count': 1,
                        'reasons': reasons,
                        'records': [record]
                    })
                    seen_suspicious.add(key)
                else:
                    # Update existing
                    for item in suspicious_names:
                        if item['first_name'].upper().strip() == first and item['last_name'].upper().strip() == last:
                            item['count'] += 1
                            item['records'].append(record)
                            break
        
        # Sort suspicious names by count
        suspicious_names.sort(key=lambda x: x['count'], reverse=True)
        
        print(f"Found {len(suspicious_names)} suspicious name patterns:")
        print()
        
        for item in suspicious_names[:50]:  # Top 50
            print(f"  {item['first_name']:30s} {item['last_name']:30s} | {item['position']:40s} | {item['count']:3d} records")
            print(f"    Reasons: {', '.join(item['reasons'])}")
            if item['records']:
                print(f"    Locations: {', '.join(set(r['province'] or 'N/A' for r in item['records'][:5]))}")
            print()
        
        print()
        
        # 3. Analyze position-name combinations that are unusual
        print("=" * 100)
        print("3. UNUSUAL POSITION-NAME COMBINATIONS")
        print("=" * 100)
        print()
        
        # Group by position-name combination
        combo_counter = Counter()
        combo_records = defaultdict(list)
        
        for record in engineer_records:
            combo = (record['position'].upper(), record['first_name'].upper().strip() if record['first_name'] else '', record['last_name'].upper().strip() if record['last_name'] else '')
            combo_counter[combo] += 1
            combo_records[combo].append(record)
        
        # Find combinations that appear suspiciously many times or have unusual patterns
        print("Position-name combinations with high frequency (possible duplicates or document fragments):")
        print()
        
        high_freq_combos = [(combo, count) for combo, count in combo_counter.items() if count > 5]
        high_freq_combos.sort(key=lambda x: x[1], reverse=True)
        
        for combo, count in high_freq_combos[:30]:
            pos, first, last = combo
            print(f"  {pos:50s} | {first:25s} {last:25s} | {count:4d} times")
            # Check if all records are identical (likely duplicates)
            sample = combo_records[combo][0]
            all_same = all(
                r['province'] == sample['province'] and
                r['municipality_city'] == sample['municipality_city'] and
                r['year'] == sample['year']
                for r in combo_records[combo]
            )
            if all_same and count > 10:
                print(f"    ⚠️  WARNING: All {count} records are identical - likely duplicates!")
            print()
        
        print()
        
        # 4. Summary of document fragments to clean
        print("=" * 100)
        print("4. DOCUMENT FRAGMENTS TO DELETE")
        print("=" * 100)
        print()
        
        print("Positions with document words (should be deleted):")
        doc_positions = sorted(set(p for p, _ in document_word_positions), key=lambda x: next(c for p, c in document_word_positions if p == x), reverse=True)
        for pos in doc_positions[:30]:
            count = next(c for p, c in document_word_positions if p == pos)
            print(f"  {pos:60s} | {count:5d} records")
        
        print()
        print("Names that are document fragments (should be deleted):")
        for record in document_fragment_names[:30]:
            print(f"  {record['first_name']:30s} {record['last_name']:30s} | {record['position']:40s} | ID:{record['id']}")
        
        print()
        
        # 5. Legitimate positions summary
        print("=" * 100)
        print("5. LIKELY LEGITIMATE ENGINEER POSITIONS")
        print("=" * 100)
        print()
        
        legitimate_patterns = ['ENGINEER I', 'ENGINEER II', 'ENGINEER III', 'ENGINEER IV', 'CIVIL ENGINEER', 'ELECTRICAL ENGINEER', 'SANITARY ENGINEER', 'STRUCTURAL ENGINEER', 'GEODETIC ENGINEER', 'ENGINEER CHIEF', 'ENGINEER ASSISTANT', 'ENGINEERING OFFICE']
        
        legitimate = []
        for position, records in positions_map.items():
            pos_upper = position.upper()
            if any(pattern in pos_upper for pattern in legitimate_patterns):
                legitimate.append((position, len(records)))
        
        legitimate.sort(key=lambda x: x[1], reverse=True)
        
        print("Legitimate engineer positions:")
        for pos, count in legitimate:
            print(f"  {pos:60s} | {count:5d} records")
        
        print()
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Total records: {len(engineer_records)}")
        print(f"Unique positions: {len(positions_map)}")
        print(f"Suspicious positions: {len(suspicious_positions)}")
        print(f"Suspicious names: {len(suspicious_names)}")
        print(f"Document fragment positions: {len(document_word_positions)}")
        print(f"Document fragment names: {len(document_fragment_names)}")
        print(f"Legitimate positions: {len(legitimate)}")
        print()
        
        # Save detailed report
        report_dir = Path(__file__).resolve().parent
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f"engineer_positions_names_survey_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("ENGINEER POSITIONS AND NAMES SURVEY REPORT\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write("=" * 100 + "\n\n")
            f.write(f"Total records: {len(engineer_records)}\n")
            f.write(f"Unique positions: {len(positions_map)}\n\n")
            
            f.write("SUSPICIOUS POSITIONS:\n")
            f.write("-" * 100 + "\n")
            for item in suspicious_positions:
                f.write(f"{item['position']:60s} | {item['count']:5d} | {', '.join(item['reasons'])}\n")
            
            f.write("\n\nSUSPICIOUS NAMES:\n")
            f.write("-" * 100 + "\n")
            for item in suspicious_names:
                f.write(f"{item['first_name']:30s} {item['last_name']:30s} | {item['position']:40s} | {item['count']:3d} | {', '.join(item['reasons'])}\n")
        
        print(f"✅ Detailed report saved to: {report_file}")
        print()
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(survey_engineer_positions_and_names())

