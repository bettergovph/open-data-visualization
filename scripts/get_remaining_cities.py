#!/usr/bin/env python3
"""Get barangay data for remaining cities"""
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

# Cities with multiple districts
cities_multi = [
    ('Antipolo', '1st District'),
    ('Cebu City', '1st District'),
    ('Cebu City', '2nd District'),
    ('Makati', '1st District'),
    ('Makati', '2nd District'),
    ('Parañaque', '1st District'),
    ('Parañaque', '2nd District'),
    ('Valenzuela', '1st District'),
    ('Valenzuela', '2nd District'),
    ('Zamboanga City', '1st District'),
    ('Zamboanga City', '2nd District'),
]

# Single districts
cities_single = [
    ('Marikina', '2nd District'),
    ('Taguig–Pateros', '2nd District'),
    ('Cagayan de Oro', '2nd District'),
]

print("=" * 80)
print("MULTI-DISTRICT CITIES")
print("=" * 80)

for city, district in cities_multi:
    prompt = f"""Please provide the COMPLETE official list of barangays for {city} {district}, Philippines.

Get data from official sources: PSA, COMELEC, Wikipedia.

Return ONLY a JSON array:
```json
["Barangay 1", "Barangay 2", ...]
```"""
    
    print(f"\n📡 Querying for {city} {district}...")
    response = call_perplexity(prompt)
    print(f"\n{city.upper()} {district.upper()}:")
    print("=" * 80)
    print(response)
    print()

print("\n" + "=" * 80)
print("SINGLE DISTRICTS")
print("=" * 80)

for city, district in cities_single:
    prompt = f"""Please provide the COMPLETE official list of barangays for {city} {district}, Philippines.

Get data from official sources: PSA, COMELEC, Wikipedia.

Return ONLY a JSON array:
```json
["Barangay 1", "Barangay 2", ...]
```"""
    
    print(f"\n📡 Querying for {city} {district}...")
    response = call_perplexity(prompt)
    print(f"\n{city.upper()} {district.upper()}:")
    print("=" * 80)
    print(response)
    print()










