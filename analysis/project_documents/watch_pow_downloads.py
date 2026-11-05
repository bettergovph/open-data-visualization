#!/usr/bin/env python3
"""Continuously parse completed POW downloads using the current POW parser."""
import argparse
import hashlib
import json
import multiprocessing
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

CODE = re.compile(r'^2027DPWH-(?:Proposal|HGAB)-\d{5}$')
DEFAULT_ROOT = os.environ.get('DPWH_STATUS_ROOT')

def utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False) + '\n')
    temporary.replace(path)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False) + '\n')
    temporary.replace(path)


def ledger_rows(ledger):
    found = {}
    ledgers = (ledger, ledger.with_name('downloads-hgab.jsonl'))
    for source in ledgers:
        if not source.is_file():
            continue
        with source.open(encoding='utf-8') as stream:
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

def parse_one(record, root_value, result_root_value, parser_version, ocr_engine='apple_tesseract'):
    """Run one isolated PyMuPDF parse and save its result and marker."""
    root, result_root = Path(root_value), Path(result_root_value)
    code, document_id = record['projectCode'], str(record['documentId'])
    key = (code, document_id, record['signature'])
    output_dir = result_root / code / (document_id + '-' + record['signature'][:16])
    relative = Path(record.get('path', ''))
    marker = {'parserVersion': parser_version, 'sourceSha256': record.get('sha256')}
    try:
        pdf = (root / 'attachments' / relative).resolve()
        if not pdf.is_file():
            raise FileNotFoundError(f'Ledger file is missing: {relative}')
        from analysis.project_documents.pow import parse_pdf
        result = parse_pdf(pdf, output_dir / 'parser-work', None, ocr_engine=ocr_engine)
        parsed_at = utc()
        wrapped = {
            'projectCode': code, 'documentId': document_id,
            'documentType': record.get('documentType'), 'sourceFileName': record.get('fileName'),
            'sourceRelativePath': str(relative), 'sourceSha256': record.get('sha256'),
            'sourceUrl': record.get('url'), 'downloadedAtUtc': record.get('at'),
            'parsedAtUtc': parsed_at, 'parserVersion': parser_version,
            'ocrEngine': ocr_engine,
            'allocationPesos': None,
            'allocationShareNote': 'NEP allocation not attached by this bulk parser; item amounts and printed POW summaries remain available.',
            **result,
        }
        atomic_json(output_dir / 'result.json', wrapped)
        no_row_scans=[int(page['page']) for page in result.get('pages',[])
            if not int(page.get('rows') or 0) and (str(page.get('method') or '').startswith('OCR') or page.get('status')=='needs_ocr')]
        marker.update({'status': 'parsed', 'parsedAtUtc': parsed_at,
                       'rows': int(result.get('uniqueCandidateRows', 0) or 0),
                       'categories': len(result.get('costCategoryBreakdown', []) or []),
                       'parseStatus': result.get('status'),
                       'paddleFallbackNeeded': ocr_engine == 'apple_tesseract' and bool(no_row_scans) and not result.get('rows'),
                       'paddleFallbackPages':no_row_scans})
    except Exception as exc:
        marker.update({'status': 'error', 'atUtc': utc(),
                       'error': f'{type(exc).__name__}: {str(exc)[:240]}'})
    atomic_json(output_dir / 'status.json', marker)
    return key, marker

