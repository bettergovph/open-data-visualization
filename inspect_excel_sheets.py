import pandas as pd
import os

base_dir = '/home/joebert/open-data-visualization/database/dpwh/contract splitting'
file1 = 'Contract Splitting 2021-2024_for ANs.xlsx'

def inspect_sheets(filename):
    print(f"--- Inspecting Sheets for {filename} ---")
    try:
        path = os.path.join(base_dir, filename)
        xls = pd.ExcelFile(path)
        print("Sheet names:", xls.sheet_names)
        
        for sheet in xls.sheet_names:
            print(f"\n--- Reading Sheet: {sheet} ---")
            df = pd.read_excel(path, sheet_name=sheet)
            print("Columns:", df.columns.tolist())
            print("First 3 rows:")
            print(df.head(3))
            
    except Exception as e:
        print(f"Error reading {filename}: {e}")

inspect_sheets(file1)
