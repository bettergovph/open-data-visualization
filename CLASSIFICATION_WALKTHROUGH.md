# Project Classification Walkthrough

## Example 1: District-Based Classification

## Sample Project

```json
{
  "project_name": "Construction of Slope Protection Works along Ingalera River, Malabago, Calasiao, Pangasinan",
  "province": "Pangasinan",
  "city": "Calasiao",
  "barangay": "Malabago",
  "contractors": ["HIGH ROCK CONSTRUCTION AND SUPPLIES INCORPORATED"],
  "date_started": "2023-05-11",
  "cost": 9799989.13
}
```

---

## Step-by-Step Classification Process

### **Step 1: Extract Project Data** (lines 264-271)

```python
proj_province = "Pangasinan"
proj_city = "Calasiao"
proj_barangay = "Malabago"
proj_municipality = None  # Calasiao doesn't contain "CITY", but it's a municipality

# Determine district type
is_city_district = False  # "CITY" not in "Calasiao"
location_key = "Calasiao"  # Since it's province district, use municipality
```

**Result:**
- Province: `"Pangasinan"`
- Location Key: `"Calasiao"` (municipality)
- District Type: **Province district** (not city)

---

### **Step 2: Extract Contractor** (lines 274-279)

```python
contractor_str = "HIGH ROCK CONSTRUCTION AND SUPPLIES INCORPORATED"
```

---

### **Step 3: Extract Project Year** (lines 282-294)

```python
date_field = "2023-05-11"
project_year = 2023  # Parsed from date_started
```

---

### **Step 4: District Lookup (O(1))** (lines 296-301)

Calls `_find_congressman_by_district()` with:
- `province = "Pangasinan"`
- `municipality_barangay = "Calasiao"`
- `project_year = 2023`

#### Inside `_find_congressman_by_district()` (lines 2109-2195):

```python
province_upper = "PANGASINAN"
location_upper = "CALASIAO"

# Step 4a: Try exact match
candidates = district_lookup.get(("PANGASINAN", "CALASIAO"), [])
# Looks for: (province, municipality) = ("PANGASINAN", "CALASIAO")
```

**What happens:**
- The `district_lookup_dict` was built from congressmen data
- It contains entries like: `("PANGASINAN", "CALASIAO") -> [(congressman_name, cm_data)]`
- If Calasiao is in a specific district (e.g., "Pangasinan 2nd District"), it finds that congressman

**Example match:**
```python
candidates = [("Mark Cojuangco", {
    "district_number": "2nd",
    "provinces": ["Pangasinan"],
    "district_municipalities": ["Calasiao", "Mangaldan", ...],
    "terms": [{"start": 2019, "end": 2025}]
})]
```

#### Step 4b: Term Filtering (lines 2131-2147)

```python
# Check if project_year (2023) falls within congressman's term
term = {"start": 2019, "end": 2025}
if 2019 <= 2023 <= 2025:  # True
    filtered_candidates.append(("Mark Cojuangco", cm_data))
```

**Result:** Candidate passes term filter ✅

#### Step 4c: Return Match (line 2193)

```python
return ("Mark Cojuangco", 100)  # (congressman_name, match_score)
```

---

### **Step 5: Contractor Lookup (O(1))** (lines 303-308)

Calls `_find_congressman_by_contractor()` with:
- `contractor_name = "HIGH ROCK CONSTRUCTION AND SUPPLIES INCORPORATED"`

#### Inside `_find_congressman_by_contractor()` (lines 2197-2210):

```python
contractor_upper = "HIGH ROCK CONSTRUCTION AND SUPPLIES INCORPORATED"

# Try exact match in contractor_lookup_dict
candidates = contractor_lookup.get("HIGH ROCK CONSTRUCTION AND SUPPLIES INCORPORATED", [])
```

**What happens:**
- If this contractor is linked to a congressman, it finds them
- Otherwise, tries normalized match, substring matches, etc.
- Checks contractor exclusions

**Result:** 
- If found: `("Some Congressman", 100)`
- If not found: `None`

**For this example, let's assume:** No contractor match → `None`

---

### **Step 6: Format Matches** (lines 310-316)

```python
best_district_match = ("Mark Cojuangco", "district", 100)
best_contractor_match = None
```

---

### **Step 7: Fallback Logic** (lines 318-334)

