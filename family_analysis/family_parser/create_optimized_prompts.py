#!/usr/bin/env python3
"""
Create Optimized LLM Prompts Based on Working Template
Uses the proven format from dynasty_relationship_prompt.txt
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

def create_optimized_prompts(names: List[Dict], names_per_prompt: int = 25):
    """Create optimized prompts using the proven format"""
    
    # Shuffle names for variety
    random.shuffle(names)
    
    # Create batches
    batches = []
    for i in range(0, len(names), names_per_prompt):
        batch = names[i:i + names_per_prompt]
        batches.append(batch)
    
    print(f"📊 Creating {len(batches)} optimized prompts with {names_per_prompt} names each")
    
    # Generate prompts for each batch
    for i, batch in enumerate(batches[:50]):  # Limit to 50 batches for now
        prompt = create_single_optimized_prompt(batch, i + 1)
        
        filename = f"optimized_prompt_batch_{i+1:02d}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        print(f"✅ Created {filename}")
    
    return len(batches)

def create_single_optimized_prompt(batch: List[Dict], batch_num: int) -> str:
    """Create a single optimized prompt using the proven format"""
    
    # Group by dynasty for better organization
    dynasty_groups = {}
    for name in batch:
        dynasty = name['dynasty']
        if dynasty not in dynasty_groups:
            dynasty_groups[dynasty] = []
        dynasty_groups[dynasty].append(name)
    
    # Count total names
    total_names = len(batch)
    
    # Create the prompt using the proven format
    prompt = f"""# Political Dynasty Relationship Analysis Prompt

You are a political research analyst specializing in Philippine political dynasties. Your task is to analyze the relationships between the following political figures and return the findings in CSV format.

## Names to Analyze:
"""
    
    # Add names in simple list format (like the working prompt)
    name_list = []
    for name in batch:
        name_list.append(name['full_name'])
    
    # Add names in batches of 10 for readability
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

Analyze all {total_names} names and return the complete relationship matrix in CSV format.
"""
    
    return prompt

def create_top_dynasties_prompt():
    """Create a specialized prompt for top dynasties"""
    
    # Get top dynasties from the working data
    top_dynasties = ["TULFO", "TAN", "MENDOZA", "RODRIGUEZ", "GO", "AQUINO", "MARCOS", "BINAY", "ESTRADA", "REVILLA"]
    
    prompt = f"""# Top Political Dynasties Relationship Analysis

You are a political research analyst specializing in Philippine political dynasties. Your task is to analyze the relationships between members of the top political dynasties in the Philippines and return the findings in CSV format.

## Top Political Dynasties to Focus On:
{', '.join(top_dynasties)}

## Your Task:
1. **Research relationships** within and between these dynasties using web sources to find:
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

Focus on the top political dynasties listed above and return the complete relationship matrix in CSV format.
"""
    
    with open('optimized_prompt_top_dynasties.txt', 'w', encoding='utf-8') as f:
        f.write(prompt)
    
    print("✅ Created optimized_prompt_top_dynasties.txt")

def main():
    """Main function to generate optimized prompts"""
    print("🚀 Creating Optimized LLM Prompts")
    print("=" * 50)
    
    # Read masterlist
    names = read_masterlist()
    print(f"📊 Loaded {len(names)} names from masterlist")
    
    # Create optimized batch prompts (25 names each for better context management)
    num_batches = create_optimized_prompts(names, names_per_prompt=25)
    
    # Create specialized top dynasties prompt
    create_top_dynasties_prompt()
    
    print(f"\n✅ Generated {num_batches + 1} optimized prompt files")
    print("\n📋 Files created:")
    
    # List all generated files
    for i in range(1, min(num_batches + 1, 51)):
        filename = f"optimized_prompt_batch_{i:02d}.txt"
        if os.path.exists(filename):
            print(f"   - {filename}")
    
    if os.path.exists("optimized_prompt_top_dynasties.txt"):
        print(f"   - optimized_prompt_top_dynasties.txt")
    
    print(f"\n🎯 Optimized prompts ready!")
    print("   - 25 names per prompt (better context management)")
    print("   - Uses proven format from working prompt")
    print("   - Focused on manageable batches for LLM analysis")

if __name__ == "__main__":
    main()
