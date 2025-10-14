# Data Comparison Report: MeiliSearch vs PhilGEPS CSV Files

**Date:** October 14, 2025  
**Analysis:** Comparing flood control data sources

---

## Summary

**NO, the CSV does NOT match what's in MeiliSearch.** They are **completely different datasets** from different sources serving different purposes.

---

## Dataset 1: MeiliSearch (`bettergov_flood_control` index)

**Source:** DPWH Flood Control Infrastructure Projects (Geodata)

**Statistics:**
- **Documents:** 9,855 projects
- **Total Cost:** ₱547,603,497,105.14
- **Unique Contractors:** 2,409
- **Years:** 2018-2025
- **Regions:** 16

**Fields:**
```
GlobalID, ProjectDescription, InfraYear, Region, Province, 
Municipality, TypeofWork, Contractor, ContractCost, 
DistrictEngineeringOffice, LegislativeDistrict, ContractID, 
ProjectID, Latitude, Longitude
```

**Example Record:**
```
GlobalID: 79e8be69-90ab-488d-bf10-9204d41338ab
Description: Construction of Babuyan River Flood Control Structure Downstream (RS), Palawan
Contractor: AZARRAGA CONSTRUCTION
Cost: 17,961,569.07
Year: 2024
Region: Region IV-B
Province: PALAWAN
Coordinates: Available for mapping
```

**Purpose:** Infrastructure project mapping and visualization with geographic coordinates

---

## Dataset 2: PhilGEPS Contracts CSV Files

**Source:** PhilGEPS Government Procurement/Contract Awards Platform

### File 1: `contracts_export_ALL_DATA.csv`
- **Size:** 1.3 GB
- **Records:** ~5,003,469 contracts (ALL government contracts)
- **Scope:** All procurement categories

### File 2: `contracts_export_flood_control_data.csv` 
- **Size:** 34 MB  
- **Records:** 104,819 contracts (filtered subset)
- **Scope:** Flood control related contracts only (~2% of ALL_DATA)

**Fields:**
```
reference_id, contract_no, award_title, notice_title, awardee_name, 
organization_name, area_of_delivery, business_category, 
contract_amount, award_date, award_status
```

**Example Record:**
```
Contract No: I-08-2024-0719
Awardee: MCTEL ENGINEERING SERVICES
Organization: MUNICIPALITY OF SALUG, ZAMBOANGA DEL NORTE
Amount: 898,330.19
Date: 2025-09-23
Area: Zamboanga Del Norte
Category: Construction Projects
Status: active
```

**Purpose:** Procurement tracking and contract monitoring (no geographic coordinates)

---

## Key Differences

| Aspect | MeiliSearch (DPWH) | CSV Files (PhilGEPS) |
|--------|-------------------|---------------------|
| **Data Source** | DPWH Infrastructure Geodata | PhilGEPS Procurement Platform |
| **Record Count** | 9,855 projects | 104,819 flood contracts / 5M total |
| **Field Structure** | Infrastructure-focused with GPS | Procurement-focused (no GPS) |
| **Geographic Data** | ✅ Latitude/Longitude included | ❌ No coordinates |
| **Primary Use** | Map visualization, project tracking | Contract awards, procurement analysis |
| **Years Coverage** | 2018-2025 | Broader range (includes future dates) |
| **Contractor Info** | Contractor name only | Awardee name + Organization |
| **Unique IDs** | GlobalID (GUID) | reference_id, contract_no |

---

## Data Relationship

```
PhilGEPS (5M contracts)
  └── Flood Control Subset (104K contracts) ≠ MeiliSearch DPWH Data (9.8K projects)
```

**These are NOT the same data:**
- PhilGEPS includes ALL flood control procurement (materials, services, construction, etc.)
- MeiliSearch contains only DPWH infrastructure projects with geographic coordinates
- There may be SOME overlap (DPWH projects that were awarded through PhilGEPS)
- But they track different aspects of flood control work

---

## Current State

✅ **MeiliSearch:** 
- Operational at `http://127.0.0.1:7700`
- Index: `bettergov_flood_control`
- Used by `/flood` visualization page
- Data is actively served to frontend

❌ **PhilGEPS CSV Files:**
- Located in `/database/` folder
- NOT imported into MeiliSearch
- NOT indexed or searchable
- NO import scripts found in codebase
- Appears to be raw data awaiting processing

---

## Recommendations

### Option 1: Import PhilGEPS Data to New Index
Create a separate MeiliSearch index for PhilGEPS contracts:
- Index name: `bettergov_philgeps_contracts` or `bettergov_flood_contracts`
- Would allow contract-level procurement analysis
- Could complement existing DPWH infrastructure data

### Option 2: Cross-Reference Analysis
- Match PhilGEPS contracts to DPWH projects
- Link procurement awards with actual infrastructure
- Identify discrepancies between awarded contracts and completed projects

### Option 3: Database Import
- Import to PostgreSQL for relational analysis
- Join with existing budget/NEP/DIME data
- More suitable for large-scale data analytics (5M rows)

---

## Conclusion

The `contracts_export_flood_control_data.csv` (104K rows) is a **filtered subset** of `contracts_export_ALL_DATA.csv` (5M rows), containing only flood control related procurement contracts from PhilGEPS.

This CSV data **does NOT match** and is **not synchronized with** MeiliSearch, which contains a completely different dataset (DPWH infrastructure geodata).

Both datasets are valuable for different purposes:
- **MeiliSearch** = "Where are the flood control projects?"
- **PhilGEPS CSV** = "What flood control contracts were awarded?"

---

**Generated by:** data comparison analysis script  
**Files Analyzed:** 
- `/database/contracts_export_ALL_DATA.csv` (1.3GB, 5M rows)
- `/database/contracts_export_flood_control_data.csv` (34MB, 104K rows)  
- MeiliSearch `bettergov_flood_control` index (9,855 docs)

