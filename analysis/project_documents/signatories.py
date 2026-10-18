"""Spatially qualified document signatories; no roster, province or surname inference."""
import json,re
from collections import defaultdict

def normal(value):return re.sub(r'\s+',' ',value).strip()
def is_name(text):
    text=normal(text)
    if re.search(r'\d|[:;/]|\b(?:REGIONAL|DISTRICT|ENGINEER|GOVERNOR|COUNCIL|DEPARTMENT|APPROVED|APPROVAL|CERTIFIED|REPUBLIC|PROJECT|SECRETARY|DEVELOPMENT|PROVINCE)\b',text,re.I):return False
    tokens=re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ.'’\-]*",text)
    return 2<=len(tokens)<=10 and len(text)<110 and any(len(t)>3 for t in tokens) and text.upper()==text

def lines(words):
    grouped=defaultdict(list)
    for word in words:grouped[(word[5],word[6])].append(word)
    return [{'text':normal(' '.join(w[4] for w in sorted(group,key=lambda w:w[0]))),'bbox':[min(w[0] for w in group),min(w[1] for w in group),max(w[2] for w in group),max(w[3] for w in group)]} for group in grouped.values()]

def qualified_role(text,kind):
    if kind=='pow':
        # Institutional headings are not a person's signature role.
        return bool(re.fullmatch(r'(?:(?:OIC|Acting|Officer[ -]in[ -]Charge)[, .-]*)?District Engineer[ .]*',normal(text),re.I))
    return kind=='rdc' and bool(re.search(r'\bgovernor\b|\bchair(?:person|man|woman)\b',text,re.I)) and not bool(re.search(r'vice|deputy|assistant|co-chair',text,re.I))

def extract(path,kind,output):
    import pymupdf
    people=[];pages=[];unresolved=[]
    with pymupdf.open(path) as document:
        for i,page in enumerate(document):
            words=page.get_text('words');records=lines(words);text=page.get_text();pages.append({'page':i+1,'text':text,'lines':records})
            if not text.strip():unresolved.append({'page':i+1,'status':'needs_ocr'});continue
            for role in records:
                t=role['text'];role_kind=None
                if qualified_role(t,'pow') and kind=='pow':role_kind='district_engineer'
                if qualified_role(t,'rdc') and kind=='rdc':role_kind='governor_or_rdc_head'
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
                    if re.search(r'\b(?:RDC|governor|province|chairperson|chairman|district engineer|regional director|secretary)\b',record['text'],re.I) and not is_name(record['text']):role_lines.append(record)
                role_lines=sorted(role_lines,key=lambda r:r['bbox'][1]);role_text=normal(' '.join(r['text'] for r in role_lines))
                if kind=='rdc' and not re.search(r'governor|\bRDC\b|regional development council',role_text,re.I):continue
                key=(name['text'],i+1,role_kind)
                if any((r['name'],r['sourcePage'],r['kind'])==key for r in people):continue
                people.append({'name':name['text'],'roleText':role_text,'kind':role_kind,'sourcePage':i+1,'nameBbox':name['bbox'],'roleBboxes':[r['bbox'] for r in role_lines],'evidenceText':name['text']+' · '+role_text,'extractionMethod':'native PDF text; same-column name above explicit role','verificationStatus':'Document-extracted candidate; inspect the cited page. Does not establish current office, sponsorship or project responsibility.'})
    output.mkdir(parents=True,exist_ok=True)
    (output/(kind+'-signatory-source.json')).write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
    return {'status':'document_candidates' if people else 'needs_ocr' if unresolved and all(r['status']=='needs_ocr' for r in unresolved) else 'no_qualified_signatory_recovered','people':people,'sourcePages':len(pages),'unresolved':unresolved,'methodology':'Only explicit roles bound to an uppercase name directly above in the same signature column. Assistant district engineers and vice-chairpersons are not substituted for the requested role. No governor inferred from project geography. Names and roles refer to the document, not a verified current roster.'}
