#!/usr/bin/env python3
"""Build exact historical MPB title-match counts for the landing-page chart."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "static/nep-preview/mpb-barangay-base-data.json"
SUMMARY = ROOT / "static/nep-preview/mpb-simple-data.json"
OUTPUT = ROOT / "static/data/mpb-historical-multiplicity.json"

source_bytes = SOURCE.read_bytes()
base = json.loads(source_bytes)
summary = json.loads(SUMMARY.read_text())['history2015To2026']
counts = {str(n): 0 for n in range(9)}
counts['9+'] = 0
for place in base['barangays']:
    appearances = sum(
        any(2015 <= int(entry.get('year') or 0) <= 2026 for entry in title.get('levelHistory', []))
        for title in place.get('buildings', [])
    )
    bucket = str(appearances) if appearances <= 8 else '9+'
    counts[bucket] += 1

if sum(counts.values()) != summary['officialBarangays']:
    raise ValueError('Exact repeat counts do not reconcile with the official barangay universe')
if counts['0'] != summary['none']:
    raise ValueError('Zero-match count does not reconcile with the summary')
if sum(counts[str(n)] for n in range(1, 4)) != summary['oneToThree']:
    raise ValueError('One-to-three counts do not reconcile with the summary')
if sum(counts[str(n)] for n in range(4, 9)) + counts['9+'] != summary['fourOrMore']:
    raise ValueError('Four-or-more counts do not reconcile with the summary')

output = {
    'period': 'FY2015–FY2026',
    'officialBarangays': summary['officialBarangays'],
    'countDefinition': 'Distinct normalized project title and official barangay identity pairs with at least one match in the period.',
    'counts': counts,
    'source': 'mpb-barangay-base-data.json',
    'sourceSha256': hashlib.sha256(source_bytes).hexdigest(),
}
OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
print(f"Wrote {OUTPUT.relative_to(ROOT)} · {sum(counts.values()):,} barangays · {counts}")
