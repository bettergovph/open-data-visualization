"""Conservative POW bill-row candidates with exact page/row evidence."""
import hashlib,json,os,re,shutil,subprocess,sys
from decimal import Decimal,InvalidOperation
from pathlib import Path
NUMBER=re.compile(r'^(?:₱|PHP)?\s*-?\d[\d,]*(?:\.\d+)?$')
ITEM=re.compile(r'^(?:\d{3,4}(?:\([^)]*\))*[a-z0-9]*|[A-Z]\.\d+(?:\([^)]*\))*[a-z0-9]*)$',re.I)
def amount(text):
    text=str(text or '').strip()
    if not NUMBER.fullmatch(text):return None
    try:return Decimal(re.sub(r'[^\d.\-]','',text))
    except InvalidOperation:return None

def candidate(cells,page,method,bbox=None):
    cells=[re.sub(r'\s+',' ',str(c or '')).strip() for c in cells]
    if not cells or not ITEM.fullmatch(cells[0]):return None
    values=[(i,amount(c)) for i,c in enumerate(cells[1:],1) if amount(c) is not None]
    if len(values) not in [2,3]:return None
    qi,q=values[0];ai,total=values[-1]
    if q<=0 or total<0 or qi<=1:return None
    unit=' '.join(c for c in cells[qi+1:values[1][0] if len(values)==3 else ai] if c)
    if not re.search(r'[A-Za-z]',unit):return None
    printed_unit_price=values[1][1] if len(values)==3 else None
    diff=abs(q*printed_unit_price-total) if printed_unit_price is not None else None
    return {'itemCode':cells[0],'description':' '.join(cells[1:qi]),'quantity':float(q),'unit':unit,'printedUnitCostPesos':float(printed_unit_price) if printed_unit_price is not None else None,'calculatedUnitCostPesos':float(total/q),'amountPesos':float(total),'sourcePage':page,'sourceCells':cells,'sourceBbox':bbox,'extractionMethod':method,'quantityTimesUnitCostDifferencePesos':float(diff) if diff is not None else None,'arithmeticStatus':'Printed unit cost unavailable; amount/quantity is derived' if diff is None else 'Within rounding tolerance' if diff<=max(Decimal('1'),abs(total)*Decimal('.001')) else 'Quantity × unit cost does not reproduce amount; review source','verificationStatus':'Machine-extracted candidate; verify source page'}

def word_rows(words,width,page,method):
    # Header-qualified BOQ pages only. Unit-price analyses, estimates and
    # recapitulation pages are not another population of payable item rows.
    text=' '.join(w[4] for w in words)
    if re.search(r'detailed\s+(?:unit\s+price|cost)\s+analysis',text,re.I):return []
    if not (re.search(r'quantity',text,re.I) and re.search(r'(?:amount|total\s+cost)',text,re.I) and re.search(r'description',text,re.I)):return []
    anchors=sorted([w for w in words if w[0]<width*.22 and ITEM.fullmatch(w[4].strip())],key=lambda w:w[1]);result=[]
    for index,start in enumerate(anchors):
        end=anchors[index+1][1]-1 if index+1<len(anchors) else start[1]+45
        block=[w for w in words if start[1]-2<=w[1]<min(end,start[1]+65)]
        numeric=sorted([w for w in block if w[0]>width*.45 and amount(w[4]) is not None],key=lambda w:w[0])
        if len(numeric) not in [2,3]:continue
        q=numeric[0];last=numeric[-1]
        description=' '.join(w[4] for w in sorted(block,key=lambda w:(round(w[1]/4),w[0])) if w!=start and w[0]>start[0]+2 and w[0]<q[0]-2)
        # Numeric columns are grouped by their physical positions. Unit words
        # must lie between quantity and the next numeric column.
        unit=' '.join(w[4] for w in block if q[2]-1<=w[0]<numeric[1][0] and w not in numeric)
        cells=[start[4],description,q[4],unit]+([numeric[1][4]] if len(numeric)==3 else [])+[last[4]]
        row=candidate(cells,page,method,[0,start[1],width,min(end,start[1]+65)])
        if row:result.append(row)
    return result

