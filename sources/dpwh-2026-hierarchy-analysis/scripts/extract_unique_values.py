#!/usr/bin/env python3
"""
Extract unique values and their counts from columns 0-9 of a CSV file.
Outputs an array of objects per column, where each object contains the value and its count.
"""

import sys
import csv
import json
from pathlib import Path
from collections import Counter

def extract_unique_values(csv_path, columns=None, output_format='json'):
    """
    Extract unique values and their counts from specified columns.
    
    Args:
        csv_path: Path to the input CSV file
        columns: List of column indices to process (default: 0-9)
        output_format: Output format - 'json' or 'print' (default: 'json')
    
    Returns:
        Dictionary with column index as key and list of {value, count} objects as value
    """
    csv_path = Path(csv_path)
    
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    if columns is None:
        columns = list(range(10))  # Columns 0-9
    
    # Read CSV and collect data for each column
    column_data = {col: [] for col in columns}
    
    print(f"Reading CSV file: {csv_path}")
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        
        # Read all rows
        for row_num, row in enumerate(reader, start=1):
            for col_idx in columns:
                if col_idx < len(row):
                    value = row[col_idx].strip() if row[col_idx] else ""
                    column_data[col_idx].append(value)
                else:
                    column_data[col_idx].append("")
            
            # Progress indicator for large files
            if row_num % 10000 == 0:
                print(f"  Processed {row_num} rows...", end='\r')
    
    print(f"\n✓ Processed {row_num} rows")
    
    # Count unique values for each column
    results = {}
    
    for col_idx in columns:
        print(f"\nProcessing column {col_idx}...")
        
        # Count occurrences
        counter = Counter(column_data[col_idx])
        
        # Create array of objects with value and count
        unique_data = [
            {"value": value, "count": count}
            for value, count in counter.most_common()
        ]
        
        results[col_idx] = unique_data
        print(f"  Found {len(unique_data)} unique values")
    
    return results

def main():
    """Main function to run the extraction."""
    # Get the script directory and project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "data"
    
    # Find CSV file in data directory
    csv_files = list(data_dir.glob("*.csv"))
    
    if not csv_files:
        print(f"Error: No CSV files found in {data_dir}")
        sys.exit(1)
    
    # Use the first CSV file found
    csv_file = csv_files[0]
    
    # Extract unique values from columns 0-9
    try:
        results = extract_unique_values(csv_file, columns=list(range(10)))
        
        # Output results
        output_file = data_dir / f"{csv_file.stem}_unique_values.json"
        
        print(f"\nWriting results to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Results saved to {output_file}")
        
        # Also print summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for col_idx in sorted(results.keys()):
            unique_count = len(results[col_idx])
            total_count = sum(item["count"] for item in results[col_idx])
            print(f"Column {col_idx}: {unique_count} unique values, {total_count} total entries")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
