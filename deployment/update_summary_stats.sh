#!/bin/bash

# Update summary statistics JSON files
# Run this periodically via cron or systemd timer

cd /home/joebert/open-data-visualization

# Activate virtual environment
source venv/bin/activate

# Run the stats generation script
python3 utils/generate_summary_stats.py

echo "✅ Summary statistics updated at $(date)"

