#!/usr/bin/env python3
"""
Generate Multiple Focused Prompts for Web-Based LLM Analysis
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

def create_focused_prompts(names: List[Dict], batch_size: int = 50):
    """Create multiple focused prompts for different batches of names"""
    
    # Shuffle names for variety
    random.shuffle(names)
    
    # Create batches
    batches = []
    for i in range(0, len(names), batch_size):
        batch = names[i:i + batch_size]
        batches.append(batch)
    
    print(f"📊 Created {len(batches)} batches of {batch_size} names each")
    
    # Generate prompts for each batch
    for i, batch in enumerate(batches[:20]):  # Limit to 20 batches
        prompt = create_single_prompt(batch, i + 1)
        
        filename = f"llm_prompt_batch_{i+1:02d}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        print(f"✅ Created {filename}")
    
    return len(batches)

def create_single_prompt(batch: List[Dict], batch_num: int) -> str:
    """Create a single focused prompt for a batch of names"""
    
    # Group by dynasty for better organization
    dynasty_groups = {}
    for name in batch:
        dynasty = name['dynasty']
        if dynasty not in dynasty_groups:
            dynasty_groups[dynasty] = []
        dynasty_groups[dynasty].append(name)
    
    # Create the prompt
    prompt = f"""# Political Dynasty Relationship Analysis - Batch {batch_num}

You are a political research analyst specializing in Philippine political dynasties. Your task is to analyze the relationships between the following political figures and return findings in CSV format.

## ANALYSIS INSTRUCTIONS

1. **Research each name** using web sources to find:
   - Family relationships (parent-child, siblings, spouses)
   - Political connections and alliances
   - Marriage connections between dynasties
   - Succession patterns within families
   - Cross-dynasty relationships

2. **Return results in CSV format** with these EXACT columns:
   - person1_name
   - person2_name  
   - relationship_type
   - relationship_description
   - dynasty1
   - dynasty2
   - source_url
   - confidence_level

## RELATIONSHIP TYPES TO IDENTIFY:
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

## NAMES TO ANALYZE (Grouped by Dynasty):

"""
    
    # Add names grouped by dynasty
    for dynasty, dynasty_names in sorted(dynasty_groups.items()):
        prompt += f"\n### {dynasty} Dynasty ({len(dynasty_names)} members):\n"
        for name in dynasty_names:
            prompt += f"- {name['full_name']}"
            if name['province']:
                prompt += f" ({name['province']})"
            if name['position']:
                prompt += f" - {name['position']}"
            prompt += "\n"
    
    prompt += f"""
## OUTPUT REQUIREMENTS:

1. **CSV Format**: Return ONLY the CSV data with the exact column headers specified
2. **Source URLs**: Include working URLs for verification
3. **Confidence Level**: Rate 1-10 (10 = highest confidence)
4. **Focus on**: Documented, verifiable relationships only
5. **Include**: Both intra-dynasty and inter-dynasty relationships

## EXAMPLE OUTPUT:
```csv
person1_name,person2_name,relationship_type,relationship_description,dynasty1,dynasty2,source_url,confidence_level
"JOHN DOE","JANE DOE","Husband","Married couple in politics","DOE","DOE","https://example.com",9
```

Analyze all {len(batch)} names above and return the complete relationship matrix in CSV format.
"""
    
    return prompt

def create_specialized_prompts():
    """Create specialized prompts for different types of analysis"""
    
    specialized_prompts = {
        "top_dynasties": {
            "title": "Top Political Dynasties Analysis",
            "description": "Focus on the largest and most influential political dynasties",
            "dynasties": ["TAN", "TULFO", "MENDOZA", "RODRIGUEZ", "GO", "AQUINO", "MARCOS", "BINAY"]
        },
        "cross_dynasty": {
            "title": "Cross-Dynasty Marriage Alliances",
            "description": "Focus on marriage connections between different political families",
            "dynasties": ["TAN", "UY", "GARCIA", "LIM", "RAMOS", "VILLANUEVA"]
        },
        "provincial_power": {
            "title": "Provincial Political Power Analysis", 
            "description": "Focus on families controlling specific provinces",
            "dynasties": ["AQUINO", "MARCOS", "BINAY", "ESTRADA", "REVILLA"]
        }
    }
    
    for prompt_type, config in specialized_prompts.items():
        prompt = f"""# {config['title']}

{config['description']}

## FOCUS AREAS:
- {config['description']}
- Key dynasties: {', '.join(config['dynasties'])}
- Marriage alliances between families
- Political succession patterns
- Cross-provincial connections

## ANALYSIS INSTRUCTIONS:
1. Research relationships within and between these dynasties
2. Focus on documented political marriages and alliances
3. Identify succession patterns and family political strategies
4. Return results in CSV format with source URLs

## CSV FORMAT:
person1_name,person2_name,relationship_type,relationship_description,dynasty1,dynasty2,source_url,confidence_level

Analyze the relationships and return findings in CSV format.
"""
        
        filename = f"llm_prompt_{prompt_type}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        print(f"✅ Created specialized prompt: {filename}")

def main():
    """Main function to generate all prompts"""
    print("🚀 Generating LLM Prompts for Political Dynasty Analysis")
    print("=" * 60)
    
    # Read masterlist
    names = read_masterlist()
    print(f"📊 Loaded {len(names)} names from masterlist")
    
    # Create focused batch prompts
    num_batches = create_focused_prompts(names, batch_size=50)
    
    # Create specialized prompts
    create_specialized_prompts()
    
    print(f"\n✅ Generated {num_batches + 3} prompt files total")
    print("\n📋 Files created:")
    
    # List all generated files
    for i in range(1, num_batches + 1):
        filename = f"llm_prompt_batch_{i:02d}.txt"
        if os.path.exists(filename):
            print(f"   - {filename}")
    
    specialized_files = [
        "llm_prompt_top_dynasties.txt",
        "llm_prompt_cross_dynasty.txt", 
        "llm_prompt_provincial_power.txt"
    ]
    
    for filename in specialized_files:
        if os.path.exists(filename):
            print(f"   - {filename}")
    
    print(f"\n🎯 Ready to feed these prompts to web-focused LLMs!")
    print("   Each prompt contains 50 names for focused analysis")
    print("   Return the CSV results and we'll parse them into the database")

if __name__ == "__main__":
    main()
