import pandas as pd
import os
import pyarrow as pa
import pyarrow.parquet as pq

def convert_excel_to_parquet(excel_path, sheet_name, parquet_path):
    print(f"\nConverting {os.path.basename(excel_path)}...")
    if not os.path.exists(excel_path):
        print(f"Error: File not found: {excel_path}")
        return

    try:
        # Read Excel file
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        print(f"  - Read {len(df)} rows.")

        # Ensure directory exists
        os.makedirs(os.path.dirname(parquet_path), exist_ok=True)

        # Convert to Parquet
        df.to_parquet(parquet_path, index=False)
        print(f"  - Saved to {parquet_path}")

    except Exception as e:
        print(f"  - Error converting file: {e}")

if __name__ == "__main__":
    # Road Condition
    road_excel = '/home/joebert/open-data-visualization/database/dpwh/road condition (2025).xlsx'
    road_sheet = 'road condition (2025)'
    road_parquet = '/home/joebert/open-data-visualization/data/parquet/road_condition_2025.parquet'
    convert_excel_to_parquet(road_excel, road_sheet, road_parquet)

    # Bridge Condition
    bridge_excel = '/home/joebert/open-data-visualization/database/dpwh/bridge condition (2025).xlsx'
    bridge_sheet = 'bridge condition (2025)'
    bridge_parquet = '/home/joebert/open-data-visualization/data/parquet/bridge_condition_2025.parquet'
    convert_excel_to_parquet(bridge_excel, bridge_sheet, bridge_parquet)
