"""Conservative POW bill-row candidates with exact page/row evidence."""
import hashlib,json,os,re,shutil,subprocess,sys
from decimal import Decimal,InvalidOperation
from pathlib import Path
NUMBER=re.compile(r'^(?:(?:₱|PHP|P)\s*)?-?\d[\d,]*(?:\.\d+)?\s*(?:₱|PHP|P)?$',re.I)
ITEM=re.compile(r'^(?:\d{3,4}(?:\([^)]*\))*[a-z0-9]*|[A-Z]\.\d+(?:\([^)]*\))*[a-z0-9]*)$',re.I)
def normalized_item_code(value):
    code=re.sub(r'\s+','',str(value or ''))
    return code if ITEM.fullmatch(code) else None

def amount(text):
    text=str(text or '').strip()
    if '%' in text:return None
    text=re.sub(r'(?<=\d)\s+(?=[\d,.])','',text)
    if not NUMBER.fullmatch(text):return None
    try:return Decimal(re.sub(r'[^\d.\-]','',text))
    except InvalidOperation:return None

def candidate(cells,page,method,bbox=None):
    cells=[re.sub(r'\s+',' ',str(c or '')).strip() for c in cells]
    item_code=normalized_item_code(cells[0]) if cells else None
    if not item_code:return None
    values=[(i,amount(c)) for i,c in enumerate(cells[1:],1) if amount(c) is not None]
    if len(values) not in [2,3]:return None
    qi,q=values[0];ai,total=values[-1]
    if q<=0 or total<0 or qi<=1:return None
    unit=' '.join(c for c in cells[qi+1:values[1][0] if len(values)==3 else ai] if c)
    if not re.search(r'[A-Za-z]',unit):return None
    printed_unit_price=values[1][1] if len(values)==3 else None
    diff=abs(q*printed_unit_price-total) if printed_unit_price is not None else None
    rounding_tolerance=q*Decimal(1).scaleb(printed_unit_price.as_tuple().exponent)/2+Decimal('.01') if printed_unit_price is not None else None
    return {'itemCode':item_code,'description':' '.join(cells[1:qi]),'quantity':float(q),'unit':unit,'printedUnitCostPesos':float(printed_unit_price) if printed_unit_price is not None else None,'calculatedUnitCostPesos':float(total/q),'amountPesos':float(total),'sourcePage':page,'sourceCells':cells,'sourceBbox':bbox,'extractionMethod':method,'quantityTimesUnitCostDifferencePesos':float(diff) if diff is not None else None,'arithmeticStatus':'Printed unit cost unavailable; amount/quantity is derived' if diff is None else 'Within rounding tolerance' if diff<=rounding_tolerance else 'Quantity × unit cost does not reproduce amount; review source','verificationStatus':'Machine-extracted candidate; verify source page'}

def component_context(text):
    contexts=component_contexts(text)
    return contexts[0] if contexts else None

def component_contexts(text):
    """Collect all lettered school/component labels printed in a POW header."""
    text=str(text or '')
    contexts=[]
    for match in re.finditer(r'(?im)(?:^|\n)\s*[a-z]\s*(?:\.\)|[.)])\s*([^\n]{4,180})',text):
        value=re.sub(r'\s+',' ',match.group(1)).strip(' ,.;')
        value=re.split(r'\s+(?:ITEM\s+NO\.|DESCRIPTION|QUANTITY|UNIT\s+OF\s+WORK)',value,flags=re.I)[0]
        value=value[:140]
        if re.match(r'^\d',value):continue
        if value and value not in contexts:contexts.append(value)
    schools=[value for value in contexts if re.search(r'\bschool\b',value,re.I)]
    return schools or contexts

