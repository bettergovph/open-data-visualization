#!/usr/bin/env python3
import os
import re
import json
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

# Get 2nd District
prompt_2nd = """Please provide the COMPLETE official list of barangays for Davao City 2nd Congressional District.

Davao City has 182 barangays total. The 1st District has 54 barangays (Poblacion + Talomo).

Get the complete list for the 2nd District from PSA, COMELEC, or Wikipedia.
Return ONLY a JSON array of barangay names:
```json
["Barangay 1", "Barangay 2", ...]
```"""

print("📡 Querying Perplexity for Davao City 2nd District...")
response_2nd = call_perplexity(prompt_2nd)
print("\n2ND DISTRICT RESPONSE:")
print("=" * 80)
print(response_2nd)
print()

# Get 3rd District  
prompt_3rd = """Please provide the COMPLETE official list of barangays for Davao City 3rd Congressional District.

Davao City has 182 barangays total. The 1st District has 54 barangays (Poblacion + Talomo).

Get the complete list for the 3rd District from PSA, COMELEC, or Wikipedia.
Return ONLY a JSON array of barangay names:
```json
["Barangay 1", "Barangay 2", ...]
```"""

print("📡 Querying Perplexity for Davao City 3rd District...")
response_3rd = call_perplexity(prompt_3rd)
print("\n3RD DISTRICT RESPONSE:")
print("=" * 80)
print(response_3rd)

