#!/usr/bin/env python3
"""
Generate JSON cache for GAB 2026 (PBC) data.
This script queries the database and generates static JSON files for the GAB 2026 endpoints.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to the path so we can import nep_postgres_client
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

try:
    from nep_postgres_client import get_db_connection as get_nep_db_connection
except ImportError:
    print("❌ Could not import nep_postgres_client. Make sure nep_postgres_client.py exists and is in PYTHONPATH.")
    sys.exit(1)

async def generate_gab_2026_cache():
    """Generate JSON cache files for GAB 2026 endpoints."""
    print("🚀 Generating GAB 2026 cache files...")
    load_dotenv()

    output_dir = Path(__file__).parent.parent / "static" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {output_dir}")

    try:
        conn = await get_nep_db_connection()
        if not conn:
            print("❌ Database connection failed")
            return
        
        # --- Generate headings_detail cache ---
        print("\n📊 Generating headings_detail cache...")
        headings_detail_data = {"status": "ok", "data": {"items": []}}
        
        try:
            rows = await conn.fetch(
                """
                SELECT sheet_name, label, original, hgab, delta
                FROM pbc_gab_2026_headings_detail
                WHERE sheet_name = (SELECT sheet_name FROM pbc_gab_2026_headings_detail LIMIT 1)
                ORDER BY COALESCE(hgab, 0) DESC, label ASC
                """
            )
            items = []
            for r in rows:
                items.append({
                    "sheet_name": r[0],
                    "label": r[1],
                    "original": float(r[2]) if r[2] is not None else None,
                    "hgab": float(r[3]) if r[3] is not None else None,
                    "delta": float(r[4]) if r[4] is not None else None,
                })
            headings_detail_data["data"]["items"] = items
            print(f"  ✅ Generated headings_detail cache: {len(items)} items")
        except Exception as e:
            error_msg = str(e)
            print(f"  ⚠️ Error querying pbc_gab_2026_headings_detail: {error_msg}")
            if "does not exist" in error_msg or "relation" in error_msg.lower():
                print("  ⚠️ Table pbc_gab_2026_headings_detail does not exist")
        
        with open(output_dir / "gab_2026_headings_detail.json", 'w') as f:
            json.dump(headings_detail_data, f, indent=2)
        print(f"  ✅ Saved headings_detail cache to {output_dir / 'gab_2026_headings_detail.json'}")

        # --- Generate sheets cache ---
        print("\n📊 Generating sheets cache...")
        sheets_data = {"status": "ok", "data": {"sheets": []}}
        
        try:
            rows = await conn.fetch("SELECT DISTINCT sheet_name FROM pbc_gab_2026_rows ORDER BY sheet_name")
            sheets = [r[0] for r in rows]
            sheets_data["data"]["sheets"] = sheets
            print(f"  ✅ Generated sheets cache: {len(sheets)} sheets")
        except Exception as e:
            error_msg = str(e)
            print(f"  ⚠️ Error querying pbc_gab_2026_rows: {error_msg}")
            if "does not exist" in error_msg or "relation" in error_msg.lower():
                print("  ⚠️ Table pbc_gab_2026_rows does not exist")
        
        with open(output_dir / "gab_2026_sheets.json", 'w') as f:
            json.dump(sheets_data, f, indent=2)
        print(f"  ✅ Saved sheets cache to {output_dir / 'gab_2026_sheets.json'}")

        # --- Generate sheet data cache (for each sheet) ---
        print("\n📊 Generating sheet data cache...")
        if sheets_data["data"]["sheets"]:
            sheet_data_dir = output_dir / "gab_2026_sheets"
            sheet_data_dir.mkdir(parents=True, exist_ok=True)
            
            for sheet_name in sheets_data["data"]["sheets"]:
                try:
                    rows = await conn.fetch(
                        "SELECT row_index, data FROM pbc_gab_2026_rows WHERE sheet_name=$1 ORDER BY row_index LIMIT 200",
                        sheet_name
                    )
                    data = []
                    for r in rows:
                        row_data = r[1]
                        # Handle if data is stored as JSON string
                        if isinstance(row_data, str):
                            try:
                                row_data = json.loads(row_data)
                            except:
                                row_data = {}
                        # Handle if data is None
                        if row_data is None:
                            row_data = {}
                        data.append({"row_index": r[0], **(row_data)})
                    
                    # Sanitize filename
                    safe_filename = "".join(c for c in sheet_name if c.isalnum() or c in (' ', '-', '_')).strip()
                    safe_filename = safe_filename.replace(' ', '_')
                    
                    sheet_file = sheet_data_dir / f"{safe_filename}.json"
                    with open(sheet_file, 'w') as f:
                        json.dump({"status": "ok", "data": {"rows": data}}, f, indent=2)
                    print(f"  ✅ Saved sheet '{sheet_name}': {len(data)} rows")
                except Exception as e:
                    print(f"  ⚠️ Error querying sheet '{sheet_name}': {e}")
        else:
            print("  ⚠️ No sheets available to cache")
        
        await conn.close()
        
        print("\n✅ All GAB 2026 cache files generated successfully!")
        print(f"   - Headings detail: {len(headings_detail_data['data']['items'])} items")
        print(f"   - Sheets: {len(sheets_data['data']['sheets'])} sheets")
        
    except Exception as e:
        print(f"❌ Error generating cache: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(generate_gab_2026_cache())

