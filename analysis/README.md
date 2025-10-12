# NEP 2026 Analysis

This folder contains analysis scripts and documentation for detecting suspicious budget patterns in NEP 2026 using the Bulacan flood control scheme as a baseline.

## 📁 Files

### Analysis Scripts
- **`analyze_nep_2026_vs_flood_baseline.py`** - Main analysis script using flood control baseline (✅ USED)
- `nep_2026_pattern_analysis.py` - Initial pattern analysis (exploratory)
- `nep_2026_sudden_rise_analysis.py` - Sudden rise detection (exploratory)
- `nep_2026_vs_budget_history.py` - Budget history comparison (exploratory)

### Documentation
- **`NEP_2026_ANALYSIS_SUMMARY.md`** - Comprehensive analysis report with findings

## 🚨 Key Finding

**Road Infrastructure** in NEP 2026 shows **+61.9% increase** vs historical average (2020-2025), exceeding the flood control pattern threshold of ≥50% YoY growth.

## 📊 Visualizations

The analysis results are visualized on the NEP page:
- Go to `/nep` page
- Click on **"🚨 NEP 2026 Analysis"** tab
- View two charts:
  1. **Red Flag Chart** - Road Infrastructure spending pattern (2020-2026)
  2. **Baseline Chart** - Bulacan flood control pattern for reference (2020-2024)

## 📁 Data Files

JSON cache files are stored in `/static/data/`:
- `nep_2026_red_flag.json` - Road infrastructure red flag data
- `flood_baseline_pattern.json` - Bulacan flood control baseline pattern
- `nep_2026_overall_analysis.json` - Overall NEP 2026 statistics
- `nep_2026_infrastructure_categories.json` - Infrastructure category breakdown

## 🔄 Running the Analysis

```bash
# Make sure you're in the project root
cd /home/joebert/open-data-visualization

# Run the main analysis script
python3 analysis/analyze_nep_2026_vs_flood_baseline.py
```

## 📋 Flood Control Baseline Metrics

The following baseline was extracted from actual Bulacan flood control data:

| Metric | Value |
|--------|-------|
| **Bulacan Growth (2022→2023)** | +118% |
| **Typical YoY Growth** | +81% |
| **Alert Threshold** | ≥50% YoY |
| **Geographic Clustering** | 60% in 3 provinces |
| **Cost Disparity** | 2.6x (urban vs rural) |

## 🎯 Pattern Match

NEP 2026 shows **1 HIGH severity indicator**:
- Road Infrastructure: +61.9% growth vs historical avg (exceeds 50% threshold)

Overall NEP 2026 analysis:
- ✅ Overall budget growth: +7.4% (Normal)
- ✅ Geographic distribution: 27.2% in top 3 regions (Better than flood's 60%)
- ✅ Flood control spending: +33.6% (Below threshold)
- 🚨 Road infrastructure: +61.9% (ALERT)

## 💡 Recommendation

Investigate NEP 2026 road infrastructure budget allocations:
1. Geographic distribution by province
2. Specific projects and beneficiaries
3. Contractor selection patterns
4. Justification for 61.9% increase

---

**Author:** BetterGovPH Data Team  
**Date:** October 12, 2025  
**Repository:** https://github.com/bettergovph/open-data-visualization

