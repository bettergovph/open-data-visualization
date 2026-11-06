"""Extract document signatories and attach exact-name ODV designation context."""
import json,re,subprocess,shutil
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

ODV_ROSTER=Path(__file__).resolve().parents[2]/'open-data-visualization/static/data/parquet/political_dynasties.parquet'
DESIGNATION_REGISTRY=Path(__file__).resolve().parents[1]/'data_sources/designation_registry/officials.json'

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
        # Keep DE and ADE separate; institutional headings are not names.
        return bool(re.fullmatch(r'(?:(?:OIC|Acting|Officer[ -]in[ -]Charge)[, .-]*)?(?:Assistant )?District Engineer(?:\s+.*)?[ .]*',normal(text),re.I))
    if kind in ('rdc','pdc','ldc'):
        return bool(re.search(r'\bgovernor\b|\bmayor\b|\bchair(?:person|man|woman)\b',text,re.I)) and not bool(re.search(r'vice|deputy|assistant|co-chair',text,re.I))
    return False

def role_kind(text,kind):
    text=normal(text)
    if kind=='pow':return 'assistant_district_engineer' if re.search(r'\bassistant\b',text,re.I) else 'district_engineer'
    if re.search(r'\bgovernor\b',text,re.I):return 'governor'
    if re.search(r'\bmayor\b',text,re.I):return 'mayor'
    return {'rdc':'rdc_chair','pdc':'pdc_chair','ldc':'ldc_chair'}.get(kind,'council_chair')

def _name_key(value):
    value=normal(value or '').upper().replace('’',"'")
    return re.sub(r'[^A-Z0-9]+',' ',value).strip()

@lru_cache(maxsize=1)
def _officials_by_name():
    """Load only role-relevant ODV entries; never use fuzzy/surname matching."""
    if DESIGNATION_REGISTRY.is_file():
        try:
            rows=json.loads(DESIGNATION_REGISTRY.read_text())['rows']
        except (OSError,ValueError,KeyError):
            rows=None
    else:
        rows=None
    if rows is None and (not ODV_ROSTER.is_file() or not shutil.which('duckdb')):
        return {}
    query=f"""
      SELECT first_name, middle_name, last_name, nickname, position,
             province, municipality_city, year
      FROM read_parquet('{ODV_ROSTER.as_posix()}')
      WHERE regexp_matches(upper(coalesce(position,'')),
        '(^| )(DISTRICT ENGINEER|ASSISTANT DISTRICT ENGINEER|GOVERNOR|MAYOR)( |$)')
    """
    if rows is None:
        try:
            result=subprocess.run(['duckdb','-json','-c',query],capture_output=True,text=True,check=True,timeout=45)
            rows=json.loads(result.stdout)
        except (OSError,subprocess.SubprocessError,ValueError):
            return {}
    index=defaultdict(list)
    for row in rows:
        if row.get('matchEligible') is False:continue
        keys={_name_key(row.get('name') or ' '.join(filter(None,[row.get('first_name'),row.get('middle_name'),row.get('last_name')])))}
        if row.get('nickname'):
            keys.add(_name_key(' '.join(filter(None,[row.get('nickname'),row.get('last_name')]))))
        for key in keys:
            if key:index[key].append(row)
    return index

