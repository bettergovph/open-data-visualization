#!/usr/bin/env python3
"""Get barangay data for lone district cities batch 1"""
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

cities = [
    'Biñan',
    'Las Piñas',
    'Malabon',
    'Mandaluyong',
    'Muntinlupa',
    'Navotas',
    'Pasay',
    'Pasig',
    'San Juan'
]

for city in cities:
    prompt = f"""Please provide the COMPLETE official list of barangays for {city} City (Lone District), Philippines.

Get data from official sources: PSA, COMELEC, Wikipedia.

Return ONLY a JSON array:
```json
["Barangay 1", "Barangay 2", ...]
```"""
    
    print(f"📡 Querying for {city}...")
    response = call_perplexity(prompt)
    print(f"\n{city.upper()}:")
    print("=" * 80)
    print(response)
    print("\n")

