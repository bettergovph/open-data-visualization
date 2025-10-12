# ⚠️ REMINDER: Update Summary Statistics After Data Import

## When to Update

After importing new data into any of these databases, run:

```bash
./deployment/update_summary_stats.sh
```

Or directly:

```bash
python3 utils/generate_summary_stats.py
```

## Databases That Need Stats Update

- ✅ Budget Analysis (`budget_analysis` database)
- ✅ NEP (`nep` database)
- ✅ DIME (`dime` database)
- ✅ Flood Control (MeiliSearch `bettergov_flood_control` index)

## What Gets Updated

The script updates these JSON files:
- `static/data/budget_summary.json`
- `static/data/nep_summary.json`
- `static/data/dime_summary.json`
- `static/data/flood_summary.json`

These files are used by frontend templates to display:
- Total project/item counts
- Data source information
- Date ranges

## After Running

Don't forget to commit and deploy the updated JSON files:

```bash
git add static/data/*_summary.json
git commit -m "Update summary statistics after data import"
git push
python3 deployment/deployment_mcp.py
```

---

**See `SUMMARY_STATS_UPDATE.md` for full documentation.**

