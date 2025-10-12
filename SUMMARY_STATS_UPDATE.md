# Summary Statistics Update Documentation

## Overview

Summary statistics are stored in JSON files under `static/data/` to avoid hardcoding values in frontend templates and to optimize page load performance.

## Current Summary Files

- `static/data/budget_summary.json` - Budget analysis statistics
- `static/data/nep_summary.json` - NEP statistics  
- `static/data/dime_summary.json` - DIME infrastructure statistics
- `static/data/flood_summary.json` - Flood control statistics

## Manual Update

To manually update summary statistics:

```bash
cd /home/joebert/open-data-visualization
python3 utils/generate_summary_stats.py
```

Or using the convenience script:

```bash
./deployment/update_summary_stats.sh
```

## What Gets Updated

The script queries the following databases and generates summary stats:

1. **Budget Analysis** (`budget_analysis` database)
   - Total items across years 2020-2025
   - Data source information
   - Date range

2. **NEP** (`nep` database)
   - Total items across years 2020-2026
   - Data source information
   - Date range

3. **DIME** (`dime` database)
   - Total project count from `projects` table
   - Data source information
   - Date range

4. **Flood Control** (MeiliSearch)
   - Total project count from MeiliSearch index `bettergov_flood_control`
   - Data source information
   - Date range

## Automatic Regeneration Options

### Option 1: Systemd Timer

Create a systemd timer to run the update script periodically:

**Service file**: `/etc/systemd/system/update-summary-stats.service`
```ini
[Unit]
Description=Update BetterGovPH Summary Statistics
After=network.target postgresql.service

[Service]
Type=oneshot
User=joebert
WorkingDirectory=/home/joebert/open-data-visualization
ExecStart=/home/joebert/open-data-visualization/deployment/update_summary_stats.sh
StandardOutput=journal
StandardError=journal
```

**Timer file**: `/etc/systemd/system/update-summary-stats.timer`
```ini
[Unit]
Description=Update Summary Statistics Daily

[Timer]
OnCalendar=daily
OnBootSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl enable update-summary-stats.timer
sudo systemctl start update-summary-stats.timer
```

### Option 2: Cron Job

Add to crontab (not recommended, prefer systemd timer):

```bash
# Update summary stats daily at 3 AM
0 3 * * * /home/joebert/open-data-visualization/deployment/update_summary_stats.sh >> /home/joebert/open-data-visualization/logs/summary_stats.log 2>&1
```

### Option 3: Application Startup

Run the update script as part of the application startup in `restart.sh`:

```bash
# Add after git pull, before building
echo "📊 Updating summary statistics..."
./deployment/update_summary_stats.sh
```

### Option 4: Post-Deploy Hook

Add to `deployment_mcp.py` as a post-deployment step to regenerate stats after successful deployment.

### Option 5: GitHub Actions

Create a workflow that runs periodically and commits updated JSON files:

```yaml
name: Update Summary Stats
on:
  schedule:
    - cron: '0 3 * * *'  # Daily at 3 AM UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  update-stats:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Generate summary stats
        run: python3 generate_summary_stats.py
      - name: Commit and push if changed
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
          git add static/data/*_summary.json
          git diff --staged --quiet || git commit -m "Update summary statistics"
          git push
```

## When to Update

Summary statistics should be updated:

- After importing new data into any database
- After significant database changes
- Daily (via automated task)
- After deployment (optional)
- On demand when discrepancies are noticed

## Dependencies

The `generate_summary_stats.py` script requires:

- `asyncpg` - for PostgreSQL queries
- `aiohttp` - for MeiliSearch API calls
- Access to all databases (budget_analysis, nep, dime)
- Access to MeiliSearch on `MEILI_HTTP_ADDR` (127.0.0.1:7700)
- Environment variables from `.env` file

## Current Status

- ✅ Script created: `generate_summary_stats.py`
- ✅ Convenience script: `deployment/update_summary_stats.sh`
- ✅ Templates updated to load from JSON files
- ✅ Fallback values in templates if JSON load fails
- ⏸️ Automatic regeneration: **NOT YET IMPLEMENTED** - waiting for decision on proper tool

## Notes

- JSON files are committed to git repository
- Changes to JSON files should trigger deployment to update production
- MeiliSearch must be accessible at `MEILI_HTTP_ADDR` for flood stats generation
- Database credentials must be in `.env` file

