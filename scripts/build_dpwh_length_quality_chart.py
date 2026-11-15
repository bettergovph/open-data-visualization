#!/usr/bin/env python3
"""Summarize DPWH road and bridge title-length data-quality issues for the Roads & Bridges chart."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'static/nep-preview/cost-per-km-page-index.json'
COST_DATA = ROOT / 'static/nep-preview/cost-per-km-data.json'
OUTPUT = ROOT / 'static/data/dpwh-length-quality-chart.json'


def main():
    data = json.loads(SOURCE.read_text())
    fields = data['projectIndexFields']
    index = {name: fields.index(name) for name in ('category', 'lengthMeters', 'lengthStatus')}
    rows = data['projectIndexRows']
    summary = {row['category']: row for row in data['summary']}
    included = {'Roads': [], 'Bridges': []}
    for row in rows:
        category = row[index['category']]
        if category in included:
            included[category].append(row)

    statuses = {category: Counter(row[index['lengthStatus']] for row in category_rows)
                for category, category_rows in included.items()}
    short = {category: sum(1 for row in category_rows
                           if row[index['lengthMeters']] is not None
                           and 0 < float(row[index['lengthMeters']]) < 10)
             for category, category_rows in included.items()}
    coordinate_projects = json.loads(COST_DATA.read_text()).get('coordinateOnlyProjects', [])
    coordinate_examples = Counter(project['category'] for project in coordinate_projects)

    issues = [
        {'label': 'No usable title-stated length', 'roads': summary['Roads']['withoutLength'],
         'bridges': summary['Bridges']['withoutLength'], 'relation': 'overall'},
        {'label': 'Chainage points only · no connected range',
         'roads': statuses['Roads'].get('Station points only: no connected range', 0),
         'bridges': statuses['Bridges'].get('Station points only: no connected range', 0),
         'relation': 'subset'},
        {'label': 'Multiple routes · common station reference unverified',
         'roads': statuses['Roads'].get('Multiple routes: common station reference unverified', 0),
         'bridges': statuses['Bridges'].get('Multiple routes: common station reference unverified', 0),
         'relation': 'subset'},
        {'label': 'Partial or unresolved chainage notation',
         'roads': statuses['Roads'].get('Partial chainage: isolated station alongside ranges', 0)
                  + statuses['Roads'].get('Incomplete chainage: mixed bare and plus-form endpoints; units or kilometer component unresolved', 0),
         'bridges': statuses['Bridges'].get('Partial chainage: isolated station alongside ranges', 0)
                    + statuses['Bridges'].get('Incomplete chainage: mixed bare and plus-form endpoints; units or kilometer component unresolved', 0),
         'relation': 'subset'},
        {'label': 'Usable but very short stated range · under 10 m',
         'roads': short['Roads'], 'bridges': short['Bridges'], 'relation': 'review'},
        {'label': 'Coordinate endpoints only · no chainage in review example',
         'roads': coordinate_examples.get('Roads', 0), 'bridges': coordinate_examples.get('Bridges', 0),
         'relation': 'coordinates'},
    ]
    result = {
        'generatedAtUtc': data.get('generatedAtUtc'),
        'categories': {category: {'lineItems': summary[category]['lineItems']}
                       for category in ('Roads', 'Bridges')},
        'issues': issues,
        'notes': {
            'subset': 'Chainage-specific rows are included in the no-usable-length total.',
            'review': 'A range under 10 m is reviewable, not automatically invalid.',
            'coordinates': 'Counts are coordinate-only route examples in this review set. Endpoint separation is an approximation, not an aligned or chainage-measured length; coordinates never fill a missing stated length.',
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == '__main__':
    main()
