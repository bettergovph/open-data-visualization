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
        'max_tokens': 16000,
        'messages': [
            {'role': 'system', 'content': 'You are a precise research assistant. Return complete, accurate data from official sources.'},
            {'role': 'user', 'content': prompt}
        ]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=120)
    return response.json()['choices'][0]['message']['content']

prompt = """Please provide the COMPLETE official list of barangays for ALL 6 congressional districts of Quezon City, Philippines.

Quezon City has 142 barangays divided into 6 congressional districts.

For EACH district (1st through 6th), provide:
- District number
- Complete list of ALL barangays in that district

Get data from official sources: PSA, COMELEC, Wikipedia.

Return in this format:
```json
{
  "1st District": ["Barangay 1", "Barangay 2", ...],
  "2nd District": ["Barangay 1", "Barangay 2", ...],
  "3rd District": ["Barangay 1", "Barangay 2", ...],
  "4th District": ["Barangay 1", "Barangay 2", ...],
  "5th District": ["Barangay 1", "Barangay 2", ...],
  "6th District": ["Barangay 1", "Barangay 2", ...]
}
```

Provide ALL barangays for ALL 6 districts now."""

print("📡 Querying Perplexity for ALL Quezon City districts...")
print("This may take a moment...")
print()
response = call_perplexity(prompt)
print(response)

