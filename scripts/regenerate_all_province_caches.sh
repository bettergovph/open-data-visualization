#!/bin/bash
# Regenerate all province caches with Infrawatch/Microsite data

set -a
source /home/joebert/open-data-visualization/.env >/dev/null 2>&1 || true
set +a

cd /home/joebert/open-data-visualization

# Get list of provinces from existing cache directories
# Use the full directory name without splitting on hyphens
provinces=$(find static/data -type d -name "province-projects-*" -printf '%f\n' | \
    sed 's/^province-projects-//' | \
    sort)

total=$(echo "$provinces" | wc -l)
current=0

echo "🚀 Regenerating $total province caches with Infrawatch/Microsite data..."
echo ""

for province_slug in $provinces; do
    current=$((current + 1))
    # Convert slug back to province name: "davao-del-norte" -> "Davao del Norte"
    province=$(echo "$province_slug" | sed 's/-/ /g' | awk '{for(i=1;i<=NF;i++){$i=toupper(substr($i,1,1)) tolower(substr($i,2))}}1')
    echo "[$current/$total] Processing: $province"
    python3 scripts/generate_province_projects_cache.py "$province" 2>&1 | grep -E "(Found|Total projects|SSP:|DIME:|PhilGEPS:|Microsite:|Total cost:|Cache generated)"
    echo ""
done

echo "✅ All province caches regenerated!"
