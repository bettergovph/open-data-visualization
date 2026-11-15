#!/usr/bin/env python3
"""Build a Good / unassessed bridge-rehabilitation chart with a historical repeat cross-check."""
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / 'static/nep-preview/bridge-rehabilitation-review.json'
REPEATS = ROOT / 'static/nep-preview/repeat-hgab-historical-gaa.json'
OUTPUT = ROOT / 'static/data/dpwh-bridge-rehab-focus.json'
GROUPS = {
    'Good · assessment year unknown': 'Good condition in inventory',
    'No inventory condition match': 'No inventory condition match',
}


def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    value = re.sub(r'\bk\s*(\d+)\s*\+', r'\1+', value)
    value = re.sub(r'\(\s*-\s*(\d+)\s*\)', r'negative \1', value)
    for old, new in [('brgy', 'barangay'), ('rd', 'road'), ('br', 'bridge'), ('ave', 'avenue'), ('st', 'street')]:
        value = re.sub(r'\b' + old + r'\b', new, value)
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def main():
    review = json.loads(REVIEW.read_text())
    repeat_data = json.loads(REPEATS.read_text())
    repeat_rows = repeat_data['rows']
    repeat_keys = defaultdict(list)
    for row in repeat_rows:
        repeat_keys[normalize(row.get('projectName'))].append(row)

    output_groups = []
    for condition, label in GROUPS.items():
        rows = [row for row in review['projects'] if row.get('inventoryCondition') == condition]
        matched = [row for row in rows if repeat_keys.get(normalize(row.get('project')))]
        repeat_observations = [prior for row in matched for prior in repeat_keys[normalize(row.get('project'))]]
        output_groups.append({
            'label': label,
            'projectRows': len(rows),
            'allocationPesos': sum(float(row.get('allocationPesos') or 0) for row in rows),
            'exactHistoricalRepeatProjectRows': len(matched),
            'historicalRepeatObservations': len(repeat_observations),
            'conditionStatus': condition,
        })

    result = {
        'generatedAtUtc': review.get('transparencySnapshotRetrievedAtUtc'),
        'reviewProjectRows': review['summary']['projects'],
        'priorGaaYears': repeat_data['summary']['years'],
        'groups': output_groups,
        'repeatMethod': repeat_data['method'],
        'limits': [
            'Good inventory labels have no assessment date in the matched records; they do not establish current condition.',
            'No inventory condition match means no supported condition match in this crosswalk. It does not establish that the bridge was never surveyed or is in poor condition.',
            'The repeat cross-check counts exact normalized titles with qualified locality matches already included in the historical HGAB-to-GAA dataset. It can miss related work described with a different title, segment, or scope.',
            'Listed allocations are proposed budget amounts, not verified spending or completed work.',
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps({'groups': output_groups, 'outputBytes': OUTPUT.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()
