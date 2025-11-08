#!/usr/bin/env python3
import os
import requests
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

def call_perplexity(prompt):
    api_key = os.getenv('PERPLEXITY_API_KEY')
    url = 'https://api.perplexity.ai/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'sonar-pro',
        'temperature': 0.0,
        'max_tokens': 8000,
        'messages': [
            {'role': 'system', 'content': 'You are a precise research assistant. Return complete, accurate data from official sources.'},
            {'role': 'user', 'content': prompt}
        ]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    return response.json()['choices'][0]['message']['content']

# Query for Districts 2, 3, 5, 6
for district_num in ['2nd', '3rd', '5th', '6th']:
    prompt = f"""Please provide the COMPLETE official list of barangays for Quezon City {district_num} District, Philippines.

Known distribution:
- 1st District: 37 barangays
- 2nd District: 5 barangays
- 3rd District: 37 barangays
- 4th District: 38 barangays
- 5th District: 14 barangays
- 6th District: 11 barangays

Get the complete list for {district_num} District from PSA, COMELEC, or Wikipedia.

Return ONLY a JSON array:
```json
["Barangay 1", "Barangay 2", ...]
```"""
    
    print(f"📡 Querying for Quezon City {district_num} District...")
    response = call_perplexity(prompt)
    print(f"\n{district_num.upper()} DISTRICT:")
    print("=" * 80)
    print(response)
    print("\n")

