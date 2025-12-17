import json

def filter_contractors():
    with open('unique_contractors.json', 'r', encoding='utf-8') as f:
        contractors = json.load(f)
    
    # Keywords for Elizaldy Co
    keywords = ['SUNWEST', 'FS CO', 'HI-TONE', 'HI TONE']
    
    matches = []
    for c in contractors:
        c_upper = c.upper()
        if any(k in c_upper for k in keywords):
            matches.append(c)
            
    print(f"Found {len(matches)} matches for Elizaldy Co:")
    matches.sort()
    for m in matches:
        print(f'"{m}",')

if __name__ == "__main__":
    filter_contractors()
