
import json
import duckdb
import re
import unicodedata
from collections import Counter

# --- Configuration ---
SAMPLE_SIZE = 100
RESURRECTED_PATH = "static/data/resurrected_projects_dpwh_enriched.json"
TRANSPARENCY_PATH = "static/data/parquet/transparency_projects.parquet"

STOPWORDS = {
    "construction", "completion", "rehabilitation", "improvement", "repair", "maintenance", 
    "upgrading", "widening", "concreting", "asphalt", "overlay", "reblocking", "building", 
    "multi-purpose", "multipurpose", "school", "classroom", "infra", "infrastructure",
    "project", "program", "phase", "package", "contract", "id", "no", "of", "the", "in", 
    "and", "to", "with", "at", "city", "province", "municipality", "barangay", "district",
    "st.", "ave.", "rd.", "ext.", "brgy", "poblacion", "water", "system", "flood", "control",
    "national", "road", "primary", "secondary", "tertiary", "bridge", "structure"
}

def normalize_and_tokenize(text):
    if not text: return set()
    # Normalize unicode
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = text.lower()
    
    # 1. Handle Parentheticals: remove content inside parens if it looks like "noise" (e.g. (completion))?
    # User said: "they intentionally add (words) to make you not match things"
    # Strategy: Replace parens with spaces to separate words, but KEEP words?
    # OR: Remove them? "Construction (Completion)" -> "Construction" vs "Construction Completion"
    # Let's clean the punctuation but keep the words for now, as they might be meaningful in some contexts.
    # BUT user said "make you NOT match", implying they are differences.
    # Let's try replacing all punctuation with spaces.
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Split by whitespace
    tokens = text.split()
    # Filter
    valid_tokens = []
    for t in tokens:
        if len(t) > 2 and t not in STOPWORDS:
            valid_tokens.append(t)
    return set(valid_tokens)

def main():
    print(f"--- Debugging Matching Logic (Sample: {SAMPLE_SIZE}) ---")
    
    # 1. Load Source Projects (Resurrected/integrity items)
    print("Loading Source Projects...")
    with open(RESURRECTED_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        matches = data.get('matches', [])
    
    # Extract names from 2026 data
    source_projects = []
    for m in matches:
        item = m.get('year_2026', {})
        name = item.get('name')
        pid = item.get('id')
        if name:
            source_projects.append({'id': pid, 'name': name})
    
    # Pick a sample: specifically include Navotas if present, plus randoms
    target_navotas = "Construction (Completion) of Multi-Purpose Building, Navotas Polytechnic College (NPC) Building, Navotas City"
    
    sample = [p for p in source_projects if target_navotas in p['name']]
    remaining = [p for p in source_projects if target_navotas not in p['name']]
    sample.extend(remaining[:SAMPLE_SIZE - len(sample)])
    
    print(f"Sample contains {len(sample)} projects.")
    
    # 2. Load Transparency Data
    print("Loading Transparency Data...")
    con = duckdb.connect()
    # Loading into memory for speed in debug
    t_rows = con.execute(f"SELECT contract_id, project_name, amount FROM read_parquet('{TRANSPARENCY_PATH}') WHERE project_name IS NOT NULL").fetchall()
    con.close()
    
    print(f"Loaded {len(t_rows)} Transparency rows.")
    
    # 3. Build Index
    print("Building Index...")
    transparency_docs = []
    transparency_index = {}
    
    for row in t_rows:
        cid, pname, pamount = row
        tokens = normalize_and_tokenize(pname)
        doc_idx = len(transparency_docs)
        transparency_docs.append({'id': cid, 'name': pname, 'tokens': tokens})
        
        for t in tokens:
            if t not in transparency_index:
                transparency_index[t] = []
            transparency_index[t].append(doc_idx)
            
    # Prune frequent tokens
    total_docs = len(transparency_docs)
    pruned = 0
    keys = list(transparency_index.keys())
    for k in keys:
        if len(transparency_index[k]) > total_docs * 0.05: # 5% threshold
            del transparency_index[k]
            pruned += 1
    print(f"Pruned {pruned} frequent tokens.")
    
    # 4. Run Matching
    print("\nRunning Matching Verification...")
    matches_found = 0
    
    for proj in sample:
        name = proj['name']
        tokens = normalize_and_tokenize(name)
        
        if len(tokens) < 2:
            print(f"[-] SKIPPING (Too few tokens): {name}")
            continue
            
        # Retrieval
        candidate_counts = Counter()
        for t in tokens:
            if t in transparency_index:
                candidate_counts.update(transparency_index[t])
        
        # Scoring
        best_candidates = []
        for idx, count in candidate_counts.items():
            # Heuristic: Match if >= 3 tokens share OR > 80% of source tokens
            is_match = False
            if count >= 3:
                is_match = True
            elif len(tokens) > 0 and count >= len(tokens) * 0.8:
                is_match = True
            
            if is_match:
                t_doc = transparency_docs[idx]
                best_candidates.append(t_doc)
        
        if best_candidates:
            matches_found += 1
            if len(best_candidates) > 0:
                 if "Navotas" in name:
                     print(f"[+] MATCHED: {name}")
                     for c in best_candidates[:5]:
                         print(f"    -> {c['id']}: {c['name']}")
        else:
            if "Navotas" in name:
                print(f"[!] NO MATCH: {name}")
                print(f"    Tokens: {tokens}")
    
    print(f"\nSummary: Found matches for {matches_found}/{len(sample)} ({matches_found/len(sample)*100:.1f}%) projects.")
    
    # 5. Verify Links via Curl
    print("\nVerifying Links via Curl (Sample 5)...")
    import subprocess
    verified_count = 0
    checked_count = 0
    
    # Collect a few IDs to check
    ids_to_check = []
    
    # Re-run matching briefly to get IDs (or reuse from verification loop if I stored them, simpler to just grab matched ones from print if I could, but better to collect during loop. Refactoring loop slightly above would be better, but appending here is easier.)
    
    # Quick re-match for just Navotas and a few others to verify
    check_projects = [p for p in sample if "Navotas" in p['name']][:3]
    if len(check_projects) < 3:
         check_projects.extend(sample[:3])
         
    for proj in check_projects:
        name = proj['name']
        tokens = normalize_and_tokenize(name)
        if len(tokens) < 2: continue
        
        candidate_counts = Counter()
        for t in tokens:
            if t in transparency_index: candidate_counts.update(transparency_index[t])
            
        best_cand = None
        for idx, count in candidate_counts.items():
            if count >= 3 or (len(tokens) > 0 and count >= len(tokens) * 0.8):
                best_cand = transparency_docs[idx]
                break
        
        if best_cand:
            cid = best_cand['id']
            # Specific check for Navotas
            if "Navotas" in name:
                print(f"\n[!] Navotas Match for '{name}':")
                print(f"    -> Found ID: {cid} | Name: {best_cand['name']}")
                
            url = f"https://transparency.dpwh.gov.ph/?project={cid}"
            print(f"Checking {url} ... ", end='', flush=True)
            try:
                # Use curl -I to get headers only, with User-Agent
                cmd = ["curl", "-I", "-s", "-o", "/dev/null", "-w", "%{http_code}", 
                       "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                       url]
                res = subprocess.run(cmd, capture_output=True, text=True)
                code = res.stdout.strip()
                print(f"[{code}]")
                if code == "200":
                    verified_count += 1
                checked_count += 1
            except Exception as e:
                print(f"Error: {e}")
                
    print(f"\nVerified {verified_count}/{checked_count} links with 200 OK.")

if __name__ == "__main__":
    main()
