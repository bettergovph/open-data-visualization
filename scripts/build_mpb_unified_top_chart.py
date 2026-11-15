#!/usr/bin/env python3
"""Build a compact chart snapshot from the three unified MPB barangay rankings."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'static/nep-preview/mpb-barangay-index.json'
OUTPUT = ROOT / 'static/data/mpb-unified-top-chart.json'


def main():
    data = json.loads(SOURCE.read_text())
    periods = data['periods']
    final_period_index = max(range(len(periods)), key=lambda index: periods[index]['year'])
    records = []
    for row in data['barangayRows']:
        stats = row[6] or []
        cumulative = next((stat for stat in reversed(stats) if stat[0] <= final_period_index), None)
        if not cumulative:
            continue
        records.append({
            'barangay': row[1],
            'municipality': row[2],
            'province': row[3],
            'highestLevel': int(cumulative[5] or 0),
            'namedMPBs': int(cumulative[4] or 0),
            'allocationPesos': sum(float(stat[1] or 0) for stat in stats),
        })

    def top(metric):
        ranked = sorted(records, key=lambda item: (-item[metric], item['barangay'].casefold(), item['municipality'].casefold()))
        return [item for item in ranked if item[metric] > 0][:10]

    result = {
        'generatedAtUtc': data.get('generatedAtUtc'),
        'throughFiscalYear': periods[final_period_index]['year'],
        'officialBarangays': data.get('summary', {}).get('officialBarangays'),
        'tables': {
            'upgrades': {'label': 'Highest upgrade level', 'unit': 'level', 'rows': top('highestLevel')},
            'techTree': {'label': 'MPBs in barangay', 'unit': 'named MPB title matches', 'rows': top('namedMPBs')},
            'economy': {'label': 'Listed allocation · all years', 'unit': 'pesos', 'rows': top('allocationPesos')},
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f"Wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == '__main__':
    main()
