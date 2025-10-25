#!/usr/bin/env python3
"""
Create 10 Optimized Prompts with 100 Names Each
Using the proven template format
"""

import random
import os
from typing import List, Dict

def read_masterlist():
    """Read the masterlist of political names"""
    names = []
    with open('masterlist_political_names.txt', 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                parts = line.strip().split(' | ')
                if len(parts) >= 2:
                    names.append({
                        'full_name': parts[0],
                        'dynasty': parts[1],
                        'province': parts[2] if len(parts) > 2 else '',
                        'position': parts[3] if len(parts) > 3 else '',
                        'year': parts[4] if len(parts) > 4 else ''
                    })
    return names

def create_10_prompts_100_names(names: List[Dict]):
    """Create 10 prompts with 100 names each using the proven format"""
    
    # Shuffle names for variety
    random.shuffle(names)
    
    print(f"📊 Creating 10 prompts with 100 names each")
    print(f"📊 Total names to use: 1,000 names")
    
    # Create 10 batches of 100 names each
    for i in range(10):
        start_idx = i * 100
        end_idx = start_idx + 100
        batch = names[start_idx:end_idx]
        
        prompt = create_single_prompt_100_names(batch, i + 1)
        
        filename = f"prompt_100_names_{i+1:02d}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        print(f"✅ Created {filename} ({len(batch)} names)")
    
    return 10

def create_single_prompt_100_names(batch: List[Dict], prompt_num: int) -> str:
    """Create a single prompt with 100 names using the proven format"""
    
    # Create the prompt using the exact proven format
    prompt = f"""# Political Dynasty Relationship Analysis Prompt

You are a political research analyst specializing in Philippine political dynasties. Your task is to analyze the relationships between the following political figures and return the findings in CSV format.

## Names to Analyze:
"""
    
    # Add names in simple list format (exactly like the working prompt)
    name_list = []
    for name in batch:
        name_list.append(name['full_name'])
    
    # Add names in batches of 10 for readability (like the working prompt)
    for i in range(0, len(name_list), 10):
        batch_names = name_list[i:i+10]
        prompt += "\n".join(batch_names) + "\n"
    
    prompt += f"""
## Your Task:
1. **Research each name** using web sources to find:
   - Family relationships (parent-child, siblings, spouses)
   - Political connections and alliances
   - Marriage connections between dynasties
   - Succession patterns within families
   - Cross-dynasty relationships

2. **Return results in CSV format** with these columns:
   - person1_name
   - person2_name  
   - relationship_type
   - relationship_description
   - dynasty1
   - dynasty2
   - source_url
   - confidence_level (1-10)

## Relationship Types to Identify:
- Father/Mother
- Son/Daughter
- Husband/Wife
- Brother/Sister
- Uncle/Aunt
- Nephew/Niece
- Cousin
- Grandfather/Grandmother
- Grandson/Granddaughter
- Father-in-law/Mother-in-law
- Son-in-law/Daughter-in-law
- Political Ally
- Business Partner
- Successor/Predecessor

## Instructions:
1. Use web sources to verify relationships
2. Focus on documented, verifiable connections
3. Include source URLs for verification
4. Rate confidence level (1=low, 10=high)
5. Identify both intra-dynasty and inter-dynasty relationships
6. Look for marriage alliances between dynasties
7. Document political succession patterns

## Output Format:
Return a CSV with the exact column headers specified above. Include a header row and ensure all fields are properly quoted if they contain commas.

## Example Output:
```csv
person1_name,person2_name,relationship_type,relationship_description,dynasty1,dynasty2,source_url,confidence_level
"BEN BITAG TULFO","ERWIN TULFO","Brother","Siblings in TULFO dynasty","TULFO","TULFO","https://example.com",9
"STEPHANY TAN","STEPHEN JAMES TAN","Husband","Married couple","TAN","TAN","https://example.com",8
```

Analyze all 100 names and return the complete relationship matrix in CSV format.
"""
    
    return prompt

def main():
    """Main function to generate 10 prompts with 100 names each"""
    print("🚀 Creating 10 Prompts with 100 Names Each")
    print("=" * 60)
    
    # Read masterlist
    names = read_masterlist()
    print(f"📊 Loaded {len(names)} names from masterlist")
    
    # Create 10 prompts with 100 names each
    num_prompts = create_10_prompts_100_names(names)
    
    print(f"\n✅ Generated {num_prompts} prompt files")
    print("\n📋 Files created:")
    
    # List all generated files
    for i in range(1, 11):
        filename = f"prompt_100_names_{i:02d}.txt"
        if os.path.exists(filename):
            print(f"   - {filename}")
    
    print(f"\n🎯 10 prompts ready!")
    print("   - 100 names per prompt")
    print("   - Uses proven format from working template")
    print("   - Total coverage: 1,000 names")
    print("   - Perfect for LLM context management")

if __name__ == "__main__":
    main()
