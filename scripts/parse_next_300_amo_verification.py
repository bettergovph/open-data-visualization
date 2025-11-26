#!/usr/bin/env python3
"""
Parse Perplexity verification results for next 300 AMOs and identify matches.
"""

import re
import json
from pathlib import Path
from typing import List, Dict, Optional

def parse_batch_file(file_path: Path) -> List[Dict]:
    """Parse a single batch verification file and extract AMO information"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract AMO list from the file
    amo_section = re.search(r'AMOs in this batch:(.*?)={80}', content, re.DOTALL)
    if not amo_section:
        return []
    
    amo_lines = amo_section.group(1).strip().split('\n')
    
    # Extract verification results
    results_section = re.search(r'PERPLEXITY VERIFICATION RESULTS(.*?)$', content, re.DOTALL)
    if not results_section:
        return []
    
    results_text = results_section.group(1).strip()
    
    # Parse each AMO result
    amo_results = []
    current_amo = None
    
    # Split by numbered entries
    entries = re.split(r'^\d+\.\s+\*\*', results_text, flags=re.MULTILINE)
    
    for entry in entries[1:]:  # Skip first empty entry
        lines = entry.strip().split('\n')
        if not lines:
            continue
        
        # Extract name (first line)
        name_match = re.match(r'([^*]+)\*\*', lines[0])
        if not name_match:
            continue
        
        name = name_match.group(1).strip()
        
        # Parse details
        position = None
        location = None
        year_term = None
        status = None
        family_relationships = []
        
        for line in lines[1:]:
            line = line.strip()
            if line.startswith('- Position:'):
                position = line.replace('- Position:', '').strip()
            elif line.startswith('- Location:'):
                location = line.replace('- Location:', '').strip()
            elif line.startswith('- Year/Term:'):
                year_term = line.replace('- Year/Term:', '').strip()
            elif line.startswith('- Status:'):
                status = line.replace('- Status:', '').strip()
            elif line.startswith('- Family relationships:'):
                rel_text = line.replace('- Family relationships:', '').strip()
                if rel_text and 'No information' not in rel_text:
                    # Parse relationship
                    # Format: "Related to [Name] ([Position], [Year]) as [Relationship]"
                    rel_match = re.search(r'Related to ([^(]+) \(([^)]+)\) as (.+)', rel_text)
                    if rel_match:
                        family_relationships.append({
                            'related_name': rel_match.group(1).strip(),
                            'related_position': rel_match.group(2).strip(),
                            'relationship_type': rel_match.group(3).strip()
                        })
        
        # Determine if this is a match
        is_elected = position and 'Not an elected official' not in position
        has_relationships = len(family_relationships) > 0
        
        if is_elected or has_relationships:
            amo_results.append({
                'name': name,
                'position': position,
                'location': location,
                'year_term': year_term,
                'status': status,
                'is_elected': is_elected,
                'family_relationships': family_relationships,
                'has_relationships': has_relationships
            })
    
    return amo_results


def main():
    """Main function to parse all verification results"""
    verification_dir = Path('analysis/amo_verification_results/next_300_verification')
    
    if not verification_dir.exists():
        print(f"❌ Verification directory not found: {verification_dir}")
        return
    
    # Find all batch files
    batch_files = sorted(verification_dir.glob('batch_*.txt'))
    
    print("=" * 80)
    print("PARSING NEXT 300 AMO VERIFICATION RESULTS")
    print("=" * 80)
    print(f"Found {len(batch_files)} batch files\n")
    
    all_matches = []
    elected_matches = []
    relationship_matches = []
    
    for batch_file in batch_files:
        print(f"📋 Parsing {batch_file.name}...")
        results = parse_batch_file(batch_file)
        
        for result in results:
            all_matches.append(result)
            if result['is_elected']:
                elected_matches.append(result)
            if result['has_relationships']:
                relationship_matches.append(result)
    
    print(f"\n✅ Parsing complete!")
    print(f"   Total matches found: {len(all_matches)}")
    print(f"   Elected officials: {len(elected_matches)}")
    print(f"   With family relationships: {len(relationship_matches)}")
    
    # Save results
    output_file = verification_dir / 'parsed_matches.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_matches': len(all_matches),
            'elected_count': len(elected_matches),
            'relationship_count': len(relationship_matches),
            'elected_matches': elected_matches,
            'relationship_matches': relationship_matches,
            'all_matches': all_matches
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("ELECTED OFFICIALS FOUND:")
    print("=" * 80)
    for match in elected_matches[:10]:
        print(f"\n{match['name']}")
        print(f"  Position: {match['position']}")
        print(f"  Location: {match['location']}")
        print(f"  Status: {match['status']}")
        if match['family_relationships']:
            rel_strs = [f"{r['relationship_type']} of {r['related_name']}" for r in match['family_relationships']]
            print(f"  Family: {', '.join(rel_strs)}")
    
    if len(elected_matches) > 10:
        print(f"\n... and {len(elected_matches) - 10} more")
    
    print("\n" + "=" * 80)
    print("FAMILY RELATIONSHIPS FOUND:")
    print("=" * 80)
    for match in relationship_matches[:10]:
        if not match['is_elected']:
            print(f"\n{match['name']}")
            for rel in match['family_relationships']:
                print(f"  {rel['relationship_type']} of {rel['related_name']} ({rel['related_position']})")
    
    if len(relationship_matches) > 10:
        print(f"\n... and {len(relationship_matches) - 10} more")


if __name__ == '__main__':
    main()