```python
# Check if we need fallback
if not best_district_match and not best_contractor_match:
    # Try province-only lookup
    # ... (not needed in this case, we have district match)
```

**Result:** No fallback needed ✅

---

### **Step 8: Extract District Congressman Info** (lines 364-382)

```python
district_congressman = "Mark Cojuangco"
district_match_type = "district"
district_match_score = 100

# Build congressman_district
cm_data = congressmen_data["Mark Cojuangco"]
district_number = "2nd"
provinces = ["Pangasinan"]
congressman_district = "2nd District Pangasinan"
```

---

### **Step 9: Extract Contractor Congressman Info** (lines 384-401)

```python
contractor_congressman = None  # No contractor match
contractor_match_type = None
contractor_match_score = 0
```

---

### **Step 10: Determine Project Classification** (lines 403-425)

```python
# project_district_type
project_province = "Pangasinan"
project_city = "Calasiao"
# "CITY" not in location, so:
project_district_type = "province"  ✅

# project_district
district_congressman = "Mark Cojuangco"
cm_data = congressmen_data["Mark Cojuangco"]
district_number = "2nd"
province_name = "Pangasinan"
project_district = "Pangasinan 2nd District"  ✅

# project_barangay_municipality
project_barangay = "Malabago"  # Has barangay
project_barangay_municipality = "Malabago"  ✅
```

---

### **Step 11: Flood Detection** (lines 450-455)

```python
is_flood = self._is_flood_related(
    "Construction of Slope Protection Works along Ingalera River, Malabago, Calasiao, Pangasinan",
    "",
    "Pangasinan, Calasiao, Malabago"
)
# Checks for flood-related keywords in project name
# "Slope Protection" might be flood-related
is_flood = True  # (depends on keyword matching)
```

---

### **Step 12: Validation** (lines 457-488)

```python
# Check all required fields
project_district_type = "province"  ✅
project_district = "Pangasinan 2nd District"  ✅
project_barangay_municipality = "Malabago"  ✅
```

**All validations pass!** ✅

---

### **Step 13: Final Output Record** (lines 494-519)

```json
{
  "source": "DIME",
  "project_name": "Construction of Slope Protection Works along Ingalera River, Malabago, Calasiao, Pangasinan",
  "contractor": "HIGH ROCK CONSTRUCTION AND SUPPLIES INCORPORATED",
  "amount": 9799989.13,
  "location": "Pangasinan, Calasiao, Malabago",
  "year": 2023,
  "status": "Completed",
  
  "district_congressman": "Mark Cojuangco",
  "district_match_type": "district",
  "district_match_score": 100,
  "congressman_district": "2nd District Pangasinan",
  
  "contractor_congressman": null,
  "contractor_match_type": null,
  "contractor_match_score": 0,
  
  "project_district_type": "province",
  "project_district": "Pangasinan 2nd District",
  "project_barangay_municipality": "Malabago",
  
  "is_flood_related": true
}
```

---

## Summary

✅ **District Match:** Found via municipality "Calasiao" in "Pangasinan 2nd District"  
✅ **Contractor Match:** None (contractor not linked to any congressman)  
✅ **Classification:**
- `project_district_type`: "province"
- `project_district`: "Pangasinan 2nd District"
- `project_barangay_municipality`: "Malabago"
✅ **Term Filtering:** Project year (2023) within congressman's term (2019-2025)  
✅ **Flood Detection:** Detected as flood-related

---

## Alternative Scenarios

### Scenario A: No Municipality/Barangay Specified

If `barangay = ""` and `city = ""`:
1. `location_key = ""` (empty)
2. `_find_congressman_by_district("Pangasinan", "", 2023, ...)`
3. Looks up `("PANGASINAN", "")` → finds all Pangasinan districts
4. **Checks if lone district or multi-district:**
   - If Pangasinan has multiple districts → prefers "Pangasinan 1st District"
   - If Pangasinan has only 1 district → returns that lone district
5. Filters by term (2023)

### Scenario B: Contractor Match Found

If contractor "HIGH ROCK" is linked to a congressman:
1. District match: "Mark Cojuangco" (via Calasiao)
2. Contractor match: "Some Other Congressman" (via contractor)
3. **Both matches are kept** in the final record:
   - `district_congressman`: "Mark Cojuangco"
   - `contractor_congressman`: "Some Other Congressman"

### Scenario C: Project Year Outside Term