def parse_pdf(path,output,allocation_pesos=None):
    try:import fitz
    except ImportError:return {'status':'parser_dependency_missing','message':'Install project_documents/requirements.txt in the document-service environment.','rows':[]}
    output.mkdir(parents=True,exist_ok=True);document=fitz.open(path);rows=[];pages=[];vision=None
    if sys.platform=='darwin' and shutil.which('swift') and any(len(p.get_text().strip())<40 for p in document):
        try:
            environment={**os.environ,'CLANG_MODULE_CACHE_PATH':str(output/'swift-module-cache'),'SWIFT_MODULECACHE_PATH':str(output/'swift-module-cache')}
            response=subprocess.run(['swift',str(Path(__file__).with_name('ocr_vision.swift')),str(path),'100'],capture_output=True,text=True,check=True,timeout=240,env=environment)
            vision=json.loads(response.stdout);(output/'pow-ocr-vision.json').write_text(response.stdout)
        except Exception:vision=None
    for number,page in enumerate(document):
        if number>=100:break
        text=page.get_text();words=page.get_text('words');method='native PDF text/table'
        if len(text.strip())<40:
            if shutil.which('tesseract'):
                textpage=page.get_textpage_ocr(language='eng',dpi=250,full=True);text=page.get_text(textpage=textpage);words=page.get_text('words',textpage=textpage);method='OCR · Tesseract'
            elif vision and any(p['page']==number+1 for p in vision['pages']):
                record=next(p for p in vision['pages'] if p['page']==number+1);words=record['words'];text=' '.join(w[4] for w in words);method='OCR · Apple Vision; original boxes/confidence retained'
            else:
                pages.append({'page':number+1,'status':'needs_ocr','message':'Image-only page; OCR required before ranking bill rows.'});continue
        page_rows=[]
        if method.startswith('native'):
            try:
                for table in page.find_tables().tables:
                    grid=table.extract();context=' '.join(str(c or '') for r in grid[:4] for c in r)
                    if not re.search(r'quantity',context,re.I) or not re.search(r'(?:amount|total\s+cost)',context,re.I):continue
                    if re.search(r'detailed\s+(?:unit\s+price|cost)\s+analysis',text,re.I):continue
                    for cells in grid:
                        row=candidate(cells,number+1,method,list(table.bbox))
                        if row:page_rows.append(row)
            except Exception:pass
        if not page_rows:page_rows=word_rows(words,page.rect.width,number+1,method)
        pages.append({'page':number+1,'status':'candidate_rows' if page_rows else 'no_bill_rows_recovered','rows':len(page_rows),'method':method})
        rows.extend(page_rows)
    # Retain repeated observations rather than summing duplicate page/table views.
    grouped={}
    for row in rows:
        key=json.dumps([row[k] for k in ['itemCode','description','quantity','unit','amountPesos']],ensure_ascii=False)
        if key in grouped:grouped[key]['observedPages'].append(row['sourcePage'])
        else:row['observedPages']=[row['sourcePage']];grouped[key]=row
    result=list(grouped.values());result.sort(key=lambda r:-r['amountPesos'])
    for row in result:row['shareOfNepAllocationPct']=round(100*row['amountPesos']/allocation_pesos,4) if allocation_pesos else None
    return {'status':'candidate_rows' if result else 'needs_ocr' if any(p['status']=='needs_ocr' for p in pages) else 'no_bill_rows_recovered','pdfSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pageCount':len(document),'pagesProcessed':len(pages),'pages':pages,'rows':result,'rowObservations':len(rows),'uniqueCandidateRows':len(result),'sumOfUniqueCandidateAmountsPesos':sum(r['amountPesos'] for r in result),'reconciledPowTotal':False,'limits':['Candidate row extraction is not a complete or reconciled POW ledger. A largest recovered row is not necessarily the largest row in the full document.','Shares use the NEP allocation, not a confirmed POW grand total, contract payment or engineering valuation.','Quantities, material units, indirect costs and engineering scope require original-page verification. Structural concrete is not cement mass.','Repeated identical row observations are grouped with page references; no budget amount is inferred from a missing cell.']}

def render_photos(path,output):
    try:import fitz
    except ImportError:return {'status':'renderer_dependency_missing','pages':[]}
    output.mkdir(parents=True,exist_ok=True);document=fitz.open(path);pages=[]
    for index,page in enumerate(document):
        if index>=50:break
        scale=min(2,1400/page.rect.width);target=output/f'photo-page-{index+1:03d}.png';page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).save(target)
        pages.append({'page':index+1,'fileName':target.name,'caption':page.get_text().strip()[:1500] or None})
    return {'status':'rendered','pageCount':len(document),'pages':pages,'truncated':len(document)>len(pages),'limits':'Full PDF pages are rendered to preserve captions, coordinates and document context. Photo dates/locations are not independently verified.'}
