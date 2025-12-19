
import duckdb
import time
import os

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

def test_speed():
    parquet_path = "static/data/parquet/transparency_projects.parquet"
    if not os.path.exists(parquet_path):
        print("Parquet not found")
        return

    print("Loading transparency...")
    t0 = time.time()
    con = duckdb.connect()
    t_rows = con.execute(f"SELECT contract_id, project_name, amount FROM read_parquet('{parquet_path}') WHERE project_name IS NOT NULL").fetchall()
    con.close()
    t1 = time.time()
    print(f"Loaded {len(t_rows)} rows in {t1-t0:.2f}s")
    
    transparency_projects_cache = []
    print("Tokenizing...")
    for row in t_rows:
        cid, pname, pamount = row
        norm = normalize_for_match(pname)
        tokens = set([t for t in norm.split() if len(t) > 2 and t not in STOPWORDS])
        transparency_projects_cache.append({
            'id': cid,
            'name': pname,
            'amount': pamount,
            'tokens': tokens
        })
    t2 = time.time()
    print(f"Tokenized in {t2-t1:.2f}s")
    
    print("Indexing...")
    transparency_index = {}
    for idx, item in enumerate(transparency_projects_cache):
        for token in item['tokens']:
            if token not in transparency_index:
                transparency_index[token] = []
            transparency_index[token].append(idx)
    t3 = time.time()
    print(f"Indexed in {t3-t2:.2f}s")
    
    print("Matching test...")
    test_name = "Construction (Completion) of Multi-Purpose Building, Navotas Polytechnic College (NPC) Building, Navotas City"
    name_norm = normalize_for_match(test_name)
    name_tokens = set([t for t in name_norm.split() if len(t) > 2 and t not in STOPWORDS])
    print(f"Test Tokens: {name_tokens}")
    
    candidate_counts = {}
    for token in name_tokens:
        if token in transparency_index:
            for idx in transparency_index[token]:
                candidate_counts[idx] = candidate_counts.get(idx, 0) + 1
    
    matches = []
    for idx, count in candidate_counts.items():
        if count >= 3:
             matches.append(transparency_projects_cache[idx]['name'])
    
    print(f"Found {len(matches)} matches: {matches[:3]}")
    t4 = time.time()
    print(f"Match time: {t4-t3:.4f}s")

if __name__ == "__main__":
    test_speed()
