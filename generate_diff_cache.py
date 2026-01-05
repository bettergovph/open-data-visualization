#!/usr/bin/env python3
"""
Standalone script to generate the DPWH 2026 Diff cache file.
This pre-computes the diff comparison and saves it to JSON for fast loading.

Usage:
    python3 generate_diff_cache.py
"""

import json
import duckdb
from pathlib import Path

def generate_diff_cache():
    print("🔄 Generating DPWH 2026 Diff cache...")
    
    # Helper function to filter line items only (exclude hierarchy headers)
    def is_line_item(name):
        """Filter out hierarchy items like region headers, funding sources, etc."""
        if not name:
            return False
        name_stripped = name.strip()
        
        # Exclude items starting with list markers
        hierarchy_prefixes = (
            'a.', 'b.', 'c.', 'd.', 'e.', 'f.', 'g.', 'h.', 'i.', 'j.', 'k.', 'l.', 'm.', 
            'n.', 'o.', 'p.', 'q.', 'r.', 's.', 't.', 'u.', 'v.', 'w.', 'x.', 'y.', 'z.',
            'A.', 'B.', 'C.', 'D.', 'E.', 'F.', 'G.', 'H.', 'I.', 'J.', 'K.', 'L.', 'M.', 
            'N.', 'O.', 'P.', 'Q.', 'R.', 'S.', 'T.', 'U.', 'V.', 'W.', 'X.', 'Y.', 'Z.',
            '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '0.',
            'I.', 'II.', 'III.', 'IV.', 'V.', 'VI.', 'VII.', 'VIII.', 'IX.', 'X.',
            'XI.', 'XII.', 'XIII.', 'XIV.', 'XV.'
        )
        if name_stripped.startswith(hierarchy_prefixes):
            return False
        
        # Exclude funding source headers
        if any(keyword in name_stripped for keyword in ['GOP', 'Loan Proceeds', 'Loan proceeds', 'Sub-Total', 'Grand Total']):
            return False
        
        return True
    
    # Paths
    ref_path = Path("static/data/budget_amendments_2026.json")
    target_parquet = Path("data/parquet/parsed_dpwh_2026.parquet")
    cache_dir = Path("static/data/api_cache")
    cache_file = cache_dir / "dpwh_diff_cache.json"
    
    # 1. Load Reference (NEP Annex A-5)
    print("   📖 Loading reference data from", ref_path)
    ref_projects = []
    if ref_path.exists():
        with open(ref_path, "r", encoding="utf-8") as f:
            ref_data = json.load(f)
            ref_projects = [
                p for p in ref_data.get("projects", [])
                if p.get("source_sheet") == "Annex A-5"
            ]
    else:
        print(f"   ❌ Error: Reference data not found at {ref_path}")
        return False

    print(f"   ✅ Loaded {len(ref_projects)} reference projects")

    # Normalize Reference
    ref_map = {}
    skipped_count = 0
    for p in ref_projects:
        name = (p.get("name") or p.get("description") or "").strip()
        if not name:
            continue
        
        # Filter out non-line-items (hierarchy headers, funding sources, etc.)
        if not is_line_item(name):
            skipped_count += 1
            continue
        
        amt = p.get("final_amount") or p.get("original_amount") or 0.0
        key = f"{name.lower()}|{float(amt):.2f}"
        ref_map[key] = {
            "name": name,
            "amount": amt,
            "original": p
        }

    print(f"   ✅ Loaded {len(ref_map)} line items from reference (filtered out {skipped_count} non-line items)")

    # 2. Load Target (DPWH 2026 Parquet)
    print("   📖 Loading target data from", target_parquet)
    target_projects = []
    
    if target_parquet.exists():
        conn = duckdb.connect()
        try:
            parquet_path_str = str(target_parquet).replace("'", "''")
            
            query = f"""
                WITH params AS (
                    SELECT 
                        _excel_row, 
                        col_J, 
                        amount, 
                        latest_qualifier_column,
                        col_B, col_C,
                        CASE WHEN LENGTH(col_H) > 3 THEN col_H ELSE NULL END as clean_H,
                        CASE WHEN LENGTH(col_I) > 3 THEN col_I ELSE NULL END as clean_I
                    FROM read_parquet('{parquet_path_str}')
                ),
                groups AS (
                    SELECT 
                        *,
                        COUNT(col_B) OVER (ORDER BY _excel_row) as grp_B,
                        COUNT(col_C) OVER (ORDER BY _excel_row) as grp_C,
                        COUNT(clean_H) OVER (ORDER BY _excel_row) as grp_H,
                        COUNT(clean_I) OVER (ORDER BY _excel_row) as grp_I
                    FROM params
                ),
                filled_data AS (
                    SELECT 
                        _excel_row,
                        amount,
                        latest_qualifier_column,
                        col_J,
                        LAST_VALUE(col_C IGNORE NULLS) OVER (PARTITION BY grp_B ORDER BY _excel_row) as cat_C,
                        LAST_VALUE(clean_H IGNORE NULLS) OVER (PARTITION BY grp_C ORDER BY _excel_row) as cat_H,
                        LAST_VALUE(clean_I IGNORE NULLS) OVER (PARTITION BY grp_H ORDER BY _excel_row) as cat_I
                    FROM groups
                )
                SELECT 
                    col_J as project_name, 
                    amount, 
                    cat_H as region,
                    cat_I as district,
                    cat_C as program
                FROM filled_data 
                WHERE 
                    latest_qualifier_column = 'J' 
                    AND col_J NOT ILIKE 'GOP' 
                    AND col_J NOT ILIKE 'Loan Proceeds'
                    AND col_J NOT ILIKE '%Sub-Total%'
                    AND col_J NOT ILIKE '%Grand Total%'
                ORDER BY _excel_row
            """
            
            rows = conn.execute(query).fetchall()
            
            for r in rows:
                name = str(r[0] or "").strip()
                if not name:
                    continue
                
                amt = float(r[1] or 0.0)
                
                target_projects.append({
                    "name": name,
                    "amount": amt,
                    "region": r[2],
                    "district": r[3],
                    "program": r[4]
                })
                
        finally:
            conn.close()
    else:
        print(f"   ❌ Error: Target data not found at {target_parquet}")
        return False

    print(f"   ✅ Loaded {len(target_projects)} target projects")

    # Normalize Target
    target_map = {}
    target_keys = set()
    target_by_name = {}  # Map by name only for detecting modifications
    
    for p in target_projects:
        name = p["name"]
        amt = p["amount"]
        key = f"{name.lower()}|{amt:.2f}"
        target_keys.add(key)
        target_map[key] = p
        
        # Also index by name only
        name_lower = name.lower()
        if name_lower not in target_by_name:
            target_by_name[name_lower] = []
        target_by_name[name_lower].append(p)

    # 3. Calculate Diff
    print("   🔍 Computing differences...")
    removed = []
    added = []
    modified = []
    
    # Build ref_by_name for modification detection
    ref_by_name = {}
    for k, v in ref_map.items():
        name_lower = v["name"].lower()
        if name_lower not in ref_by_name:
            ref_by_name[name_lower] = []
        ref_by_name[name_lower].append(v)
    
    # Removed/Modified: In Ref but not in Target (exact match) or Modified (name match, amount diff)
    for k, v in ref_map.items():
        if k not in target_keys:
            # Not an exact match - check if it's a modification
            name_lower = v["name"].lower()
            if name_lower in target_by_name:
                # Same name exists in target with different amount - it's modified
                target_versions = target_by_name[name_lower]
                # For simplicity, take the first matching target item
                # (In reality, there might be multiple, but usually it's 1:1)
                if len(target_versions) == 1:
                    modified.append({
                        "name": v["name"],
                        "ref_amount": v["amount"],
                        "target_amount": target_versions[0]["amount"],
                        "program": target_versions[0].get("program")
                    })
                else:
                    # Multiple targets with same name - ambiguous, treat as removed
                    removed.append({
                        "name": v["name"],
                        "amount": v["amount"],
                        "program": v["original"].get("program_id")
                    })
            else:
                # Truly removed
                removed.append({
                    "name": v["name"],
                    "amount": v["amount"],
                    "program": v["original"].get("program_id")
                })
    
    # Added: In Target but not in Ref (exact match) and not already counted as Modified
    modified_names = set(m["name"].lower() for m in modified)
    for k in target_keys:
        if k not in ref_map:
            p = target_map[k]
            name_lower = p["name"].lower()
            # Don't count as added if it's already in modified list
            if name_lower not in modified_names or name_lower not in ref_by_name:
                added.append({
                    "name": p["name"],
                    "amount": p["amount"],
                    "region": p.get("region"),
                    "district": p.get("district"),
                    "program": p.get("program")
                })
    
    # Sort by Amount Descending
    removed.sort(key=lambda x: x["amount"], reverse=True)
    added.sort(key=lambda x: x["amount"], reverse=True)
    modified.sort(key=lambda x: x["target_amount"], reverse=True)
    
    match_count = len(ref_projects) - len(removed) - len(modified)
    
    response_data = {
        "status": "ok",
        "data": {
            "stats": {
                "ref_count": len(ref_map),
                "target_count": len(target_projects),
                "added_count": len(added),
                "removed_count": len(removed),
                "modified_count": len(modified),
                "match_count": match_count
            },
            "removed": removed,
            "added": added,
            "modified": modified
        }
    }
    
    print(f"   ✅ Found {len(added)} added, {len(removed)} removed, {len(modified)} modified, {match_count} matches")
    
    # 4. Save to cache files (7 files: stats + 3 previews + 3 full)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Stats only (tiny file)
    stats_file = cache_dir / "dpwh_diff_stats.json"
    stats_data = {
        "status": "ok",
        "stats": {
            "ref_count": len(ref_map),
            "target_count": len(target_projects),
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
            "match_count": match_count
        }
    }
    
    print("   💾 Saving cache files...")
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats_data, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Stats: {stats_file.name} ({stats_file.stat().st_size / 1024:.2f} KB)")
    
    # Removed items (preview + full)
    preview_limit = 50
    removed_preview_file = cache_dir / "dpwh_diff_removed_preview.json"
    with open(removed_preview_file, 'w', encoding='utf-8') as f:
        json.dump({"data": removed[:preview_limit], "has_more": len(removed) > preview_limit}, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Removed Preview: {removed_preview_file.name} ({removed_preview_file.stat().st_size / 1024:.2f} KB)")
    
    removed_file = cache_dir / "dpwh_diff_removed_full.json"
    with open(removed_file, 'w', encoding='utf-8') as f:
        json.dump({"data": removed}, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Removed Full: {removed_file.name} ({removed_file.stat().st_size / 1024:.2f} KB)")
    
    # Modified items (preview + full)
    modified_preview_file = cache_dir / "dpwh_diff_modified_preview.json"
    with open(modified_preview_file, 'w', encoding='utf-8') as f:
        json.dump({"data": modified[:preview_limit], "has_more": len(modified) > preview_limit}, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Modified Preview: {modified_preview_file.name} ({modified_preview_file.stat().st_size / 1024:.2f} KB)")
    
    modified_file = cache_dir / "dpwh_diff_modified_full.json"
    with open(modified_file, 'w', encoding='utf-8') as f:
        json.dump({"data": modified}, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Modified Full: {modified_file.name} ({modified_file.stat().st_size / 1024:.2f} KB)")
    
    # Added items (preview + full)
    added_preview_file = cache_dir / "dpwh_diff_added_preview.json"
    with open(added_preview_file, 'w', encoding='utf-8') as f:
        json.dump({"data": added[:preview_limit], "has_more": len(added) > preview_limit}, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Added Preview: {added_preview_file.name} ({added_preview_file.stat().st_size / 1024:.2f} KB)")
    
    added_file = cache_dir / "dpwh_diff_added_full.json"
    with open(added_file, 'w', encoding='utf-8') as f:
        json.dump({"data": added}, f, ensure_ascii=False, indent=2)
    print(f"   ✅ Added Full: {added_file.name} ({added_file.stat().st_size / 1024:.2f} KB)")
    
    total_preview_size = (stats_file.stat().st_size + removed_preview_file.stat().st_size + 
                          modified_preview_file.stat().st_size + added_preview_file.stat().st_size) / 1024
    total_full_size = (removed_file.stat().st_size + modified_file.stat().st_size + 
                       added_file.stat().st_size) / 1024 / 1024
    print(f"   📊 Initial load (stats + previews): {total_preview_size:.2f} KB")
    print(f"   📊 Full data (on-demand): {total_full_size:.2f} MB")
    
    return True

if __name__ == "__main__":
    success = generate_diff_cache()
    if success:
        print("\n✅ Done! The Changes tab should now load instantly.")
    else:
        print("\n❌ Failed to generate cache. Please check error messages above.")