def parse_paddle_fallback(record, root_value, result_root_value, parser_version):
    """Use one dedicated PaddleOCR process for primary parses with no bill rows."""
    root, result_root = Path(root_value), Path(result_root_value)
    code, document_id = record['projectCode'], str(record['documentId'])
    key = (code, document_id, record['signature'])
    output_dir = result_root / code / (document_id + '-' + record['signature'][:16])
    result_path = output_dir / 'result.json'
    marker = {'parserVersion': parser_version, 'sourceSha256': record.get('sha256')}
    try:
        pdf = (root / 'attachments' / Path(record.get('path', ''))).resolve()
        if not pdf.is_file():raise FileNotFoundError('Ledger file is missing')
        primary=json.loads(result_path.read_text())
        from analysis.project_documents.pow import parse_pdf
        primary_marker=json.loads((output_dir/'status.json').read_text())
        paddle=parse_pdf(pdf,output_dir/'paddle-fallback',None,ocr_engine='paddle',
            page_numbers=set(primary_marker.get('paddleFallbackPages') or []))
        merged=dict(primary)
        merged['paddleFallback']={'status':paddle.get('status'),'rows':len(paddle.get('rows',[])),
            'pagesProcessed':paddle.get('pagesProcessed'),'engine':'PaddleOCR PP-OCRv6'}
        if paddle.get('rows'):
            fallback_pages={int(page['page']):page for page in paddle.get('pages',[]) if page.get('page') is not None}
            merged['pages']=[fallback_pages.get(int(page['page']),page) if int(page.get('page') or 0) in fallback_pages else page
                for page in primary.get('pages',[])]
            merged.update({k:paddle[k] for k in ('rows','uniqueCandidateRows','rowObservations',
                'sumOfUniqueCandidateAmountsPesos','status') if k in paddle})
            merged['pagesProcessed']=primary.get('pagesProcessed',paddle.get('pagesProcessed'))
            if paddle.get('costCategoryBreakdown'):
                categories={(int(row.get('sourcePage') or 0),str(row.get('label') or '').casefold()):row
                    for row in primary.get('costCategoryBreakdown',[])}
                categories.update({(int(row.get('sourcePage') or 0),str(row.get('label') or '').casefold()):row
                    for row in paddle.get('costCategoryBreakdown',[])})
                merged['costCategoryBreakdown']=list(categories.values())
            merged['ocrEngine']='apple_tesseract + PaddleOCR fallback'
        atomic_json(result_path,merged)
        parsed_rows=merged.get('rows') or []
        marker.update({'status':'parsed','parsedAtUtc':utc(),'rows':len(parsed_rows),
            'categories':len(merged.get('costCategoryBreakdown',[]) or []),'parseStatus':merged.get('status'),
            'paddleFallbackNeeded':False,'paddleFallbackStatus':paddle.get('status'),
            'paddleRowsRecovered':len(paddle.get('rows',[]) or [])})
    except Exception as exc:
        marker.update({'status':'parsed','parsedAtUtc':utc(),'rows':0,'categories':0,
            'parseStatus':'no_bill_rows_recovered','paddleFallbackNeeded':False,
            'paddleFallbackStatus':'error','error':f'{type(exc).__name__}: {str(exc)[:240]}'})
    atomic_json(output_dir/'status.json',marker)
    return key,marker


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--root', type=Path, default=Path(DEFAULT_ROOT) if DEFAULT_ROOT else None)
    cli.add_argument('--interval', type=int, default=20)
    cli.add_argument('--workers', type=int, default=1, help='primary Apple/Tesseract parser processes for new or unparsed PDFs')
    cli.add_argument('--paddle-workers', type=int, default=1, help='PaddleOCR processes for primary parses that recovered no bill rows')
    cli.add_argument('--once', action='store_true')
    cli.add_argument('--status', action='store_true', help='print the latest internal status and exit')
    args = cli.parse_args()
    if args.root is None:
        raise SystemExit('Set DPWH_STATUS_ROOT or pass --root.')
    if not 1 <= args.workers <= 7:
        cli.error('--workers must be between 1 and 7')
    if not 1 <= args.paddle_workers <= 7:
        cli.error('--paddle-workers must be between 1 and 7')
    root, ledger = args.root, args.root / 'attachments' / 'downloads.jsonl'
    result_root = root / 'parsed_pow'
    status_path = root / 'pow-parser-watcher-status.json'
    if args.status:
        try:
            print(json.dumps(json.loads(status_path.read_text()), ensure_ascii=False, indent=2))
        except (OSError, ValueError) as exc:
            raise SystemExit(f'Parser status is unavailable: {exc}')
        return
    if not ledger.is_file():
        raise SystemExit(f'Download ledger not found: {ledger}')
    import pymupdf  # Fail before consuming the queue if the document parser runtime is absent.
    parser_version = hashlib.sha256(Path(__file__).with_name('pow.py').read_bytes()).hexdigest()
    try:
        prior = json.loads(status_path.read_text())
    except (OSError, ValueError):
        prior = None
    same_version = prior and prior.get('parserVersion') == parser_version
    lifetime = {
        'parserVersion': parser_version,
        'processed': 0, 'skippedCurrent': 0,
        'errors': int(prior.get('errors', 0)) if same_version else 0,
        'rows': 0, 'categories': 0,
        'startedAtUtc': prior.get('startedAtUtc') if same_version else utc(),
        'workers': args.workers, 'active': [], 'current': None,
    }
    completed, observed, retry_after, active = {}, set(), {}, {}
    paddle_queue,paddle_active={},{}
    previous_download_checkpoint = str((prior or {}).get('lastDownloaderRecordUtc') or '')
    first_scan = True
    pool = ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context('spawn'))
    paddle_pool = ProcessPoolExecutor(max_workers=args.paddle_workers, mp_context=multiprocessing.get_context('spawn'))
    try:
        while True:
            # Harvest completed jobs first so newly arrived downloads can take priority immediately.
            for future, details in list(active.items()):
                if not future.done():
                    continue
                record, key, priority = details
                try:
                    returned_key, marker = future.result()
                    if returned_key != key:
                        raise RuntimeError('Parser worker returned a different document key')
                except Exception as exc:
                    marker = {'status': 'error', 'parserVersion': parser_version,
                              'sourceSha256': record.get('sha256'), 'atUtc': utc(),
                              'error': f'{type(exc).__name__}: {str(exc)[:240]}'}
                    output_dir = result_root / key[0] / (key[1] + '-' + key[2][:16])
                    atomic_json(output_dir / 'status.json', marker)
                completed[key] = marker
                if marker.get('paddleFallbackNeeded'):
                    paddle_queue[key]=(record,marker)
                if marker.get('status') == 'error':
                    lifetime['errors'] += 1
                    lifetime['lastError'] = f'{key[0]} {key[1]}: {marker.get("error")}'
                    retry_after[key] = time.time() + 300
                else:
                    lifetime['lastParsedAtUtc'] = marker.get('parsedAtUtc')
                    lifetime['lastResultStatus'] = marker.get('parseStatus')
                del active[future]

            for future,details in list(paddle_active.items()):
                if not future.done():continue
                record,key=details
                try:
                    returned_key,marker=future.result()
                    if returned_key!=key:raise RuntimeError('Paddle fallback returned a different document key')
                except Exception as exc:
                    marker=completed.get(key,{})
                    marker.update({'paddleFallbackNeeded':False,'paddleFallbackStatus':'error',
                        'error':f'{type(exc).__name__}: {str(exc)[:240]}'})
                    output_dir=result_root/key[0]/(key[1]+'-'+key[2][:16]);atomic_json(output_dir/'status.json',marker)
                completed[key]=marker;del paddle_active[future]

            records = ledger_rows(ledger)
            fresh, without_result, stale_or_error, waiting_retry = [], [], [], []
            scan_keys = set()
            active_keys = {details[1] for details in active.values()}
            paddle_active_keys = {details[1] for details in paddle_active.values()}
            for record in records:
                key = (record['projectCode'], str(record['documentId']), record['signature'])
                scan_keys.add(key)
                if key in active_keys or key in paddle_active_keys:
                    continue
                output_dir = result_root / key[0] / (key[1] + '-' + key[2][:16])
                marker_path = output_dir / 'status.json'
                prior_marker = completed.get(key)
                if prior_marker and prior_marker.get('status') == 'parsed':
                    continue
                marker = None
                try:
                    marker = json.loads(marker_path.read_text())
                    if marker.get('status') == 'parsed' and marker.get('parseStatus') != 'parser_dependency_missing' and marker.get('parserVersion') == parser_version and marker.get('sourceSha256') == record.get('sha256'):
                        completed[key] = marker
                        if marker.get('paddleFallbackNeeded'):paddle_queue[key]=(record,marker)
                        continue
                except (OSError, ValueError):
                    pass
                if prior_marker and prior_marker.get('status') == 'error' and retry_after.get(key, 0) > time.time():
                    waiting_retry.append(record)
                    continue
                timestamp = str(record.get('at') or '')
                is_new = key not in observed and (
                    not first_scan or not previous_download_checkpoint or timestamp > previous_download_checkpoint
                )
                if is_new:
                    fresh.append(record)
                elif marker is None and not marker_path.exists():
                    without_result.append(record)
                else:
                    stale_or_error.append(record)
            observed.update(scan_keys)
            first_scan = False
            fresh.sort(key=lambda r: (str(r.get('at') or ''), r['projectCode'], str(r['documentId'])), reverse=True)
            without_result.sort(key=lambda r: (str(r.get('at') or ''), r['projectCode'], str(r['documentId'])))
            stale_or_error.sort(key=lambda r: (str(r.get('at') or ''), r['projectCode'], str(r['documentId'])))
            pending = fresh + without_result + stale_or_error

            slots = max(0, args.workers - len(active))
            selected = pending[:slots]
            for record in selected:
                key = (record['projectCode'], str(record['documentId']), record['signature'])
                priority = ('new download' if record in fresh else
                            'missing parse result' if record in without_result else 'retry/stale result')
                future = pool.submit(parse_one, record, str(root), str(result_root), parser_version,'apple_tesseract')
                active[future] = (record, key, priority)
                pending.remove(record)

            paddle_slots=max(0,args.paddle_workers-len(paddle_active))
            for key,(record,primary_marker) in list(paddle_queue.items())[:paddle_slots]:
                future=paddle_pool.submit(parse_paddle_fallback,record,str(root),str(result_root),parser_version)
                paddle_active[future]=(record,key);del paddle_queue[key]

            successful = [value for value in completed.values() if value.get('status') == 'parsed']
            lifetime['skippedCurrent'] = len(successful)
            lifetime['processed'] = len(successful)
            lifetime['rows'] = sum(int(value.get('rows', 0) or 0) for value in successful)
            lifetime['categories'] = sum(int(value.get('categories', 0) or 0) for value in successful)
            lifetime['pending'] = len(pending) + len(waiting_retry)
            lifetime['pendingNewDownloads'] = max(0, len(fresh) - sum(1 for r in selected if r in fresh))
            lifetime['pendingWithoutParseResult'] = max(0, len(without_result) - sum(1 for r in selected if r in without_result))
            lifetime['pendingRetry'] = len(stale_or_error) - sum(1 for r in selected if r in stale_or_error) + len(waiting_retry)
            lifetime['totalPendingIncludingActive'] = lifetime['pending'] + len(active)
            lifetime['active'] = [
                {'projectCode': record['projectCode'], 'documentId': key[1],
                 'fileName': record.get('fileName'), 'priority': priority,'stage':'Apple/Tesseract primary'}
                for record, key, priority in active.values()
            ]
            lifetime['active'].extend({'projectCode':record['projectCode'],'documentId':key[1],
                'fileName':record.get('fileName'),'priority':'no-row OCR fallback','stage':'PaddleOCR'}
                for record,key in paddle_active.values())
            lifetime['activeCount'] = len(active)+len(paddle_active)
            lifetime['workers'] = args.workers
            lifetime['primaryOcrEngine']='Apple Vision/Tesseract'
            lifetime['paddleFallbackWorkers']=args.paddle_workers
            lifetime['pendingPaddleFallback']=len(paddle_queue)
            lifetime['queuePolicy'] = 'New downloads first; then missing parse results; then failed or stale results.'
            lifetime['totalDownloadedPow'] = len(records)
            lifetime['lastDownloaderRecordUtc'] = records[-1].get('at') if records else None
            lifetime['lastQueueScanAtUtc'] = utc()
            lifetime['heartbeatAtUtc'] = lifetime['lastQueueScanAtUtc']
            lifetime['status'] = 'running' if pending or active or paddle_active or paddle_queue else ('waiting_retry' if waiting_retry else 'idle')
            lifetime['current'] = lifetime['active'][0] if lifetime['active'] else None
            lifetime['updatedAtUtc'] = utc()
            atomic_json(status_path, lifetime)

            if args.once and not pending and not active and not paddle_active and not paddle_queue and not waiting_retry:
                lifetime['status'] = 'complete'
                lifetime['finishedAtUtc'] = utc()
                atomic_json(status_path, lifetime)
                return
            if not pending and not active and not paddle_active and not paddle_queue and not waiting_retry and not args.once:
                time.sleep(max(5, args.interval))
            else:
                time.sleep(1)
    finally:
        pool.shutdown(wait=True, cancel_futures=False)
        paddle_pool.shutdown(wait=True,cancel_futures=False)

if __name__ == '__main__':
    main()
