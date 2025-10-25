#!/usr/bin/env python3
"""
Create Optimal Number of Prompts Based on Context Size
Calculate if 50 or 100 names fit better in LLM context
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

def calculate_optimal_prompts():
    """Calculate optimal number of prompts based on context size"""
    
    # Test with 50 names first
    test_names = ["TEST NAME"] * 50
    
    # Create test prompt with 50 names
    test_prompt_50 = create_test_prompt(test_names, 50)
    size_50 = len(test_prompt_50.encode('utf-8'))
    
    # Create test prompt with 100 names  
    test_names_100 = ["TEST NAME"] * 100
    test_prompt_100 = create_test_prompt(test_names_100, 100)
    size_100 = len(test_prompt_100.encode('utf-8'))
    
    print(f"📊 Context Size Analysis:")
    print(f"   50 names: {size_50:,} bytes")
    print(f"   100 names: {size_100:,} bytes")
    
    # Assume LLM context limit is around 4K tokens = ~16,000 characters
    # Conservative estimate: 12,000 characters for safety
    context_limit = 12000
    
    if size_50 <= context_limit:
        print(f"✅ 50 names fit comfortably in context ({size_50:,} < {context_limit:,})")
        return 50, 20  # 50 names per prompt, 20 prompts for 1000 names
    elif size_100 <= context_limit:
        print(f"✅ 100 names fit in context ({size_100:,} < {context_limit:,})")
        return 100, 10  # 100 names per prompt, 10 prompts for 1000 names
    else:
        print(f"⚠️  Both sizes exceed context limit")
        print(f"   Using 25 names per prompt for safety")
        return 25, 40  # 25 names per prompt, 40 prompts for 1000 names

def create_test_prompt(names: List[str], num_names: int) -> str:
    """Create a test prompt to measure size"""
    
    prompt = f"""# Political Dynasty Relationship Analysis Prompt

You are a political research analyst specializing in Philippine political dynasties. Your task is to analyze the relationships between the following political figures and return the findings in CSV format.

## Names to Analyze:
"""
    
    # Add names in batches of 10
    for i in range(0, len(names), 10):
        batch_names = names[i:i+10]
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

Analyze all {num_names} names and return the complete relationship matrix in CSV format.
"""
    
    return prompt

def create_optimal_prompts(names: List[Dict], names_per_prompt: int, num_prompts: int):
    """Create optimal number of prompts"""
    
    # Shuffle names for variety
    random.shuffle(names)
    
    print(f"📊 Creating {num_prompts} prompts with {names_per_prompt} names each")
    print(f"📊 Total names to use: {num_prompts * names_per_prompt} names")
    
    # Create prompts
    for i in range(num_prompts):
        start_idx = i * names_per_prompt
        end_idx = start_idx + names_per_prompt
        batch = names[start_idx:end_idx]
        
        prompt = create_single_prompt(batch, i + 1, names_per_prompt)
        
        filename = f"optimal_prompt_{i+1:02d}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        print(f"✅ Created {filename} ({len(batch)} names)")
    
    return num_prompts

def create_single_prompt(batch: List[Dict], prompt_num: int, names_per_prompt: int) -> str:
    """Create a single prompt using the proven format"""
    
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

Analyze all {names_per_prompt} names and return the complete relationship matrix in CSV format.
"""
    
    return prompt

def main():
    """Main function to create optimal prompts"""
    print("🚀 Creating Optimal LLM Prompts Based on Context Size")
    print("=" * 70)
    
    # Read masterlist
    names = read_masterlist()
    print(f"📊 Loaded {len(names)} names from masterlist")
    
    # Calculate optimal configuration
    names_per_prompt, num_prompts = calculate_optimal_prompts()
    
    # Create optimal prompts
    actual_prompts = create_optimal_prompts(names, names_per_prompt, num_prompts)
    
    print(f"\n✅ Generated {actual_prompts} optimal prompt files")
    print("\n📋 Files created:")
    
    # List all generated files
    for i in range(1, actual_prompts + 1):
        filename = f"optimal_prompt_{i:02d}.txt"
        if os.path.exists(filename):
            print(f"   - {filename}")
    
    print(f"\n🎯 Optimal prompts ready!")
    print(f"   - {names_per_prompt} names per prompt")
    print(f"   - {actual_prompts} total prompts")
    print(f"   - Uses proven format from working template")
    print(f"   - Perfect for LLM context management")

if __name__ == "__main__":
    main()
