#!/bin/bash
cd /home/joebert/open-data-visualization

files=(
  "static/data/congressman-projects-alfredo-marañon-iii/all-projects-cache.json"
  "static/data/congressman-projects-alfredo-marañon-iii/summary.json"
  "static/data/congressman-projects-aurelio-dueñas-gonzales-jr/all-projects-cache.json"
  "static/data/congressman-projects-aurelio-dueñas-gonzales-jr/summary.json"
  "static/data/congressman-projects-kid-peña/all-projects-cache.json"
  "static/data/congressman-projects-kid-peña/summary.json"
  "static/data/congressman-projects-mario-vittorio-mariño/all-projects-cache.json"
  "static/data/congressman-projects-mario-vittorio-mariño/summary.json"
  "static/data/congressman-projects-marvey-mariño/all-projects-cache.json"
  "static/data/congressman-projects-marvey-mariño/summary.json"
  "static/data/congressman-projects-ria-christina-fariñas/all-projects-cache.json"
  "static/data/congressman-projects-ria-christina-fariñas/summary.json"
  "static/data/congressman-projects-romulo-peña-jr/all-projects-cache.json"
  "static/data/congressman-projects-romulo-peña-jr/summary.json"
  "static/data/congressman-projects-shirlyn-bañas-nograles/all-projects-cache.json"
  "static/data/congressman-projects-shirlyn-bañas-nograles/summary.json"
)

for file in "${files[@]}"; do
  if [ -f "$file" ]; then
    rm "$file"
    echo "Deleted: $file"
  elif git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
    git rm "$file" 2>/dev/null && echo "Removed from git: $file" || echo "Could not remove: $file"
  else
    echo "Not found: $file"
  fi
done

