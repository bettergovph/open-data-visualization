# ✅ AHK Script Ready for Execution

**Date:** $(date +"%Y-%m-%d %H:%M:%S")
**Status:** Ready to process 100 contractors

## 📋 Script Configuration

**File:** `sec_scraper/sec_search.ahk`
**Contractor List:** `sec_scraper/contractor_list_top100_no_sec.txt`
**Total Contractors:** 100 (from master list of 1,939)

## ✅ Key Features

### 1. Mouse Reset (Prevents Infinite Scrolling)
```ahk
MouseMove, 1, 1
Sleep, 300
```
Resets mouse to top-left corner at the start of each contractor loop.

### 2. Smart Skip
Checks if result file already exists and skips to next contractor.

### 3. Clean Navigation
- Escape + Shift+Tab to return to search field
- No redundant navigation

## 🔝 Top 10 Contractors to be Scraped

1. LEGACY CONSTRUCTION CORPORATION (133 projects)
2. EGB CONSTRUCTION CORPORATION (95 projects)
3. TOPNOTCH CATALYST BUILDERS INC (88 projects)
4. SUNWEST INC (79 projects)
5. HI-TONE CONSTRUCTION DEVELOPMENT CORP (61 projects)
6. MG SAMIDAN CONSTRUCTION (60 projects)
7. ROYAL CROWN MONARCH CONSTRUCTION SUPPLIES CORP (60 projects)
8. TRIPLE 8 CONSTRUCTION SUPPLY INC (60 projects)
9. WAWAO BUILDERS (60 projects)
10. LR TIQUI BUILDERS INC (59 projects)

## 📊 Current Database State

- **Total Contractors:** 54
- **With SEC Data:** 41
- **NO SEC RESULTS:** 13 (suspicious)

## 🎯 Expected After This Run

If all 100 complete successfully:
- **Total Contractors:** ~154
- **With SEC Data:** ~120-130 (estimate)
- **NO SEC RESULTS:** ~20-30 (estimate)

## 🚀 How to Run

1. Navigate to Windows machine
2. Open `sec_scraper/sec_search.ahk`
3. Run the script (double-click or right-click → Run Script)
4. Script will:
   - Open Edge browser
   - Navigate to SEC website
   - Process 100 contractors automatically
   - Save results to `sec_scraper/sec_results/`
   - Close browser when done

## 📝 After Completion

Run the parser to process results:
```bash
cd /home/joebert/open-data-visualization
python3 sec_scraper/sec_contractor_parser.py
python3 sec_scraper/generate_sec_json.py
```

---

*Ready to process 100 high-priority contractors!* 🎯
