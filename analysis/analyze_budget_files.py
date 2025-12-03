import pandas as pd
import sys

files = [
    "database/win/Annex A - Line By Line Amendments.xlsx",
    "database/win/Annex A-1 DA-Farm-to-Market Roads.xlsx",
    "database/win/Annex A-2 DepEd - Office of the Secretary - Non Implementing Unit Secondary Schools.xlsx",
    "database/win/Annex A-4 BSGC-OEOs-NIA Details of NIA's Operations Budget.xlsx",
    "database/win/Annex A-5 Details of DPWH's Programs&Projects.xlsx",
    "database/win/General Summary of Committee Report No. 18 on House Bill No. 4058 (FY 2026 GAB).xlsx"
]

for i, file in enumerate(files, 1):
    print(f"\n{'='*80}")
    print(f"FILE {i}: {file.split('/')[-1]}")
    print('='*80)
    
    try:
        xl = pd.ExcelFile(file)
        print(f"\nSheet names ({len(xl.sheet_names)}): {xl.sheet_names[:10]}")
        if len(xl.sheet_names) > 10:
            print(f"... and {len(xl.sheet_names) - 10} more sheets")
        
        # Read first sheet
        df = pd.read_excel(file, sheet_name=xl.sheet_names[0], nrows=20)
        print(f"\nFirst sheet: '{xl.sheet_names[0]}'")
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"\nFirst 10 rows:")
        print(df.head(10).to_string())
        
    except Exception as e:
        print(f"Error reading file: {e}")
