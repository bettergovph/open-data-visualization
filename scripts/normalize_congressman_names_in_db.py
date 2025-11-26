#!/usr/bin/env python3
"""
Normalize congressman display names in the database to canonical forms.
This consolidates name variations (e.g., "Elpidio F. Barzaga Jr." and "Elpidio Barzaga Jr.")
into a single canonical name (preferring names with middle names for family tree tracing).
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List
import duckdb

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def _normalize_congressman_name(name: str) -> str:
    """
    Normalize congressman name for matching.
    Removes middle initials, middle names, extra spaces, and creates a base key from first+last name.
    Handles hyphenated names by taking the last part.
    """
    if not name:
        return ""
    # Convert to lowercase and strip
    normalized = name.lower().strip()
    # Remove middle initials (single letters with periods, e.g., "F.", "M.", "B.")
    normalized = re.sub(r'\b[a-z]\.\s+', ' ', normalized)
    # Remove extra spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Extract first name, last name, and suffix
    parts = normalized.split()
    suffixes = {'jr', 'sr', 'ii', 'iii', 'iv', 'v', 'jr.', 'sr.', 'ii.', 'iii.', 'iv.', 'v.'}
    
    if len(parts) == 0:
        return ""
    elif len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return ' '.join(parts)
    else:
        # 3+ parts: first name, middle name(s), last name, optional suffix
        first_name = parts[0]
        
        # Find last name (could be hyphenated like "Besas-Tutor")
        last_name_part = parts[-1] if parts[-1] not in suffixes else parts[-2]
        
        # Handle hyphenated last names (take the part after the hyphen, or the whole thing)
        if '-' in last_name_part:
            # For hyphenated names like "Besas-Tutor", use "Tutor"
            last_name = last_name_part.split('-')[-1]
        else:
            last_name = last_name_part
        
        suffix = parts[-1] if parts[-1] in suffixes else None
        
        # Build normalized: first + last + suffix
        result = f"{first_name} {last_name}"
        if suffix:
            result += f" {suffix}"
        return result

def normalize_names_in_database():
    """Normalize all congressman display names in DuckDB"""
    # Find DuckDB file
    parquet_dir = Path(__file__).parent.parent / 'data' / 'parquet'
    duckdb_path = parquet_dir / 'dynasty_data.duckdb'
    
    if not duckdb_path.exists():
        # Try alternative location
        parquet_dir = Path(__file__).parent.parent / 'static' / 'data' / 'parquet'
        duckdb_path = parquet_dir / 'dynasty_data.duckdb'
    
    if not duckdb_path.exists():
        print(f"❌ DuckDB file not found at {duckdb_path}")
        print("   Tried locations:")
        print(f"   - {Path(__file__).parent.parent / 'data' / 'parquet' / 'dynasty_data.duckdb'}")
        print(f"   - {Path(__file__).parent.parent / 'static' / 'data' / 'parquet' / 'dynasty_data.duckdb'}")
        return
    
    conn = duckdb.connect(str(duckdb_path))
    try:
        # Get all congressmen
        rows = conn.execute("SELECT id, display_name FROM congressmen_config ORDER BY id").fetchall()
        
        # Group by normalized name
        normalized_groups = {}
        
        for row in rows:
            congressman_id = row[0]
            display_name = row[1]
            if not display_name:
                continue
            
            normalized = _normalize_congressman_name(display_name)
            if normalized not in normalized_groups:
                normalized_groups[normalized] = []
            normalized_groups[normalized].append((congressman_id, display_name))
        
        # For each group with multiple variations, pick longest/most complete as canonical
        # (prefer names with middle names, full names over nicknames)
        # Middle names are important for tracing family trees
        updates = []
        for normalized, variations in normalized_groups.items():
            if len(variations) > 1:
                # Multiple variations - pick longest/most complete as canonical
                # This keeps middle names, full names, and avoids nicknames
                # Priority: full middle names > middle initials > no middle names
                def name_priority(v):
                    name = v[1]
                    parts = name.split()
                    word_count = len(parts)
                    has_middle = word_count > 2
                    
                    # Check if name has full middle names (not just initials)
                    # Full middle name = word longer than 1 character (not "F.", "M.", etc.)
                    has_full_middle = False
                    full_middle_count = 0
                    if word_count > 2:
                        # Check middle parts (skip first and last)
                        for part in parts[1:-1]:
                            # Remove period if present
                            clean_part = part.rstrip('.')
                            if len(clean_part) > 1:
                                has_full_middle = True
                                full_middle_count += 1
                    
                    # Check if last name is hyphenated (more complete)
                    last_name = parts[-1] if parts else ""
                    has_hyphenated_last = '-' in last_name
                    
                    # Priority: has_full_middle > full_middle_count > has_hyphenated_last > has_middle > length
                    return (has_full_middle, full_middle_count, has_hyphenated_last, has_middle, len(name))
                
                canonical_variation = max(variations, key=name_priority)
                canonical_name = canonical_variation[1]
                canonical_id = canonical_variation[0]
                
                print(f"\n📝 Normalizing group: {normalized}")
                for congressman_id, display_name in variations:
                    if display_name != canonical_name:
                        print(f"   '{display_name}' -> '{canonical_name}'")
                        updates.append((canonical_name, congressman_id))
                    else:
                        print(f"   '{display_name}' (canonical - keeping)")
        
        # Update database
        if updates:
            print(f"\n🔄 Updating {len(updates)} congressman names in database...")
            for canonical_name, congressman_id in updates:
                conn.execute(
                    "UPDATE congressmen_config SET display_name = ? WHERE id = ?",
                    [canonical_name, congressman_id]
                )
            print(f"✅ Updated {len(updates)} names")
        else:
            print("\n✅ No name variations found - all names are already canonical")
        
    finally:
        conn.close()

if __name__ == '__main__':
    print("🚀 Starting congressman name normalization in database...")
    normalize_names_in_database()
    print("✅ Done!")

