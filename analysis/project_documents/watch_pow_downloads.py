#!/usr/bin/env python3
"""Continuously parse completed POW downloads using the current POW parser."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CODE = re.compile(r'^2027DPWH-Proposal-\d{5}$')
DEFAULT_ROOT = os.environ.get('DPWH_STATUS_ROOT')

def utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False) + '\n')
    temporary.replace(path)

def ledger_rows(ledger):
    found = {}
    with ledger.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get('status') != 'downloaded' or str(record.get('documentType', '')).strip().casefold() != 'pow':
                continue
            code, document_id, signature = record.get('projectCode', ''), str(record.get('documentId', '')), str(record.get('signature', ''))
            if not CODE.fullmatch(code) or not document_id.isdigit() or not re.fullmatch(r'[a-f0-9]{64}', signature):
                continue
            found[(code, document_id, signature)] = record
    return sorted(found.values(), key=lambda r: (r.get('at', ''), r['projectCode'], str(r['documentId'])))

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--root', type=Path, default=Path(DEFAULT_ROOT) if DEFAULT_ROOT else None)
    cli.add_argument('--interval', type=int, default=20)
    cli.add_argument('--once', action='store_true')
    args = cli.parse_args()
    if args.root is None:
        raise SystemExit('Set DPWH_STATUS_ROOT or pass --root.')
    root, ledger = args.root, args.root / 'attachments' / 'downloads.jsonl'
    result_root = root / 'parsed_pow'
    status_path = root / 'pow-parser-watcher-status.json'
    if not ledger.is_file():
        raise SystemExit(f'Download ledger not found: {ledger}')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from analysis.project_documents.pow import parse_pdf
    import pymupdf  # Fail before consuming the queue if the document parser runtime is absent.
    parser_version = hashlib.sha256(Path(__file__).with_name('pow.py').read_bytes()).hexdigest()
    prior, _ = (None, None)
    try:
        prior = json.loads(status_path.read_text())
    except (OSError, ValueError):
        pass
    lifetime = {
        'parserVersion': parser_version,
        'processed': int(prior.get('processed', 0)) if prior and prior.get('parserVersion') == parser_version else 0,
        'skippedCurrent': 0,
        'errors': int(prior.get('errors', 0)) if prior and prior.get('parserVersion') == parser_version else 0,
        'rows': int(prior.get('rows', 0)) if prior and prior.get('parserVersion') == parser_version else 0,
        'categories': int(prior.get('categories', 0)) if prior and prior.get('parserVersion') == parser_version else 0,
        'startedAtUtc': prior.get('startedAtUtc') if prior and prior.get('parserVersion') == parser_version else utc(),
        'current': None,
    }
    completed = {}
    while True:
        records = ledger_rows(ledger)
        pending = []
        for record in records:
            key = (record['projectCode'], str(record['documentId']), record['signature'])
            output_dir = result_root / key[0] / (key[1] + '-' + key[2][:16])
            marker_path = output_dir / 'status.json'
            if key in completed:
                continue
            try:
                marker = json.loads(marker_path.read_text())
                if marker.get('status') == 'parsed' and marker.get('parseStatus') != 'parser_dependency_missing' and marker.get('parserVersion') == parser_version and marker.get('sourceSha256') == record.get('sha256'):
                    completed[key] = marker
                    continue
            except (OSError, ValueError):
                pass
            pending.append(record)
        successful = [value for value in completed.values() if value.get('status') == 'parsed']
        lifetime['skippedCurrent'] = len(successful)
        lifetime['processed'] = len(successful)
        lifetime['rows'] = sum(int(value.get('rows', 0) or 0) for value in successful)
        lifetime['categories'] = sum(int(value.get('categories', 0) or 0) for value in successful)
        lifetime['pending'] = len(pending)
        lifetime['totalDownloadedPow'] = len(records)
        lifetime['lastDownloaderRecordUtc'] = records[-1].get('at') if records else None
        lifetime['status'] = 'running' if pending else 'idle'
        lifetime['updatedAtUtc'] = utc()
        atomic_json(status_path, lifetime)
        if not pending:
            if args.once:
                return
            time.sleep(max(5, args.interval))
            continue
        record = pending[0]
        code, document_id = record['projectCode'], str(record['documentId'])
        output_dir = result_root / code / (document_id + '-' + record['signature'][:16])
        relative = Path(record.get('path', ''))
        pdf = (root / 'attachments' / relative).resolve()
        lifetime['current'] = {'projectCode': code, 'documentId': document_id, 'fileName': record.get('fileName')}
        lifetime['updatedAtUtc'] = utc()
        atomic_json(status_path, lifetime)
        marker = {'parserVersion': parser_version, 'sourceSha256': record.get('sha256')}
        try:
            if not pdf.is_file():
                raise FileNotFoundError(f'Ledger file is missing: {relative}')
            result = parse_pdf(pdf, output_dir / 'parser-work', None)
            parsed_at = utc()
            wrapped = {
                'projectCode': code, 'documentId': document_id,
                'documentType': record.get('documentType'), 'sourceFileName': record.get('fileName'),
                'sourceRelativePath': str(relative), 'sourceSha256': record.get('sha256'),
                'sourceUrl': record.get('url'), 'downloadedAtUtc': record.get('at'),
                'parsedAtUtc': parsed_at, 'parserVersion': parser_version,
                'allocationPesos': None,
                'allocationShareNote': 'NEP allocation not attached by this bulk parser; item amounts and printed POW summaries remain available.',
                **result,
            }
            atomic_json(output_dir / 'result.json', wrapped)
            marker.update({'status': 'parsed', 'parsedAtUtc': parsed_at, 'rows': int(result.get('uniqueCandidateRows', 0) or 0), 'categories': len(result.get('costCategoryBreakdown', []) or []), 'parseStatus': result.get('status')})
            lifetime['processed'] += 1
            lifetime['rows'] += marker['rows']
            lifetime['categories'] += marker['categories']
            lifetime['lastParsedAtUtc'] = parsed_at
            lifetime['lastResultStatus'] = result.get('status')
        except Exception as exc:
            marker.update({'status': 'error', 'atUtc': utc(), 'error': f'{type(exc).__name__}: {str(exc)[:240]}'})
            lifetime['errors'] += 1
            lifetime['lastError'] = f'{code} {document_id}: {marker["error"]}'
        atomic_json(output_dir / 'status.json', marker)
        completed[(code, document_id, record['signature'])] = marker
        lifetime['current'] = None
        lifetime['updatedAtUtc'] = utc()
        atomic_json(status_path, lifetime)
        if args.once and not pending[1:]:
            return

if __name__ == '__main__':
    main()