If `project_year = 2015` but congressman's term is 2019-2025:
1. District lookup finds candidate
2. Term filtering excludes candidate (2015 not in 2019-2025)
3. Falls back to province-only lookup
4. Finds another congressman whose term includes 2015

---

## Example 2: Contractor-Based Classification (S-ANG)

### Sample Project

```json
{
  "project_name": "Construction of Flood Control Structure, Barangay Poblacion, Iloilo City",
  "province": "Iloilo",
  "city": "Iloilo City",
  "barangay": "Poblacion",
  "contractors": ["S-ANG CONSTRUCTION AND GENERAL TRADING, INC."],
  "date_started": "2022-08-15",
  "cost": 15000000.00
}
```

---

## Step-by-Step Classification Process

### **Step 1: Extract Project Data** (lines 264-271)

```python
proj_province = "Iloilo"
proj_city = "Iloilo City"
proj_barangay = "Poblacion"
proj_municipality = None  # "Iloilo City" contains "CITY"

# Determine district type
is_city_district = True  # "CITY" in "Iloilo City"
location_key = "Poblacion"  # Since it's city district, use barangay
```

**Result:**
- Province: `"Iloilo"`
- Location Key: `"Poblacion"` (barangay)
- District Type: **City district** (Iloilo City)

---

### **Step 2: Extract Contractor** (lines 274-279)

```python
contractor_str = "S-ANG CONSTRUCTION AND GENERAL TRADING, INC."
```

---

### **Step 3: Extract Project Year** (lines 282-294)

```python
date_field = "2022-08-15"
project_year = 2022  # Parsed from date_started
```

---

### **Step 4: District Lookup (O(1))** (lines 296-301)

Calls `_find_congressman_by_district()` with:
- `province = "Iloilo"`
- `municipality_barangay = "Poblacion"` (barangay for city district)
- `project_year = 2022`

#### Inside `_find_congressman_by_district()` (lines 2109-2195):

```python
province_upper = "ILOILO"
location_upper = "POBLACION"

# Step 4a: Try exact match
candidates = district_lookup.get(("ILOILO", "POBLACION"), [])
# Looks for: (city, barangay) = ("ILOILO", "POBLACION")
```

**What happens:**
- The `district_lookup_dict` searches for Iloilo City + Poblacion barangay
- If Poblacion is in a specific district (e.g., "Iloilo City 1st District"), it finds that congressman

**Example match:**
```python
candidates = [("Julienne Baronda", {
    "district_number": "1st",
    "provinces": ["Iloilo City"],
    "barangays": ["Poblacion", "Molo", ...],
    "is_city_district": True,
    "terms": [{"start": 2019, "end": 2025}]
})]
```

#### Step 4b: Term Filtering (lines 2131-2147)

```python
# Check if project_year (2022) falls within congressman's term
term = {"start": 2019, "end": 2025}
if 2019 <= 2022 <= 2025:  # True
    filtered_candidates.append(("Julienne Baronda", cm_data))
```

**Result:** Candidate passes term filter ✅

#### Step 4c: Return Match (line 2193)

```python
return ("Julienne Baronda", 100)  # (congressman_name, match_score)
```

---

### **Step 5: Contractor Lookup (O(1))** (lines 303-308)

Calls `_find_congressman_by_contractor()` with:
- `contractor_name = "S-ANG CONSTRUCTION AND GENERAL TRADING, INC."`

#### Inside `_find_congressman_by_contractor()` (lines 2197-2240):

```python
contractor_upper = "S-ANG CONSTRUCTION AND GENERAL TRADING, INC."
normalized = "S ANG CONSTRUCTION AND GENERAL TRADING INC"  # Removed special chars

# Step 5a: Try exact match
candidates = contractor_lookup.get("S-ANG CONSTRUCTION AND GENERAL TRADING, INC.", [])
```

**What happens:**
- The `contractor_lookup_dict` was built from congressmen's `contractors` and `contractor_patterns` lists
- If a congressman has "S-ANG" in their contractor list, it's mapped in the lookup

**Example:**
- Congressman "Julienne Baronda" has `contractors: ["S-ANG CONSTRUCTION AND GENERAL TRADING, INC."]`
- This creates entries in `contractor_lookup`:
  - `"S-ANG CONSTRUCTION AND GENERAL TRADING, INC."` → `[("Julienne Baronda", cm_data)]`
  - `"S ANG CONSTRUCTION AND GENERAL TRADING INC"` → `[("Julienne Baronda", cm_data)]` (normalized)

