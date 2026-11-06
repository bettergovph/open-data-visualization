"""Conservative POW bill-row candidates with exact page/row evidence."""
import hashlib,json,os,re,shutil,subprocess,sys,tempfile
from decimal import Decimal,InvalidOperation
from pathlib import Path
_PADDLE_OCR=None

def paddle_words(page,dpi=170):
    """Run PaddleOCR through quarter-turn and high-resolution retries."""
    global _PADDLE_OCR
    try:
        import numpy as np
        os.environ['PADDLE_PDX_CACHE_HOME']=str(Path(tempfile.gettempdir())/'paddleocr-cache')
        from paddleocr import PaddleOCR
        from PIL import Image
        import io,pymupdf as fitz
    except ImportError:return None
    if _PADDLE_OCR is None:
        try:_PADDLE_OCR=PaddleOCR(lang='en',ocr_version='PP-OCRv5',use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
        except Exception:_PADDLE_OCR=False
    if _PADDLE_OCR is False:return None
    attempts=[]
    for rotation,resolution in [(0,dpi),(90,dpi),(180,dpi),(270,dpi),(90,350),(270,350)]:
        try:
            pix=page.get_pixmap(matrix=fitz.Matrix(resolution/72,resolution/72),alpha=False)
            image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            rotated=image.rotate(rotation,expand=True) if rotation else image
            result=_PADDLE_OCR.predict(np.asarray(rotated))[0]
            words=[]
            for box,text,confidence in zip(result.get('rec_boxes',[]),result.get('rec_texts',[]),result.get('rec_scores',[])):
                text=str(text).strip()
                if not text:continue
                x0,y0,x1,y1=map(float,box);words.append((x0,y0,x1,y1,text,float(confidence)))
            joined=' '.join(w[4] for w in words)
            structure=(4*len(re.findall(r'\b(?:ITEM\s*NO|DESCRIPTION|QUANTITY|AMOUNT|TOTAL\s+COST|AS\s+SUBMITTED)\b',joined,re.I))
                +3*sum(bool(ITEM.fullmatch(w[4])) for w in words)+sum(bool(amount(w[4])) for w in words))
            confidence=sum(w[5] for w in words)/len(words) if words else 0
            attempts.append({'words':[(*w[:5],0,int(round((w[1]+w[3])/16)),0) for w in words],
                'width':rotated.width,'text':joined,'rotation':rotation,'dpi':resolution,
                'structureScore':structure,'meanConfidence':round(confidence,4),'wordCount':len(words),
                'method':f'OCR · PaddleOCR PP-OCRv5 · rotated scan {rotation}° at {resolution} dpi'})
        except Exception:continue
    return {'attempts':attempts} if attempts else None
NUMBER=re.compile(r'^(?:(?:₱|PHP|P)\s*)?-?\d[\d,]*(?:\.\d+)?\s*(?:₱|PHP|P)?$',re.I)
ITEM=re.compile(r'^(?:\d{3,4}(?:\([^)]*\))*[a-z0-9]*|[A-Z]\.\d+(?:\([^)]*\))*[a-z0-9]*)$',re.I)
SUMMARY_PAGE=re.compile(r'PROGRAM\s+OF\s+WORKS?\s*/\s*BUDGET\s+COST|BREAKDOWN\s+OF\s+EXPENDITURES|SUMMARY\s+OF\s+(?:THE\s+)?(?:PROGRAM\s+OF\s+WORKS?|PROJECT\s+COST|COST\s+ESTIMATE)',re.I)
def normalized_item_code(value):
    code=re.sub(r'\s+','',str(value or '')).translate(str.maketrans({'[':'(',']':')','а':'a','А':'A'}))
    code=re.sub(r'(?<=\d)B(?=\()', '8', code)
    # OCR can read the closing parenthesis in a code as a square bracket and
    # occasionally emits one extra closer (for example ``1201(1)]``).
    while code.count(')')>code.count('(') and code.endswith(')'):
        code=code[:-1]
    return code if ITEM.fullmatch(code) else None

def item_code_at_anchor(tokens,anchor,width):
    parts=[anchor['text']]
    end=anchor.get('x1',anchor['x'])
    for token in sorted((t for t in tokens if anchor['y']-5<=t['y']<=anchor['y']+5 and end<t['x']<width*.1),key=lambda t:t['x']):
        if token['x']-end>width*.018:break
        value=token['text'].strip()
        if not (normalized_item_code(value) or re.fullmatch(r'\(?[A-Za-z0-9]{1,2}\)?',value)):break
        parts.append(value);end=token.get('x1',token['x'])
    return normalized_item_code(''.join(parts)) or normalized_item_code(anchor['text'])

def amount(text):
    text=str(text or '').strip()
    if '%' in text:return None
    text=re.sub(r'(?<=\d)\s+(?=[\d,.])','',text)
    # Vision OCR occasionally swaps thousands separators, e.g.
    # ``66.437,644.16`` for ``66,437,644.16``. Repair only this
    # unambiguous grouped-number shape; leave other malformed values alone.
    text=re.sub(r'^(\d{1,3})\.(\d{3}),(\d{3}\.\d{2})$',r'\1,\2,\3',text)
    # A scan can turn the second thousands separator into a decimal point,
    # e.g. ``37,109.274.84`` for ``37,109,274.84``.
    text=re.sub(r'^(\d{1,3}(?:,\d{3})*)\.(\d{3})\.(\d{2})$',r'\1,\2.\3',text)
    text=re.sub(r'^(\d{1,3})\.(\d{3})\.(\d{3})\.(\d{2})$',r'\1,\2,\3.\4',text)
    text=re.sub(r'^(\d{1,3})\.(\d{3})\.(\d{3})(\d{2})$',r'\1,\2,\3.\4',text)
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
    # A component prefix or numbered schedule is not itself a school/site name.
    # Retain only labels with an explicit physical or institutional entity.
    entities=[value for value in contexts if re.search(
        r'\b(?:school|building|barangay|municipal hall|town hall|health center|hospital|evacuation center|day care|classroom|site|facility|office|covered court|gymnasium|water tank|pump station|bridge|road segment|multi.?purpose building)\b',
        value,re.I)]
    return entities

def summary_qualitative_facts(text,page,method,include_counts=False,words=None):
    """Extract explicit project scale/context printed on summary pages."""
    text=str(text or '')
    facts=[]
    if include_counts:
        count_pattern=re.compile(r'(?<![\w/])\(?\s*(\d{1,4}(?:\.0+)?)\s+(sites?|schools?|buildings?|locations?|barangays?|components?|classrooms?|facilities?|tanks?|pumps?|sets?)\b\s*\)?',re.I)
        for match in count_pattern.finditer(text):
            label=match.group(2).lower().rstrip('s')
            unit={'site':'sites','school':'schools','building':'buildings','location':'locations','barangay':'barangays','component':'components','classroom':'classrooms','facilitie':'facilities','tank':'tanks','pump':'pumps','set':'sets'}.get(label,match.group(2).lower())
            count=float(match.group(1))
            if not count.is_integer():continue
            fact={'kind':'declared_count','label':unit,'value':int(count),'printedText':re.sub(r'\s+',' ',match.group(0)).strip(),
                  'sourcePage':page,'extractionMethod':method,
                  'verificationStatus':'Machine-extracted summary fact; verify the cited POW page'}
            if not any(x['kind']==fact['kind'] and x['label']==fact['label'] and x['value']==fact['value'] for x in facts):facts.append(fact)
    for value in component_contexts(text):
        facts.append({'kind':'named_component','label':'Component / site','value':value,'printedText':value,
                      'sourcePage':page,'extractionMethod':method,
                      'verificationStatus':'Machine-extracted component label; verify the cited POW page'})
    location_value=None
    if include_counts and words:
        tokens=[]
        for word in words:
            if len(word)<5:continue
            try:x0,y0,x1,y1=map(float,word[:4])
            except (TypeError,ValueError):continue
            tokens.append({'x':x0,'x1':x1,'y':(y0+y1)/2,'text':str(word[4]).strip()})
        for token in tokens:
            if token['text'].casefold().strip(':')!='project':continue
            label=next((t for t in tokens if t['text'].casefold().strip(':')=='location'
                        and abs(t['y']-token['y'])<=4 and token['x1']<=t['x']<=token['x1']+40),None)
            if not label:continue
            value_tokens=sorted((t for t in tokens if t['x']>label['x1'] and abs(t['y']-label['y'])<=4),key=lambda t:t['x'])
            if value_tokens:
                location_value=' '.join(t['text'] for t in value_tokens).strip(' :;,.')
                location_value=re.split(r'\s+(?:[a-c]\.?\s*(?:Sundays|Holidays|Rainy\s+days)|QTY\b|UNIT\b|ITEM\s+NO\.?|DESCRIPTION\b|FUND\s+SOURCE\b|ALLOT(?:T)?ED\s+AMOUNT\b)',location_value,flags=re.I)[0].strip(' :;,.')
                break
    if include_counts and not location_value:
        location=re.search(r'\bPROJECT\s+LOCATION\s*:?\s*(.{4,180}?)(?=\s+(?:WORK\s+LOCATION|TARGET\s+START|TARGET\s+COMPLETION|DATE\s+PREPARED|FUND\s+SOURCE|PROJECT\s+ID|ITEM\s+NO\.?|DESCRIPTION\s+OF\s+WORKS)\b|$)',text,re.I)
        if location:location_value=re.sub(r'\s+',' ',location.group(1)).strip(' :;,.')
    if location_value:
        value=location_value
        if value:facts.append({'kind':'project_location','label':'Project location','value':value,'printedText':value,
            'sourcePage':page,'extractionMethod':method,
            'verificationStatus':'Machine-extracted printed project location; verify the cited POW page'})
    return facts

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

def cost_category_totals_from_words(words,width,page,method):
    """Map scanned cost-summary rows by their printed columns and nearby label.

    Category summaries place the description at the left, share in a middle
    column, and category total to its right. OCR token order and fixed y bins
    are unreliable on these forms, so associate words by coordinates.
    """
    if not words or not width:return []
    tokens=[]
    for word in words:
        if len(word)<5:continue
        try:x0,y0,x1,y1=map(float,word[:4])
        except (TypeError,ValueError):continue
        tokens.append({'x':x0,'x1':x1,'y':(y0+y1)/2,'y0':y0,'y1':y1,'text':str(word[4]).strip()})
    shares=[t for t in tokens if re.fullmatch(r'\d{1,4}(?:[.,]\d{1,4})?%',t['text']) and width*.32<=t['x']<=width*.9]
    share_columns=[]
    for token in sorted(shares,key=lambda t:t['x']):
        if not share_columns or token['x']-share_columns[-1][-1]['x']>width*.03:share_columns.append([token])
        else:share_columns[-1].append(token)
    # A summary may also show unrelated percentages elsewhere on the page
    # (for example EAO). Only repeated percentage columns form category rows.
    retained_columns=[group for group in share_columns if len(group)>=3]
    shares=[token for group in retained_columns for token in group]
    shares.sort(key=lambda t:(t['y'],t['x']))
    share_columns=retained_columns
    column_centers=[sum(t['x'] for t in group)/len(group) for group in share_columns]
    found_by_label={};used_label_bands={}
    for share_token in shares:
        share_value=re.sub(r'[^\d.]','',share_token['text'].replace(',','.'))
        # OCR sometimes drops the decimal point in a printed percentage
        # (for example, 28.07% becomes 2807%).
        if '.' not in share_value and len(share_value)>=3:
            share_value=share_value[:-2]+'.'+share_value[-2:]
        try:share=float(share_value)
        except ValueError:continue
        if not 0<=share<100:continue
        # Summary rows on some native-text DPWH forms are only about 9 pt
        # apart. A 10 pt band joins neighboring categories and can select the
        # wrong amount; stay within the printed text height instead.
        row_tolerance=(max(9.0,min(12.0,(share_token['y1']-share_token['y0'])*.8))
                       if method.startswith('OCR') else max(3.5,min(5.0,(share_token['y1']-share_token['y0'])*.75)))
        row_tokens=[t for t in tokens if abs(t['y']-share_token['y'])<=row_tolerance]
        column_index=min(range(len(column_centers)),key=lambda i:abs(column_centers[i]-share_token['x'])) if column_centers else 0
        lower_x=share_token['x']+width*.045
        upper_x=column_centers[column_index+1]-width*.035 if column_index+1<len(column_centers) else width*.96
        monetary=[]
        for token in row_tokens:
            if token['x']<lower_x or token['x']>=upper_x:continue
            parsed=amount(token['text'])
            if parsed is not None and parsed>0:monetary.append((token,parsed))
        # OCR may split cents into a neighboring token. Join adjacent words
        # only within this summary row, preserving the printed x ordering.
        joined=[]
        for token,value in sorted(monetary,key=lambda pair:pair[0]['x']):
            if joined and token['x']-joined[-1][0]['x1']<=width*.01:
                previous=joined[-1][0]
                combined=amount(str(previous['text'])+'.'+str(token['text']))
                if combined is not None:
                    # Keep the previous token geometry when merging OCR-split
                    # cents. The row-ranking step below needs its y coordinate
                    # to align the amount with the printed percentage row.
                    joined[-1]=({**previous,'x1':token['x1'],'y0':min(previous['y0'],token['y0']),
                                 'y1':max(previous['y1'],token['y1']),
                                 'y':(min(previous['y0'],token['y0'])+max(previous['y1'],token['y1']))/2,
                                 'text':str(previous['text'])+'.'+str(token['text'])},combined)
                    continue
            joined.append((token,value))
        monetary=joined
        if share>0:
            if not monetary:continue
            # Prefer vertical alignment before x proximity. OCR baselines can
            # differ by several pixels across the same printed row.
            amount_token,amount_value=min(monetary,key=lambda pair:(abs(pair[0]['y']-share_token['y']),abs(pair[0]['x']-(share_token['x']+width*.10))))
            if amount_token['x']>width*.9:continue
        else:amount_value=0.0
        label_tokens=[t for t in row_tokens if width*.07<=t['x']<width*.28
                      and not re.fullmatch(r'DIVISION|\|',t['text'],re.I)
                      and not re.fullmatch(r'\d+(?:\.\d+)?',t['text'])]
        if method.startswith('OCR') and label_tokens:
            label_bands=[]
            for token in sorted(label_tokens,key=lambda t:t['y']):
                if not label_bands or token['y']-label_bands[-1][-1]['y']>3.5:label_bands.append([token])
                else:label_bands[-1].append(token)
            used=used_label_bands.setdefault(column_index,set())
            available=[band for band in label_bands if round(sum(t['y'] for t in band)/len(band),1) not in used]
            choices=available or label_bands
            selected=min(choices,key=lambda band:abs(sum(t['y'] for t in band)/len(band)-share_token['y']))
            used.add(round(sum(t['y'] for t in selected)/len(selected),1))
            label_tokens=selected
        label=' '.join(t['text'] for t in sorted(label_tokens,key=lambda t:t['x']))
        label=re.sub(r'\s+',' ',label).strip(' .,:;|-')
        if len(label)<4 or re.search(r'\b(?:TOTAL|SUBTOTAL|GRAND|SEE\s+DPWH|OCM)\b',label,re.I):continue
        part_match=re.search(r'\bPART\s*([A-I])\b|^([A-I])\s*[.):]?\s+',label,re.I)
        if part_match:
            part=next(g for g in part_match.groups() if g).upper()
            label=PART_CATEGORIES.get(part,label)
        else:
            normalized_label=re.sub(r'[^a-z]+',' ',label.casefold()).strip()
            aliases=[('A','facilities for the engineer'),('B','other general requirements'),('C','earth works'),('D','reinforced concrete'),('E','finishing and other civil works'),('F','electrical'),('G','mechanical'),('H','plumbing and sanitary works'),('I','fire protection works')]
            part=next((code for code,phrase in aliases if normalized_label==phrase or normalized_label.startswith(phrase)),None)
            if part:label=PART_CATEGORIES[part]
        key=label.casefold()
        row=found_by_label.setdefault(key,{'label':label,'sharePct':share,'amountPesos':None,
             'sourcePage':page,'extractionMethod':method,
             'verificationStatus':'Machine-extracted printed category summary; verify cited POW page'})
        if column_index==0:
            row['submittedAmountPesos']=float(amount_value)
            row['amountPesos']=float(amount_value)
        elif len(column_centers)>1 and column_index==1:
            row['evaluatedAmountPesos']=float(amount_value)
            if row.get('amountPesos') is None:row['amountPesos']=float(amount_value)
        elif row.get('amountPesos') is None:
            row['amountPesos']=float(amount_value)
    return list(found_by_label.values())

PART_CATEGORIES={
    'A':'Facilities for the Engineer','B':'Other General Requirements',
    'C':'Earthwork','D':'Reinforced concrete',
    'E':'Finishing and other civil works','F':'Electrical','G':'Mechanical',
    'H':'Plumbing and sanitary works','I':'Fire protection works',
}

def category_from_heading(text):
    text=str(text or '')
    match=re.search(r'\bPART\s*([A-I])\b|\bPART([A-I])\b',text,re.I)
    if match:return PART_CATEGORIES.get((match.group(1) or match.group(2)).upper())
    normalized=re.sub(r'[^a-z]+',' ',text.casefold()).strip()
    compact=normalized.replace(' ','')
    for code,label in PART_CATEGORIES.items():
        key=re.sub(r'[^a-z]+','',label.casefold())
        if key and (key in compact or (code=='C' and 'earthworks' in compact)):
            return label
    return None

def item_rows_from_words(words,width,page,method,current_category=None):
    """Recover submitted direct-cost item rows from scanned multi-column POWs."""
    if not words or not width:return [],current_category
    tokens=[]
    for word in words:
        if len(word)<5:continue
        try:x0,y0,x1,y1=map(float,word[:4])
        except (TypeError,ValueError):continue
        tokens.append({'x':x0,'y':(y0+y1)/2,'text':str(word[4]).strip()})
    # Carry the Part heading across pages, but switch category at each new
    # heading. A heading's table total can also name the preceding Part.
    prior_category=current_category
    bands=[]
    for token in sorted((t for t in tokens if t['x']<width*.36),key=lambda t:t['y']):
        band=next((b for b in reversed(bands) if abs(b['y']-token['y'])<=10),None)
        if band is None:band={'y':token['y'],'tokens':[]};bands.append(band)
        band['tokens'].append(token)
    category_at=[];part_total_y=[]
    for band in bands:
        text=' '.join(t['text'] for t in sorted(band['tokens'],key=lambda t:t['x']))
        if re.search(r'TOTAL\s+OF\s+PART',text,re.I):part_total_y.append(band['y'])
        heading_category=category_from_heading(text)
        if heading_category:
            current_category=heading_category
            category_at.append((band['y'],current_category))
    anchors=sorted((t for t in tokens if t['x']<width*.18 and normalized_item_code(t['text'])),key=lambda t:t['y'])
    rows=[]
    for index,anchor in enumerate(anchors):
        next_y=anchors[index+1]['y'] if index+1<len(anchors) else float('inf')
        next_total=next((y for y in part_total_y if y>anchor['y']),float('inf'))
        next_y=min(next_y,next_total)
        category=next((value for y,value in reversed(category_at) if y<=anchor['y']),prior_category)
        block=[t for t in tokens if anchor['y']-8<=t['y']<next_y and t['x']>=width*.28]
        statuses=[]
        for token in block:
            if token['text'].upper()!='AS':continue
            neighbor=next((t for t in block if width*.32<=t['x']<=width*.42 and abs(t['y']-token['y'])<=4 and t['x']>token['x']),None)
            if neighbor and neighbor['text'].upper().startswith('SUBMIT'):
                statuses.append((token['y'], 'as_submitted'))
        if not statuses:continue
        desc=' '.join(t['text'] for t in sorted(tokens,key=lambda t:(t['y'],t['x']))
                      if anchor['y']-8<=t['y']<=anchor['y']+9 and width*.08<=t['x']<width*.30)
        desc=re.sub(r'\s+',' ',desc).strip(' .,:;-')
        for row_y,basis in statuses:
            at=[t for t in block if abs(t['y']-row_y)<=8]
            quantity=next((amount(t['text']) for t in at if width*.40<=t['x']<width*.47 and amount(t['text']) is not None),None)
            unit=next((t['text'] for t in at if width*.47<=t['x']<width*.51 and re.search(r'[A-Za-z]',t['text'])),None)
            direct=next((amount(t['text']) for t in sorted(at,key=lambda t:t['x']) if width*.51<=t['x']<width*.58 and amount(t['text']) is not None),None)
            if direct is None or not desc:continue
            if quantity is not None and quantity<=0:continue
            rows.append({'itemCode':item_code_at_anchor(tokens,anchor,width),'description':desc,
                'quantity':float(quantity) if quantity is not None else None,'unit':unit,
                'printedUnitCostPesos':None,
                'calculatedUnitCostPesos':float(direct/quantity) if quantity else None,
                'amountPesos':float(direct),'sourcePage':page,'sourceCells':None,
                'sourceBbox':[width*.08,anchor['y']-8,width*.58,row_y+8],
                'extractionMethod':method+' · submitted direct-cost column mapped by OCR word positions',
                'arithmeticStatus':'Direct cost amount/quantity is derived; printed rate is a total-cost rate' if quantity else 'Quantity/unit not recovered; verify source row',
                'verificationStatus':'Machine-extracted submitted item row; verify source page',
                'costBasis':basis,'amountBasis':'Submitted direct-cost item amount',
                'costCategory':category})
    return rows,current_category

def summary_item_rows_from_words(words,width,page,method,current_category=None):
    """Map the compact ITEMIZED BREAKDOWN table used by some DEOs.

    These sheets print an item code, description, quantity, unit, and submitted
    direct cost on one physical row instead of repeating AS SUBMITTED labels.
    """
    if not words or not width:return [],current_category
    text=' '.join(str(w[4]) for w in words)
    has_direct_cost=(re.search(r'DIRECT\s+COST',text,re.I) or
                     (re.search(r'\bDIRECT\b',text,re.I) and len(re.findall(r'\bCOST\b',text,re.I))>=2))
    if not (re.search(r'ITEMIZED',text,re.I) and re.search(r'DESCRIPTION',text,re.I)
            and re.search(r'(?:QUANTITY|\bQTY\b)',text,re.I) and has_direct_cost):
        return [],current_category
    prior_category=current_category
    tokens=[]
    for word in words:
        if len(word)<5:continue
        try:x0,y0,x1,y1=map(float,word[:4])
        except (TypeError,ValueError):continue
        tokens.append({'x':x0,'x1':x1,'y':(y0+y1)/2,'text':str(word[4]).strip()})
    # Use the printed UNIT heading when OCR keeps the unit just outside the
    # usual normalized column band (common on rotated landscape scans).
    unit_headers=[(t['x']+t['x1'])/2 for t in tokens if t['text'].strip().upper()=='UNIT']
    unit_column=min(unit_headers,key=lambda x:abs(x-width*.46)) if unit_headers else None
    bands=[]
    for token in sorted((t for t in tokens if t['x']<width*.36),key=lambda t:t['y']):
        band=next((b for b in reversed(bands) if abs(b['y']-token['y'])<=10),None)
        if band is None:band={'y':token['y'],'tokens':[]};bands.append(band)
        band['tokens'].append(token)
    category_at=[]
    for band in bands:
        line=' '.join(t['text'] for t in sorted(band['tokens'],key=lambda t:t['x']))
        heading_category=category_from_heading(line)
        if heading_category:
            current_category=heading_category
            category_at.append((band['y'],current_category))
    anchors=sorted((t for t in tokens if t['x']<width*.11 and normalized_item_code(t['text'])),key=lambda t:t['y'])
    rows=[]
    for anchor in anchors:
        same=[t for t in tokens if abs(t['y']-anchor['y'])<=9]
        category=next((value for y,value in reversed(category_at) if y<=anchor['y']),None)
        if category is None:category=prior_category
        description=' '.join(t['text'] for t in sorted(same,key=lambda t:t['x']) if width*.08<=t['x']<width*.315
                            and t['text'].upper() not in {'AS','SUBMITTED','EVALUATED'})
        description=re.sub(r'\s+',' ',description).strip(' .,:;-')
        quantity=next((amount(t['text']) for t in same if width*.28<=t['x']<width*.40 and amount(t['text']) is not None),None)
        unit_tokens=[t for t in same if re.search(r'[A-Za-z]',t['text']) and
                     ((unit_column is not None and abs((t['x']+t['x1'])/2-unit_column)<=width*.025)
                      or (unit_column is None and width*.40<=t['x']<width*.49))]
        unit=' '.join(t['text'] for t in sorted(unit_tokens,key=lambda t:t['x'])).strip(' :;,.') or None
        direct_tokens=sorted((t for t in same if width*.46<=t['x']<width*.57 and re.fullmatch(r'[\d,.]+',t['text'])),key=lambda t:t['x'])
        direct=None
        if direct_tokens:
            # Scanned landscape tables sometimes split one printed amount
            # over adjacent OCR words, including its decimal part.
            groups=[]
            for token in direct_tokens:
                if groups and token['x']-groups[-1][-1]['x1']<=width*.01:
                    groups[-1].append(token)
                else:groups.append([token])
            group=max(groups,key=lambda g:len(g))
            if len(group)==1:direct=amount(group[0]['text'])
            else:
                joined=''.join(re.sub(r'[^\d.]','',t['text']) for t in group)
                if '.' not in joined and len(re.sub(r'\D','',joined))>=3:
                    digits=re.sub(r'\D','',joined);joined=digits[:-2]+'.'+digits[-2:]
                direct=amount(joined)
                if direct is None:
                    direct=next((amount(t['text']) for t in group if amount(t['text']) is not None and amount(t['text'])>=1000),None)
        if not description or direct is None:continue
        share_tokens=sorted((t for t in same if t['x']>=width*.88 and re.fullmatch(r'[\d,.]+%?',t['text'])),key=lambda t:t['x'])
        direct_share=None
        if share_tokens:
            share_groups=[]
            for token in share_tokens:
                if share_groups and token['x']-share_groups[-1][-1]['x1']<=width*.01:share_groups[-1].append(token)
                else:share_groups.append([token])
            share_group=max(share_groups,key=lambda g:len(g))
            share_text=''.join(re.sub(r'[^\d.]','',t['text']) for t in share_group)
            if len(share_group)>1 and '.' not in share_text and len(share_text)>=3:
                share_text=share_text[:-4]+'.'+share_text[-4:]
            try:
                candidate_share=float(share_text.replace(',','.'))
                if 0<candidate_share<=100:direct_share=candidate_share
            except ValueError:pass
        rows.append({'itemCode':item_code_at_anchor(tokens,anchor,width),'description':description,
            'quantity':float(quantity) if quantity is not None else None,'unit':unit,
            'directCostSharePct':direct_share,
            'printedUnitCostPesos':None,'calculatedUnitCostPesos':float(direct/quantity) if quantity else None,
            'amountPesos':float(direct),'sourcePage':page,'observedPages':[page],
            'sourceCells':None,'sourceBbox':[width*.08,anchor['y']-9,width*.57,anchor['y']+9],
            'extractionMethod':method+' · compact submitted row mapped by OCR word positions',
            'arithmeticStatus':'Direct cost amount/quantity is derived; printed inclusive unit cost is separate' if quantity else 'Quantity not recovered; verify source row',
            'verificationStatus':'Machine-extracted submitted item row; verify source page',
            'costBasis':'as_submitted','amountBasis':'Submitted direct-cost item amount','costCategory':category})
    return rows,current_category

def itemized_rows(grid,page,bbox,context_text=''):
    """Recognize the submitted/evaluated DPWH itemized bill, not unit-price analyses."""
    clean=[[re.sub(r'\s+',' ',str(c or '')).strip() for c in row] for row in grid]
    header=next((i for i,row in enumerate(clean) if 'DIRECT COST' in row and any('TOTAL UNIT COST' in c for c in row) and ((('ITEM NO.' in row and 'DESCRIPTION' in row) and any(re.fullmatch(r'(?:QUANTITY|QTY)\.?',c) for c in row)) or any('ITEM NO.' in r for r in clean[i+1:i+4]))),None)
    if header is None:return None
    headings=clean[header]
    item_index=headings.index('ITEM NO.') if 'ITEM NO.' in headings else 1
    description_index=headings.index('DESCRIPTION') if 'DESCRIPTION' in headings else 2
    q=next((i for i,c in enumerate(headings) if re.fullmatch(r'(?:QUANTITY|QTY)\.?',c)),4)
    unit=headings.index('UNIT') if 'UNIT' in headings else 6
    direct=headings.index('DIRECT COST')
    following=clean[header+1:header+5]
    sub=next((row for row in following if any(re.search(r'\bTOTAL\b',c) for c in row) and any(re.search(r'\bUNIT\s+COST\b',c) for c in row)),None)
    basis=next((row for row in following if 'AS SUBMITTED' in row and 'AS EVALUATED' in row and not any('ITEM NO.' in c for c in row)),None)
    if not sub or not basis:return None
    total=next(i for i,c in enumerate(sub) if re.search(r'\bTOTAL\b',c))
    price=next(i for i,c in enumerate(sub) if re.search(r'\bUNIT\s+COST\b',c))
    indirect=next(i for i,c in enumerate(headings) if 'TOTAL UNIT COST' in c)
    if not (q<unit<=direct<=total<price<indirect):return None
    records=[];controls=[]
    context_source=context_text or ' '.join(' '.join(r) for r in clean[:header])
    contexts=component_contexts(context_source)
    current_contexts=contexts
    current_category=None
    def column(start,end,label):return next((i for i in range(start,min(end,len(basis))) if basis[i]==label),None)
    for label in ('AS SUBMITTED','AS EVALUATED'):
        qi=column(q,unit,label)
        if qi is None:qi=q
        ai=column(total,price,label);pi=column(price,indirect,label)
        if qi is None or ai is None:continue
        for cells in clean[header+1:]:
            joined=' '.join(cells)
            heading_category=category_from_heading(joined)
            if heading_category:current_category=heading_category
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
                row.update({'sourceCells':cells,'costBasis':label.lower().replace(' ','_'),'amountBasis':'Direct cost total; excludes markup, VAT and EAO','componentContext':context,'componentContexts':current_contexts,'costCategory':current_category,'columnMapping':{'quantity':qi,'unit':unit,'directCostTotal':ai,'directUnitCost':pi}})
                records.append(row)
            elif re.search(r'(?:GRAND\s+TOTAL|TOTAL\s+OF\s+PART\s+[A-I])',joined,re.I) and amount(cells[ai]) is not None:
                printed=float(amount(cells[ai]));subset=[r for r in records if r['costBasis']==label.lower().replace(' ','_')]
                part_total=re.search(r'TOTAL\s+OF\s+PART\s+([A-I])',joined,re.I)
                if part_total:
                    target_category=PART_CATEGORIES.get(part_total.group(1).upper())
                    subset=[r for r in subset if r.get('costCategory')==target_category]
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
    vision_path=output/'pow-ocr-vision.json'
    project_code=output.parents[1].name if len(output.parents)>1 else ''
    reviewed_path=Path(__file__).with_name('pow_reviewed_category_totals.json')
    try:
        review_config=json.loads(reviewed_path.read_text())
        preferred_rotations=review_config.get('pageRotationOverrides',{}).get(project_code,[])
    except (OSError,ValueError,AttributeError):
        preferred_rotations=[]
    rotation_args=['--preferred-rotations='+','.join(map(str,preferred_rotations))] if preferred_rotations else []
    module_cache=Path(os.environ.get('TMPDIR') or '/tmp')/'bettergov-pow-swift-module-cache'
    try:module_cache.mkdir(parents=True,exist_ok=True)
    except OSError:pass
    swift_environment={**os.environ,'CLANG_MODULE_CACHE_PATH':str(module_cache),'SWIFT_MODULECACHE_PATH':str(module_cache)}
    # Reuse OCR already saved for this cached PDF. This also makes targeted
    # parser reruns work when the local OCR executable is temporarily absent.
    try:
        if not preferred_rotations and vision_path.is_file() and vision_path.stat().st_mtime_ns>=path.stat().st_mtime_ns:
            cached_vision=json.loads(vision_path.read_text())
            if cached_vision.get('pages'):vision=cached_vision
    except (OSError,ValueError,AttributeError):
        vision=None
    if vision is None and sys.platform=='darwin' and shutil.which('swift') and any(len(p.get_text().strip())<40 for p in document):
        try:
            response=subprocess.run(['swift',str(Path(__file__).with_name('ocr_vision.swift')),str(path),'100',*rotation_args],capture_output=True,text=True,check=True,timeout=240,env=swift_environment)
            vision=json.loads(response.stdout)
            if isinstance(vision,dict):vision['pdfSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            vision_path.write_text(json.dumps(vision,ensure_ascii=False))
        except Exception:
            # Keep a valid current sidecar if a fresh OCR invocation fails.
            pass
    current_context=None;current_cost_category=None;cost_categories=[];summary_pages=[];qualitative_facts=[]
    for number,page in enumerate(document):
        if number>=100:break
        precomputed_orientation_candidates=[]
        native_page_rotation=page.rotation
        page_rect_orientation='landscape' if page.rect.width>page.rect.height else 'portrait' if page.rect.height>page.rect.width else 'square'
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
            elif sys.platform=='darwin' and shutil.which('swift'):
                try:
                    response=subprocess.run(['swift',str(Path(__file__).with_name('ocr_vision.swift')),str(path),f'--page={number+1}','--all-candidates',*rotation_args],capture_output=True,text=True,check=True,timeout=240,env=swift_environment)
                    retry_page=next((item for item in json.loads(response.stdout).get('pages',[]) if item.get('page')==number+1),None)
                    if retry_page:
                        precomputed_orientation_candidates=[candidate for candidate in retry_page.get('candidates',[]) if candidate.get('words')]
                        if precomputed_orientation_candidates:
                            best_orientation=precomputed_orientation_candidates[0]
                            words=best_orientation['words'];ocr_width=best_orientation.get('width',page.rect.width)
                            rotation=best_orientation.get('rotation',0);method='OCR · Apple Vision six-orientation retry; selected '+str(rotation)+'°'
                            text=' '.join(str(w[4]) for w in words)
                        else:
                            pages.append({'page':number+1,'status':'needs_ocr','message':'Six orientation/resolution attempts returned no OCR words.'});continue
                    else:
                        pages.append({'page':number+1,'status':'needs_ocr','message':'Targeted orientation retry returned no page record.'});continue
                except Exception:
                    pages.append({'page':number+1,'status':'needs_ocr','message':'Image-only page; orientation retry could not run.'});continue
            else:
                pages.append({'page':number+1,'status':'needs_ocr','message':'Image-only page; OCR required before ranking bill rows.'});continue
        category_count_before=len(cost_categories)
        category_text=text
        # Percentages on DPWH-OMSP-13-15 bill pages are often the VAT rate.
        # Only read project-wide categories from the dedicated budget summary
        # page, which also carries the overall program/cost heading.
        is_category_summary=bool(SUMMARY_PAGE.search(text))
        if is_category_summary:summary_pages.append(number+1)
        qualitative_text=text
        if is_category_summary:
            try:qualitative_text+='\n'+' '.join(str(cell or '') for table in page.find_tables().tables for row in table.extract() for cell in row)
            except Exception:pass
        qualitative_facts.extend(summary_qualitative_facts(qualitative_text,number+1,method,include_counts=is_category_summary,words=words if method.startswith('OCR') else None))
        if is_category_summary and words:
            mapped=cost_category_totals_from_words(words,ocr_width,number+1,method)
            if mapped:
                # A real printed category summary is a full allocation split.
                # This prevents percentages inside a single unit-price/detail
                # table from being misreported as project-wide cost categories.
                share_total=sum(row['sharePct'] for row in mapped)
                if len(mapped)>=3 and 98<=share_total<=102:
                    cost_categories.extend(mapped)
            elif method.startswith('OCR'):
                category_lines={}
                for word in words:category_lines.setdefault(round(word[1]/5),[]).append(word)
                category_text='\n'.join(' '.join(w[4] for w in sorted(line,key=lambda x:x[0]))
                                        for _,line in sorted(category_lines.items()))
                cost_categories.extend(cost_category_totals(category_text,number+1,method))
        elif is_category_summary:
            cost_categories.extend(cost_category_totals(category_text,number+1,method))
        page_rows=[]
        page_start_category=current_cost_category
        # Detailed component-breakdown sheets repeat item codes and show
        # materials/labour/equipment amounts plus mark-up and VAT. They are
        # supporting cost analyses, not another set of direct-cost bill rows.
        # Qualify the whole heading family (including "FOR EACH ITEM") before
        # the native-table and OCR paths can mistake component columns for
        # duplicate bill amounts.
        component_heading=' '.join([text,*[str(w[4]) for w in words]])
        is_component_cost_analysis=bool(re.search(r'DETAILED\s+BREAKDOWN\s+OF\s+COMPONENT\b',component_heading,re.I))
        current_context=component_context(text) or current_context
        if method.startswith('native'):
            try:
                for table in page.find_tables().tables:
                    grid=table.extract();source_tables.append({'page':number+1,'bbox':list(table.bbox),'cells':grid})
                    itemized=None if is_component_cost_analysis else itemized_rows(grid,number+1,list(table.bbox),text)
                    if itemized is not None:
                        page_rows.extend(itemized['rows']);itemized_controls.extend(itemized['controls']);continue
                    continued=[] if is_component_cost_analysis else continuation_rows(grid,number+1,list(table.bbox),current_context)
                    if continued:
                        page_rows.extend(continued);continue
                    context=' '.join(str(c or '') for r in grid[:4] for c in r)
                    if is_component_cost_analysis or not re.search(r'quantity',context,re.I) or not re.search(r'(?:amount|total\s+cost)',context,re.I):continue
                    if re.search(r'detailed\s+(?:unit\s+price|cost)\s+analysis',text,re.I):continue
                    for cells in grid:
                        row=candidate(cells,number+1,method,list(table.bbox))
                        if row:page_rows.append(row)
            except Exception:pass
        review=False
        if not page_rows:
            if method.startswith('OCR') and not is_component_cost_analysis:
                page_rows,current_cost_category=item_rows_from_words(words,ocr_width,number+1,method,current_cost_category)
            if not page_rows and not is_component_cost_analysis:page_rows,review=word_rows(words,ocr_width,number+1,method)
        if method.startswith('OCR') and not is_component_cost_analysis:
            compact_rows,compact_category=summary_item_rows_from_words(words,ocr_width,number+1,method,page_start_category)
            if compact_rows:
                compact_keys={(r.get('itemCode'),r.get('amountPesos')) for r in compact_rows}
                page_rows=[r for r in page_rows if (r.get('itemCode'),r.get('amountPesos')) not in compact_keys]
                page_rows.extend(compact_rows)
                current_cost_category=compact_category
        # Native extraction can return plenty of text while still failing to
        # map a rotated table. Retry only pages with no recovered rows or
        # summary totals, then choose the orientation that actually parses.
        if not is_component_cost_analysis and not page_rows and len(cost_categories)==category_count_before:
            page_hint=(text+' '+' '.join(str(w[4]) for w in words)).upper()
            likely_pow_page=(bool(re.search(r'ITEM\s*(?:NO|NUMBER)|DESCRIPTION|QUANTITY|UNIT\s+OF\s+WORK|DIRECT\s+COST|TOTAL\s+COST|PROGRAM\s+OF\s+WORKS|BREAKDOWN\s+OF\s+EXPENDITURES',page_hint))
                             or (method.startswith('OCR') and (len(words)>=12 or bool(page.get_images(full=True)))))
            if likely_pow_page:
                orientation_candidates=precomputed_orientation_candidates
                if sys.platform=='darwin' and shutil.which('swift'):
                    try:
                        response=subprocess.run(['swift',str(Path(__file__).with_name('ocr_vision.swift')),str(path),f'--page={number+1}','--all-candidates',*rotation_args],capture_output=True,text=True,check=True,timeout=240,env=swift_environment)
                        retry_data=json.loads(response.stdout)
                        retry_page=next((item for item in retry_data.get('pages',[]) if item.get('page')==number+1),None)
                        if retry_page:orientation_candidates=[candidate for candidate in retry_page.get('candidates',[]) if candidate.get('words')]
                    except Exception:
                        orientation_candidates=[]
                if not orientation_candidates and shutil.which('tesseract'):
                    original_rotation=page.rotation
                    for rotation,dpi in [(0,250),(90,250),(180,250),(270,250),(90,350),(270,350)]:
                        try:
                            page.set_rotation(rotation)
                            textpage=page.get_textpage_ocr(language='eng',dpi=dpi,full=True)
                            candidate_words=page.get_text('words',textpage=textpage)
                            orientation_candidates.append({'rotation':rotation,'width':page.rect.width,'words':candidate_words,'score':0,'method':f'OCR · Tesseract orientation retry {rotation}° at {dpi} dpi'})
                        except Exception:continue
                    page.set_rotation(original_rotation)
                best_retry=None
                for candidate_orientation in orientation_candidates:
                    retry_words=candidate_orientation.get('words',[])
                    retry_width=candidate_orientation.get('width') or ocr_width
                    retry_method=candidate_orientation.get('method') or 'OCR · Apple Vision orientation retry (six attempts), selected '+str(candidate_orientation.get('rotation',0))+'°'
                    retry_category=page_start_category
                    retry_rows,retry_category=item_rows_from_words(retry_words,retry_width,number+1,retry_method,retry_category)
                    retry_review=False
                    if not retry_rows:retry_rows,retry_review=word_rows(retry_words,retry_width,number+1,retry_method)
                    compact_retry,compact_category=summary_item_rows_from_words(retry_words,retry_width,number+1,retry_method,page_start_category)
                    if compact_retry:
                        retry_keys={(r.get('itemCode'),r.get('amountPesos')) for r in compact_retry}
                        retry_rows=[r for r in retry_rows if (r.get('itemCode'),r.get('amountPesos')) not in retry_keys]+compact_retry
                        retry_category=compact_category
                    retry_lines={}
                    for word in retry_words:retry_lines.setdefault(round(word[1]/5),[]).append(word)
                    retry_text='\n'.join(' '.join(str(w[4]) for w in sorted(line,key=lambda x:x[0])) for _,line in sorted(retry_lines.items()))
                    retry_summary=[]
                    if re.search(r'PROGRAM\s+OF\s+WORKS?\s*/\s*BUDGET\s+COST|BREAKDOWN\s+OF\s+EXPENDITURES',retry_text,re.I):
                        retry_summary=cost_category_totals_from_words(retry_words,retry_width,number+1,retry_method)
                        if not retry_summary:retry_summary=cost_category_totals(retry_text,number+1,retry_method)
                    retry_quality=(len(retry_rows)*1000+len(retry_summary)*100+int(candidate_orientation.get('score',0)))
                    if retry_rows or len(retry_summary)>=3:
                        if best_retry is None or retry_quality>best_retry[0]:
                            best_retry=(retry_quality,retry_rows,retry_category,retry_review,retry_words,retry_width,retry_method,retry_summary,retry_text)
                if best_retry:
                    _,page_rows,current_cost_category,review,words,ocr_width,method,retry_summary,text=best_retry
                    if retry_summary:
                        share_total=sum(r['sharePct'] for r in retry_summary)
                        if len(retry_summary)>=3 and 90<=share_total<=110:cost_categories.extend(retry_summary)
        paddle_record=None
        scanned_page=method.startswith('OCR') or (len(text.strip())<40 and bool(page.get_images(full=True)))
        if not is_component_cost_analysis and scanned_page:
            paddle=paddle_words(page)
            if paddle:
                paddle_candidates=[]
                for attempt in paddle['attempts']:
                    candidate_words=attempt['words'];candidate_method=attempt['method'];candidate_width=attempt['width']
                    candidate_rows,candidate_category=item_rows_from_words(candidate_words,candidate_width,number+1,candidate_method,page_start_category)
                    candidate_review=False
                    if not candidate_rows:candidate_rows,candidate_review=word_rows(candidate_words,candidate_width,number+1,candidate_method)
                    compact_rows,compact_category=summary_item_rows_from_words(candidate_words,candidate_width,number+1,candidate_method,page_start_category)
                    if compact_rows:
                        compact_keys={(r.get('itemCode'),r.get('amountPesos')) for r in compact_rows}
                        candidate_rows=[r for r in candidate_rows if (r.get('itemCode'),r.get('amountPesos')) not in compact_keys]+compact_rows
                        candidate_category=compact_category
                    paddle_candidates.append((candidate_rows,candidate_review,candidate_category,attempt))
                if paddle_candidates:
                    paddle_rows,paddle_review,paddle_category,paddle_best=max(paddle_candidates,key=lambda candidate:(
                        len(candidate[0]),sum(bool(row.get('itemCode')) for row in candidate[0]),not candidate[1],
                        candidate[3]['structureScore'],candidate[3]['meanConfidence'],candidate[3]['wordCount']))
                    existing_codes={row.get('itemCode') for row in page_rows if row.get('itemCode')}
                    conflicts=[];original_page_row_count=len(page_rows)
                    existing_keys={(row.get('itemCode'),row.get('amountPesos'),row.get('quantity')) for row in page_rows}
                    for row in paddle_rows:
                        code=row.get('itemCode');key=(code,row.get('amountPesos'),row.get('quantity'))
                        if code and code in existing_codes:
                            prior=next((saved for saved in page_rows if saved.get('itemCode')==code),None)
                            if prior and (prior.get('amountPesos'),prior.get('quantity'))!=(row.get('amountPesos'),row.get('quantity')):conflicts.append(code)
                            continue
                        if key not in existing_keys:
                            page_rows.append(row);existing_keys.add(key)
                            if code:existing_codes.add(code)
                    if paddle_category is not None:current_cost_category=paddle_category
                    paddle_record={'method':paddle_best['method'],'rotation':paddle_best['rotation'],'dpi':paddle_best['dpi'],
                        'meanConfidence':paddle_best['meanConfidence'],'candidateRows':len(paddle_rows),
                        'addedRows':len(page_rows)-original_page_row_count,
                        'conflictingItemCodes':sorted(set(conflicts))}
                    if not method.startswith('OCR') or not words:
                        words=paddle_best['words'];ocr_width=paddle_best['width'];text=paddle_best['text'];method=paddle_best['method']
                    if not page_rows and paddle_review:review=True
        if method.startswith('OCR') and page_rows:
            lines={}
            for w in words:lines.setdefault(round(w[1]/5),[]).append(w)
            page_context=component_context('\n'.join(' '.join(w[4] for w in sorted(line,key=lambda x:x[0])) for _,line in sorted(lines.items())))
            if page_context:
                for row in page_rows:row['componentContext']=page_context
        role='supporting_detail' if is_component_cost_analysis else 'summary' if is_category_summary else 'itemized_detail' if re.search(r'ITEM\s*(?:NO\.?|NUMBER)|QUANTITY.{0,80}(?:UNIT|AMOUNT|COST)',text,re.I) else 'supporting_detail'
        selected_rotation_match=re.search(r'rotated scan\s+(\d+)°',method)
        page_record={'page':number+1,'pageRole':role,'nativePageRotation':native_page_rotation,'pageRectOrientation':page_rect_orientation,
                      'ocrSelectedRotationDegrees':int(selected_rotation_match.group(1)) if selected_rotation_match else None,
                      'status':'candidate_rows' if page_rows else 'needs_manual_review' if review else 'no_bill_rows_recovered','rows':len(page_rows),'method':method,'reviewNote':'Numeric columns could not be mapped safely; inspect the source page.' if review else None}
        if paddle_record:
            page_record.update({'paddleMethod':paddle_record['method'],'paddleSelectedRotationDegrees':paddle_record['rotation'],
                'paddleSelectedDpi':paddle_record['dpi'],'paddleMeanConfidence':paddle_record['meanConfidence'],
                'paddleCandidateRows':paddle_record['candidateRows'],'paddleAddedRows':paddle_record['addedRows']})
            if paddle_record['conflictingItemCodes']:page_record['paddleConflictingItemCodes']=paddle_record['conflictingItemCodes']
        pages.append(page_record)
        rows.extend(page_rows)
    # Retain repeated observations rather than summing duplicate page/table views.
    grouped={}
    for row in rows:
        key=json.dumps([row[k] for k in ['itemCode','description','quantity','unit','amountPesos']]+[row.get('costBasis'),row.get('amountBasis'),row.get('componentContext')],ensure_ascii=False)
        if key in grouped:grouped[key]['observedPages'].append(row['sourcePage'])
        else:row['observedPages']=[row['sourcePage']];grouped[key]=row
    (output/'pow-native-tables.json').write_text(json.dumps(source_tables,ensure_ascii=False,indent=2)+'\n')
    result=list(grouped.values());result.sort(key=lambda r:-r['amountPesos'])
    # A small reviewed correction list records values that were checked on
    # the original page when OCR confused a digit despite otherwise locating
    # the correct row. The parser applies it in both watcher and on-demand runs.
    reviewed_path=Path(__file__).with_name('pow_reviewed_category_totals.json')
    project_code=next((parent.name for parent in (path.parent,*path.parents)
                       if re.fullmatch(r'\d{4}DPWH-Proposal-\d{5}',parent.name)),None)
    if project_code and reviewed_path.is_file():
        try:
            reviewed_data=json.loads(reviewed_path.read_text())
            reviewed_rows=reviewed_data.get('reviewedRows',{}).get(project_code,[])
            reviewed_rows_to_add=reviewed_data.get('reviewedRowsToAdd',{}).get(project_code,[])
            direct_total=reviewed_data.get('directCostTotalsPesos',{}).get(project_code)
        except (OSError,ValueError):reviewed_rows=[];reviewed_rows_to_add=[];direct_total=None
        if direct_total:
            # When OCR drops the decimal and grouping marks, the printed
            # percent-of-direct-cost column can identify the cents scale.
            # Only repair a value when dividing by 100 lands inside the
            # rounding interval of the printed four-decimal percentage.
            tolerance=float(direct_total)*0.0000005
            for target in result:
                share=target.get('directCostSharePct')
                if share is None:continue
                expected=float(direct_total)*float(share)/100
                candidate_amount=round(float(target['amountPesos'])/100,2)
                if abs(float(target['amountPesos'])-expected)>tolerance and abs(candidate_amount-expected)<=tolerance:
                    target['amountPesos']=candidate_amount
                    if target.get('quantity'):target['calculatedUnitCostPesos']=candidate_amount/target['quantity']
                    target['extractionMethod']+=' · decimal scale recovered from printed direct-cost share'
                    target['verificationStatus']='OCR decimal scale recovered using printed direct-cost share and POW total; verify source page'
        for correction in reviewed_rows:
            target=next((row for row in result if row.get('itemCode')==correction.get('itemCode')
                         and row.get('sourcePage')==correction.get('sourcePage')),None)
            if target is None:continue
            target['amountPesos']=float(correction['amountPesos'])
            target['directCostSharePct']=correction.get('directCostSharePct')
            if correction.get('quantity') is not None:target['quantity']=float(correction['quantity'])
            if correction.get('unit') is not None:target['unit']=correction['unit']
            if target.get('quantity'):target['calculatedUnitCostPesos']=target['amountPesos']/target['quantity']
            target['description']=correction.get('description') or target.get('description')
            target['manualReview']=True
            target['verificationStatus']=correction.get('verificationStatus','Manually reviewed against source POW page')
            target['extractionMethod']+=' · source-page checked correction'
        for seed in reviewed_rows_to_add:
            quantity=float(seed['quantity']) if seed.get('quantity') is not None else None
            amount_value=float(seed['amountPesos'])
            basis=seed.get('costBasis','as_submitted')
            normalized_description=' '.join(str(seed.get('description') or '').casefold().split())
            target=next((row for row in result if row.get('sourcePage')==seed.get('sourcePage')
                         and row.get('costBasis')==basis
                         and abs(float(row.get('amountPesos') or 0)-amount_value)<=.01
                         and (row.get('costCategory')==seed.get('costCategory') or not seed.get('costCategory'))),None)
            reviewed_row={
                'itemCode':seed.get('itemCode'),'description':seed.get('description'),
                'quantity':quantity,'unit':seed.get('unit'),
                'printedUnitCostPesos':float(seed['printedUnitCostPesos']) if seed.get('printedUnitCostPesos') is not None else None,
                'inclusiveUnitCostPesos':float(seed['inclusiveUnitCostPesos']) if seed.get('inclusiveUnitCostPesos') is not None else None,
                'calculatedUnitCostPesos':amount_value/quantity if quantity else None,
                'amountPesos':amount_value,'directCostSharePct':float(seed['directCostSharePct']) if seed.get('directCostSharePct') is not None else round(100*amount_value/float(direct_total),4) if direct_total else None,
                'sourcePage':seed.get('sourcePage'),'observedPages':[seed.get('sourcePage')],
                'sourceCells':None,'sourceBbox':None,'componentContext':None,'componentContexts':[],
                'extractionMethod':'Manual source transcription · reviewed POW page '+str(seed.get('sourcePage')),
                'arithmeticStatus':'Manually transcribed; verify source arithmetic and columns',
                'verificationStatus':seed.get('verificationStatus','Manually transcribed from the source POW page'),
                'manualReview':True,'costBasis':basis,'amountBasis':'Direct cost total; excludes markup, VAT and EAO',
                'costCategory':seed.get('costCategory')}
            if target is not None:
                target.update(reviewed_row)
            else:
                result.append(reviewed_row)
    for row in result:row['shareOfNepAllocationPct']=round(100*row['amountPesos']/allocation_pesos,4) if allocation_pesos else None
    for row in result:
        allocation_share=row.get('shareOfNepAllocationPct')
        row['lowShareParsingIndicator']=bool(allocation_share is not None and allocation_share<1)
    page_category_totals={}
    for row in cost_categories:
        p=row.get('sourcePage');group=page_category_totals.setdefault(p,[]);group.append(row)
    eligible_category_pages={p for p,group in page_category_totals.items()
        if len(group)>=3 and 98<=sum(float(r.get('sharePct') or 0) for r in group)<=102}
    unique_categories=[]
    for row in cost_categories:
        if row.get('sourcePage') not in eligible_category_pages:continue
        if not any(r['label'].casefold()==row['label'].casefold() and r['amountPesos']==row['amountPesos'] for r in unique_categories):unique_categories.append(row)
    unique_categories.sort(key=lambda r:-r['amountPesos'])
    unique_facts=[]
    for fact in qualitative_facts:
        key=(fact['kind'],fact['label'],str(fact['value']).casefold())
        if not any((x['kind'],x['label'],str(x['value']).casefold())==key for x in unique_facts):unique_facts.append(fact)
    declared=[f for f in unique_facts if f['kind']=='declared_count']
    named=[f for f in unique_facts if f['kind']=='named_component']
    breakdown_status='named_components_detected' if named else 'count_only_no_named_breakdown_detected' if declared else 'component_breakdown_not_detected'
    summary_metadata={'summaryPages':summary_pages,'qualitativeFacts':unique_facts,'componentBreakdownStatus':breakdown_status}
    return {'status':'candidate_rows' if result else 'needs_ocr' if any(p['status']=='needs_ocr' for p in pages) else 'needs_manual_review' if any(p['status']=='needs_manual_review' for p in pages) else 'no_bill_rows_recovered','pdfSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pageCount':len(document),'pagesProcessed':len(pages),'pages':pages,'rows':result,'costCategoryBreakdown':unique_categories,'summaryMetadata':summary_metadata,'rowObservations':len(rows),'uniqueCandidateRows':len(result),'sumOfUniqueCandidateAmountsPesos':sum(r['amountPesos'] for r in result),'reconciledPowTotal':False,'itemizedDirectCostControls':itemized_controls,'amountBasis':'Each item records its cost basis; direct costs are not inclusive project costs. Printed category summaries are preserved as separate evidence and are not added to itemized rows.','limits':['Reconciled itemized direct-cost subtotals, when available, do not reconcile the complete POW including indirect costs, VAT and EAO. Candidate row extraction is not a complete or reconciled POW ledger. A largest recovered row is not necessarily the largest row in the full document.','Shares use the NEP allocation, not a confirmed POW grand total, contract payment or engineering valuation.','Quantities, material units, indirect costs and engineering scope require original-page verification. Structural concrete is not cement mass.','Printed category summaries and itemized bill rows are separate evidence and must not be summed together.','Repeated identical row observations are grouped with source pages rather than silently summed.']}

def render_photos(path,output):
    try:import pymupdf as fitz
    except ImportError:return {'status':'renderer_dependency_missing','pages':[]}
    output.mkdir(parents=True,exist_ok=True);document=fitz.open(path);pages=[]
    for index,page in enumerate(document):
        if index>=50:break
        scale=min(2,1400/page.rect.width);target=output/f'photo-page-{index+1:03d}.png';page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).save(target)
        pages.append({'page':index+1,'fileName':target.name,'caption':page.get_text().strip()[:1500] or None})
    return {'status':'rendered','pageCount':len(document),'pages':pages,'truncated':len(document)>len(pages),'limits':'Full PDF pages are rendered to preserve captions, coordinates and document context. Photo dates/locations are not independently verified.'}
