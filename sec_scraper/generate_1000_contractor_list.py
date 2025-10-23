#!/usr/bin/env python3
"""
Generate a list of 1000 contractors for AHK script
Prioritizes contractors without SEC data first, then fills with contractors that have SEC data
"""

import json
import os

def main():
    # Read the contractors_top.json file
    contractors_file = '../static/data/contractors_top.json'
    
    if not os.path.exists(contractors_file):
        print(f"❌ Error: {contractors_file} not found")
        return
    
    with open(contractors_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Separate contractors by SEC status
    contractors_without_sec = []
    contractors_with_sec = []
    
    for contractor in data['data']['contractors']:
        if contractor['sec_number'] is None:
            contractors_without_sec.append(contractor)
        else:
            contractors_with_sec.append(contractor)
    
    print(f"📊 Found {len(contractors_without_sec)} contractors without SEC data")
    print(f"📊 Found {len(contractors_with_sec)} contractors with SEC data")
    
    # Combine lists - prioritize those without SEC data
    all_contractors = contractors_without_sec + contractors_with_sec
    
    # Take first 1000 contractors
    target_contractors = all_contractors[:1000]
    
    print(f"🎯 Selected {len(target_contractors)} contractors for AHK script")
    
    # Count how many without SEC data in the final list
    without_sec_count = sum(1 for c in target_contractors if c['sec_number'] is None)
    with_sec_count = len(target_contractors) - without_sec_count
    
    print(f"   - Without SEC data: {without_sec_count}")
    print(f"   - With SEC data: {with_sec_count}")
    
    # Generate AHK format list
    ahk_content = "contractors := [\n"
    
    for i, contractor in enumerate(target_contractors):
        # Escape quotes in contractor names
        escaped_name = contractor['contractor'].replace('"', '""')
        ahk_content += f'    "{escaped_name}"'
        
        # Add comma except for the last item
        if i < len(target_contractors) - 1:
            ahk_content += ","
        
        ahk_content += "\n"
    
    ahk_content += "]\n"
    
    # Write to the AHK contractor list file
    output_file = 'contractor_list_top1000.txt'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(ahk_content)
    
    print(f"✅ Generated {output_file} with {len(target_contractors)} contractors")
    
    # Show first 10 contractors as preview
    print("\n🔍 Preview (first 10 contractors):")
    for i, contractor in enumerate(target_contractors[:10]):
        sec_status = "❌ No SEC" if contractor['sec_number'] is None else "✅ Has SEC"
        print(f"  {i+1}. {contractor['contractor']} ({contractor['count']} projects) {sec_status}")
    
    if len(target_contractors) > 10:
        print(f"  ... and {len(target_contractors) - 10} more")
    
    # Show statistics
    print(f"\n📈 Statistics:")
    print(f"   - Total contractors: {len(target_contractors)}")
    print(f"   - Without SEC data: {without_sec_count} ({without_sec_count/len(target_contractors)*100:.1f}%)")
    print(f"   - With SEC data: {with_sec_count} ({with_sec_count/len(target_contractors)*100:.1f}%)")

if __name__ == "__main__":
    main()

