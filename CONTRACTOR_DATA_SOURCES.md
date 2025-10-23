# Contractor Data Sources Documentation

## Overview

This document clarifies the different contractor data sources used across the BetterGovPH visualization platform and explains the confusion that can arise from having multiple contractor datasets.

## 🗄️ Three Main Databases

### 1. **Flood Control Database (MeiliSearch)**
- **Source**: DPWH Flood Control Projects
- **Contractor Field**: `Contractor`
- **Data Type**: Flood control infrastructure projects
- **Coverage**: ~9,855 projects, ~2,409 unique contractors
- **Used In**: `/flood` page
- **Standard Deviation Analysis**: ✅ Available (MeiliSearch contractors only)

### 2. **DIME Database (PostgreSQL)**
- **Source**: Digital Information for Monitoring and Evaluation
- **Contractor Field**: `contractors` (array field)
- **Data Type**: Major infrastructure projects
- **Coverage**: ~12,870 projects, contractors stored as arrays
- **Used In**: `/dime` page
- **Standard Deviation Analysis**: ❌ Not implemented

### 3. **PhilGEPS Database (PostgreSQL)**
- **Source**: Philippine Government Electronic Procurement System
- **Contractor Field**: `awardee_name`
- **Data Type**: Government procurement contracts
- **Coverage**: Large number of contracts, contractors as awardees
- **Used In**: `/contractors` page (SEC verification)
- **Standard Deviation Analysis**: ❌ Not implemented

## 📊 Venn Diagram Data Sources

The Venn diagram on `/contractors` shows the overlap between these three databases:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Flood Control │    │      DIME       │    │    PhilGEPS     │
│   (MeiliSearch) │    │  (PostgreSQL)   │    │  (PostgreSQL)   │
│                 │    │                 │    │                 │
│ Contractor:     │    │ contractors:    │    │ awardee_name:   │
│ "ABC Corp"      │    │ ["ABC Corp"]    │    │ "ABC Corp"      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Overlap Categories:
- **Flood Only**: Contractors appearing only in flood control projects
- **DIME Only**: Contractors appearing only in DIME projects  
- **PhilGEPS Only**: Contractors appearing only in PhilGEPS contracts
- **Flood + DIME**: Contractors in both flood and DIME
- **Flood + PhilGEPS**: Contractors in both flood and PhilGEPS
- **DIME + PhilGEPS**: Contractors in both DIME and PhilGEPS
- **All Three**: Contractors appearing in all three databases

## 🔍 Page-Specific Contractor Data

### `/flood` Page
- **Primary Source**: MeiliSearch flood control database
- **Contractor Analysis**: Standard deviation analysis of flood contractors
- **Data Scope**: ~2,409 unique contractors from flood projects
- **Chart**: Shows contractor project count distribution with standard deviation bars

### `/dime` Page  
- **Primary Source**: PostgreSQL DIME database
- **Contractor Analysis**: Basic contractor statistics
- **Data Scope**: All contractors from DIME projects
- **Chart**: General contractor distribution (no standard deviation analysis)

### `/contractors` Page
- **Primary Source**: SEC database (PostgreSQL)
- **Contractor Analysis**: SEC verification status
- **Data Scope**: All contractors across all three databases
- **Venn Diagram**: Shows overlap between Flood, DIME, and PhilGEPS
- **Standard Deviation**: 📝 TODO - Implement for ALL contractors

## ⚠️ Data Quality Challenges

### 1. **Name Inconsistencies**
- Same contractor may appear with different names:
  - "ABC Construction Corp."
  - "ABC Construction Corporation" 
  - "ABC CONSTRUCTION CORP"
  - "ABC Construction"

### 2. **Database Overlaps**
- Same project may appear in multiple databases
- Contractors may be counted multiple times
- Cross-database deduplication is complex

### 3. **Missing Data**
- PhilGEPS lacks location data
- Some contractors have no SEC registration
- Incomplete contractor information

## 📈 Standard Deviation Analysis

### Current Implementation (`/flood`)
- **Scope**: MeiliSearch flood contractors only
- **Data**: 10,547 contractors with project counts
- **Statistics**: Mean: 14.87, Std Dev: 34.52
- **Bars**: 1SD, 1.5SD, 2SD, 2.5SD, 3SD

### Planned Implementation (`/contractors`)
- **Scope**: ALL contractors across all databases
- **Data**: Combined contractor project counts
- **Statistics**: Will include cross-database analysis
- **Bars**: Same standard deviation levels

## 🔧 Technical Implementation

### Database Connections
```python
# Flood Control (MeiliSearch)
flood_client = FloodControlClient()

# DIME (PostgreSQL)
dime_conn = await asyncpg.connect(
    database='dime',
    # ... connection details
)

# PhilGEPS (PostgreSQL) 
philgeps_conn = await asyncpg.connect(
    database='philgeps',
    # ... connection details
)

# SEC (PostgreSQL)
sec_conn = await asyncpg.connect(
    database='sec',
    # ... connection details
)
```

### API Endpoints
- `/api/flood/statistics` - Flood contractor statistics
- `/api/dime/statistics` - DIME contractor statistics  
- `/api/contractors/venn` - Cross-database contractor overlap
- `/api/contractors/standard-deviation` - Standard deviation analysis

## 📝 TODO: Complete Implementation

### For `/contractors` Standard Deviation Analysis:

1. **Create Combined Analysis Script**
   ```python
   # utils/contractor_standard_deviation_all_databases.py
   # - Query all three databases
   # - Combine contractor project counts
   # - Calculate standard deviation across all data
   # - Generate comprehensive analysis
   ```

2. **Update API Endpoint**
   ```python
   # Add to visualization.py
   @app.get("/api/contractors/standard-deviation-all")
   async def get_all_contractors_standard_deviation():
       # Return analysis for ALL contractors
   ```

3. **Implement Chart**
   ```javascript
   // Add to contractors.html
   async function createAllContractorsDistributionChart() {
       // Load combined analysis
       // Display standard deviation bars
       // Show cross-database statistics
   }
   ```

## 🎯 Key Differences Summary

| Aspect | `/flood` | `/dime` | `/contractors` |
|--------|----------|---------|----------------|
| **Data Source** | MeiliSearch | PostgreSQL | All 3 DBs |
| **Contractor Count** | ~2,409 | Variable | All combined |
| **Standard Deviation** | ✅ Implemented | ❌ Not implemented | 📝 TODO |
| **Venn Diagram** | ❌ No | ❌ No | ✅ Yes |
| **Cross-DB Analysis** | ❌ No | ❌ No | ✅ Yes |

## 🔍 Troubleshooting

### Common Confusion Points:
1. **"Why are contractor counts different?"** - Different data sources and scopes
2. **"Why no standard deviation on /dime?"** - Not implemented yet
3. **"Why different statistics?"** - Different contractor datasets
4. **"Why Venn diagram only on /contractors?"** - Cross-database analysis requires all sources

### Data Validation:
- Always check which database is being queried
- Verify contractor name normalization
- Consider cross-database duplicates
- Account for missing data

---

**Last Updated**: January 27, 2025  
**Version**: 1.0  
**Maintainer**: BetterGovPH Development Team
