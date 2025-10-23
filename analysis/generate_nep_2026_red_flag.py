#!/usr/bin/env python3
"""
Generate NEP 2026 Red Flag Analysis JSON
Creates the JSON file expected by the frontend for the red flag chart
"""

import asyncio
import os
import json
import asyncpg
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def get_db_connection():
    """Get PostgreSQL connection to NEP database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'joebert'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_NEP', 'nep')
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

async def generate_red_flag_data():
    """Generate red flag analysis data for NEP 2026"""
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get year-over-year budget data for road infrastructure
        query = """
        WITH yearly_totals AS (
            SELECT 
                CASE 
                    WHEN table_name = 'budget_2020' THEN 2020
                    WHEN table_name = 'budget_2021' THEN 2021
                    WHEN table_name = 'budget_2022' THEN 2022
                    WHEN table_name = 'budget_2023' THEN 2023
                    WHEN table_name = 'budget_2024' THEN 2024
                    WHEN table_name = 'budget_2025' THEN 2025
                    WHEN table_name = 'budget_2026' THEN 2026
                END as year,
                SUM(amount) as total_amount
            FROM (
                SELECT 'budget_2020' as table_name, amount FROM budget_2020 WHERE LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%'
                UNION ALL
                SELECT 'budget_2021' as table_name, amount FROM budget_2021 WHERE LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%'
                UNION ALL
                SELECT 'budget_2022' as table_name, amount FROM budget_2022 WHERE LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%'
                UNION ALL
                SELECT 'budget_2023' as table_name, amount FROM budget_2023 WHERE LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%'
                UNION ALL
                SELECT 'budget_2024' as table_name, amount FROM budget_2024 WHERE LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%'
                UNION ALL
                SELECT 'budget_2025' as table_name, amount FROM budget_2025 WHERE LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%'
                UNION ALL
                SELECT 'budget_2026' as table_name, amount FROM budget_2026 WHERE LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%'
            ) all_data
            GROUP BY table_name
            ORDER BY year
        )
        SELECT year, total_amount FROM yearly_totals
        """
        
        results = await conn.fetch(query)
        await conn.close()
        
        # Process results
        years = []
        budgets = []
        
        for row in results:
            years.append(row['year'])
            budgets.append(float(row['total_amount'] or 0))
        
        # Calculate historical average (2020-2025, excluding 2026)
        historical_years = [y for y in years if y < 2026]
        historical_budgets = [budgets[i] for i, y in enumerate(years) if y < 2026]
        historical_avg = sum(historical_budgets) / len(historical_budgets) if historical_budgets else 0
        
        return {
            'success': True,
            'years': years,
            'budgets': budgets,
            'historical_avg': historical_avg,
            'analysis_date': datetime.now().isoformat(),
            'description': 'NEP Road Infrastructure Budget Analysis (2020-2026)',
            'red_flags': {
                'sudden_rise_2026': budgets[-1] > historical_avg * 1.5 if len(budgets) > 0 else False,
                'historical_average': historical_avg,
                'current_year': budgets[-1] if len(budgets) > 0 else 0
            }
        }
        
    except Exception as e:
        print(f"❌ Error generating red flag data: {e}")
        await conn.close()
        return None

async def main():
    """Generate NEP 2026 red flag JSON file"""
    print("🔍 Generating NEP 2026 Red Flag Analysis...")
    
    data = await generate_red_flag_data()
    
    if not data:
        print("❌ Failed to generate red flag data")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Save to JSON file
    output_file = 'static/data/nep_2026_red_flag.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated {output_file}")
    print(f"📊 Years: {data['years']}")
    print(f"💰 Budgets: {[f'₱{b/1000000000:.1f}B' for b in data['budgets']]}")
    print(f"📈 Historical Average: ₱{data['historical_avg']/1000000000:.1f}B")

if __name__ == "__main__":
    asyncio.run(main())
