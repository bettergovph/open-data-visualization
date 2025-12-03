#!/usr/bin/env python3
"""Download DO 172 s2016 PDF"""
import requests
from pathlib import Path

url = "https://www.dpwh.gov.ph/dpwh/sites/default/files/issuances/DO_172_s2016.pdf"
output_path = Path(__file__).parent / "DO_172_s2016.pdf"

print(f"Downloading {url}...")
response = requests.get(url, timeout=60)
response.raise_for_status()

with open(output_path, 'wb') as f:
    f.write(response.content)

print(f"✅ Downloaded to {output_path}")
print(f"File size: {len(response.content) / 1024:.2f} KB")