```python
candidates = [("Julienne Baronda", {
    "district_number": "1st",
    "provinces": ["Iloilo City"],
    "contractors": ["S-ANG CONSTRUCTION AND GENERAL TRADING, INC.", ...],
    "contractor_exclusions": {}
})]
```

#### Step 5b: Check Exclusions (lines 2224-2238)

```python
contractor_exclusions = cm_data.get('contractor_exclusions', {})
# Example: {"S-ANG": ["S-ANG OTHER COMPANY"]}  # Exclude if name contains both
excluded = False

# Check if contractor should be excluded
# In this case, no exclusions match, so:
excluded = False
```

**Result:** No exclusions match ✅

#### Step 5c: Return Match (line 2238)

```python
return ("Julienne Baronda", 50)  # (congressman_name, match_score)
# Note: Contractor matches have score 50 (lower than district match score 100)
```

---

### **Step 6: Format Matches** (lines 310-316)

```python
best_district_match = ("Julienne Baronda", "district", 100)
best_contractor_match = ("Julienne Baronda", "contractor", 50)
```

**Note:** Both matches point to the same congressman! This is common when a contractor is linked to a congressman from the same district.

---

### **Step 7: Fallback Logic** (lines 318-334)

```python
# Check if we need fallback
if not best_district_match and not best_contractor_match:
    # ... (not needed, we have both matches)
```

**Result:** No fallback needed ✅

---

### **Step 8: Extract District Congressman Info** (lines 364-382)

```python
district_congressman = "Julienne Baronda"
district_match_type = "district"
district_match_score = 100

# Build congressman_district
cm_data = congressmen_data["Julienne Baronda"]
district_number = "1st"
provinces = ["Iloilo City"]
congressman_district = "1st District Iloilo City"
```

---

### **Step 9: Extract Contractor Congressman Info** (lines 384-401)

```python
contractor_cm = "Julienne Baronda"
# Check if different from district match
if best_district_match[0] != contractor_cm:  # False - same congressman
    contractor_congressman = None  # Don't duplicate
else:
    contractor_congressman = None  # Same as district, so don't set separately
```

**Result:** Since both matches point to the same congressman, only `district_congressman` is set.

---

### **Step 10: Determine Project Classification** (lines 403-425)

```python
# project_district_type
project_province = "Iloilo"
project_city = "Iloilo City"
# "CITY" in location, so:
project_district_type = "city"  ✅

# project_district
district_congressman = "Julienne Baronda"
cm_data = congressmen_data["Julienne Baronda"]
district_number = "1st"
province_name = "Iloilo City"
project_district = "Iloilo City 1st District"  ✅

# project_barangay_municipality
project_barangay = "Poblacion"  # Has barangay
project_barangay_municipality = "Poblacion"  ✅
```

---

### **Step 11: Flood Detection** (lines 450-455)

```python
is_flood = self._is_flood_related(
    "Construction of Flood Control Structure, Barangay Poblacion, Iloilo City",
    "",
    "Iloilo, Iloilo City, Poblacion"
)
# "Flood Control" is a clear flood-related keyword
is_flood = True  ✅
```

---

### **Step 12: Validation** (lines 457-488)

```python
# Check all required fields
project_district_type = "city"  ✅
project_district = "Iloilo City 1st District"  ✅
project_barangay_municipality = "Poblacion"  ✅
```

**All validations pass!** ✅

---

### **Step 13: Final Output Record** (lines 494-519)

```json
{
  "source": "DIME",
  "project_name": "Construction of Flood Control Structure, Barangay Poblacion, Iloilo City",
  "contractor": "S-ANG CONSTRUCTION AND GENERAL TRADING, INC.",
  "amount": 15000000.00,
  "location": "Iloilo, Iloilo City, Poblacion",
  "year": 2022,
  "status": "Completed",
  
  "district_congressman": "Julienne Baronda",
  "district_match_type": "district",
  "district_match_score": 100,
  "congressman_district": "1st District Iloilo City",
  
  "contractor_congressman": null,
  "contractor_match_type": null,
  "contractor_match_score": 0,
  
  "project_district_type": "city",
  "project_district": "Iloilo City 1st District",
  "project_barangay_municipality": "Poblacion",
  
  "is_flood_related": true
}
```

