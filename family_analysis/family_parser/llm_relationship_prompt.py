#!/usr/bin/env python3
"""
LLM Prompt for Finding Political Dynasty Relationships
"""

def create_llm_prompt():
    """Create a comprehensive prompt for LLM to find relationships"""
    
    # Read the names from file
    with open('top5_dynasty_names.txt', 'r') as f:
        names = [line.strip() for line in f.readlines() if line.strip()]
    
    prompt = f"""
# Political Dynasty Relationship Analysis Prompt

You are a political research analyst specializing in Philippine political dynasties. Your task is to analyze the relationships between members of the top 5 political dynasties in the Philippines and return the findings in CSV format.

## Top 5 Political Dynasties Analyzed:
1. **TULFO Dynasty** - 4,054 members
2. **TAN Dynasty** - 4,013 members  
3. **MENDOZA Dynasty** - 2,910 members
4. **RODRIGUEZ Dynasty** - 2,674 members
5. **GO Dynasty** - 2,389 members

## Names to Analyze:
{chr(10).join(names[:50])}  # Show first 50 names
... and {len(names)-50} more names

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

Analyze all {len(names)} names and return the complete relationship matrix in CSV format.
"""
    
    return prompt

def save_prompt():
    """Save the prompt to a file"""
    prompt = create_llm_prompt()
    
    with open('dynasty_relationship_prompt.txt', 'w') as f:
        f.write(prompt)
    
    print("✅ LLM prompt saved to dynasty_relationship_prompt.txt")
    print(f"📊 Prompt includes {len(open('top5_dynasty_names.txt').readlines())} names to analyze")

if __name__ == "__main__":
    save_prompt()
