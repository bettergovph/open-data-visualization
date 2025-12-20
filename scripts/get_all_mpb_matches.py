#!/usr/bin/env python3
"""
Generate MPB transparency matches for ALL Multi-Purpose Building projects (not limited to top 100).
Writes output to `all_mpb_targets.json` in the repository root.

This is adapted from `get_top_100_mpb_matches.py` but processes the full set of MPB projects
found in the resurrected and flagged 2026 project lists.
"""

import json
import duckdb
import os
import re
import unicodedata
from datetime import datetime

# --- Configuration ---
DATA_DIR = "static/data"
OUTPUT_JSON = "all_mpb_targets.json"


def normalize_for_match(text):
    if not text:
        return ""
    try:
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        text = text.lower()
        text = re.sub(r"[^\w\s]", ' ', text)
        text = text.strip()
        text = text.replace("city of ", "").replace("municipality of ", "")
    except:
        return ""
    return text


def main():
    print("=" * 80)
    print(" ALL MPB TRANSPARENCY MATCHER")
    print("=" * 80)

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

    # 2. Filter for "Multi-Purpose Building"
    mpb_projects = []
    for p in projects:
        name_lower = (p.get('name') or "").lower()
        if "multi-purpose building" in name_lower or "multipurpose building" in name_lower or "multi purpose building" in name_lower:
            mpb_projects.append(p)

    print(f"Total MPB Projects Found: {len(mpb_projects)}")

    # 3. Sort by Amount descending
    mpb_projects.sort(key=lambda x: x.get('amount', 0) or 0, reverse=True)

    # 4. Load Transparency Data & Index
    print("Loading Transparency Data...")
    transparency_parquet_path = os.path.join(DATA_DIR, "parquet/transparency_projects.parquet")

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
        if not pname:
            continue
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
            transparency_index.setdefault(token, []).append(idx)

    # Prune very common tokens (keep MPB-related tokens)
    threshold = len(transparency_projects) * 0.05 if transparency_projects else 0
    KEEP_TOKENS = {"multi-purpose", "multipurpose", "building"}
    for token, count in list(token_counts.items()):
        if count > threshold and token not in KEEP_TOKENS:
            transparency_index.pop(token, None)

    print(f"Indexed Transparency Data. Tokens indexed: {len(transparency_index)}")

    import math
    total_docs = len(transparency_projects)
    token_weights = {token: math.log(total_docs / (count + 1)) for token, count in token_counts.items()} if total_docs else {}

    # 5. Perform matching for all MPB projects
    print("Matching Projects (Weighted)...")
    targets = []

    for p in mpb_projects:
        name_norm = normalize_for_match(p.get('name'))
        name_tokens = set([t for t in name_norm.split() if len(t) > 2 and t not in STOPWORDS])
        target_score = sum(token_weights.get(t, 0) for t in name_tokens)
        # Do not skip projects with few tokens or zero score — we still want to
        # include them in the final output (they will have empty `matches`).

        candidate_scores = {}
        for token in name_tokens:
            if token in transparency_index:
                w = token_weights.get(token, 0)
                for idx in transparency_index[token]:
                    candidate_scores[idx] = candidate_scores.get(idx, 0) + w

        matches = []
        for idx, score in candidate_scores.items():
            ratio = score / target_score if target_score > 0 else 0
            if ratio >= 0.65:
                proj = transparency_projects[idx]
                matches.append({'contract_id': proj['id'], 'name': proj['name'], 'amount': proj['amount'], 'score': ratio})

        # STRICT FILTER: ensure match is actually MPB
        valid_matches = []
        for m in matches:
            t_name = (m['name'] or '').lower()
            has_strong_keyword = any(k in t_name for k in ("multi-purpose", "multipurpose", "mpb", "multi purpose"))
            if not has_strong_keyword:
                continue
            valid_matches.append(m)

        valid_matches.sort(key=lambda x: x['score'], reverse=True)

        # Deduplicate and keep top 5
        unique_matches = []
        seen_ids = set()
        for m in valid_matches:
            if m['contract_id'] not in seen_ids:
                unique_matches.append(m)
                seen_ids.add(m['contract_id'])
                if len(unique_matches) >= 5:
                    break

        # Always include the project in the output. If there are no unique_matches
        # this will be an empty list (zero transparency matches).
        targets.append({
            'project_id': p.get('id'),
            'project_name': p.get('name'),
            'amount': p.get('amount', 0),
            'matches': [{'contract_id': m['contract_id'], 'name': m['name'], 'amount': m.get('amount')} for m in unique_matches]
        })

    print(f"Found matches for {len(targets)} MPB projects out of {len(mpb_projects)} MPBs.")

    # Save
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(targets, f, indent=2, ensure_ascii=False)

    print(f"Saved targets to {OUTPUT_JSON}")


if __name__ == '__main__':
    main()