def cost_category_totals(text,page,method):
    """Read printed category share/amount summaries without treating them as bill rows."""
    found=[]
    pattern=re.compile(
        r"(?P<label>[A-Za-z][A-Za-z0-9 &'()/.,-]{2,100}?)\s+"
        r"(?P<share>\d{1,3}(?:\.\d{1,4})?)\s*%\s*"
        r"(?:₱|PHP|PhP|P\s*)?\s*(?P<amount>\d[\d,]*(?:\.\d{2})?)",
        re.I)
    for line in str(text or '').splitlines():
        line=re.sub(r'\s+',' ',line).strip()
        for match in pattern.finditer(line):
            label=re.sub(r'\s+',' ',match.group('label')).strip(' .,:;|-')
            if len(label)<4 or re.search(r'\b(?:I\.?S\.?|O\.?C\.?M\.?|VAT|CONTINGENCY|GRAND TOTAL)\b',label,re.I):continue
            if re.match(r'^(?:\d{2,}|[A-Z]?\.?\d)',label,re.I):continue
            share=float(match.group('share'));amount_value=amount(match.group('amount'))
            if not 0<share<=100 or amount_value is None or amount_value<=0:continue
            row={'label':label,'sharePct':share,'amountPesos':float(amount_value),
                 'sourcePage':page,'extractionMethod':method,
                 'verificationStatus':'Machine-extracted printed category total; verify cited POW page'}
            if not any(r['label'].casefold()==label.casefold() and r['amountPesos']==row['amountPesos'] for r in found):found.append(row)
    return found

def itemized_rows(grid,page,bbox,context_text=''):
    """Recognize the submitted/evaluated DPWH itemized bill, not unit-price analyses."""
    clean=[[re.sub(r'\s+',' ',str(c or '')).strip() for c in row] for row in grid]
    header=next((i for i,row in enumerate(clean) if 'DIRECT COST' in row and any('TOTAL UNIT COST' in c for c in row) and ((('ITEM NO.' in row and 'DESCRIPTION' in row) and ('QUANTITY' in row or 'QTY' in row)) or any('ITEM NO.' in r for r in clean[i+1:i+4]))),None)
    if header is None:return None
    headings=clean[header]
    item_index=headings.index('ITEM NO.') if 'ITEM NO.' in headings else 1
    description_index=headings.index('DESCRIPTION') if 'DESCRIPTION' in headings else 2
    q=headings.index('QUANTITY') if 'QUANTITY' in headings else headings.index('QTY') if 'QTY' in headings else 4
    unit=headings.index('UNIT') if 'UNIT' in headings else 6
    direct=headings.index('DIRECT COST')
    following=clean[header+1:header+5]
    sub=next((row for row in following if 'TOTAL' in row and 'UNIT COST' in row),None)
    basis=next((row for row in following if 'AS SUBMITTED' in row and 'AS EVALUATED' in row),None)
    if not sub or not basis:return None
    total=sub.index('TOTAL');price=sub.index('UNIT COST');indirect=next(i for i,c in enumerate(headings) if 'TOTAL UNIT COST' in c)
    if not (q<unit<=direct<=total<price<indirect):return None
    records=[];controls=[]
    context_source=context_text or ' '.join(' '.join(r) for r in clean[:header])
    contexts=component_contexts(context_source)
    current_contexts=contexts
    def column(start,end,label):return next((i for i in range(start,min(end,len(basis))) if basis[i]==label),None)
    for label in ('AS SUBMITTED','AS EVALUATED'):
        qi=column(q,unit,label);ai=column(total,price,label);pi=column(price,indirect,label)
        if qi is None or ai is None:continue
        for cells in clean[header+1:]:
            if len(cells)>max(item_index,description_index) and re.fullmatch(r'\d{1,3}',cells[item_index]) and re.search(r'\b(?:school|building|camp)\b',cells[description_index],re.I):
                current_contexts=[cells[description_index].strip(' ,.;')]
                continue
            if len(cells)<=max(qi,ai,unit):continue
            if len(cells)>max(item_index,description_index,qi,ai,unit) and normalized_item_code(cells[item_index]) and amount(cells[qi]) is not None and amount(cells[ai]) is not None:
                values=[cells[item_index],cells[description_index] if description_index<len(cells) else '',cells[qi],cells[unit]]
                printed=cells[pi] if pi is not None and pi<len(cells) else ''
                if amount(printed) is not None:values.append(printed)
                values.append(cells[ai]);row=candidate(values,page,'native DPWH itemized bill · mapped submitted/evaluated columns',bbox)
                if not row:continue
                context=current_contexts[0] if len(current_contexts)==1 else None
                row.update({'sourceCells':cells,'costBasis':label.lower().replace(' ','_'),'amountBasis':'Direct cost total; excludes markup, VAT and EAO','componentContext':context,'componentContexts':current_contexts,'columnMapping':{'quantity':qi,'unit':unit,'directCostTotal':ai,'directUnitCost':pi}})
                records.append(row)
            elif 'GRAND TOTAL' in cells and amount(cells[ai]) is not None:
                printed=float(amount(cells[ai]));subset=[r for r in records if r['costBasis']==label.lower().replace(' ','_')]
                recovered=round(sum(r['amountPesos'] for r in subset),2)
                controls.append({'sourcePage':page,'basis':label.lower().replace(' ','_'),'amountBasis':'Itemized direct-cost subtotal only','printedPesos':printed,'recoveredItemRows':len(subset),'recoveredPesos':recovered,'differencePesos':round(recovered-printed,2),'reconciled':bool(subset) and abs(recovered-printed)<=.01,'sourceCells':cells})
    return {'rows':records,'controls':controls}

