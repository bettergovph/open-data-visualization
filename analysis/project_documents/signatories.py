"""Spatially qualified document signatories; no roster, province or surname inference."""
import json,re
from collections import defaultdict

def normal(value):return re.sub(r'\s+',' ',value).strip()
def is_name(text):
    text=normal(text)
    if re.search(r'\d|[:;/]|\b(?:REGIONAL|DISTRICT|ENGINEER|ASSISTANT|ADE|DE|GOVERNOR|MAYOR|COUNCIL|DEPARTMENT|APPROVED|APPROVAL|CERTIFIED|REPUBLIC|PROJECT|SECRETARY|DEVELOPMENT|PROVINCE|CHAIRPERSON|CHAIRMAN|CHAIRWOMAN)\b',text,re.I):return False
    tokens=re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.'’\-]*",text)
    return 2<=len(tokens)<=10 and len(text)<110 and any(len(t)>3 for t in tokens) and text.upper()==text

def lines(words):
    grouped=defaultdict(list)
    for word in words:grouped[(word[5],word[6])].append(word)
    return [{'text':normal(' '.join(w[4] for w in sorted(group,key=lambda w:w[0]))),'bbox':[min(w[0] for w in group),min(w[1] for w in group),max(w[2] for w in group),max(w[3] for w in group)]} for group in grouped.values()]

def qualified_role(text,kind):
    text=normal(text)
    text=re.sub(r'\bA\s*[.]?\s*D\s*[.]?\s*E\s*[.]?\b','ADE',text,flags=re.I)
    text=re.sub(r'\b(?:Asst\.?|Assistant)\s+District\s+Engineer\b','Assistant District Engineer',text,flags=re.I)
    # Body text mentions officials and engineering offices frequently. Only
    # short, role-shaped labels qualify as signature roles.
    if len(text)>90:return None
    if kind=='pow':
        # Institutional headings are not a person's signature role.
        return 'district_engineer' if re.fullmatch(r'(?:(?:OIC|Acting|Officer[ -]in[ -]Charge)[, .-]*)?District Engineer[ .,;-]*',text,re.I) else None
    if kind not in ('rdc','ldc'):return None
    if re.fullmatch(r'(?:(?:OIC|Acting|Officer[ -]in[ -]Charge)[, .-]*)?(?:Assistant District Engineer|ADE)(?:[, .;-]+(?:DPWH|DEO|District Engineering Office).*)?',text,re.I):return 'assistant_district_engineer'
    if re.fullmatch(r'(?:(?:OIC|Acting|Officer[ -]in[ -]Charge)[, .-]*)?District Engineer(?:[, .;-]+(?:DPWH|DEO|District Engineering Office).*)?',text,re.I):return 'district_engineer'
    if re.fullmatch(r'(?:(?:Provincial|Regional)\s+)?Governor(?:[, .;-]+(?:Province|LGU|OIC|Acting).*)?',text,re.I):return 'governor'
    if re.fullmatch(r'(?:(?:City|Municipal|Municipality)\s+)?Mayor(?:[, .;-]+(?:OIC|Acting|LGU).*)?',text,re.I):return 'mayor'
    if re.fullmatch(r'(?:(?:RDC|LDC|Regional Development Council|Local Development Council)[, .;-]+)?Chair(?:person|man|woman)(?:[, .;-]+(?:RDC|LDC|Council).*)?',text,re.I):return 'rdc_head'
    return None

def extract(path,kind,output):
    import pymupdf
    people=[];pages=[];unresolved=[]
    with pymupdf.open(path) as document:
        for i,page in enumerate(document):
            words=page.get_text('words');records=lines(words);text=page.get_text();method='native PDF text'
            if not any(qualified_role(record['text'],kind) for record in records):
                try:
                    from .pow import paddle_words
                    ocr=paddle_words(page)
                except Exception:ocr=None
                if ocr:
                    ocr_records=lines(ocr['words'])
                    if sum(bool(qualified_role(record['text'],kind)) for record in ocr_records)>=sum(bool(qualified_role(record['text'],kind)) for record in records):
                        records=ocr_records;text=ocr['text'];method=ocr['method']
            pages.append({'page':i+1,'text':text,'lines':records,'method':method})
            if not text.strip():unresolved.append({'page':i+1,'status':'needs_ocr'});continue
            for role in records:
                t=role['text'];role_kind=qualified_role(t,kind)
                if not role_kind:continue
                x0,y0,x1,y1=role['bbox'];center=(x0+x1)/2
                candidates=[]
                for record in records:
                    a,b,c,d=record['bbox'];dx=abs((a+c)/2-center);dy=y0-d
                    if 0<=dy<=55 and dx<=max(35,(x1-x0)*.65) and is_name(record['text']):candidates.append((dy+dx*.2,record))
                candidates.sort(key=lambda pair:pair[0])
                if not candidates or len(candidates)>1 and abs(candidates[0][0]-candidates[1][0])<2:
                    unresolved.append({'page':i+1,'roleText':t,'status':'name_not_uniquely_bound_to_role'});continue
                name=candidates[0][1];role_lines=[role]
                # Preserve wrapped role/jurisdiction lines in the same signature column.
                for record in records:
                    a,b,c,d=record['bbox']
                    if record is role or not (y0-1<=b<=y1+36):continue
                    if abs((a+c)/2-center)>max(45,(x1-x0)*.65):continue
                    if re.search(r'\b(?:RDC|LDC|governor|mayor|province|chairperson|chairman|district engineer|assistant district engineer|regional director|secretary)\b',record['text'],re.I) and not is_name(record['text']):role_lines.append(record)
                role_lines=sorted(role_lines,key=lambda r:r['bbox'][1]);role_text=normal(' '.join(r['text'] for r in role_lines))
                key=(name['text'],i+1,role_kind)
                if any((r['name'],r['sourcePage'],r['kind'])==key for r in people):continue
                people.append({'name':name['text'],'roleText':role_text,'kind':role_kind,'sourcePage':i+1,'nameBbox':name['bbox'],'roleBboxes':[r['bbox'] for r in role_lines],'evidenceText':name['text']+' · '+role_text,'extractionMethod':method+'; same-column name above explicit role','verificationStatus':'Document-extracted candidate; inspect the cited page. Does not establish current office, sponsorship or project responsibility.'})
    output.mkdir(parents=True,exist_ok=True)
    (output/(kind+'-signatory-source.json')).write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
    return {'status':'document_candidates' if people else 'needs_ocr' if unresolved and all(r['status']=='needs_ocr' for r in unresolved) else 'no_qualified_signatory_recovered','people':people,'sourcePages':len(pages),'unresolved':unresolved,'methodology':'Only explicit DE, ADE, Governor, Mayor or council-head roles bound to an uppercase name directly above in the same signature column. No official is inferred from project geography. Names and roles refer to the document, not a verified current roster.'}
