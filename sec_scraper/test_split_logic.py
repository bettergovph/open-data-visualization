#!/usr/bin/env python3
"""Test the split logic to see what it produces"""

import re
from typing import List, Dict

def extract_former_names(name: str) -> Dict[str, any]:
    """Extract both current and former names from a contractor name
    
    Handles:
    - Complete: "NEW (FORMERLY: OLD)"
    - Incomplete: "NEW (FORMERLY" or "NEW (FORMERLY: OLD" (missing closing paren)
    - No parens: "NEW FORMERLY: OLD"
    """
    result = {
        'current': None,
        'former': []
    }
    
    # Pattern 1: Check for FORMERLY without or with incomplete parentheses
    # Matches: "NAME (FORMERLY..." or "NAME (FORMERLY: ..." or "NAME FORMERLY..."
    formerly_match = re.search(r'^(.+?)\s*\(?\s*\b(FORMERLY|FORMER|PREVIOUSLY|PREV)\b[\s:]*(.*)$', name, re.IGNORECASE)
    
    if formerly_match:
        current = formerly_match.group(1).strip()
        old_name_part = formerly_match.group(3).strip()
        
        # Remove trailing/leading punctuation and closing paren if present
        old_name_part = re.sub(r'^\s*[:;,\s]+', '', old_name_part)
        old_name_part = re.sub(r'\)?\s*$', '', old_name_part).strip()
        
        result['current'] = current
        
        if old_name_part and len(old_name_part) > 10:
            result['former'].append(old_name_part)
        
        return result
    
    # Pattern 2: Normal parentheses (no FORMERLY keyword)
    parentheses_pattern = r'\((.*?)\)'
    matches = re.findall(parentheses_pattern, name)
    
    if matches:
        # Clean the main name (remove parentheses content)
        main_name = re.sub(parentheses_pattern, '', name).strip()
        result['current'] = main_name if main_name and len(main_name) > 3 else name.strip()
    else:
        result['current'] = name.strip()
    
    return result

def split_joint_venture(name: str) -> List[Dict[str, any]]:
    """Split a joint venture contractor name into individual contractors"""
    if not name:
        return []
    
    # First, extract current and former names
    name_data = extract_former_names(name)
    current_name = name_data['current']
    former_names = name_data['former']
    
    individual_contractors = []
    
    # Process current name - only split on /
    if current_name and '/' in current_name:
        parts = current_name.split('/')
        
        for part in parts:
            cleaned = part.strip()
            cleaned = re.sub(r'\b(?:JOINT\s+VENTURE|JV)\b', '', cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned).strip()
            
            if cleaned and len(cleaned) > 10:
                individual_contractors.append({
                    'name': cleaned,
                    'former_names': []
                })
    elif current_name:
        individual_contractors.append({
            'name': current_name,
            'former_names': []
        })
    
    # Process former names as separate entries
    for former_name in former_names:
        individual_contractors.append({
            'name': former_name,
            'former_names': []
        })
    
    return individual_contractors if individual_contractors else [{'name': name.strip(), 'former_names': []}]

# Test cases
test_cases = [
    "TAGUSAO CONSTRUCTION & TRADING INC. (FORMERLY: TAGUSAO CONSTRUCTION & TRADING)",
    "HI-TONE CONSTRUCTION & DEVELOPMENT CORP. (FORMERLY",
    "YURICH BUILDERS AND CONSTRUCTION SUPPLY INC. / SEVEN DIGIT CONSTRUCTION AND TRUCKING SERVICES CORP. (FORMERLY: SEVEN DIGIT CONSTRUCTION & SUPPLIES)",
    "ORANI CONSTRUCTION AND SUPPLY CORPORATION (FORMERLY:ORANI BUILDERS & SUPPLY)",
    "LLABAN CONSTRUCTION & SUPPLY (FORMERLY: LLABAN CON",
]

for test in test_cases:
    print(f"\n{'='*80}")
    print(f"INPUT: {test}")
    print(f"{'='*80}")
    result = split_joint_venture(test)
    print(f"OUTPUT ({len(result)} contractors):")
    for i, contractor in enumerate(result, 1):
        print(f"  {i}. {contractor['name']}")
        if contractor['former_names']:
            print(f"     Former: {contractor['former_names']}")