def continuation_rows(grid,page,bbox,context=None):
    """Read headerless continuation sheets with the standard 12-column BOQ layout."""
    records=[]
    for raw in grid:
        cells=[re.sub(r'\s+',' ',str(c or '')).strip() for c in raw]
        if len(cells)<12 or not normalized_item_code(cells[0]) or amount(cells[2]) is None:continue
        if not re.search(r'[A-Za-z]',cells[4]) or not re.search(r'%\s*$',cells[11]):continue
        for label,amount_index,price_index,total_unit_index in (('as_submitted',5,7,9),('as_evaluated',6,8,10)):
            if any(amount(cells[i]) is None for i in (amount_index,price_index,total_unit_index)):continue
            row=candidate([cells[0],cells[1],cells[2],cells[4],cells[price_index],cells[amount_index]],page,'native DPWH itemized bill · continuation columns',bbox)
            if not row:continue
            row.update({'sourceCells':cells,'costBasis':label,'amountBasis':'Direct cost total; excludes markup, VAT and EAO','componentContext':context,'columnMapping':{'quantity':2,'unit':4,'directCostTotal':amount_index,'directUnitCost':price_index,'totalUnitCost':total_unit_index}})
            records.append(row)
    return records

def word_rows(words,width,page,method):
    # Header-qualified BOQ pages only. Unit-price analyses, estimates and
    # recapitulation pages are not another population of payable item rows.
    text=' '.join(w[4] for w in words)
    if re.search(r'detailed\s+(?:(?:unit\s+price|cost)\s+analysis|breakdown\s+of\s+component)',text,re.I):return [],False
    if not (re.search(r'quantity',text,re.I) and re.search(r'(?:amount|total\s+cost|direct\s+cost)',text,re.I) and re.search(r'description',text,re.I)):return [],False
    anchors=sorted([w for w in words if normalized_item_code(w[4]) and w[0]<width*(.15 if re.fullmatch(r'\d{3,4}',w[4].strip()) else .32)],key=lambda w:w[1]);result=[]
    # OCR pages often flatten adjacent quantity, unit-price, indirect-cost and
    # total-cost cells into one line. Use the printed column headings to map
    # the two required fields; if headings are missing, decline the page.
    if method.startswith('OCR'):
        def center(word):return (word[0]+word[2])/2
        merged=[]
        for start in anchors:
            if re.fullmatch(r'[A-Z]\.\d+',start[4],re.I):
                suffix=next((w for w in words if re.fullmatch(r'\([^)]{1,8}\)',w[4].strip()) and abs(w[1]-start[1])<3 and 0<w[0]-start[2]<width*.04),None)
                if suffix:start=tuple([start[0],min(start[1],suffix[1]),suffix[2],max(start[3],suffix[3]),start[4]+suffix[4]]+list(start[5:]))
            merged.append(start)
        anchors=merged
        def header_center(pattern):
            hits=[w for w in words if re.fullmatch(pattern,w[4].strip(),re.I)]
            return sum(center(w) for w in hits)/len(hits) if hits else None
        qx=header_center(r'QUANTITY')
        # Map the Total under Direct Cost; later TOTAL headings belong to unit
        # cost or inclusive amounts. Keep the header's vertical alignment.
        q_words=[w for w in words if re.fullmatch(r'QUANTITY',w[4].strip(),re.I)]
        qy=sum((w[1]+w[3])/2 for w in q_words)/len(q_words) if q_words else None
        direct_words=[w for w in words if re.fullmatch(r'DIRECT',w[4].strip(),re.I) and qy is not None and abs((w[1]+w[3])/2-qy)<max(100,width*.06)]
        direct_word=min(direct_words,key=lambda w:center(w)) if direct_words else None
        direct_x=center(direct_word) if direct_word else None
        totals=[w for w in words if re.fullmatch(r'TOTAL',w[4].strip(),re.I)]
        aligned_totals=[w for w in totals if qy is not None and abs((w[1]+w[3])/2-qy)<max(100,width*.06)]
        total_word=min(aligned_totals,key=lambda w:abs(center(w)-direct_x)) if aligned_totals and direct_x is not None else None
        tx=center(total_word) if total_word else None
        unit_headers=[center(w) for w in words if re.fullmatch(r'UNIT',w[4].strip(),re.I)]
        unitx=min(unit_headers,key=lambda x:abs(x-qx)) if qx is not None and unit_headers else None
        if qx is None or tx is None:return [],bool(anchors)
        result=[]
        for index,start in enumerate(anchors):
            end=anchors[index+1][1]-8 if index+1<len(anchors) else start[1]+40
            block=[w for w in words if start[1]-18<=w[1]<min(end,start[1]+45)]
            nums=[w for w in block if amount(w[4]) is not None]
            if not nums:continue
            q=min(nums,key=lambda w:abs(center(w)-qx));total=min(nums,key=lambda w:abs(center(w)-tx))
            if q is total or abs(center(q)-qx)>width*.06 or abs(center(total)-tx)>width*.06:continue
            if q[1]>start[1]+10 or total[1]>start[1]+10:continue
            description=' '.join(w[4] for w in sorted(block,key=lambda w:(round(w[1]/4),w[0])) if w[0]>start[2]+2 and center(w)<qx-width*.025 and amount(w[4]) is None and w[4].upper() not in {'AS','SUBMITTED','EVALUATED'})
            unit_words=[w for w in block if unitx is not None and abs(center(w)-unitx)<width*.07 and amount(w[4]) is None and re.search(r'[A-Za-z]',w[4]) and w[4].upper() not in {'AS','SUBMITTED','EVALUATED','P'}]
            unit=' '.join(w[4] for w in sorted(unit_words,key=lambda w:w[0]))
            if not unit:continue
            row=candidate([start[4],description,q[4],unit,total[4]],page,method,[0,start[1],width,min(end,start[1]+45)])
            if row:result.append(row)
        return result,bool(anchors and not result)
    result=[]
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
    return result,False

