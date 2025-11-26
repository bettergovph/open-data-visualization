import json
from pathlib import Path

def check_counts():
    path = Path('/home/joebert/open-data-visualization/static/data/budget_amendments_2026.json')
    if not path.exists():
        print(f"File not found: {path}")
        return

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        projects = data.get('projects', [])
        count = len(projects)
        print(f"File: {path.name}")
        print(f"Total Projects: {count}")
        
        # Group by source_sheet
        from collections import Counter
        sheets = Counter(p.get('source_sheet', 'Unknown') for p in projects)
        print("\nCounts by Source Sheet:")
        for sheet, count in sheets.items():
            print(f"- {sheet}: {count}")
            
        # Check if we can find the 17,179 subset
        # Maybe it's everything EXCEPT Annex A-1?
        non_annex_a1 = [p for p in projects if p.get('source_sheet') != 'Annex A-1']
        print(f"\nNon-Annex A-1 Projects: {len(non_annex_a1)}")
        
        amounts = [p.get('final_amount') or p.get('original_amount') or 0 for p in non_annex_a1]
        amounts = [a for a in amounts if a > 0]
        print(f"Non-Annex A-1 Unique Amounts: {len(set(amounts))}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_counts()