def designation_matches(name,kind,role):
    index=_officials_by_name()
    if not index:return {'status':'roster_unavailable','matches':[]}
    role=role_kind(role,kind)
    rows=index.get(_name_key(name),[])
    if role in ('district_engineer','assistant_district_engineer'):
        rows=[r for r in rows if ('ASSISTANT DISTRICT ENGINEER' in (r.get('position') or '').upper()) == (role=='assistant_district_engineer') and 'DISTRICT ENGINEER' in (r.get('position') or '').upper()]
    elif role=='governor':rows=[r for r in rows if re.search(r'\bGOVERNOR\b',(r.get('position') or '').upper()) and not re.search(r'\bVICE\b',(r.get('position') or '').upper())]
    elif role=='mayor':rows=[r for r in rows if re.search(r'\bMAYOR\b',(r.get('position') or '').upper()) and not re.search(r'\bVICE\b',(r.get('position') or '').upper())]
    grouped={}
    for r in rows:
        item={k:r.get(k) for k in ('position','province','municipality_city','organization')}
        key=tuple(str(item.get(k) or '') for k in item)
        grouped.setdefault(key,{**item,'years':set(),'sourceRecords':[]})
        for source in r.get('sources',[]):
            if source not in grouped[key]['sourceRecords']:
                grouped[key]['sourceRecords'].append(source)
        year=r.get('year')
        if year is not None and str(year).lower()!='nan':
            try:grouped[key]['years'].add(int(float(year)))
            except (TypeError,ValueError,OverflowError):pass
    matches=[{**item,'years':sorted(item['years'])} for item in grouped.values()]
    locations={(m.get('province'),m.get('municipality_city')) for m in matches if m.get('province') or m.get('municipality_city')}
    if matches and not locations:return {'status':'exact_name_unresolved_locality','matches':matches}
    status=('exact_name_designation_match' if len(locations)==1 else 'exact_name_multiple_locality_matches') if matches else 'no_exact_name_designation_match'
    return {'status':status,'matches':matches}

def extract(path,kind,output):
    import pymupdf
    people=[];pages=[];unresolved=[]
    with pymupdf.open(path) as document:
        for i,page in enumerate(document):
            words=page.get_text('words');records=lines(words);text=page.get_text();pages.append({'page':i+1,'text':text,'lines':records})
            if not text.strip():unresolved.append({'page':i+1,'status':'needs_ocr'});continue
            for role in records:
                t=role['text']
                if not qualified_role(t,kind):continue
                found_role_kind=role_kind(t,kind)
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
                    if re.search(r'\b(?:RDC|governor|mayor|province|chairperson|chairman|chairwoman|district engineer|regional director|secretary)\b',record['text'],re.I) and not is_name(record['text']):role_lines.append(record)
                role_lines=sorted(role_lines,key=lambda r:r['bbox'][1]);role_text=normal(' '.join(r['text'] for r in role_lines))
                if kind in ('rdc','pdc','ldc') and not re.search(r'governor|mayor|\bRDC\b|\bPDC\b|\bLDC\b|development council|chair',role_text,re.I):continue
                key=(name['text'],i+1,found_role_kind)
                if any((r['name'],r['sourcePage'],r['kind'])==key for r in people):continue
                roster=designation_matches(name['text'],kind,role_text)
                status=('Exact name and designation match in ODV roster; inspect the cited document and roster dates/locality.' if roster['status']=='exact_name_designation_match' else 'ODV has multiple exact-name locality records; designation is ambiguous.' if roster['status']=='exact_name_multiple_locality_matches' else 'Exact-name designation candidate in ODV; locality is unresolved. Check the cited document, source year and appointment.' if roster['status']=='exact_name_unresolved_locality' else 'ODV designation roster unavailable; inspect the cited document.' if roster['status']=='roster_unavailable' else 'Document-extracted candidate; inspect the cited page. No exact designation match in ODV; this does not establish current office, sponsorship or project responsibility.')
                people.append({'name':name['text'],'roleText':role_text,'kind':found_role_kind,'sourcePage':i+1,'nameBbox':name['bbox'],'roleBboxes':[r['bbox'] for r in role_lines],'evidenceText':name['text']+' · '+role_text,'extractionMethod':'native PDF text; same-column name above explicit role','verificationStatus':status,'designationRegistry':roster})
    output.mkdir(parents=True,exist_ok=True)
    (output/(kind+'-signatory-source.json')).write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
    return {'status':'document_candidates' if people else 'needs_ocr' if unresolved and all(r['status']=='needs_ocr' for r in unresolved) else 'no_qualified_signatory_recovered','people':people,'sourcePages':len(pages),'unresolved':unresolved,'methodology':'Only explicit roles bound to an uppercase name directly above in the same signature column. DE and ADE remain distinct; vice-role titles are excluded. ODV matches use exact normalized full name plus designation; locality and year are context, not proof of current office or project responsibility.'}
