#!/usr/bin/env python3
"""
Standalone script to generate the DPWH 2026 Diff cache file.
This pre-computes the diff comparison and saves it to JSON for fast loading.

Usage:
    python3 generate_diff_cache.py
"""

import json
import re
import duckdb
from pathlib import Path

def normalize_project_name(name):
    """
    Normalize project name by removing location coordinates, chainage, and station markers.
    """
    if not name:
        return ""
    
    normalized = name
    
    # 1. Remove coordinate patterns: (lat, lon) or (lon, lat)
    normalized = re.sub(r'\(\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+\s*\)', '', normalized)
    
    # 2. Remove station/chainage markers: Sta. 1+400
    normalized = re.sub(
        r'[S][Tt][Aa]\.\s*\d+\s*\+\s*\d+(?:\.\d+)?(?:\s*-\s*(?:[S][Tt][Aa]\.\s*)?\d+\s*\+\s*\d+(?:\.\d+)?)?',
        '', 
        normalized,
        flags=re.IGNORECASE
    )
    
    # 3. Remove K-markers (kilometer markers): K0 578+755 - K0579+295
    # Also handles k0483 + 000 with spaces
    normalized = re.sub(
        r',?\s*K\d*\s*\d+\s*\+\s*\d+(?:\s*-\s*K\d*\s*\d+\s*\+\s*\d+)?',
        '',
        normalized,
        flags=re.IGNORECASE
    )
    
    # 4. Remove loan notations
    normalized = re.sub(
        r',\s*(?:ADB|AIIB|WB|JICA|KfW)\s+(?:L/A|Loan)\s+No\..*$',
        '',
        normalized,
        flags=re.IGNORECASE
    )

    # 5. Remove miscellaneous parentheticals that aren't coordinates (e.g., "(tuguegarao sect)")
    normalized = re.sub(r'\([^)]*\)', '', normalized)
    
    # 6. Final cleanup of whitespace and commas
    normalized = re.sub(r'\s*,\s*,\s*', ', ', normalized)
    normalized = re.sub(r',\s+', ', ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r',\s*$', '', normalized)
    normalized = re.sub(r'^\s*,\s*', '', normalized)
    
    return normalized.strip()

def clean_tokens(text):
    """Extract clean tokens from text, removing punctuation and common words."""
    if not text:
        return set()
    # Normalize: lower case and remove punctuation
    text = text.lower()
    # Replace common delimiters with spaces to ensure tokens are split correctly
    text = re.sub(r'[,\-./()]+', ' ', text)
    words = text.split()
    
    # Words to ignore (very common structural words)
    common_words = {
        'along', 'road', 'bridge', 'construction', 'rehabilitation', 'improvement', 
        'project', 'with', 'from', 'near', 'across', 
        'section', 'phase', 'series', 'going', 'toward',
        'roadway', 'network', 'system',
        'multi', 'purpose', 'building', 'structure'
    }
    
    # Only keep words > 3 chars that are not common
    tokens = set(w for w in words if len(w) > 3 and w not in common_words)
    return tokens

def find_similar_match(ref_normalized, target_token_index, target_by_normalized):
    """
    Find a similar match in target using a pre-built token index for speed.
    Uses stricter thresholds to prevent false positives while allowing minor variations.
    """
    ref_lower = ref_normalized.lower()
    ref_tokens = clean_tokens(ref_normalized)
    
    if not ref_tokens:
        return None
        
    # Find candidates that share at least one token
    candidates = {} # target_norm_lower -> count of shared tokens
    for token in ref_tokens:
        if token in target_token_index:
            for target_norm_lower in target_token_index[token]:
                candidates[target_norm_lower] = candidates.get(target_norm_lower, 0) + 1
                
    best_match = None
    best_match_score = 0
    
    # Only check candidates that share at least one token
    for target_norm_lower, shared_count in candidates.items():
        # Safely get target items (they might have been consumed in 1-to-1 matching)
        target_items = target_by_normalized.get(target_norm_lower)
        if not target_items:
            continue
            
        target_lower = target_norm_lower.lower()
        
        # 1. Substring match (very high confidence)
        if ref_lower in target_lower or target_lower in ref_lower:
            shorter_len = min(len(ref_lower), len(target_lower))
            longer_len = max(len(ref_lower), len(target_lower))
            # Require 80% length similarity for substring matches
            if shorter_len / longer_len >= 0.8:
                return target_items

        # 2. Token-based similarity
        target_tokens = clean_tokens(target_norm_lower)
        if not target_tokens:
            continue
            
        intersection = len(ref_tokens & target_tokens)
        union = len(ref_tokens | target_tokens)
        similarity = intersection / union if union > 0 else 0
        
        shorter_set_len = min(len(ref_tokens), len(target_tokens))
        coverage = intersection / shorter_set_len if shorter_set_len > 0 else 0
        
        # Stricter thresholds based on user feedback:
        # - High Jaccard similarity (>= 0.7) OR
        # - Very high coverage (>= 0.9) of the shorter token set
        if similarity >= 0.7 or coverage >= 0.9:
            if similarity > best_match_score:
                best_match_score = similarity
                best_match = target_items
                
    return best_match

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
        
        # Exclude funding source headers and known summary items
        if any(keyword in name_stripped for keyword in ['GOP', 'Loan Proceeds', 'Loan proceeds', 'Sub-Total', 'Grand Total', 'Rehabilitation of Disaster-Related Infrastructure']):
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
    ref_by_normalized = {}  # Map normalized name -> list of ref items
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
        normalized_name = normalize_project_name(name)
        
        # Use normalized name for key to enable fuzzy matching
        key = f"{normalized_name.lower()}|{float(amt):.2f}"
        ref_map[key] = {
            "name": name,  # Keep original name for display
            "normalized_name": normalized_name,
            "amount": amt,
            "original": p
        }
        
        # Also index by normalized name only
        norm_lower = normalized_name.lower()
        if norm_lower not in ref_by_normalized:
            ref_by_normalized[norm_lower] = []
        ref_by_normalized[norm_lower].append(ref_map[key])

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
            
            target_skipped_count = 0
            for r in rows:
                name = str(r[0] or "").strip()
                if not name:
                    continue
                
                # Filter out non-line-items (hierarchy headers, funding sources, etc.)
                if not is_line_item(name):
                    target_skipped_count += 1
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

    print(f"   ✅ Loaded {len(target_projects)} target projects (filtered out {target_skipped_count} non-line items)")

    # Normalize Target
    target_map = {}
    target_keys = set()
    target_by_normalized = {}  # Map by normalized name only for detecting modifications
    
    for p in target_projects:
        name = p["name"]
        amt = p["amount"]
        normalized_name = normalize_project_name(name)
        
        # Use normalized name for key to enable fuzzy matching
        key = f"{normalized_name.lower()}|{amt:.2f}"
        target_keys.add(key)
        target_map[key] = {
            "name": name,  # Keep original name for display
            "normalized_name": normalized_name,
            "amount": amt,
            "region": p.get("region"),
            "district": p.get("district"),
            "program": p.get("program")
        }
        
        # Also index by normalized name only
        norm_lower = normalized_name.lower()
        if norm_lower not in target_by_normalized:
            target_by_normalized[norm_lower] = []
        target_by_normalized[norm_lower].append(target_map[key])

    # Pre-build token index for fast similarity matching
    print("   🏗️ Building token index for faster matching...")
    target_token_index = {}
    for target_norm_lower in target_by_normalized:
        tokens = clean_tokens(target_norm_lower)
        for token in tokens:
            if token not in target_token_index:
                target_token_index[token] = []
            target_token_index[token].append(target_norm_lower)

    # Pre-build name -> normalized map for ref for faster added lookup
    ref_name_to_norm = {v["name"].lower(): v["normalized_name"].lower() for v in ref_map.values()}

    # 3. Calculate Diff using 1-to-1 Matching
    print("   🔍 Computing differences with 1-to-1 matching...")
    removed = []
    added = []
    modified = []
    matched_count = 0
    
    # Track which target items are still available for matching
    # key: normalized_name -> list of target_map[key] items
    available_targets_by_norm = {}
    for norm_name, items in target_by_normalized.items():
        available_targets_by_norm[norm_name] = list(items) # shallow copy list
        
    # Track which ref items are matched
    ref_items_to_match = list(ref_map.values())
    
    # Level 1: Match Exact normalized name AND amount (Matched items)
    remaining_ref = []
    for v in ref_items_to_match:
        norm_name = v["normalized_name"].lower()
        amt = float(v["amount"])
        
        found_exact = False
        if norm_name in available_targets_by_norm:
            # Look for item with same amount
            for i, target_item in enumerate(available_targets_by_norm[norm_name]):
                if abs(float(target_item["amount"]) - amt) < 0.01:
                    available_targets_by_norm[norm_name].pop(i)
                    matched_count += 1
                    found_exact = True
                    break
        
        if not found_exact:
            remaining_ref.append(v)
            
    # Level 2: Match Exact normalized name but different amount (Modified items)
    still_remaining_ref = []
    for v in remaining_ref:
        norm_name = v["normalized_name"].lower()
        
        if norm_name in available_targets_by_norm and available_targets_by_norm[norm_name]:
            # Take the first available target item with this name
            target_item = available_targets_by_norm[norm_name].pop(0)
            modified.append({
                "name": v["name"],
                "ref_amount": v["amount"],
                "target_amount": target_item["amount"],
                "program": target_item.get("program") or v["original"].get("program_id")
            })
        else:
            still_remaining_ref.append(v)
            
    # Level 3: Match by similarity (Fuzzy Modified items)
    # Re-build token index for remaining targets
    remaining_target_pool = []
    for items in available_targets_by_norm.values():
        remaining_target_pool.extend(items)
        
    # Map for fuzzy lookup
    fuzzy_target_by_norm = {}
    fuzzy_token_index = {}
    for target_item in remaining_target_pool:
        norm_lower = target_item["normalized_name"].lower()
        if norm_lower not in fuzzy_target_by_norm:
            fuzzy_target_by_norm[norm_lower] = []
        fuzzy_target_by_norm[norm_lower].append(target_item)
        
        tokens = clean_tokens(norm_lower)
        for token in tokens:
            if token not in fuzzy_token_index:
                fuzzy_token_index[token] = []
            fuzzy_token_index[token].append(norm_lower)
            
    # Final match loop
    final_remaining_ref = []
    for v in still_remaining_ref:
        match_items = find_similar_match(v["normalized_name"], fuzzy_token_index, fuzzy_target_by_norm)
        if match_items and match_items:
            # Match found! Consume the first one
            target_item = match_items.pop(0)
            modified.append({
                "name": v["name"],
                "ref_amount": v["amount"],
                "target_amount": target_item["amount"],
                "program": target_item.get("program") or v["original"].get("program_id")
            })
            # If that was the last one for that name, remove it from the pool
            if not match_items:
                del fuzzy_target_by_norm[target_item["normalized_name"].lower()]
                # Optimization: we don't strictly need to clean fuzzy_token_index
        else:
            final_remaining_ref.append(v)
            
    # Results
    removed = [{
        "name": v["name"],
        "amount": v["amount"],
        "program": v["original"].get("program_id")
    } for v in final_remaining_ref]
    
    # Added items are those remaining in available_targets_by_norm
    added = []
    for norm_name, items in fuzzy_target_by_norm.items():
        for p in items:
            added.append({
                "name": p["name"],
                "amount": p["amount"],
                "region": p.get("region"),
                "district": p.get("district"),
                "program": p.get("program")
            })
            
    # Sort for consistent output
    removed.sort(key=lambda x: x["amount"], reverse=True)
    added.sort(key=lambda x: x["amount"], reverse=True)
    modified.sort(key=lambda x: x["target_amount"], reverse=True)
    
    stats = {
        "ref_count": len(ref_map),
        "target_count": len(target_projects) + target_skipped_count,
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
        "match_count": matched_count
    }
    
    print(f"   ✅ Stats: {len(added)} added, {len(removed)} removed, {len(modified)} modified, {matched_count} matches")
    
    # Response Data
    response_data = {
        "status": "ok",
        "data": {
            "stats": stats,
            "removed": removed,
            "added": added,
            "modified": modified
        }
    }
    
    # 4. Save to cache files (7 files: stats + 3 previews + 3 full)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Stats only (tiny file)
    stats_file = cache_dir / "dpwh_diff_stats.json"
    stats_data = {
        "status": "ok",
        "stats": {
            "ref_count": len(ref_map),
            "target_count": len(target_projects) + target_skipped_count,
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
            "match_count": matched_count
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