**Note:** Even though contractor matched, `contractor_congressman` is `null` because it's the same as `district_congressman`. The system avoids duplication.

---

## Summary

✅ **District Match:** Found via barangay "Poblacion" in "Iloilo City 1st District"  
✅ **Contractor Match:** Found "S-ANG CONSTRUCTION" linked to same congressman  
✅ **Classification:**
- `project_district_type`: "city"
- `project_district`: "Iloilo City 1st District"
- `project_barangay_municipality`: "Poblacion"
✅ **Term Filtering:** Project year (2022) within congressman's term (2019-2025)  
✅ **Flood Detection:** Detected as flood-related

---

## Alternative Scenarios for Contractor Matching

### Scenario A: Contractor Matches Different Congressman

If "S-ANG" was linked to a different congressman (e.g., "John Doe" from another district):

```python
best_district_match = ("Julienne Baronda", "district", 100)
best_contractor_match = ("John Doe", "contractor", 50)
```

**Final output:**
```json
{
  "district_congressman": "Julienne Baronda",
  "contractor_congressman": "John Doe",  // Different congressman!
  "contractor_congressman_district": "2nd District Some Province"
}
```

### Scenario B: Contractor Pattern Matching

If congressman has `contractor_patterns: ["S-ANG"]` instead of exact name:

```python
# In _find_congressman_by_contractor():
contractor_upper = "S-ANG CONSTRUCTION AND GENERAL TRADING, INC."

# Try substring match
for pattern, cm_list in contractor_lookup.items():
    if "S-ANG" in contractor_upper:  # Pattern found!
        candidates.extend(cm_list)
        break
```

**Result:** Still matches via pattern! ✅

### Scenario C: Contractor Exclusions

If congressman has exclusions:
```python
contractor_exclusions = {
    "S-ANG": ["S-ANG OTHER COMPANY", "S-ANG DIFFERENT CORP"]
}
```

