#!/usr/bin/env python3
"""
Cache Excel program data to JSON for faster API access.
This script reads the Citizen Budget Coalition Excel file and creates cached JSON.
"""

import pandas as pd
import json
import os
from datetime import datetime
from typing import Dict, List, Any

class ExcelProgramCacheGenerator:
    """Generate cached JSON from Excel program data"""
    
    def __init__(self):
        self.excel_path = os.path.join(os.path.dirname(__file__), "database", "Citizens Budget Tracker (Flood Control 2018-2025).xlsx")
        self.cache_file = os.path.join(os.path.dirname(__file__), "static", "data", "excel_programs_cache.json")
        
        # Target programs
        self.target_programs = [
            "Convergence and Special Support Program",
            "Local Program", 
            "Asset Preservation Program",
            "Flood Management Program",
            "General Administration and Support",
            "Bridge Program",
            "Network Development Program",
            "Support to Operations"
        ]
    
    def load_excel_data(self) -> pd.DataFrame:
        """Load and clean Excel data"""
        if not os.path.exists(self.excel_path):
            raise FileNotFoundError(f"Excel file not found: {self.excel_path}")
        
        print(f"📊 Loading Excel data from: {self.excel_path}")
        df = pd.read_excel(self.excel_path, sheet_name='10a DPWH budget by program')
        
        # Clean the data
        df_clean = df.dropna(subset=['Program'])
        
        # Convert numeric columns
        numeric_cols = ['GAA', 'NEP', 'Insertions']
        for col in numeric_cols:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
        
        print(f"✅ Loaded {len(df_clean)} records")
        return df_clean
    
    def process_program_data(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Process Excel data into program comparison format"""
        program_data = []
        
        for program in self.target_programs:
            print(f"📊 Processing {program}...")
            
            # Filter data for this program
            program_df = df[df['Program'] == program]
            
            if program_df.empty:
                print(f"  ⚠️ No data found for {program}")
                program_data.append({
                    'program': program,
                    'budget_total': 0,
                    'budget_count': 0,
                    'budget_yearly': {},
                    'nep_total': 0,
                    'nep_count': 0,
                    'nep_yearly': {},
                    'gaa_yearly': {},
                    'insertions_yearly': {}
                })
                continue
            
            # Create yearly data
            budget_yearly = {}
            nep_yearly = {}
            gaa_yearly = {}
            insertions_yearly = {}
            
            for _, row in program_df.iterrows():
                year = str(int(row['FY'])) if pd.notna(row['FY']) else 'Unknown'
                gaa_amount = float(row['GAA']) if pd.notna(row['GAA']) else 0
                nep_amount = float(row['NEP']) if pd.notna(row['NEP']) else 0
                insertion_amount = float(row['Insertions']) if pd.notna(row['Insertions']) else 0
                
                budget_yearly[year] = gaa_amount  # Using GAA as budget data
                nep_yearly[year] = nep_amount
                gaa_yearly[year] = gaa_amount
                insertions_yearly[year] = insertion_amount
            
            program_data.append({
                'program': program,
                'budget_total': sum(budget_yearly.values()),
                'budget_count': len(program_df),
                'budget_yearly': budget_yearly,
                'nep_total': sum(nep_yearly.values()),
                'nep_count': len(program_df),
                'nep_yearly': nep_yearly,
                'gaa_yearly': gaa_yearly,
                'insertions_yearly': insertions_yearly
            })
            
            print(f"  ✅ {program}: Budget ₱{sum(budget_yearly.values()):,.0f}, NEP ₱{sum(nep_yearly.values()):,.0f}")
        
        return program_data
    
    def generate_cache(self) -> Dict[str, Any]:
        """Generate the complete cache data"""
        try:
            # Load Excel data
            df = self.load_excel_data()
            
            # Process program data
            programs = self.process_program_data(df)
            
            # Create cache structure
            cache_data = {
                "success": True,
                "programs": programs,
                "total_programs": len(self.target_programs),
                "data_source": "citizen_budget_coalition_excel",
                "source_file": "Citizens Budget Tracker (Flood Control 2018-2025).xlsx",
                "sheet_name": "10a DPWH budget by program",
                "generated_at": datetime.now().isoformat(),
                "description": "Cached program comparison data from Citizen Budget Coalition Excel file"
            }
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            # Save to JSON
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            print(f"💾 Cache saved to: {self.cache_file}")
            
            # Print summary
            total_budget = sum(p['budget_total'] for p in programs)
            total_nep = sum(p['nep_total'] for p in programs)
            
            print(f"\n📋 Summary:")
            print(f"  📊 Total programs: {len(programs)}")
            print(f"  💰 Total Budget (GAA): ₱{total_budget:,.0f}")
            print(f"  💰 Total NEP: ₱{total_nep:,.0f}")
            
            return cache_data
            
        except Exception as e:
            print(f"❌ Error generating cache: {e}")
            return {"success": False, "error": str(e)}

def main():
    """Main function to generate the cache"""
    generator = ExcelProgramCacheGenerator()
    generator.generate_cache()

if __name__ == "__main__":
    main()
