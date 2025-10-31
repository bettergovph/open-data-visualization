#!/usr/bin/env python3
"""
Survey Engineer Positions - Analyze engineer positions to find unusual patterns
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv
from collections import Counter
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


async def survey_engineer_positions():
    """Survey engineer positions to find unusual patterns"""
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
        print("ENGINEER POSITIONS SURVEY - UNUSUAL PATTERNS ANALYSIS")
        print("=" * 100)
        print()
        
        # Get all engineer positions with max 2 words
        engineer_positions = await conn.fetch('''
            SELECT DISTINCT position, COUNT(*) as count
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
            GROUP BY position
            ORDER BY count DESC, position
        ''')
        
        print(f"📊 Total unique engineer positions (max 2 words): {len(engineer_positions)}")
        print()
        
        # Show all engineer positions
        print("=" * 100)
        print("ALL ENGINEER POSITIONS (sorted by frequency)")
        print("=" * 100)
        print()
        
        for i, row in enumerate(engineer_positions, 1):
            print(f"{i:4d}. {row['position']:60s} | {row['count']:6d} records")
        
        print()
        
        # Analyze patterns
        print("=" * 100)
        print("PATTERN ANALYSIS")
        print("=" * 100)
        print()
        
        # 1. Check for unusual word combinations
        print("1. POSITION WORD ANALYSIS:")
        print("-" * 100)
        
        word_counter = Counter()
        position_words = {}
        
        for row in engineer_positions:
            pos = row['position'].upper()
            words = pos.split()
            word_counter.update(words)
            
            for word in words:
                if word not in position_words:
                    position_words[word] = []
                position_words[word].append(row['position'])
        
        print("   Most common words in engineer positions:")
        for word, count in word_counter.most_common(20):
            print(f"      {word:20s} | {count:4d} times")
        print()
        
        # 2. Check for positions with unusual suffixes/prefixes
        print("2. UNUSUAL PATTERNS:")
        print("-" * 100)
        
        unusual_patterns = []
        
        for row in engineer_positions:
            pos = row['position'].upper()
            pos_lower = row['position']
            
            # Check for unusual patterns
            unusual = False
            reason = []
            
            # Very short positions (likely incomplete)
            if len(pos) < 8:
                unusual = True
                reason.append(f"Very short ({len(pos)} chars)")
            
            # Positions with numbers (e.g., "ENGINEER 1", "ENGINEER II")
            if any(char.isdigit() for char in pos):
                unusual = True
                reason.append("Contains numbers")
            
            # Positions with unusual punctuation
            if any(char in pos for char in ['-', '/', '(', ')', '.']):
                unusual = True
                reason.append("Contains punctuation")
            
            # Positions with very common words that might be document fragments
            suspicious_words = ['OF', 'THE', 'AND', 'FOR', 'TO', 'IN', 'ON', 'AT', 'BY']
            words = pos.split()
            if any(word in suspicious_words for word in words):
                unusual = True
                reason.append("Contains common document words")
            
            if unusual:
                unusual_patterns.append({
                    'position': pos_lower,
                    'count': row['count'],
                    'reasons': reason
                })
        
        if unusual_patterns:
            print(f"   Found {len(unusual_patterns)} positions with unusual patterns:")
            for item in sorted(unusual_patterns, key=lambda x: x['count'], reverse=True):
                print(f"      {item['position']:60s} | {item['count']:6d} records | {', '.join(item['reasons'])}")
        else:
            print("   ✅ No unusual patterns detected")
        
        print()
        
        # 3. Check for duplicate/near-duplicate positions
        print("3. DUPLICATE/NEAR-DUPLICATE ANALYSIS:")
        print("-" * 100)
        
        position_map = {}
        for row in engineer_positions:
            pos_upper = row['position'].upper().strip()
            if pos_upper not in position_map:
                position_map[pos_upper] = []
            position_map[pos_upper].append(row['position'])
        
        duplicates = {k: v for k, v in position_map.items() if len(v) > 1}
        if duplicates:
            print(f"   Found {len(duplicates)} positions with case/variation differences:")
            for pos_upper, variations in sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True):
                print(f"      {pos_upper}")
                for var in sorted(variations):
                    count = next(r['count'] for r in engineer_positions if r['position'] == var)
                    print(f"         - {var:50s} ({count} records)")
        else:
            print("   ✅ No duplicate variations found")
        
        print()
        
        # 4. Check positions by region/province
        print("4. REGIONAL DISTRIBUTION (Top 10 by position):")
        print("-" * 100)
        
        top_positions = [row['position'] for row in engineer_positions[:10]]
        
        for pos in top_positions:
            regions = await conn.fetch('''
                SELECT region, COUNT(*) as count
                FROM political_dynasties
                WHERE position = $1
                  AND region IS NOT NULL AND region != ''
                GROUP BY region
                ORDER BY count DESC
                LIMIT 5
            ''', pos)
            
            if regions:
                print(f"   {pos}:")
                for r in regions:
                    print(f"      {r['region']:50s} | {r['count']:5d} records")
                print()
        
        # 5. Check year distribution
        print("5. YEAR DISTRIBUTION:")
        print("-" * 100)
        
        years = await conn.fetch('''
            SELECT year, COUNT(*) as count
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
              AND year IS NOT NULL
            GROUP BY year
            ORDER BY year DESC
        ''')
        
        if years:
            print("   Engineer positions by year:")
            for y in years:
                print(f"      {y['year']:6d} | {y['count']:6d} records")
        else:
            print("   ⚠️  No year data available")
        
        print()
        
        # Summary report
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Total unique engineer positions: {len(engineer_positions)}")
        print(f"Total records with engineer positions: {sum(r['count'] for r in engineer_positions)}")
        print(f"Positions with unusual patterns: {len(unusual_patterns)}")
        print(f"Positions with duplicate variations: {len(duplicates)}")
        print()
        
        # Save report
        report_dir = Path(__file__).resolve().parent
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = report_dir / f"engineer_positions_survey_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("ENGINEER POSITIONS SURVEY REPORT\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write("=" * 100 + "\n\n")
            f.write(f"Total unique positions: {len(engineer_positions)}\n")
            f.write(f"Total records: {sum(r['count'] for r in engineer_positions)}\n\n")
            f.write("ALL POSITIONS:\n")
            f.write("-" * 100 + "\n")
            for i, row in enumerate(engineer_positions, 1):
                f.write(f"{i:4d}. {row['position']:60s} | {row['count']:6d}\n")
        
        print(f"✅ Report saved to: {report_file}")
        print()
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(survey_engineer_positions())