**What happens:**
- If contractor name is "S-ANG CONSTRUCTION AND GENERAL TRADING, INC."
- Checks if any exclusion matches: "S-ANG OTHER COMPANY" not in name ✅
- **Match is allowed** (exclusion doesn't apply)

But if contractor was "S-ANG OTHER COMPANY":
- Exclusion "S-ANG OTHER COMPANY" is found in name
- **Match is excluded** ❌

---

## Example 3: Contractor Pattern Matching (SUNWEST)

### Sample Project

```json
{
  "project_name": "Flood Control for Urban Core and Central District of Zamboanga City to include Pumping Station and RROW, Zamboanga City (Package II)",
  "province": "Zamboanga Del Sur",
  "city": "Zamboanga City",
  "barangay": "",
  "contractors": ["SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)"],
  "date_started": "2018-10-10",
  "cost": 198360500.00
}
```

---

## Step-by-Step Classification Process

### **Step 1: Extract Project Data** (lines 264-271)

```python
proj_province = "Zamboanga Del Sur"
proj_city = "Zamboanga City"
proj_barangay = ""  # Empty
proj_municipality = None  # "Zamboanga City" contains "CITY"

# Determine district type
is_city_district = True  # "CITY" in "Zamboanga City"
location_key = ""  # Since it's city district but no barangay, location_key is empty
```

**Result:**
- Province: `"Zamboanga Del Sur"`
- Location Key: `""` (empty - no barangay specified)
- District Type: **City district** (Zamboanga City)

---

### **Step 2: Extract Contractor** (lines 274-279)

```python
contractor_str = "SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)"
```

---

### **Step 3: Extract Project Year** (lines 282-294)

```python
date_field = "2018-10-10"
project_year = 2018  # Parsed from date_started
```

---

### **Step 4: District Lookup (O(1))** (lines 296-301)

Calls `_find_congressman_by_district()` with:
- `province = "Zamboanga Del Sur"`
- `municipality_barangay = ""` (empty - no barangay)
- `project_year = 2018`

#### Inside `_find_congressman_by_district()` (lines 2109-2195):

```python
province_upper = "ZAMBOANGA DEL SUR"
location_upper = ""  # Empty

# Step 4a: Try exact match
candidates = district_lookup.get(("ZAMBOANGA DEL SUR", ""), [])
# Looks for: (city, "") = ("ZAMBOANGA DEL SUR", "") - city-wide projects
```

**What happens:**
- Since `location_upper` is empty, it searches for city-wide matches
- Finds all congressmen representing Zamboanga City districts
- Checks if it's a lone district or multi-district

**Example match:**
```python
# Zamboanga City has multiple districts
total_districts_for_province = {"1ST", "2ND"}  # Multiple districts exist

# Candidates found:
candidates = [
    ("Mannix Dalipe", {
        "district_number": "1st",
        "provinces": ["Zamboanga City"],
        "is_city_district": True,
        "terms": [{"start": 2019, "end": 2025}]
    }),
    ("Jaime Cojuangco", {
        "district_number": "2nd",
        "provinces": ["Zamboanga City"],
        "is_city_district": True,
        "terms": [{"start": 2019, "end": 2025}]
    })
]

# Since multiple districts exist and no specific barangay, prefers 1st district
# Returns: ("Mannix Dalipe", 100)
```

#### Step 4b: Term Filtering (lines 2131-2147)

```python
# Check if project_year (2018) falls within congressman's term
term = {"start": 2019, "end": 2025}
if 2019 <= 2018 <= 2025:  # False - 2018 is before term
    # This candidate is filtered out
```

**Result:** Candidate filtered out (project year 2018 is before term 2019-2025) ❌

**Fallback:** System tries other congressmen or falls back to province-only match

**For this example, let's assume:** Falls back to province-only match or finds another congressman whose term includes 2018

**Final district match:** `("Some Congressman", 10)` (fallback match with lower score)

---

### **Step 5: Contractor Lookup (O(1))** (lines 303-308)

Calls `_find_congressman_by_contractor()` with:
- `contractor_name = "SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)"`

#### Inside `_find_congressman_by_contractor()` (lines 2197-2240):

```python
contractor_upper = "SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)"
normalized = "SUNWEST INC FORMERLY SUNWEST CONSTRUCTION DEVELOPMENT CORPORATION"  # Removed special chars

# Step 5a: Try exact match
candidates = contractor_lookup.get("SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)", [])
# No exact match found
```

**Step 5b: Try normalized match**
```python
candidates = contractor_lookup.get("SUNWEST INC FORMERLY SUNWEST CONSTRUCTION DEVELOPMENT CORPORATION", [])
# Still no match
```

**Step 5c: Try substring/pattern match** (lines 2216-2221)
```python
# Check if any pattern in contractor_lookup matches
for pattern, cm_list in contractor_lookup.items():
    if "SUNWEST" in contractor_upper:  # Pattern "SUNWEST" found!
        candidates.extend(cm_list)
        break
```

**What happens:**
- The `contractor_lookup_dict` contains patterns like "SUNWEST" linked to congressmen
- Contractor links come from three sources:
  1. **Database (`contractor_dynasty_matches` table)**: Direct contractor-to-congressman links
  2. **Config file (`family_connections.contractors`)**: Family-linked contractors from `dynasty-projects-config.json`
  3. **Party contractors**: Contractors linked via party-list memberships
- If a congressman has `contractor_patterns: ["SUNWEST"]` or a contractor name containing "SUNWEST", it's in the lookup
- The substring match finds all congressmen linked to "SUNWEST" pattern

**Example:**
- Congressman "Zaldy Co" has `contractor_patterns: ["SUNWEST"]` or `contractors: ["SUNWEST CONSTRUCTION"]` (from database or config)
- This creates entry: `"SUNWEST"` → `[("Zaldy Co", cm_data)]`

```python
candidates = [("Zaldy Co", {
    "district_number": "Lone District",
    "provinces": ["Las Piñas City"],
    "contractor_patterns": ["SUNWEST"],
    "contractor_exclusions": {}
})]
```

#### Step 5d: Check Exclusions (lines 2224-2238)

```python
contractor_exclusions = cm_data.get('contractor_exclusions', {})
# Example: {"SUNWEST": ["SUNWEST OTHER COMPANY"]}  # Exclude if name contains both
excluded = False

# Check if contractor should be excluded
# "SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)" 
# doesn't contain "SUNWEST OTHER COMPANY", so:
excluded = False
```

**Result:** No exclusions match ✅

#### Step 5e: Return Match (line 2238)

```python
return ("Zaldy Co", 50)  # (congressman_name, match_score)
# Note: Contractor matches have score 50 (lower than district match score 100)
```

---

### **Step 6: Format Matches** (lines 310-316)

```python
best_district_match = ("Some Congressman", "district", 10)  # Fallback match
best_contractor_match = ("Zaldy Co", "contractor", 50)  # SUNWEST pattern match
```

**Note:** Different congressmen! District match is for Zamboanga City, contractor match is for Las Piñas City (Zaldy Co).

---

### **Step 7: Fallback Logic** (lines 318-334)

```python
# Check if we need fallback
if not best_district_match and not best_contractor_match:
    # ... (not needed, we have both matches)
```

**Result:** No fallback needed ✅

---

### **Step 8: Extract District Congressman Info** (lines 364-382)

```python
district_congressman = "Some Congressman"
district_match_type = "district"
district_match_score = 10  # Lower score (fallback match)

# Build congressman_district
cm_data = congressmen_data["Some Congressman"]
district_number = "1st"
provinces = ["Zamboanga City"]
congressman_district = "1st District Zamboanga City"
```

---

### **Step 9: Extract Contractor Congressman Info** (lines 384-401)

```python
contractor_cm = "Zaldy Co"
# Always set contractor_congressman (even if same as district - for accurate counts)
contractor_congressman = "Zaldy Co"  # ✅ Always set now!

# Build contractor_congressman_district
cm_data = congressmen_data["Zaldy Co"]
district_number = "Lone District"
provinces = ["Las Piñas City"]
contractor_congressman_district = "Lone District Las Piñas City"
```

**Result:** Both congressmen are set! ✅

---

### **Step 10: Determine Project Classification** (lines 403-425)

```python
# project_district_type
project_province = "Zamboanga Del Sur"
project_city = "Zamboanga City"
# "CITY" in location, so:
project_district_type = "city"  ✅

# project_district
district_congressman = "Some Congressman"
cm_data = congressmen_data["Some Congressman"]
district_number = "1st"
province_name = "Zamboanga City"
project_district = "Zamboanga City 1st District"  ✅

# project_barangay_municipality
project_barangay = ""  # No barangay specified
# Falls back to extracting from location or using city name
project_barangay_municipality = "Zamboanga City"  ✅ (or extracted from project name)
```

---

### **Step 11: Flood Detection** (lines 450-455)

```python
is_flood = self._is_flood_related(
    "Flood Control for Urban Core and Central District of Zamboanga City to include Pumping Station and RROW, Zamboanga City (Package II)",
    "",
    "Zamboanga Del Sur, Zamboanga City"
)
# "Flood Control" is a clear flood-related keyword
is_flood = True  ✅
```

---

### **Step 12: Validation** (lines 457-488)

```python
# Check all required fields
project_district_type = "city"  ✅
project_district = "Zamboanga City 1st District"  ✅
project_barangay_municipality = "Zamboanga City"  ✅
```

**All validations pass!** ✅

---

### **Step 13: Final Output Record** (lines 494-519)

```json
{
  "source": "DIME",
  "project_name": "Flood Control for Urban Core and Central District of Zamboanga City to include Pumping Station and RROW, Zamboanga City (Package II)",
  "contractor": "SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)",
  "amount": 198360500.00,
  "location": "Zamboanga Del Sur, Zamboanga City",
  "year": 2018,
  "status": "Completed",
  
  "district_congressman": "Some Congressman",
  "district_match_type": "district",
  "district_match_score": 10,
  "congressman_district": "1st District Zamboanga City",
  
  "contractor_congressman": "Zaldy Co",
  "contractor_match_type": "contractor",
  "contractor_match_score": 50,
  "contractor_congressman_district": "Lone District Las Piñas City",
  
  "project_district_type": "city",
  "project_district": "Zamboanga City 1st District",
  "project_barangay_municipality": "Zamboanga City",
  
  "is_flood_related": true
}
```

**Key Points:**
- ✅ **Two different congressmen** are linked to this project
- ✅ **District match:** "Some Congressman" (via location in Zamboanga City)
- ✅ **Contractor match:** "Zaldy Co" (via SUNWEST pattern matching)
- ✅ Both are tracked separately for accurate statistics

---

## Summary

✅ **District Match:** Found via city-wide match in "Zamboanga City 1st District" (fallback, lower score)  
✅ **Contractor Match:** Found "Zaldy Co" via SUNWEST pattern matching  
✅ **Classification:**
- `project_district_type`: "city"
- `project_district`: "Zamboanga City 1st District"
- `project_barangay_municipality`: "Zamboanga City"
✅ **Two Congressmen:** Project linked to both district and contractor congressmen (different people)  
✅ **Flood Detection:** Detected as flood-related

---

## Key Differences: Pattern Matching vs Exact Match

### Pattern Matching (SUNWEST):
- Searches for substring "SUNWEST" in contractor name
- Matches: "SUNWEST CONSTRUCTION", "SUNWEST, INC.", "SUNWEST DEVELOPMENT", etc.
- More flexible than exact match
- Used when congressman has `contractor_patterns: ["SUNWEST"]`

### Exact Match (S-ANG):
- Searches for exact contractor name or normalized version
- Matches: "S-ANG CONSTRUCTION AND GENERAL TRADING, INC." exactly
- More precise, less flexible
- Used when congressman has `contractors: ["S-ANG CONSTRUCTION AND GENERAL TRADING, INC."]`

Both approaches ensure contractor links are properly tracked for accurate statistics!

---

## Where Contractor Links Come From

Contractor links are loaded from **three sources** (in order of priority):

### 1. Database: `contractor_dynasty_matches` Table (Primary Source)
- **Source:** PostgreSQL `dynasty` database
- **Table:** `contractor_dynasty_matches`
- **Fields:** `dynasty_first_name`, `dynasty_last_name`, `company_name`, `role`
- **How it works:** Direct links between contractors and congressmen based on verified relationships
- **Example:** If "Zaldy Co" is linked to "SUNWEST CONSTRUCTION" in this table, all SUNWEST projects match to Zaldy Co
- **Code:** Lines 1791-1799 in `generate_dynasty_projects_cache_duckdb.py`

### 2. Config File: `family_connections.contractors` (Exported from DB)
- **Source:** `dynasty-projects-config.json` (exported from database)
- **Database Table:** `dynasty_projects_congressmen_config.family_connections` (JSON field)
- **Export Script:** `scripts/export_dynasty_json_from_db.py`
- **How it works:** 
  - The `family_connections.contractors` field in the database is populated from `contractor_dynasty_matches`
  - The JSON file is exported from `dynasty_projects_congressmen_config` table
  - **Note:** The JSON is a cached/exported version - the database is the source of truth
- **Path in JSON:** `target_congressmen[].family_connections.contractors[]`
- **Code:** Lines 1957-1963 in `generate_dynasty_projects_cache_duckdb.py`

### 3. Party Contractors
- **Source:** PostgreSQL `dynasty` database
- **Tables:** `party_list_members` + `political_dynasties`
- **How it works:** Contractors linked via party-list memberships
- **Example:** If a congressman is a party-list member, contractors associated with that party are linked
- **Code:** Lines 1972-1977 in `generate_dynasty_projects_cache_duckdb.py`

### How Patterns Are Generated

From each contractor name, the system generates **patterns** using `_expand_patterns()`:
- Base name: "SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION"
- Patterns generated:
  - "SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION" (full name)
  - "SUNWEST CONSTRUCTION DEVELOPMENT CORPORATION" (removed parentheses)
  - "SUNWEST" (substring, minimum 3 chars)
  - "CONSTRUCTION" (substring)
  - "DEVELOPMENT" (substring)
  - etc.

These patterns are stored in `contractor_lookup_dict` for O(1) matching!

### Example: SUNWEST → Zaldy Co

1. **Database lookup (Primary):** Checks `contractor_dynasty_matches` table for "Zaldy Co" + "SUNWEST"
   - This is the primary source - loaded directly into `contractor_lookup_dict`
   
2. **Config lookup (Secondary):** Checks `family_connections.contractors` from JSON (which was exported from `dynasty_projects_congressmen_config` table)
   - The JSON is just a cached version - the database table is the source of truth
   - The `family_connections.contractors` field in the database is populated from `contractor_dynasty_matches`
   
3. **Pattern matching:** When project has "SUNWEST, INC.", it matches the "SUNWEST" pattern
   - Patterns are generated from contractor names using `_expand_patterns()`
   - Stored in `contractor_lookup_dict` for O(1) matching
   
4. **Result:** Project is linked to "Zaldy Co" via contractor match ✅

**Important:** The JSON config file (`dynasty-projects-config.json`) is **built from the database** via `scripts/export_dynasty_json_from_db.py`. The database (`contractor_dynasty_matches` and `dynasty_projects_congressmen_config`) is the **source of truth**.