def parse_pdf(path,output,allocation_pesos=None):
    try:import pymupdf as fitz
    except ImportError:return {'status':'parser_dependency_missing','message':'Install project_documents/requirements.txt in the document-service environment.','rows':[]}
    output.mkdir(parents=True,exist_ok=True);document=fitz.open(path);rows=[];pages=[];vision=None;itemized_controls=[];source_tables=[]
    if sys.platform=='darwin' and shutil.which('swift') and any(len(p.get_text().strip())<40 for p in document):
        try:
            environment={**os.environ,'CLANG_MODULE_CACHE_PATH':str(output/'swift-module-cache'),'SWIFT_MODULECACHE_PATH':str(output/'swift-module-cache')}
            response=subprocess.run(['swift',str(Path(__file__).with_name('ocr_vision.swift')),str(path),'100'],capture_output=True,text=True,check=True,timeout=240,env=environment)
            vision=json.loads(response.stdout);(output/'pow-ocr-vision.json').write_text(response.stdout)
        except Exception:vision=None
    current_context=None;cost_categories=[]
    for number,page in enumerate(document):
        if number>=100:break
        text=page.get_text();words=page.get_text('words');method='native PDF text/table';ocr_width=page.rect.width
        if len(text.strip())<40:
            if shutil.which('tesseract'):
                original_rotation=page.rotation;attempts=[]
                # Some proposal scans are landscape sheets embedded in portrait
                # pages. OCR all quarter-turns and keep the orientation that
                # exposes the most bill structure and numbered rows.
                for rotation in (original_rotation,(original_rotation+90)%360,(original_rotation+180)%360,(original_rotation+270)%360):
                    try:
                        page.set_rotation(rotation)
                        textpage=page.get_textpage_ocr(language='eng',dpi=250,full=True)
                        attempt_text=page.get_text(textpage=textpage);attempt_words=page.get_text('words',textpage=textpage);attempt_width=page.rect.width
                        score=(4*len(re.findall(r'\b(?:ITEM\s*NO|DESCRIPTION|QUANTITY|AMOUNT|TOTAL\s+COST)\b',attempt_text,re.I))
                               +min(20,sum(bool(ITEM.fullmatch(w[4].strip())) for w in attempt_words)))
                        attempts.append((score,attempt_text,attempt_words,rotation,attempt_width))
                    except Exception:continue
                page.set_rotation(original_rotation)
                if attempts:
                    _,text,words,rotation,ocr_width=max(attempts,key=lambda x:x[0])
                    method='OCR · Tesseract'+(' · rotated scan '+str(rotation)+'°' if rotation!=original_rotation else '')
                else:text='';words=[]
            elif vision and any(p['page']==number+1 for p in vision['pages']):
                record=next(p for p in vision['pages'] if p['page']==number+1);words=record['words'];text=' '.join(w[4] for w in words);ocr_width=record.get('width',page.rect.width);rotation=record.get('rotation',0);method='OCR · Apple Vision'+(' · rotated scan '+str(rotation)+'°' if rotation else '')+'; original boxes/confidence retained'
            else:
                pages.append({'page':number+1,'status':'needs_ocr','message':'Image-only page; OCR required before ranking bill rows.'});continue
        category_text=text
        if method.startswith('OCR') and words:
            category_lines={}
            for word in words:category_lines.setdefault(round(word[1]/5),[]).append(word)
            category_text='\n'.join(' '.join(w[4] for w in sorted(line,key=lambda x:x[0]))
                                    for _,line in sorted(category_lines.items()))
        cost_categories.extend(cost_category_totals(category_text,number+1,method))
        page_rows=[]
        current_context=component_context(text) or current_context
        if method.startswith('native'):
            try:
                for table in page.find_tables().tables:
                    grid=table.extract();source_tables.append({'page':number+1,'bbox':list(table.bbox),'cells':grid})
                    itemized=itemized_rows(grid,number+1,list(table.bbox),text)
                    if itemized is not None:
                        page_rows.extend(itemized['rows']);itemized_controls.extend(itemized['controls']);continue
                    continued=continuation_rows(grid,number+1,list(table.bbox),current_context)
                    if continued:
                        page_rows.extend(continued);continue
                    context=' '.join(str(c or '') for r in grid[:4] for c in r)
                    if not re.search(r'quantity',context,re.I) or not re.search(r'(?:amount|total\s+cost)',context,re.I):continue
                    if re.search(r'detailed\s+(?:unit\s+price|cost)\s+analysis',text,re.I):continue
                    for cells in grid:
                        row=candidate(cells,number+1,method,list(table.bbox))
                        if row:page_rows.append(row)
            except Exception:pass
        review=False
        if not page_rows:
            page_rows,review=word_rows(words,ocr_width,number+1,method)
        if method.startswith('OCR') and page_rows:
            lines={}
            for w in words:lines.setdefault(round(w[1]/5),[]).append(w)
            page_context=component_context('\n'.join(' '.join(w[4] for w in sorted(line,key=lambda x:x[0])) for _,line in sorted(lines.items())))
            if page_context:
                for row in page_rows:row['componentContext']=page_context
        pages.append({'page':number+1,'status':'candidate_rows' if page_rows else 'needs_manual_review' if review else 'no_bill_rows_recovered','rows':len(page_rows),'method':method,'reviewNote':'Numeric columns could not be mapped safely; inspect the source page.' if review else None})
        rows.extend(page_rows)
    # Retain repeated observations rather than summing duplicate page/table views.
    grouped={}
    for row in rows:
        key=json.dumps([row[k] for k in ['itemCode','description','quantity','unit','amountPesos']]+[row.get('costBasis'),row.get('amountBasis'),row.get('componentContext')],ensure_ascii=False)
        if key in grouped:grouped[key]['observedPages'].append(row['sourcePage'])
        else:row['observedPages']=[row['sourcePage']];grouped[key]=row
    (output/'pow-native-tables.json').write_text(json.dumps(source_tables,ensure_ascii=False,indent=2)+'\n')
    result=list(grouped.values());result.sort(key=lambda r:-r['amountPesos'])
    for row in result:row['shareOfNepAllocationPct']=round(100*row['amountPesos']/allocation_pesos,4) if allocation_pesos else None
    for row in result:
        allocation_share=row.get('shareOfNepAllocationPct')
        row['lowShareParsingIndicator']=bool(allocation_share is not None and allocation_share<1)
    unique_categories=[]
    for row in cost_categories:
        if not any(r['label'].casefold()==row['label'].casefold() and r['amountPesos']==row['amountPesos'] for r in unique_categories):unique_categories.append(row)
    unique_categories.sort(key=lambda r:-r['amountPesos'])
    return {'status':'candidate_rows' if result else 'needs_ocr' if any(p['status']=='needs_ocr' for p in pages) else 'needs_manual_review' if any(p['status']=='needs_manual_review' for p in pages) else 'no_bill_rows_recovered','pdfSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pageCount':len(document),'pagesProcessed':len(pages),'pages':pages,'rows':result,'costCategoryBreakdown':unique_categories,'rowObservations':len(rows),'uniqueCandidateRows':len(result),'sumOfUniqueCandidateAmountsPesos':sum(r['amountPesos'] for r in result),'reconciledPowTotal':False,'itemizedDirectCostControls':itemized_controls,'amountBasis':'Each item records its cost basis; direct costs are not inclusive project costs. Printed category shares are preserved as separate summary evidence and are not added to itemized rows.','limits':['Reconciled itemized direct-cost subtotals, when available, do not reconcile the complete POW including indirect costs, VAT and EAO. Candidate row extraction is not a complete or reconciled POW ledger. A largest recovered row is not necessarily the largest row in the full document.','Shares use the NEP allocation, not a confirmed POW grand total, contract payment or engineering valuation.','Quantities, material units, indirect costs and engineering scope require original-page verification. Structural concrete is not cement mass.','Printed category summaries and itemized bill rows are separate evidence and must not be summed together.','Repeated identical row observations are grouped with page references; no budget amount is inferred from a missing cell.']}

def render_photos(path,output):
    try:import pymupdf as fitz
    except ImportError:return {'status':'renderer_dependency_missing','pages':[]}
    output.mkdir(parents=True,exist_ok=True);document=fitz.open(path);pages=[]
    for index,page in enumerate(document):
        if index>=50:break
        scale=min(2,1400/page.rect.width);target=output/f'photo-page-{index+1:03d}.png';page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).save(target)
        pages.append({'page':index+1,'fileName':target.name,'caption':page.get_text().strip()[:1500] or None})
    return {'status':'rendered','pageCount':len(document),'pages':pages,'truncated':len(document)>len(pages),'limits':'Full PDF pages are rendered to preserve captions, coordinates and document context. Photo dates/locations are not independently verified.'}
