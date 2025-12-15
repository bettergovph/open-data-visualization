import json
import re
import shutil
from pathlib import Path

DISTRICTS_FILE = Path("static/data/districts.json")
WINNERS_FILE = Path("static/data/elections_2025_winners.json")

def clean_candidate_name(raw_name):
    name = re.sub(r'^\d+\.\s*', '', raw_name)
    name = re.sub(r'\s*\(.*?\)$', '', name)
    if ',' in name:
        parts = name.split(',', 1)
        last = parts[0].strip()
        first = parts[1].strip()
        return f"{first} {last}".title()
    return name.title()

def parse_contest_location(contest_name):
    prefix = "MEMBER, HOUSE OF REPRESENTATIVES of "
    if not contest_name.startswith(prefix):
        return None, None, None
    rest = contest_name[len(prefix):]
    parts = rest.split(' - ')
    if len(parts) == 2:
        return parts[0], None, parts[1]
    elif len(parts) >= 3:
        return parts[0], parts[1], parts[-1]
    return None, None, None

def normalize_district_key(dist_part):
    d = dist_part.upper()
    if "LONE" in d: return "Lone District"
    if "FIRST" in d: return "1st District"
    if "SECOND" in d: return "2nd District"
    if "THIRD" in d: return "3rd District"
    if "FOURTH" in d: return "4th District"
    if "FIFTH" in d: return "5th District"
    if "SIXTH" in d: return "6th District"
    if "SEVENTH" in d: return "7th District"
    if "EIGHTH" in d: return "8th District"
    return dist_part.title()

def update_districts():
    print("🔄 Loading data...")
    with open(DISTRICTS_FILE, 'r', encoding='utf-8') as f:
        d_data = json.load(f)
    with open(WINNERS_FILE, 'r', encoding='utf-8') as f:
        winners_data = json.load(f)

    shutil.copy(DISTRICTS_FILE, str(DISTRICTS_FILE) + ".bak")

    updates_count = 0
    misses = []

    for contest, info in winners_data.items():
        winner = info.get('winner')
        if not winner: continue

        raw_name = winner['name']
        clean_name = clean_candidate_name(raw_name)
        new_rep_str = f"{clean_name} (2025-present)"

        prov_part, city_part, dist_part = parse_contest_location(contest)
        if not prov_part: continue

        target_dist_key = normalize_district_key(dist_part)
        target_key = None

        # 1. City Key Priority
        if city_part:
            simple_city = city_part.replace("CITY OF ", "")
            # Remove parenthesis like "(1ST COUNCILOR DISTRICT)"
            simple_city = re.sub(r'\(.*?\)', '', simple_city).strip()
            
            for k in d_data['districts'].keys():
                if k.upper() == city_part.upper():
                    target_key = k
                    break
                if k.upper() == simple_city.upper() or k.upper() == f"{simple_city} CITY".upper():
                    target_key = k
                    break
                # Taguig fuzzy
                if "TAGUIG" in simple_city.upper() and "TAGUIG" in k.upper() and "PATEROS" in k.upper():
                     target_key = k
                     break
        
        # 2. Province Key Fallback
        if not target_key:
             if prov_part == "MAGUINDANAO DEL NORTE":
                 target_key = "Maguindanao"
                 if target_dist_key == "Lone District": target_dist_key = "1st District"
             elif prov_part == "MAGUINDANAO DEL SUR":
                 target_key = "Maguindanao"
                 if target_dist_key == "Lone District": target_dist_key = "2nd District"
             else:
                 for k in d_data['districts'].keys():
                    if k.upper() == prov_part.upper():
                        target_key = k
                        break
        
        # 3. Special Case: Province match but City Sub-match needed
        if target_key and city_part:
             simple_city = city_part.replace("CITY OF ", "")
             simple_city = re.sub(r'\(.*?\)', '', simple_city).strip().title()
             
             # If target_key is NOT the city itself (it's the province), find the city district
             if not target_key.upper().startswith(simple_city.upper()):
                 p_data = d_data['districts'][target_key]
                 for m_key, m_dist in p_data.get('municipalities', {}).items():
                      if m_key.upper() == simple_city.upper() or m_key.upper() == f"{simple_city} CITY".upper():
                           target_dist_key = m_dist
                           break
        
        # 4. Agusan del Norte Logic
        if prov_part == "AGUSAN DEL NORTE" and not city_part and target_dist_key == "Lone District":
             target_dist_key = "2nd District"

        if target_key:
            if 'representatives' not in d_data['districts'][target_key]:
                 d_data['districts'][target_key]['representatives'] = {}
            
            reps = d_data['districts'][target_key]['representatives']
            all_dists = d_data['districts'][target_key].get('all_districts', [])
            
            # Aliases
            if target_dist_key == "Lone District" and "At-large District" in reps:
                target_dist_key = "At-large District"
            elif target_dist_key == "Lone District" and "At-large District" in all_dists:
                 target_dist_key = "At-large District"
            
            # Taguig Special Mapping in target_dist_key
            if "TAGUIG" in contest and "PATEROS" in contest:
                 target_dist_key = "1st District" 
            elif "TAGUIG" in contest and "2ND" in contest:
                 target_dist_key = "2nd District"

            # Apply
            if target_dist_key in reps or target_dist_key in all_dists:
                d_data['districts'][target_key]['representatives'][target_dist_key] = new_rep_str
                updates_count += 1
            # Implicit Lone -> 1st
            elif target_dist_key == "Lone District" and ("1st District" in reps or "1st District" in all_dists):
                if len(all_dists) == 1 or len(reps) == 1:
                     d_data['districts'][target_key]['representatives']["1st District"] = new_rep_str
                     updates_count += 1
                else:
                     misses.append(f"{contest} -> Ambiguous Lone mapping for {target_key}")
            # Force add if missing but looks valid (Trusted Source)
            elif "District" in target_dist_key:
                  d_data['districts'][target_key]['representatives'][target_dist_key] = new_rep_str
                  updates_count += 1
            else:
                 misses.append(f"{contest} -> Key Found: {target_key}, Dist {target_dist_key} invalid {all_dists}")
        else:
            misses.append(f"{contest} -> No Key match for {prov_part}/{city_part}")

    print(f"✅ Updated {updates_count} representatives.")
    if misses:
        print(f"⚠️ Missed {len(misses)} contests (First 10):")
        for m in misses[:10]:
            print(f"   {m}")

    with open(DISTRICTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(d_data, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    update_districts()
