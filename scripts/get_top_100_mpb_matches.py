
import json
import duckdb
import os
import re
import unicodedata
from datetime import datetime

# --- Configuration ---
DATA_DIR = "static/data"
OUTPUT_JSON = "top_100_mpb_targets.json"

# --- Re-using Logic from generate_integrated_matrix.py ---

def normalize_for_match(text):
    if not text: return ""
    try:
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        text = text.lower()
        # Remove punctuation (keep words separated)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = text.strip()
        text = text.replace("city of ", "").replace("municipality of ", "")
    except:
        return ""
    return text

def main():
    print("="*80)
    print(" TOP 100 MPB TRANSPARENCY MATCHER")
    print("="*80)

    # 1. Load Projects (Resurrected & Flagged)
    print("Loading 2026 Projects...")
    resurrected_path = os.path.join(DATA_DIR, "resurrected_projects_dpwh_enriched.json")
    flagged_path = os.path.join(DATA_DIR, "flagged_amount_projects_2026.json")
    
    projects = []

    # Load Resurrected
    if os.path.exists(resurrected_path):
        with open(resurrected_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            matches = data.get('matches', [])
            for m in matches:
                y2026 = m.get('year_2026', {})
                if y2026:
                    projects.append({
                        'id': y2026.get('id'),
                        'name': y2026.get('name'),
                        'amount': y2026.get('amount', 0),
                        'source': 'resurrected'
                    })

    # Load Flagged
    if os.path.exists(flagged_path):
        with open(flagged_path, 'r', encoding='utf-8') as f:
            flagged = json.load(f)
            for p in flagged:
                projects.append({
                    'id': p.get('id'),
                    'name': p.get('name'),
                    'amount': p.get('amount', 0),
                    'source': 'flagged'
                })

    print(f"Total Projects Loaded: {len(projects)}")

    # 2. Filter for "Multi-Purpose Building" AND Repeated Status
    # User Request: "top 100 which are already flagged as repeated"
    # In our context, 'resurrected' = repeated (historical match).
    
    mpb_projects = []
    for p in projects:
        # Strict filter: Must be from resurrected source (Repeated)
        if p.get('source') != 'resurrected':
            continue
            
        name_lower = (p['name'] or "").lower()
        if "multi-purpose building" in name_lower or "multipurpose building" in name_lower:
            mpb_projects.append(p)
    
    print(f"Total Repeated MPB Projects Found: {len(mpb_projects)}")

    # 3. Sort by Amount and Take Top 100
    mpb_projects.sort(key=lambda x: x['amount'], reverse=True)
    top_100 = mpb_projects[:100]
    
    print("Top 100 MPBs selected.")

    # 4. Load Transparency Data & Index
    print("Loading Transparency Data...")
    transparency_parquet_path = os.path.join(DATA_DIR, "parquet/transparency_projects.parquet")
    
    # STOPWORDS (Corrected)
    STOPWORDS = {
        "construction", "completion", "rehabilitation", "improvement", "repair", "maintenance", 
        "upgrading", "widening", "concreting", "asphalt", "overlay", "reblocking", 
        "school", "classroom", "infra", "infrastructure",
        "project", "program", "phase", "package", "contract", "id", "no", "of", "the", "in", 
        "and", "to", "with", "at", "city", "province", "municipality", "barangay", "district",
        "st.", "ave.", "rd.", "ext.", "brgy", "poblacion", "water", "system", "flood", "control"
    }
    
    con = duckdb.connect()
    t_rows = con.execute(f"SELECT contract_id, project_name, amount FROM read_parquet('{transparency_parquet_path}') WHERE project_name IS NOT NULL").fetchall()
    con.close()

    transparency_projects = []
    for row in t_rows:
        cid, pname, pamount = row
        if not pname: continue
        norm = normalize_for_match(pname)
        tokens = set([t for t in norm.split() if len(t) > 2 and t not in STOPWORDS])
        transparency_projects.append({
            'id': cid, 'name': pname, 'amount': pamount, 'tokens': tokens
        })
    
    # Indexing
    transparency_index = {}
    token_counts = {}
    for idx, item in enumerate(transparency_projects):
        for token in item['tokens']:
            token_counts[token] = token_counts.get(token, 0) + 1
            if token not in transparency_index:
                transparency_index[token] = []
            transparency_index[token].append(idx)
            
    # Pruning (Corrected Logic)
    threshold = len(transparency_projects) * 0.05
    KEEP_TOKENS = {"multi-purpose", "multipurpose", "building"}
    
    pruned_count = 0
    for token, count in token_counts.items():
        if count > threshold:
            if token in KEEP_TOKENS: continue
            if token in transparency_index:
                del transparency_index[token]
                pruned_count += 1
                
    print(f"Indexed Transparency Data. Pruned {pruned_count} tokens.")

    import math
    
    # 5. Compute IDF Weights
    # IDF(t) = log(Total Documents / (Document Frequency(t) + 1))
    print("Computing IDF Weights...")
    total_docs = len(transparency_projects)
    token_weights = {}
    
    for token, count in token_counts.items():
        token_weights[token] = math.log(total_docs / (count + 1))
        
    # Optional: Penalize "very common" terms further or boost "very rare" terms
    # For now, standard IDF should handle 'lakeshore' (rare) vs 'taguig' (common).
    
    # 6. Perform Weighted Matching
    print("Matching Projects (Weighted)...")
    targets = []
    
    for p in top_100:
        name_norm = normalize_for_match(p['name'])
        name_tokens = set([t for t in name_norm.split() if len(t) > 2 and t not in STOPWORDS])
        
        # Calculate Target's Max Possible Score (Self-Score)
        target_score = sum(token_weights.get(t, 0) for t in name_tokens)
        
        if len(name_tokens) < 2:
            continue
            
        candidate_scores = {}
        
        # 6a. Find Candidates
        for token in name_tokens:
            if token in transparency_index:
                # Weight of this token
                w = token_weights.get(token, 0)
                for idx in transparency_index[token]:
                    candidate_scores[idx] = candidate_scores.get(idx, 0) + w
        
        # 6b. Filter Candidates
        matches = []
        for idx, score in candidate_scores.items():
            # Evaluation Metric: Score Ratio
            # How much of the Target's "Uniqueness" is covered by the Candidate?
            ratio = score / target_score if target_score > 0 else 0
            
            # Thresholds:
            # - High Ratio (> 0.6) suggests good coverage of important terms
            # - Or if score is very high (meaning several rare terms matched)
             
            is_match = False
            if ratio >= 0.65: # Require 65% of information overlap
                 is_match = True
            
            if is_match:
                proj = transparency_projects[idx]
                matches.append({
                    'contract_id': proj['id'],
                    'name': proj['name'],
                    'amount': proj['amount'],
                    'score': ratio # Store score for sorting
                })
        
        # STRICT FILTER: Ensure transparency match is actually an MPB
        valid_matches = []
        for m in matches:
            t_name = m['name'].lower()
            
            # User Feedback: "multi purpose building can't even be read on the project name"
            # We must be very strict. Terms like "structure", "facility", "center" alone are causing match errors with Flood Control Structures.
            
            has_strong_keyword = False
            # Check for strong indicators: "multi-purpose" or "multipurpose" or "mpb"
            if "multi-purpose" in t_name or "multipurpose" in t_name or "mpb" in t_name:
                has_strong_keyword = True
            
            # Special case: sometimes it is "multi purpose" with space
            if "multi purpose" in t_name:
                has_strong_keyword = True

            if not has_strong_keyword:
                continue
                
            valid_matches.append(m)
            
        matches = valid_matches
        
        # Sort matches by score descending
        matches.sort(key=lambda x: x['score'], reverse=True)
        
        # Deduplicate matches by Contract ID
        unique_matches = []
        seen_ids = set()
        for m in matches:
            if m['contract_id'] not in seen_ids:
                unique_matches.append(m)
                seen_ids.add(m['contract_id'])
                if len(unique_matches) >= 5: break
        
        if unique_matches:
            targets.append({
                'project_id': p['id'],
                'project_name': p['name'],
                'amount': p['amount'],
                'matches': unique_matches
            })

    print(f"Found matches for {len(targets)} out of 100 projects.")

    # 7. Save Targets
    # Clean up output (remove score)
    clean_targets = []
    for t in targets:
        clean_matches = [{'contract_id': m['contract_id'], 'name': m['name'], 'amount': m['amount']} for m in t['matches']]
        t['matches'] = clean_matches
        clean_targets.append(t)
        
    with open(OUTPUT_JSON, "w", encoding='utf-8') as f:
        json.dump(clean_targets, f, indent=2)
        
    print(f"Saved targets to {OUTPUT_JSON}")
    
    # 8. Generate Readable List
    md_output = "top_100_mpb_list.md"
    with open(md_output, "w", encoding='utf-8') as f:
        f.write("# Top 100 Repeated Multi-Purpose Buildings (by Cost)\n\n")
        f.write("| Rank | Amount | Project Name | Transparency Matches |\n")
        f.write("|:--|:--|:---|:--|\n")
        
        for idx, p in enumerate(top_100, 1):
            matches = [t['matches'] for t in targets if t['project_id'] == p['id']]
            match_count = len(matches[0]) if matches else 0
            
            amt_fmt = f"P{p['amount']:,.2f}"
            f.write(f"| {idx} | {amt_fmt} | {p['name']} | {match_count} |\n")
            
    print(f"Generated readable list: {md_output}")

if __name__ == "__main__":
    main()
