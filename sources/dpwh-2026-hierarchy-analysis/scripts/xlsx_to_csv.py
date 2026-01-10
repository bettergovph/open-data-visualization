#!/usr/bin/env python3
"""
Convert XLSX file to CSV using calamine.
Transforms the Excel file in the data directory to CSV format.
"""

import os
import sys
import csv
from pathlib import Path
from python_calamine import CalamineWorkbook

def convert_xlsx_to_csv(xlsx_path, output_dir=None):
    """
    Convert XLSX file to CSV files (one per sheet).
    
    Args:
        xlsx_path: Path to the input XLSX file
        output_dir: Directory to save CSV files (default: same as XLSX file)
    """
    xlsx_path = Path(xlsx_path)
    
    if not xlsx_path.exists():
        raise FileNotFoundError(f"XLSX file not found: {xlsx_path}")
    
    # Set output directory
    if output_dir is None:
        output_dir = xlsx_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    
    # Open the Excel file
    print(f"Reading XLSX file: {xlsx_path}")
    workbook = CalamineWorkbook.from_path(str(xlsx_path))
    
    # Get number of sheets
    num_sheets = workbook.sheet_names
    print(f"Found {len(num_sheets)} sheet(s): {', '.join(num_sheets)}")
    
    # Convert each sheet to CSV
    for sheet_index, sheet_name in enumerate(num_sheets):
        print(f"\nProcessing sheet {sheet_index + 1}: {sheet_name}")
        
        # Get the sheet
        sheet = workbook.get_sheet_by_index(sheet_index)
        
        # Generate output CSV filename
        # Sanitize sheet name for filename
        safe_sheet_name = "".join(c for c in sheet_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_sheet_name = safe_sheet_name.replace(' ', '_')
        
        csv_filename = f"{xlsx_path.stem}_{safe_sheet_name}.csv"
        csv_path = output_dir / csv_filename
        
        # Read all data from the sheet
        data = sheet.to_python()
        
        # Write to CSV
        print(f"Writing to: {csv_path}")
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(data)
        
        print(f"✓ Converted {len(data)} rows to {csv_path}")
    
    print(f"\n✓ Conversion complete! CSV files saved to: {output_dir}")

def main():
    """Main function to run the conversion."""
    # Get the script directory and project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    data_dir = project_root / "data"
    
    # Find XLSX file in data directory
    xlsx_files = list(data_dir.glob("*.xlsx"))
    
    if not xlsx_files:
        print(f"Error: No XLSX files found in {data_dir}")
        sys.exit(1)
    
    # Use the first XLSX file found
    xlsx_file = xlsx_files[0]
    
    # Output CSV files to data directory
    output_dir = data_dir
    
    try:
        convert_xlsx_to_csv(xlsx_file, output_dir)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
