import pandas as pd
import os

base_dir = '/home/joebert/open-data-visualization/database/dpwh/contract splitting'
file1 = 'Contract Splitting 2021-2024_for ANs.xlsx'
file2 = 'contract splitting candidates.xlsx'

def inspect_file(filename):
    print(f"--- Inspecting {filename} ---")
    try:
        path = os.path.join(base_dir, filename)
        df = pd.read_excel(path)
        print("Columns:")
        print(df.columns.tolist())
        print("\nData Types:")
        print(df.dtypes)
        print("\nFirst 3 rows:")
        print(df.head(3))
        print("\n")
    except Exception as e:
        print(f"Error reading {filename}: {e}")

inspect_file(file1)
inspect_file(file2)
