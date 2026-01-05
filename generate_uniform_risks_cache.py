#!/usr/bin/env python3
"""
Standalone script to generate the DPWH 2026 Uniform Risks cache file.
This pre-computes the uniform risks analysis and saves it to JSON for fast loading.

Usage:
    python3 generate_uniform_risks_cache.py
"""

import json
import duckdb
from pathlib import Path

def generate_uniform_risks_cache(min_cluster_size=10):
    print(f"🔄 Generating DPWH 2026 Uniform Risks cache (min_cluster_size={min_cluster_size})...")
    
    # Paths
    parquet_file = Path("data/parquet/parsed_dpwh_2026.parquet")
    cache_dir = Path("static/data/api_cache")
    cache_file = cache_dir / f"uniform_risks_cache_size{min_cluster_size}.json"
    
    if not parquet_file.exists():
        print(f"   ❌ Error: Data file not found at {parquet_file}")
        return False
    
    print("   📖 Loading and analyzing data from", parquet_file)
    
    conn = duckdb.connect()
    try:
        parquet_path_str = str(parquet_file).replace("'", "''")
        
        # Use the same DuckDB query as the API endpoint
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
            filled_context AS (
               SELECT
                    _excel_row, col_J, amount, latest_qualifier_column,
                    LAST_VALUE(col_C IGNORE NULLS) OVER (PARTITION BY grp_B ORDER BY _excel_row) as cat_C,
                    LAST_VALUE(clean_H IGNORE NULLS) OVER (PARTITION BY grp_C ORDER BY _excel_row) as cat_H,
                    LAST_VALUE(clean_I IGNORE NULLS) OVER (PARTITION BY grp_H ORDER BY _excel_row) as cat_I
               FROM groups
            ),
            marked AS (
                SELECT *,
                    amount = LAG(amount) OVER (ORDER BY _excel_row) as match_prev,
                    amount = LEAD(amount) OVER (ORDER BY _excel_row) as match_next
                FROM filled_context
                WHERE latest_qualifier_column = 'J' 
                AND col_J NOT ILIKE 'GOP' 
                AND col_J NOT ILIKE 'Loan Proceeds'
                AND col_J NOT ILIKE '%Sub-Total%'
            ),
            runs AS (
                SELECT *,
                    CASE WHEN match_prev THEN 0 ELSE 1 END as is_new_run
                FROM marked
                WHERE match_prev OR match_next
            ),
            grouped_runs AS (
                SELECT *,
                    SUM(is_new_run) OVER (ORDER BY _excel_row) as run_id
                FROM runs
            ),
            cluster_stats AS (
                SELECT run_id, COUNT(*) as cnt 
                FROM grouped_runs 
                GROUP BY run_id 
                HAVING COUNT(*) >= {min_cluster_size}
            )
            SELECT 
                r._excel_row,
                r.amount,
                r.col_J as project_name,
                r.cat_C as program,
                r.cat_H as region,
                r.cat_I as district,
                r.run_id,
                cs.cnt as cluster_size
            FROM grouped_runs r
            JOIN cluster_stats cs ON r.run_id = cs.run_id
            ORDER BY cs.cnt DESC, r.run_id, r._excel_row
            LIMIT 10000
        """
        
        rows = conn.execute(query).fetchall()
        cols = [desc[0] for desc in conn.description]
        data = [dict(zip(cols, r)) for r in rows]
        
        print(f"   ✅ Found {len(data)} risk items across clusters")
        
    finally:
        conn.close()
    
    # Apply hierarchy label fixes (same as API endpoint)
    print("   🔧 Applying hierarchy label fixes...")
    try:
        hierarchy_json_path = Path("/home/joebert/dpwh-2026-hierarchy-analysis/data/FY 2026_DPWH DETAILS ENROLLED COPY (Final)_hierarchy.json")
        
        if not hierarchy_json_path.exists():
            hierarchy_json_path = Path("static/data/FY 2026_DPWH DETAILS ENROLLED COPY (Final)_hierarchy.json")
        
        if hierarchy_json_path.exists():
            with open(hierarchy_json_path, 'r', encoding='utf-8') as f:
                h_data = json.load(f)
            
            correction_map = {}
            
            def traverse(nodes, parent_region=None, parent_district=None, parent_program=None):
                for node in nodes:
                    amt = node.get('amount')
                    if amt is None or amt == 0:
                        continue
                    
                    r_amt = round(float(amt), 2)
                    
                    val = node.get('value', '').strip()
                    val_lower = val.lower()
                    
                    is_region = 'region' in val_lower and 'district' not in val_lower
                    is_district = 'district' in val_lower
                    
                    curr_region = val if is_region else parent_region
                    curr_district = val if is_district else parent_district
                    curr_program = val if not is_region and not is_district else parent_program
                    
                    if r_amt not in correction_map:
                        correction_map[r_amt] = []
                    
                    correction_map[r_amt].append({
                        'name_clean': val_lower.replace('.', ''),
                        'region': curr_region,
                        'district': curr_district,
                        'program': curr_program
                    })
                    
                    if node.get('children'):
                        traverse(node['children'], curr_region, curr_district, curr_program)
            
            if isinstance(h_data, list):
                traverse(h_data)
            elif isinstance(h_data, dict) and h_data.get('data'):
                traverse(h_data['data'])
            
            fixes_applied = 0
            for row in data:
                p_name = str(row.get('project_name', '')).strip().lower().replace('.', '')
                try:
                    p_amt = float(row.get('amount', 0))
                    r_amt = round(p_amt, 2)
                except:
                    continue
                
                candidates = correction_map.get(r_amt)
                if candidates:
                    matches = [c for c in candidates if c['name_clean'] in p_name or p_name in c['name_clean']]
                    
                    best_match = None
                    if matches:
                        regions = set(m['region'] for m in matches if m.get('region'))
                        if len(regions) <= 1:
                            best_match = matches[0]
                    
                    if not best_match and candidates:
                        distinct_regions = set(c['region'] for c in candidates if c.get('region'))
                        if len(distinct_regions) > 1:
                            common_programs = sorted(list(set(c['program'] for c in candidates if c.get('program'))))
                            best_program = " / ".join(common_programs) if common_programs else None
                            best_match = {
                                'region': 'Mixed / Nationwide',
                                'district': 'Various Districts',
                                'program': best_program
                            }
                    
                    if best_match:
                        row['region'] = best_match.get('region') or row.get('region')
                        row['district'] = best_match.get('district') or row.get('district')
                        row['program'] = best_match.get('program') or row.get('program')
                        fixes_applied += 1
            
            print(f"   ✅ Applied {fixes_applied} label corrections")
        
    except Exception as e:
        print(f"   ⚠️ Skipping hierarchy label fixes: {str(e)}")
    
    # Save to cache
    response_data = {"data": data}
    
    print("   💾 Saving cache to", cache_file)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(response_data, f, ensure_ascii=False, indent=2)
    
    print(f"   ✅ Cache file created successfully!")
    print(f"   📊 File size: {cache_file.stat().st_size / 1024:.2f} KB")
    return True

if __name__ == "__main__":
    success = generate_uniform_risks_cache(min_cluster_size=10)
    if success:
        print("\n✅ Done! The Uniform Risks tab should now load instantly.")
    else:
        print("\n❌ Failed to generate cache. Please check error messages above.")
