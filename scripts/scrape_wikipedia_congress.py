#!/usr/bin/env python3
"""
Scrape Wikipedia 20th Congress of the Philippines to get House of Representatives list
"""
import requests
from bs4 import BeautifulSoup
import json
import re

def scrape_congress():
    url = 'https://en.wikipedia.org/wiki/20th_Congress_of_the_Philippines'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the House of Representatives section
    congress_data = []
    
    # Find all tables with class 'wikitable'
    tables = soup.find_all('table', class_='wikitable')
    
    for table in tables:
        # Check if this looks like a representative table
        headers = table.find_all('th')
        header_text = ' '.join([h.get_text().strip() for h in headers])
        
        # Look for tables with District or Representative in headers
        if 'District' in header_text or 'Representative' in header_text or 'Member' in header_text:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    cell_texts = [c.get_text().strip() for c in cells]
                    # Extract links for representative names
                    links = row.find_all('a')
                    link_texts = [a.get_text().strip() for a in links if a.get_text().strip()]
                    
                    # Look for district patterns
                    district_match = None
                    for text in cell_texts:
                        if '1st' in text or '2nd' in text or '3rd' in text or 'th' in text or 'District' in text:
                            district_match = text
                            break
                    
                    if district_match or link_texts:
                        congress_data.append({
                            'cells': cell_texts,
                            'links': link_texts
                        })
    
    # Build structured output
    structured_data = []
    current_province = None
    
    for entry in congress_data[1:]:  # Skip header row
        cells = entry['cells']
        if len(cells) >= 3:
            # First column might be province or empty (continuation)
            if cells[0] and cells[0] not in ['', '1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', 'Lone']:
                current_province = cells[0]
            
            # Get district and representative
            if cells[0] in ['1st', '2nd', '3rd', '4th', '5th', '6th', '7th', '8th', 'Lone']:
                district = cells[0]
                representative = cells[1] if len(cells) > 1 else ''
            else:
                district = cells[1] if len(cells) > 1 else ''
                representative = cells[2] if len(cells) > 2 else ''
            
            if current_province and representative:
                structured_data.append({
                    'province': current_province,
                    'district': district,
                    'representative': representative.replace('[a]', '').replace('[b]', '').replace('[c]', '').replace('[d]', '').strip(),
                    'party': cells[3] if len(cells) > 3 else ''
                })
    
    # Save to JSON
    output_path = 'static/data/20th_congress_representatives.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(structured_data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(structured_data)} representatives to {output_path}")
    
    # Show sample
    for item in structured_data[:20]:
        print(f"{item['province']} {item['district']}: {item['representative']}")
    
    return structured_data

if __name__ == '__main__':
    scrape_congress()
