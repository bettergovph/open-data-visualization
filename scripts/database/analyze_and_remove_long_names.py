#!/usr/bin/env python3
"""
Analyze name and position combinations, identify very long names (suspect parsing errors)
"""

import asyncio
import os
from pathlib import Path

import asyncpg


def load_env_from_dotenv() -> None:
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


async def analyze_and_clean():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    print("=" * 80)
    print("ANALYZING NAME AND POSITION COMBINATIONS")
    print("=" * 80)
    print()
    
    # Get all name combinations with length analysis
    rows = await conn.fetch(
        """
        SELECT 
            UPPER(TRIM(first_name)) AS first_name,
            UPPER(TRIM(last_name)) AS last_name,
            LENGTH(UPPER(TRIM(first_name))) AS first_len,
            LENGTH(UPPER(TRIM(last_name))) AS last_len,
            LENGTH(UPPER(TRIM(first_name))) + LENGTH(UPPER(TRIM(last_name))) AS total_len,
            COUNT(*) AS occurrences
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
        GROUP BY UPPER(TRIM(first_name)), UPPER(TRIM(last_name))
        ORDER BY (LENGTH(UPPER(TRIM(first_name))) + LENGTH(UPPER(TRIM(last_name)))) DESC, occurrences DESC
        """
    )
    
    # Analyze length distribution
    print("NAME LENGTH DISTRIBUTION:")
    print("-" * 80)
    
    # Very long names (>80 chars total) - definitely suspect
    very_long = [(r['first_name'], r['last_name'], r['first_len'], r['last_len'], r['total_len'], r['occurrences']) 
                 for r in rows if r['total_len'] > 80]
    
    # Long names (50-80 chars) - suspicious
    long_names = [(r['first_name'], r['last_name'], r['first_len'], r['last_len'], r['total_len'], r['occurrences']) 
                  for r in rows if 50 <= r['total_len'] <= 80]
    
    # Very long first names (>40 chars) - suspect
    very_long_first = [(r['first_name'], r['last_name'], r['first_len'], r['last_len'], r['total_len'], r['occurrences']) 
                       for r in rows if r['first_len'] > 40]
    
    # Very long last names (>40 chars) - suspect
    very_long_last = [(r['first_name'], r['last_name'], r['first_len'], r['last_len'], r['total_len'], r['occurrences']) 
                      for r in rows if r['last_len'] > 40]
    
    print(f"Very long names (>80 chars total): {len(very_long)}")
    print(f"Long names (50-80 chars total): {len(long_names)}")
    print(f"Very long first names (>40 chars): {len(very_long_first)}")
    print(f"Very long last names (>40 chars): {len(very_long_last)}")
    print()
    
    # Show top 50 very long names
    print("TOP 50 VERY LONG NAMES (>80 chars total):")
    print("-" * 80)
    for i, (first, last, flen, llen, tlen, occ) in enumerate(very_long[:50], 1):
        full = f"{first} {last}"
        print(f"{i:2d}. [{tlen:3d} chars] ({flen:2d}+{llen:2d}) {full[:70]}... ({occ} occurrences)")
    if len(very_long) > 50:
        print(f"    ... and {len(very_long) - 50} more")
    print()
    
    # Show top 30 long names (50-80 chars)
    if long_names:
        print("TOP 30 LONG NAMES (50-80 chars total):")
        print("-" * 80)
        for i, (first, last, flen, llen, tlen, occ) in enumerate(long_names[:30], 1):
            full = f"{first} {last}"
            print(f"{i:2d}. [{tlen:3d} chars] ({flen:2d}+{llen:2d}) {full} ({occ} occurrences)")
        if len(long_names) > 30:
            print(f"    ... and {len(long_names) - 30} more")
        print()
    
    # Combine all suspicious names
    suspicious_set = set()
    for first, last, _, _, _, _ in very_long:
        suspicious_set.add((first, last))
    for first, last, _, _, _, _ in very_long_first:
        suspicious_set.add((first, last))
    for first, last, _, _, _, _ in very_long_last:
        suspicious_set.add((first, last))
    
    # Also include names with suspicious patterns in the name itself
    suspicious_patterns = [
        lambda f, l: len(f.split()) > 5 or len(l.split()) > 5,  # More than 5 words in name
        lambda f, l: 'ENGINEER' in f and len(f) > 20,  # ENGINEER in long first name
        lambda f, l: 'SECTION' in f or 'SECTION' in l,  # SECTION in name
        lambda f, l: 'DISTRICT' in f and len(f) > 15,  # DISTRICT in long first name
        lambda f, l: 'CONSTRUCTION' in f or 'CONSTRUCTION' in l,  # CONSTRUCTION in name
        lambda f, l: 'PROJECT' in f and len(f) > 15,  # PROJECT in long first name
    ]
    
    for first, last, _, _, tlen, _ in rows:
        if tlen > 50:  # Only check long names
            for pattern_func in suspicious_patterns:
                if pattern_func(first, last):
                    suspicious_set.add((first, last))
                    break
    
    print(f"TOTAL SUSPICIOUS NAME COMBINATIONS: {len(suspicious_set)}")
    print()
    
    # Get counts for suspicious names
    suspicious_with_counts = []
    for first, last in suspicious_set:
        # Find in rows
        for r in rows:
            if r['first_name'] == first and r['last_name'] == last:
                suspicious_with_counts.append((first, last, r['total_len'], r['occurrences']))
                break
    
    suspicious_with_counts.sort(key=lambda x: x[2], reverse=True)
    
    print("TOP 100 SUSPICIOUS NAME COMBINATIONS (sorted by length):")
    print("-" * 80)
    for i, (first, last, tlen, occ) in enumerate(suspicious_with_counts[:100], 1):
        full = f"{first} {last}"
        if len(full) > 75:
            display = full[:72] + "..."
        else:
            display = full
        print(f"{i:3d}. [{tlen:3d} chars] {display:75s} ({occ} occurrences)")
    print()
    
    # Delete suspicious entries
    print("=" * 80)
    print("DELETING SUSPICIOUS ENTRIES")
    print("=" * 80)
    print()
    
    total_deleted = 0
    deleted_combos = 0
    
    for first, last, tlen, occ in suspicious_with_counts:
        result = await conn.execute(
            """
            DELETE FROM political_dynasties
            WHERE UPPER(TRIM(first_name)) = $1
              AND UPPER(TRIM(last_name)) = $2
            """,
            first, last
        )
        deleted = int(result.split()[-1])
        if deleted > 0:
            total_deleted += deleted
            deleted_combos += 1
    
    print(f"✅ Deleted {total_deleted:,} records from {deleted_combos} suspicious name combinations")
    print()
    
    # Generate report
    report_file = Path(__file__).resolve().parents[2] / "LONG_NAMES_CLEANUP_REPORT.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("LONG NAMES CLEANUP REPORT\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("STATISTICS:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Very long names (>80 chars total): {len(very_long)}\n")
        f.write(f"Long names (50-80 chars total): {len(long_names)}\n")
        f.write(f"Very long first names (>40 chars): {len(very_long_first)}\n")
        f.write(f"Very long last names (>40 chars): {len(very_long_last)}\n")
        f.write(f"Total suspicious combinations: {len(suspicious_set)}\n")
        f.write(f"Records deleted: {total_deleted:,}\n")
        f.write(f"Name combinations removed: {deleted_combos}\n\n")
        
        f.write("DELETED ENTRIES (first 200):\n")
        f.write("-" * 80 + "\n")
        for i, (first, last, tlen, occ) in enumerate(suspicious_with_counts[:200], 1):
            full = f"{first} {last}"
            f.write(f"{i:3d}. [{tlen:3d} chars] {full} ({occ} occurrences)\n")
    
    await conn.close()
    
    print(f"📄 Report saved to: {report_file}")


if __name__ == '__main__':
    asyncio.run(analyze_and_clean())

