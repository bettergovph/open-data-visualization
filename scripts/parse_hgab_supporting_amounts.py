#!/usr/bin/env python3
"""Extract project amounts from matched HGAB BP 202 and COI PDFs.

Only exact-title COI amounts and labelled BP 202 totals are retained. Missing,
ambiguous, scanned, and unavailable documents remain explicitly unparsed.
The script updates expectation-vs-reality JSON and its project-context shards.
"""
import argparse
import concurrent.futures
import collections
import hashlib
import json
import os
import re
import ssl
import tempfile
import unicodedata
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'static/nep-preview'
KINDS = {'BP 202', 'Certificate of Implementability'}
AMOUNT = re.compile(r'(?<![A-Za-z0-9.,])(?:\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{6,}(?:\.\d{1,2})?)(?!\d)')

def normalize(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()

def money(text, thousands=False):
    try:
        value = float(text.replace(',', ''))
        return round(value * 1000) if thousands else round(value, 2)
    except (TypeError, ValueError):
        return None

def coi_money(text, document_text=''):
    """Respect P'000 for abbreviated values, but don't rescale full-peso figures.

    Some COIs print amounts such as 12,000,000 under a generic Php'000 header.
    Scaling those again creates a thousand-fold overstatement. Values below
    one million are treated as abbreviated thousands when that header exists;
    larger printed figures are retained as pesos.
    """
    value = money(text)
    if value is None:
        return None, 'PHP as printed'
    thousands_header = bool(re.search(r"(?:\bp\s*['‘’]?\s*000\b|\bphp\s*['‘’]?\s*000\b)", document_text, re.I))
    if thousands_header and value < 1_000_000:
        return value * 1000, "P'000 (converted to PHP)"
    if thousands_header:
        return value, "PHP as printed (P'000 header; no additional scaling)"
    return value, 'PHP as printed'

def page_text(page, allow_ocr=False):
    text = page.get_text('text')
    if not allow_ocr:
        return text, 'native PDF text'
    try:
        textpage = page.get_textpage_ocr(language='eng', dpi=240, full=True)
        return page.get_text('text', textpage=textpage), 'Tesseract OCR'
    except Exception:
        return text, 'native PDF text; OCR unavailable'

def fetch(url, cache_dir, max_bytes):
    key = hashlib.sha256(url.encode()).hexdigest() + '.pdf'
    path = cache_dir / key
    if path.is_file() and path.stat().st_size:
        return path
    request = urllib.request.Request(url, headers={'User-Agent': 'BetterGov-supporting-document-amount-review/1.0'})
    with urllib.request.urlopen(request, timeout=45, context=ssl.create_default_context()) as response:
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes or not content.startswith(b'%PDF-'):
        raise ValueError('Response is not a valid PDF within the configured size limit')
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path

def extract_bp202(pdf_path):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    results, methods = [], set()
    pages = list(enumerate(doc, 1))
    for page_no, page in pages:
        text, method = page_text(page)
        methods.add(method)
        for match in re.finditer(r'Total\s+Proposal\s+Cost\s*:?\s*(?:(?:PHP)\s*|₱\s*)?((?:\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{6,}(?:\.\d{2})?))', text, re.I):
            value = money(match.group(1))
            if value is not None:
                results.append({'amountPesos': value, 'printedValue': match.group(1), 'amountUnit': 'PHP',
                                'amountLabel': 'Total Proposal Cost', 'sourcePage': page_no})
    if not results:
        for page_no, page in pages:
            text, method = page_text(page, allow_ocr=True)
            methods.add(method)
            if method != 'Tesseract OCR':
                continue
            for match in re.finditer(r'Total\s+Proposal\s+Cost\s*:?\s*(?:(?:PHP)\s*|₱\s*)?((?:\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{6,}(?:\.\d{2})?))', text, re.I):
                value = money(match.group(1))
                if value is not None:
                    results.append({'amountPesos': value, 'printedValue': match.group(1), 'amountUnit': 'PHP',
                                    'amountLabel': 'Total Proposal Cost', 'sourcePage': page_no})
    unique = {(x['amountPesos'], x['sourcePage']): x for x in results}
    if len(unique) == 1:
        result = next(iter(unique.values()))
        result['extractionMethod'] = 'Tesseract OCR' if 'Tesseract OCR' in methods else 'native PDF text extraction'
        return result, 'value_extracted'
    return None, 'ambiguous_amount' if unique else 'amount_not_found'

def extract_coi(pdf_path, title):
    import pymupdf
    wanted = normalize(title)
    if not wanted:
        return None, 'title_unavailable'
    hits = []
    doc = pymupdf.open(pdf_path)
    document_text = '\n'.join(page.get_text('text') for page in doc)
    pages = list(enumerate(doc, 1)); methods = set()
    def scan_page(page_no, page, allow_ocr=False):
        text, method = page_text(page, allow_ocr=allow_ocr)
        methods.add(method)
        normalized_chars = []
        source_positions = []
        previous_space = True
        for source_index, original_char in enumerate(text):
            chars = unicodedata.normalize('NFKD', original_char).encode('ascii', 'ignore').decode().lower()
            for char in chars:
                if char.isalnum():
                    normalized_chars.append(char); source_positions.append(source_index); previous_space = False
                elif not previous_space:
                    normalized_chars.append(' '); source_positions.append(source_index); previous_space = True
        normalized = ''.join(normalized_chars).strip()
        starts = [m.start() for m in re.finditer(re.escape(wanted), normalized)]
        for start in starts:
            normalized_end = start + len(wanted) - 1
            source_end = source_positions[min(normalized_end, len(source_positions)-1)] + 1
            tail = text[source_end:source_end + 250]
            match = AMOUNT.search(tail)
            if not match:
                continue
            raw = match.group(0)
            value, amount_unit = coi_money(raw, document_text + '\n' + text)
            if value is not None:
                hits.append({'amountPesos': value, 'printedValue': raw,
                             'amountUnit': amount_unit,
                             'amountLabel': 'Project amount in COI project list', 'sourcePage': page_no})
    for page_no, page in pages:
        scan_page(page_no, page)
    if not hits:
        for page_no, page in pages:
            scan_page(page_no, page, allow_ocr=True)
    unique = {(x['amountPesos'], x['sourcePage'], x['printedValue']): x for x in hits}
    if len(unique) == 1:
        result = next(iter(unique.values()))
        result['extractionMethod'] = 'Tesseract OCR' if 'Tesseract OCR' in methods else 'native PDF text extraction'
        return result, 'value_extracted'
    return None, 'ambiguous_project_amount' if unique else 'exact_project_amount_not_found'

def extract_coi_project_list(pdf_path, title_rows):
    """Extract separately titled project amounts from a COI that lists many projects."""
    import pymupdf
    wanted = collections.defaultdict(list)
    for row in title_rows:
        key = normalize(row.get('title'))
        if key:
            wanted[key].append(row)
    doc = pymupdf.open(pdf_path)
    pages = list(enumerate(doc, 1)); hits = collections.defaultdict(list); methods = set()
    document_text = '\n'.join(page.get_text('text') for page in doc)
    all_text = []

    def scan(page_no, text, method):
        methods.add(method); all_text.append(text)
        normalized_chars, source_positions = [], []
        previous_space = True
        for source_index, original_char in enumerate(text):
            chars = unicodedata.normalize('NFKD', original_char).encode('ascii', 'ignore').decode().lower()
            for char in chars:
                if char.isalnum():
                    normalized_chars.append(char); source_positions.append(source_index); previous_space = False
                elif not previous_space:
                    normalized_chars.append(' '); source_positions.append(source_index); previous_space = True
        normalized = ''.join(normalized_chars).strip()
        for title, rows in wanted.items():
            start = 0
            while True:
                start = normalized.find(title, start)
                if start < 0:
                    break
                end = start + len(title)
                bounded = (start == 0 or normalized[start - 1] == ' ') and (end == len(normalized) or normalized[end] == ' ')
                if bounded and source_positions:
                    source_end = source_positions[min(end - 1, len(source_positions) - 1)] + 1
                    amount_match = AMOUNT.search(text[source_end:source_end + 250])
                    if amount_match:
                        raw = amount_match.group(0)
                        value, amount_unit = coi_money(raw, document_text + '\n' + text)
                        hits[title].append({'amountPesos': value,
                                            'printedValue': raw, 'amountUnit': amount_unit,
                                            'amountLabel': 'Project amount in COI project list', 'sourcePage': page_no,
                                            'extractionMethod': 'Tesseract OCR' if method == 'Tesseract OCR' else 'native PDF text extraction'})
                start = end

    native_texts = []
    for page_no, page in pages:
        text, method = page_text(page)
        native_texts.append(text)
        if text.strip():
            scan(page_no, text, method)
    # OCR pages without native text even if another page already produced hits.
    for page_no, page in pages:
        if native_texts[page_no - 1].strip():
            continue
        text, method = page_text(page, allow_ocr=True)
        if method == 'Tesseract OCR':
            scan(page_no, text, method)

    results = {}
    for title, rows in wanted.items():
        # Repeated identical titles cannot be assigned safely by title alone.
        if len(rows) != 1 or title not in hits:
            continue
        unique = {(x['amountPesos'], x['sourcePage'], x['printedValue']): x for x in hits[title] if x['amountPesos'] is not None}
        row = rows[0]
        if len(unique) == 1:
            result = next(iter(unique.values()))
            result['status'] = 'value_extracted'
            result['matchBasis'] = 'Exact normalized project title followed by the listed amount; multi-project COI list'
        elif unique:
            result = {'status': 'ambiguous_project_amount', 'amountLabel': 'Project amount in COI project list',
                      'extractionMethod': 'native PDF text extraction · multiple amount candidates'}
        else:
            result = {'status': 'exact_project_amount_not_found', 'amountLabel': 'Project amount in COI project list',
                      'extractionMethod': 'native PDF text + Tesseract OCR fallback attempted'}
        result.update({'documentKind': 'Certificate of Implementability', 'sourceStage': 'HGAB supporting document',
                       'sourceProvider': 'BetterGov budget assets', 'sourceUrl': None, 'sourceName': None})
        results[row['hgabId']] = result
    return results

def parse_one(project_id, doc, title, cache_dir, max_bytes):
    code, kind, url, filename = doc[:4]
    provider = 'InfraWatch' if 'infrawatch' in url.lower() else 'BetterGov budget assets'
    result = {'documentKind': kind, 'sourceProvider': provider,
              'sourceStage': 'NEP counterpart Proposal document' if provider == 'InfraWatch' else 'HGAB supporting document',
              'sourceUrl': url, 'sourceName': filename, 'status': 'fetch_failed'}
    try:
        path = fetch(url, cache_dir, max_bytes)
        extracted, status = extract_bp202(path) if kind == 'BP 202' else extract_coi(path, title)
        result['status'] = status
        if not extracted:
            if status in {'amount_not_found', 'exact_project_amount_not_found'}:
                result['extractionMethod'] = 'native PDF text + Tesseract OCR fallback attempted'
            elif status in {'ambiguous_amount', 'ambiguous_project_amount'}:
                result['extractionMethod'] = 'native PDF text extraction · multiple amount candidates'
        if extracted and extracted['amountPesos'] < 100_000:
            result['candidateAmountPesos'] = extracted['amountPesos']
            result['candidatePrintedValue'] = extracted['printedValue']
            result['candidateSourcePage'] = extracted['sourcePage']
            result['status'] = 'amount_requires_review'
            extracted = None
        if extracted:
            result.update(extracted)
            result['matchBasis'] = ('Labelled Total Proposal Cost field · one BP 202 per project' if kind == 'BP 202' else 'Exact normalized project title followed by its listed amount; one COI may support multiple project rows')
            result.setdefault('extractionMethod', 'native PDF text extraction')
        return project_id, kind, result
    except Exception as exc:
        result['errorType'] = type(exc).__name__
        result['error'] = str(exc)[:180]
        return project_id, kind, result

def load_context():
    manifest_path = STATIC / 'project-context/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    records = {}
    for shard, meta in manifest['shards'].items():
        path = STATIC / 'project-context' / meta['path']
        data = json.loads(path.read_text())
        for row in data.get('projects', []):
            records[row['hgabId']] = (shard, row)
    return manifest_path, manifest, records

def load_infrawatch_documents(project_ids):
    """Read only PDF links carried by a title-matched record for an HGAB ID."""
    result = {}
    for path in (STATIC / 'project-evidence').glob('*.json'):
        if path.name == 'manifest.json':
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for records in data.get('titles', {}).values():
            if not isinstance(records, list):
                continue
            for record in records:
                matched = set(record.get('identifiers', [])) & project_ids
                if not matched:
                    continue
                evidence = record.get('evidence', {})
                links = evidence.get('transparencyLinks', [])
                if isinstance(evidence.get('transparency'), dict):
                    links = links or evidence['transparency'].get('documentLinks', [])
                for project_id in matched:
                    for link in links or []:
                        kind, url = link.get('type'), link.get('url')
                        if kind in KINDS and url and 'infrawatch.ph' in url.lower() and urlsplit(url).path.lower().endswith('.pdf'):
                            filename = urlsplit(url).path.rsplit('/', 1)[-1]
                            result.setdefault(project_id, {})[kind] = (filename, url)
    return result

def parse_coi_list_one(url, filename, title_rows, cache_dir, max_bytes):
    path = fetch(url, cache_dir, max_bytes)
    results = extract_coi_project_list(path, title_rows)
    provider = 'InfraWatch' if 'infrawatch' in url.lower() else 'BetterGov budget assets'
    for result in results.values():
        result['sourceProvider'] = provider
        result['sourceStage'] = 'NEP counterpart Proposal document' if provider == 'InfraWatch' else 'HGAB supporting document'
        result['sourceUrl'] = url
        result['sourceName'] = filename
    return url, results

def run_coi_project_list_scan(rows, contexts, manifest_path, manifest, args):
    """Scan each COI once and map its exact project-list titles to all comparison rows."""
    title_rows = [{'hgabId': row['hgabId'], 'title': row['title'], 'office': row.get('office'),
                   'amountPesos': row.get('allocationPesos')} for row in rows]
    documents = {}
    project_ids = {row['hgabId'] for row in rows}
    linked = load_infrawatch_documents(project_ids)
    for row in rows:
        context = contexts.get(row['hgabId'])
        if not context:
            continue
        for doc in context[1].get('documents', []):
            if len(doc) >= 4 and doc[1] == 'Certificate of Implementability' and doc[2]:
                documents.setdefault(doc[2], doc[3] or doc[0])
        for kind, (filename, url) in linked.get(row['hgabId'], {}).items():
            if kind == 'Certificate of Implementability':
                documents.setdefault(url, filename)
    print(f'COI list scan: {len(documents):,} distinct PDFs · {len(title_rows):,} comparison project titles', flush=True)
    outcomes = {}
    max_bytes = args.max_pdf_mb * 1024 * 1024
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(parse_coi_list_one, url, filename, title_rows, args.cache, max_bytes)
                   for url, filename in documents.items()]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            url, projects = future.result()
            for hgab_id, result in projects.items():
                result['documentKind'] = 'Certificate of Implementability'
                outcomes.setdefault(hgab_id, {})[(result['documentKind'], url)] = result
            if index % 100 == 0:
                print(f'COI PDFs scanned {index:,}/{len(futures):,}', flush=True)
    counts = {}
    for hgab_id, results in outcomes.items():
        context = contexts.get(hgab_id)
        if not context:
            continue
        existing = {(item.get('documentKind'), item.get('sourceUrl')): item
                    for item in context[1].get('supportingDocumentAmounts', [])}
        for key, item in results.items():
            prior = existing.get(key)
            if prior and prior.get('status') == 'value_extracted':
                continue
            existing[key] = item
            counts[item['status']] = counts.get(item['status'], 0) + 1
        context[1]['supportingDocumentAmounts'] = sorted(existing.values(), key=lambda item: (item.get('documentKind', ''), item.get('sourceUrl', '')))
    updates = {hgab_id: context[1].get('supportingDocumentAmounts', []) for hgab_id, context in contexts.items() if hgab_id in outcomes}
    for filename in ['expectation-vs-reality-data.json', 'expectation-vs-reality-flagged-data.json']:
        path = STATIC / filename
        data = json.loads(path.read_text())
        for row in data.get('projects', []):
            if row['hgabId'] in updates:
                row['supportingDocumentAmounts'] = updates[row['hgabId']]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    for shard, meta in manifest['shards'].items():
        path = STATIC / 'project-context' / meta['path']
        data = json.loads(path.read_text()); changed = False
        for row in data.get('projects', []):
            if row['hgabId'] in updates and row.get('supportingDocumentAmounts') != updates[row['hgabId']]:
                row['supportingDocumentAmounts'] = updates[row['hgabId']]; changed = True
        if changed:
            raw = (json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
            path.write_bytes(raw); meta['bytes'] = len(raw); meta['version'] = hashlib.sha256(raw).hexdigest()[:8]
    manifest['sourceVersion'] = hashlib.sha256(json.dumps({key: value for key, value in updates.items()}, sort_keys=True).encode()).hexdigest()[:16]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
    print('COI project-list statuses:', json.dumps(counts, sort_keys=True), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='Limit project rows for a small initial pass')
    parser.add_argument('--hgab-id', help='Process one exact HGAB row for a pilot')
    parser.add_argument('--scan-coi-project-lists', action='store_true', help='Scan each linked COI once against all selected project titles to recover amounts for every listed project')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--max-pdf-mb', type=int, default=50)
    parser.add_argument('--cache', type=Path, default=Path(tempfile.gettempdir()) / 'hgab-supporting-pdf-cache')
    args = parser.parse_args()
    import pymupdf  # fail early if parser dependency is absent
    del pymupdf
    manifest_path, manifest, contexts = load_context()
    primary = json.loads((STATIC / 'expectation-vs-reality-data.json').read_text())
    rows = primary['projects']
    if args.hgab_id:
        rows = [row for row in rows if row['hgabId'] == args.hgab_id]
    if args.limit:
        rows = rows[:args.limit]
    if args.scan_coi_project_lists:
        run_coi_project_list_scan(rows, contexts, manifest_path, manifest, args)
        return
    tasks = []
    infrawatch_docs = load_infrawatch_documents({row['hgabId'] for row in rows})
    for row in rows:
        hgab_id = row['hgabId']; context = contexts.get(hgab_id)
        if not context:
            continue
        context_row = context[1]
        existing = context_row.get('supportingDocumentAmounts', [])
        prior = {(item.get('documentKind'), item.get('sourceUrl')): item for item in existing}
        for doc in context_row.get('documents', []):
            if len(doc) >= 4 and doc[1] in KINDS and doc[2]:
                previous = prior.get((doc[1], doc[2]))
                if previous and previous.get('status') in {'value_extracted', 'amount_requires_review'}:
                    continue
                tasks.append((hgab_id, doc, row['title']))
        seen_urls = {doc[2] for doc in context_row.get('documents', []) if len(doc) >= 4}
        for kind, (filename, url) in infrawatch_docs.get(hgab_id, {}).items():
            if url not in seen_urls:
                previous = prior.get((kind, url))
                if previous and previous.get('status') in {'value_extracted', 'amount_requires_review'}:
                    continue
                tasks.append((hgab_id, (filename, kind, url, filename), row['title']))
    print(f'Projects: {len(rows):,} · PDF documents queued: {len(tasks):,}', flush=True)
    outcomes = {}
    max_bytes = args.max_pdf_mb * 1024 * 1024
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(parse_one, project_id, doc, title, args.cache, max_bytes) for project_id, doc, title in tasks]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            code, kind, result = future.result()
            outcomes.setdefault(code, []).append(result)
            if index % 100 == 0:
                print(f'Processed {index:,}/{len(futures):,}', flush=True)
    counts = {}
    for row in rows:
        hgab_id = row['hgabId']; context = contexts.get(hgab_id)
        if not context:
            continue
        prior = {(item.get('documentKind'), item.get('sourceUrl')): item
                 for item in context[1].get('supportingDocumentAmounts', [])}
        for item in outcomes.get(hgab_id, []):
            prior[(item.get('documentKind'), item.get('sourceUrl'))] = item
        amounts = list(prior.values())
        amounts.sort(key=lambda item: (item['documentKind'], item.get('sourceUrl', '')))
        context[1]['supportingDocumentAmounts'] = amounts
        row['supportingDocumentAmounts'] = amounts
        for item in amounts:
            counts[item['status']] = counts.get(item['status'], 0) + 1
    for filename in ['expectation-vs-reality-data.json', 'expectation-vs-reality-flagged-data.json']:
        path = STATIC / filename
        data = json.loads(path.read_text())
        updates = {r['hgabId']: r.get('supportingDocumentAmounts', []) for r in rows}
        for row in data['projects']:
            if row['hgabId'] in updates:
                row['supportingDocumentAmounts'] = updates[row['hgabId']]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    for shard, meta in manifest['shards'].items():
        path = STATIC / 'project-context' / meta['path']
        data = json.loads(path.read_text())
        changed = False
        for row in data.get('projects', []):
            if row['hgabId'] in outcomes:
                row['supportingDocumentAmounts'] = sorted(outcomes[row['hgabId']], key=lambda item: (item['documentKind'], item.get('sourceUrl', '')))
                changed = True
        if changed:
            raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
            path.write_text(raw)
            meta['bytes'] = path.stat().st_size
            meta['version'] = hashlib.sha256(raw.encode()).hexdigest()[:8]
    manifest['sourceVersion'] = hashlib.sha256(json.dumps({r['hgabId']: r.get('supportingDocumentAmounts', []) for r in rows}, sort_keys=True).encode()).hexdigest()[:16]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')) + '\n')
    print('Statuses:', json.dumps(counts, sort_keys=True), flush=True)

if __name__ == '__main__':
    main()
