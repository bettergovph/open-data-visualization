# ✅ AHK Script Ready for Execution

**Date:** 2025-10-23 22:35:00
**Status:** Ready to process 1000 contractors

## 📋 Script Configuration

**File:** `sec_scraper/sec_search.ahk`
**Contractor List:** `sec_scraper/contractor_list_top1000.txt`
**Total Contractors:** 1000 (Clean contractor names directly from SEC database - NO SEC data, NOT previously searched)

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

## 🔝 Top 10 Contractors to be Scraped (Clean Names from Database)

1. LEGACY CONSTRUCTION CORPORATION (685 projects)
2. ST. TIMOTHY CONSTRUCTION CORPORATION (648 projects)
3. ALPHA & OMEGA GEN. CONTRACTOR & DEVELOPMENT CORP (587 projects)
4. QM BUILDERS (560 projects)
5. EGB CONSTRUCTION (451 projects)
6. J.B. FELIPE CONSTRUCTION (450 projects)
7. CENTERWAYS CONSTRUCTION AND DEVELOPMENT INC. (400 projects)
8. TOPNOTCH CATALYST BUILDERS INC. (397 projects)
9. ROYAL CROWN MONARCH CONSTRUCTION & SUPPLIES CORP (394 projects)
10. SUNWEST, INC (393 projects)

## ✅ Verification: All Contractors Need SEC Scraping

All 1000 contractors in the list have been filtered to ensure they:
- Have NO SEC data (sec_number is null) ✅
- Have NOT been previously searched with no results (status != 'NO_SEC_RESULTS') ✅
- Are clean contractor names directly from the database (no "FORMERLY:" or messy data) ✅

This means every contractor in the list needs to be scraped from the SEC database and has not been previously processed.

## 📊 Current Database State

- **Total Contractors:** 54
- **With SEC Data:** 41
- **NO SEC RESULTS:** 13 (suspicious)

## 🎯 Expected After This Run

If all 1000 complete successfully:
- **Total Contractors:** ~1054
- **With SEC Data:** ~800-900 (estimate)
- **NO SEC RESULTS:** ~100-200 (estimate)

## 🚀 How to Run

1. Navigate to Windows machine
2. Open `sec_scraper/sec_search.ahk`
3. Run the script (double-click or right-click → Run Script)
4. Script will:
   - Open Edge browser
   - Navigate to SEC website
   - Process 1000 contractors automatically
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

*Ready to process 61 high-priority contractors without SEC data!* 🎯
