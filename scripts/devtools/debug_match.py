
import duckdb

con = duckdb.connect()
print("Checking Transparency Project 22OA0084:")
res = con.execute("SELECT contract_id, project_name, amount FROM 'static/data/parquet/transparency_projects.parquet' WHERE contract_id = '22OA0084'").fetchall()
print(res)

print("\nChecking Tokens:")
STOPWORDS = {
    "construction", "completion", "rehabilitation", "improvement", "repair", "maintenance", 
    "upgrading", "widening", "concreting", "asphalt", "overlay", "reblocking", "building", 
    "multi-purpose", "multipurpose", "school", "classroom", "infra", "infrastructure",
    "project", "program", "phase", "package", "contract", "id", "no", "of", "the", "in", 
    "and", "to", "with", "at", "city", "province", "municipality", "barangay", "district",
    "st.", "ave.", "rd.", "ext.", "brgy", "poblacion", "water", "system", "flood", "control"
}

def normalize_for_match(text):
    if not text: return ""
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = text.lower().strip()
    text = text.replace("city of ", "").replace("municipality of ", "")
    return text

if res:
    name = res[0][1]
    norm = normalize_for_match(name)
    tokens = set([t for t in norm.split() if len(t) > 2 and t not in STOPWORDS])
    print(f"Name: {name}")
    print(f"Restricted Tokens: {tokens}")
    
    target = "Construction (Completion) of Multi-Purpose Building, Navotas Polytechnic College (NPC) Building, Navotas City"
    t_norm = normalize_for_match(target)
    t_tokens = set([t for t in t_norm.split() if len(t) > 2 and t not in STOPWORDS])
    print(f"\nTarget Name: {target}")
    print(f"Target Tokens: {t_tokens}")
    
    common = tokens.intersection(t_tokens)
    print(f"\nCommon: {common}")
    print(f"Count: {len(common)}")
