#!/usr/bin/env python3
"""Build NEP and unpaired-removal document summary for dpwh.html.

Matches DPWH portal proposal metadata to the existing NEP removal-review rows
using normalized title, office and exact allocation. Unpaired rows remain review
candidates; they are not asserted to be confirmed deletions or replacements.
"""
import argparse
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = os.environ.get('DPWH_PROJECT_METADATA_ROOT')
TYPE_ALIASES = {'geotagged photos': 'Geotagged Photos'}

def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def build(project_data_path, source_root, output_path):
    project_data = json.loads(project_data_path.read_text())
    quality = next((r for r in project_data.get('quality', []) if str(r.get('fiscal_year')) == '2027'), {})
    removals = project_data.get('removals', {}).get('domestic', {}).get('rows', [])
    candidates = defaultdict(list)
    for row in removals:
        key = (normalize(row.get('nepTitle')), normalize(row.get('office')), int(row.get('nepPesos') or 0))
        candidates[key].append(row)

    matched = {}
    for entry in os.scandir(source_root):
        if not entry.is_dir() or not re.fullmatch(r'2027DPWH-Proposal-\d{5}', entry.name):
            continue
        metadata_path = Path(entry.path) / 'metadata.json'
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, ValueError):
            continue
        amount = round(float(metadata.get('amount') or 0) * 1000)
        key = (normalize(metadata.get('projectName')), normalize(metadata.get('office')), amount)
        rows = candidates.get(key, [])
        if len(rows) != 1:
            continue
        code = metadata.get('code') or entry.name
        matched[code] = {
            'code': code,
            'candidateId': rows[0].get('nepId'),
            'documents': metadata.get('documents') or [],
        }

    type_counts = Counter()
    extension_counts = Counter()
    projects_by_doc_count = Counter()
    matched_codes = set(matched)
    for code, project in matched.items():
        documents = project['documents']
        projects_by_doc_count[len(documents)] += 1
        for doc in documents:
            doc_id = str(doc.get('id'))
            label = str(doc.get('documentType') or 'Unlabelled').strip()
            label = TYPE_ALIASES.get(label.casefold(), label)
            type_counts[label] += 1
            extension = Path(str(doc.get('fileName') or '')).suffix.lower() or Path(str(doc.get('url') or '').split('?')[0]).suffix.lower() or 'unknown'
            extension_counts[extension] += 1


    buckets = [
        ('No listed documents', 0, 0),
        ('1–3 documents', 1, 3),
        ('4–6 documents', 4, 6),
        ('7+ documents', 7, float('inf')),
    ]
    by_project = [
        {'label': label, 'projects': sum(n for count, n in projects_by_doc_count.items() if lower <= count <= upper)}
        for label, lower, upper in buckets
    ]
    total_nep = int(float(quality.get('records') or 0))
    total_allocation = round(float(quality.get('total_amount') or 0))
    result = {
        'generatedAtUtc': utc_now(),
        'sources': {
            'nepQuality': 'dpwh-data.json · quality · fiscal year 2027',
            'removalCandidates': 'dpwh-data.json · removals.domestic.rows',
            'portalMetadata': 'DPWH Transparency project metadata snapshot',
        },
        'nepBaseline': {
            'fiscalYear': 2027,
            'projectRecords': total_nep,
            'totalAllocationPesos': total_allocation,
            'medianAllocationPesos': round(float(quality.get('median_amount') or 0)),
        },
        'unpairedNepDocuments': {
            'candidateRows': len(removals),
            'exactPortalMatches': len(matched),
            'projectsWithDocuments': len(matched) - projects_by_doc_count.get(0, 0),
            'projectsWithoutListedDocuments': projects_by_doc_count.get(0, 0),
            'documentRecordsListed': sum(type_counts.values()),
            'powRecords': sum(count for label, count in type_counts.items() if label.strip().casefold() == 'pow'),
            'documentTypes': [{'type': label, 'records': count} for label, count in type_counts.most_common()],
            'extensions': [{'extension': label, 'records': count} for label, count in extension_counts.most_common()],
            'projectsByDocumentCount': by_project,
            'matchingRule': 'Unique exact match on normalized proposal title, district office and allocation amount; all three fields must agree.',
            'candidateStatus': 'Unpaired NEP line · removal review; not a confirmed deletion or replacement.',
            'interpretation': 'These are portal-listed proposal documents associated with NEP lines that have no selected HGAB counterpart in this screen. They may be considered potentially stranded; this does not prove the project was replaced, that the documents were literally wasted, or that they have no continuing value.',
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + '.tmp')
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(output_path)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-data', type=Path, default=Path('static/nep-preview/dpwh-data.json'))
    parser.add_argument('--portal-projects', type=Path, default=Path(DEFAULT_ROOT) if DEFAULT_ROOT else None)
    parser.add_argument('--output', type=Path, default=Path('static/nep-preview/dpwh-nep-document-summary.json'))
    args = parser.parse_args()
    if args.portal_projects is None:
        raise SystemExit('Set DPWH_PROJECT_METADATA_ROOT or pass --portal-projects.')
    result = build(args.project_data, args.portal_projects, args.output)
    s = result['unpairedNepDocuments']
    print(f"NEP baseline: {result['nepBaseline']['projectRecords']:,} records · ₱{result['nepBaseline']['totalAllocationPesos']:,}")
    print(f"Unpaired removal candidates: {s['exactPortalMatches']:,}/{s['candidateRows']:,} exact portal matches · {s['documentRecordsListed']:,} listed document records · {s['powRecords']:,} POWs")

if __name__ == '__main__':
    main()
