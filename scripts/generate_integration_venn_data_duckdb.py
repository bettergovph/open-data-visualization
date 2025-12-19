import duckdb
import json
import os
from datetime import datetime

PARQUET_PATH = "data/parquet/integrated_projects.parquet"
OUTPUT_PATH = "static/data/integration_venn_data.json"

def generate_venn_data():
    print(f"Loading {PARQUET_PATH}...")
    conn = duckdb.connect()
    
    # We group by project_name to find overlaps
    # We collect the list of unique sources for each project_name
    query = f"""
    SELECT 
        project_name,
        LIST_SORT(LIST(DISTINCT source)) as sources
    FROM '{PARQUET_PATH}'
    GROUP BY project_name
    """
    
    print("Executing aggregation query...")
    df = conn.execute(query).df()
    
    print(f"Processed {len(df)} unique projects.")
    
    venn_counts = {}
    source_totals = {
        "SSP": 0,
        "DIME": 0,
        "PhilGEPS": 0,
        "Microsite": 0,
        "Transparency": 0
    }
    
    # Iterate to count intersections and totals
    for sources in df['sources']:
        # Update totals
        for s in sources:
            if s in source_totals:
                source_totals[s] += 1
            else:
                # Handle unexpected sources if any
                source_totals[s] = source_totals.get(s, 0) + 1
        
        # Create combination key
        # Sources are already sorted from the query, but let's be safe
        combo_key = ",".join(sorted(sources))
        
        if combo_key in venn_counts:
            venn_counts[combo_key] += 1
        else:
            venn_counts[combo_key] = 1

    # Total unique projects matching the filter
    total_unique = len(df)
    
    output_data = {
        "venn_counts": venn_counts,
        "source_totals": source_totals,
        "total_unique": total_unique,
        "generated_at": datetime.now().isoformat()
    }
    
    print("Source Totals:")
    print(json.dumps(source_totals, indent=2))
    
    print(f"Writing output to {OUTPUT_PATH}...")
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print("Done.")

if __name__ == "__main__":
    generate_venn_data()
