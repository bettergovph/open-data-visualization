"""
Analyze PhilGEPS CSV data to find complementary fields for MeiliSearch
"""
import csv
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flood_client import FloodControlClient
from collections import defaultdict

async def main():
    print("🔍 Analyzing Complementary Data Between CSV and MeiliSearch")
    print("=" * 80)
    
    # Read CSV sample
    csv_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "database/contracts_export_flood_control_data.csv")
    
    print("\n📄 PhilGEPS CSV Fields:")
    print("-" * 80)
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        csv_fields = reader.fieldnames
        
        print("Available fields:")
        for i, field in enumerate(csv_fields, 1):
            print(f"  {i:2d}. {field}")
        
        # Get sample rows
        sample_rows = []
        for i, row in enumerate(reader):
            if i >= 10:
                break
            sample_rows.append(row)
    
    print("\n" + "=" * 80)
    print("📊 DETAILED SAMPLE RECORDS FROM CSV:")
    print("=" * 80)
    
    for i, row in enumerate(sample_rows[:5], 1):
        print(f"\n{'='*80}")
        print(f"RECORD {i}:")
        print(f"{'='*80}")
        for field, value in row.items():
            # Highlight important fields
            if field in ['contract_no', 'reference_id', 'award_date', 'award_status']:
                print(f"  ⭐ {field:25s}: {value}")
            else:
                print(f"     {field:25s}: {value}")
    
    # Get MeiliSearch sample
    print("\n" + "=" * 80)
    print("📊 MEILISEARCH DPWH FIELDS:")
    print("=" * 80)
    
    client = FloodControlClient()
    projects, _ = await client.search_projects("", limit=3)
    
    if projects:
        print("\nAvailable fields in MeiliSearch:")
        sample_project = projects[0]
        meili_fields = [attr for attr in dir(sample_project) if not attr.startswith('_')]
        for i, field in enumerate(meili_fields, 1):
            value = getattr(sample_project, field)
            if value:
                print(f"  {i:2d}. {field}")
        
        print("\n" + "=" * 80)
        print("SAMPLE MEILISEARCH RECORD:")
        print("=" * 80)
        for field in meili_fields:
            value = getattr(sample_project, field)
            if value:
                print(f"     {field:25s}: {value}")
    
    print("\n" + "=" * 80)
    print("💡 COMPLEMENTARY DATA IN CSV (Not in MeiliSearch):")
    print("=" * 80)
    
    complementary = {
        'reference_id': 'PhilGEPS unique reference ID',
        'contract_no': '⭐ Official contract number (MeiliSearch lacks this!)',
        'award_title': 'Procurement title/name',
        'notice_title': 'Original procurement notice title',
        'awardee_name': '⭐ Contractor/Company name (may differ from MeiliSearch)',
        'organization_name': '⭐ Awarding government agency/office',
        'business_category': '⭐ Procurement category (Construction/Hardware/Materials)',
        'award_date': '⭐ Exact contract award date',
        'award_status': '⭐ Contract status (active/completed/cancelled)'
    }
    
    print("\n📋 Fields that ADD value to MeiliSearch data:\n")
    for field, description in complementary.items():
        print(f"  • {field:25s} - {description}")
    
    print("\n" + "=" * 80)
    print("💎 HIGH-VALUE COMPLEMENTARY FIELDS:")
    print("=" * 80)
    
    print("""
TOP FIELDS TO ADD FROM CSV:

1. ⭐ contract_no
   - Official contract number
   - Essential for procurement tracking
   - Legal reference for audits

2. ⭐ organization_name  
   - Which government office awarded the contract
   - Shows procurement authority

3. ⭐ award_date
   - Exact date contract was awarded
   - Critical for timeline analysis

4. ⭐ award_status
   - active/completed/cancelled/suspended
   - Essential for monitoring

5. ⭐ business_category
   - Construction Projects vs Hardware vs Materials
   - Helps differentiate contract types
""")
    
    # Analyze data statistics
    print("\n" + "=" * 80)
    print("📈 DATA COMPLETENESS ANALYSIS:")
    print("=" * 80)
    
    field_stats = defaultdict(lambda: {'filled': 0, 'empty': 0, 'samples': []})
    
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 1000:  # Sample first 1000 rows
                break
            for field, value in row.items():
                if value and value.strip():
                    field_stats[field]['filled'] += 1
                    if len(field_stats[field]['samples']) < 3:
                        field_stats[field]['samples'].append(value)
                else:
                    field_stats[field]['empty'] += 1
    
    print("\nField completeness (first 1000 rows):\n")
    for field in csv_fields:
        stats = field_stats[field]
        total = stats['filled'] + stats['empty']
        pct = (stats['filled'] / total * 100) if total > 0 else 0
        status = "✅" if pct > 90 else "⚠️" if pct > 50 else "❌"
        print(f"  {status} {field:25s}: {pct:5.1f}% filled ({stats['filled']:4d}/{total:4d})")
        if field in ['contract_no', 'reference_id', 'award_status', 'organization_name', 'business_category']:
            print(f"     Samples: {stats['samples'][:2]}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(main())

