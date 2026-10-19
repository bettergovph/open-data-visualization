#!/usr/bin/env python3
"""On-demand project-document worker, bound to localhost behind ODV.
GET metadata does not fetch documents. POST prepare fetches this project's selected
POW/RDC PDFs and, when enabled, photo attachments as-is. Photo tables retain source links.
Set HTTPS_PROXY on the worker to a PH egress proxy if required.
"""
import argparse,concurrent.futures,hashlib,json,os,re,ssl,threading,time,urllib.request,uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote,urlsplit
from .pow import parse_pdf
CODE=re.compile(r'^2027DPWH-Proposal-\d{5}$')
MODULE=Path(__file__).resolve().parent
CACHE=Path(os.environ.get('DPWH_DOCUMENT_CACHE',str(MODULE.parent/'data_sources/dpwh_project_documents/on_demand'))).resolve()
MAX_DOCUMENT_BYTES=int(os.environ.get('DPWH_DOCUMENT_MAX_BYTES',str(512*1024*1024)))
API=os.environ.get('DPWH_METADATA_API','https://api.dpwh.bettergov.ph/nep/projects').rstrip('/')
JOBS={};LOCK=threading.Lock();POOL=concurrent.futures.ThreadPoolExecutor(max_workers=2)

def storage_guard():
    volume=os.environ.get("DPWH_EXTERNAL_VOLUME") or ("/Volumes/T5 EVO" if str(CACHE).startswith("/Volumes/T5 EVO/") else None)
    if volume and not os.path.ismount(volume):raise RuntimeError("External document volume is not mounted; refusing local fallback")

def save(path,data):
    storage_guard()
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
def request(url,allow_unverified_pdf=False):
    if urlsplit(url).scheme!='https':raise ValueError('HTTPS source required')
    # urllib respects HTTPS_PROXY / SSL_CERT_FILE; do not disable verification.
    req=urllib.request.Request(url,headers={'User-Agent':'BetterGov-on-demand-project-evidence/1.0'})
    if allow_unverified_pdf and os.environ.get('DPWH_DOCUMENT_ALLOW_UNVERIFIED_TLS')=='1' and urlsplit(url).hostname=='s3.infrawatch.ph':
        class SameHostRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,request,fp,code,msg,headers,newurl):
                if urlsplit(newurl).hostname!='s3.infrawatch.ph' or urlsplit(newurl).scheme!='https':raise ValueError('TLS bypass does not extend to redirected hosts')
                return super().redirect_request(request,fp,code,msg,headers,newurl)
        opener=urllib.request.build_opener(SameHostRedirect(),urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
        return opener.open(req,timeout=45)
    return urllib.request.urlopen(req,timeout=45)
def metadata(code,refresh=False):
    path=CACHE/code/'metadata.json'
    if path.exists() and not refresh:return json.loads(path.read_text())
    with request(API+'/'+code) as response:payload=json.load(response)
    if payload.get('status')!=200 or payload.get('data',{}).get('code')!=code:raise ValueError('Metadata project identity differs')
    data=payload['data'];save(path,data);return data
def kinds(doc):
    text=re.sub(r'[^a-z]+',' ',doc.get('documentType','').lower()).strip()
    return 'pow' if text=='pow' or 'program of work' in text else 'photos' if 'geotagged' in text and 'photo' in text else 'rdc' if 'rdc' in text or 'regional development council' in text else None

def photo_extension(url):
    extension=Path(unquote(urlsplit(url).path)).suffix.lower()
    return extension if re.fullmatch(r'\.[a-z0-9]{1,10}',extension) else '.bin'

def reviewed(code,allocation):
    path=MODULE/'burol_reviewed_rows.json'
    if code!='2027DPWH-Proposal-03421':return None
    data=json.loads(path.read_text())
    for row in data['rows']:
        row['shareOfNepAllocationPct']=round(row['amountPesos']/allocation*100,4) if allocation else None
        row['calculatedUnitCostPesos']=row['amountPesos']/row['quantity']
        row['sourcePage']=row.get('sourcePage',data.get('sourcePage'));row['verificationStatus']=data['verificationStatus']
    data['sumPesos']=round(sum(r['amountPesos'] for r in data['rows']),2)
    data['shareOfNepAllocationPct']=round(data['sumPesos']/allocation*100,4) if allocation else None
    return data

def state(code):
    data=metadata(code);allocation=round(float(data['amount'])*1000)
    with LOCK:job=dict(JOBS.get(code,{}))
    result_path=CACHE/code/'result.json'
    result=json.loads(result_path.read_text()) if result_path.exists() else None
    return {'project':{**data,'nepAllocationPesos':allocation},'job':job or {'status':'ready' if result else 'not_requested'},'result':result,'reviewedRows':reviewed(code,allocation),'stage':'NEP FY2027 proposal documents; not an awarded-contract or as-built record'}

def process(code,refresh=False):
    from .cache_lock import project_lock
    storage_guard()
    with project_lock(CACHE/code):return _process(code,refresh)

def _process(code,refresh=False):
    output={'projectCode':code,'documents':[],'preparedAtUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    try:
        storage_guard()
        project=metadata(code,refresh);allocation=round(float(project['amount'])*1000)
        docs=[(d,kinds(d)) for d in project.get('documents',[]) if kinds(d)]
        for document,kind in docs:
            if kind=='photos' and os.environ.get('DPWH_DOCUMENT_CACHE_PHOTOS')!='1':
                output['documents'].append({'kind':'photos','metadata':document,'status':'link_only','directLink':document['url'],'displayPolicy':'direct_source_link; photo files are not fetched'});continue
            row={'kind':kind,'metadata':document,'transportTlsVerified':not (os.environ.get('DPWH_DOCUMENT_ALLOW_UNVERIFIED_TLS')=='1' and urlsplit(document['url']).hostname=='s3.infrawatch.ph')}
            if kind=='photos':row.update(directLink=document['url'],displayPolicy='direct_source_link; downloaded copy retained externally')
            # Stable, content-versioned assets; only explicitly selected project documents are fetched.
            version=hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest()[:16]
            storage_guard()
            folder=CACHE/code/'assets'/version;folder.mkdir(parents=True,exist_ok=True)
            asset=folder/(('photo'+photo_extension(document['url'])) if kind=='photos' else (kind+'.pdf'))
            legacy_photo_pdf=folder/'photos.pdf'
            if kind=='photos' and not asset.exists() and legacy_photo_pdf.is_file():asset=legacy_photo_pdf
            row['version']=version
            if kind=='photos':row['cachedAsset']=version+'/'+asset.name
            else:row['pdfAsset']=version+'/'+asset.name
            row['transport']=os.environ.get('DPWH_DOCUMENT_TRANSPORT','https')
            if row['transport']=='curl':row['transportTlsVerified']=True
            try:
                if not asset.exists():
                    part=asset.with_suffix(asset.suffix+'.part')
                    if os.environ.get('DPWH_DOCUMENT_TRANSPORT')=='curl':
                        from .curl_fetch import download
                        download(document['url'],part)
                        row['transport']='curl'
                    elif os.environ.get('DPWH_DOCUMENT_TRANSPORT')=='browser':
                        from .browser_fetch import download
                        download(document['url'],part,allow_unverified=row['transportTlsVerified'] is False)
                        row['transport']='playwright-chrome'
                    else:
                        with request(document['url'],allow_unverified_pdf=True) as source,part.open('wb') as target:
                            total=0
                            while chunk:=source.read(1024*1024):
                                storage_guard()
                                total+=len(chunk)
                                if total>MAX_DOCUMENT_BYTES:raise ValueError('Document exceeds worker size limit')
                                target.write(chunk)
                        row['transport']='https'
                    if part.stat().st_size>MAX_DOCUMENT_BYTES:raise ValueError('Document exceeds worker size limit')
                    if kind!='photos':
                        with part.open('rb') as stream:head=stream.read(1024)
                        if b'%PDF-' not in head:raise ValueError('Source response is not a PDF')
                        if document.get('sizeBytes') is not None and part.stat().st_size!=document['sizeBytes']:raise ValueError('PDF length differs from source metadata')
                    asset.parent.mkdir(parents=True,exist_ok=True);part.replace(asset)
                row['sha256']=hashlib.sha256(asset.read_bytes()).hexdigest()
                if kind=='pow':row['pow']=parse_pdf(asset,folder,allocation)
                elif kind=='rdc':
                    from .signatories import extract
                    row['signatories']=extract(asset,'rdc',folder)
                if kind=='pow':
                    from .signatories import extract
                    row['signatories']=extract(asset,'pow',folder)
                row['status']='available'
            except Exception as exc:
                if kind=='photos':row.update({'status':'link_only','downloadStatus':'failed','downloadError':type(exc).__name__+': '+str(exc)[:220]})
                else:row.update({'status':'access_or_processing_error','error':type(exc).__name__+': '+str(exc)[:220]})
            output['documents'].append(row)
        save(CACHE/code/'result.json',output)
        with LOCK:JOBS[code]={'status':'ready','hasErrors':any(d['status'] not in ('available','link_only') for d in output['documents'])}
    except Exception as exc:
        with LOCK:JOBS[code]={'status':'error','error':type(exc).__name__+': '+str(exc)[:220]}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def send_json(self,status,data):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def route(self):
        parts=urlsplit(self.path).path.strip('/').split('/')
        if len(parts)<2 or parts[0]!='projects' or not CODE.fullmatch(parts[1]):return None,None
        return parts[1],parts[2:]
    def do_GET(self):
        if self.path=='/health':return self.send_json(200,{'status':'ok','mode':'on_demand','bulkDownload':False})
        code,tail=self.route()
        if not code:return self.send_json(404,{'error':'Unknown project-document route'})
        if tail and tail[0]=='assets':
            if len(tail)!=3 or not re.fullmatch(r'[a-f0-9]{16}',tail[1]) or not re.fullmatch(r'(?:pow|photos|rdc)\.pdf|photo-page-\d{3}\.png',tail[2]):return self.send_json(404,{'error':'Unknown asset'})
            path=CACHE/code/'assets'/tail[1]/tail[2]
            if not path.is_file():return self.send_json(404,{'error':'Requested asset is not prepared'})
            self.send_response(200);self.send_header('Content-Type','application/pdf' if path.suffix=='.pdf' else 'image/png');self.send_header('Content-Length',str(path.stat().st_size));self.send_header('Cache-Control','public, max-age=86400');self.end_headers()
            with path.open('rb') as stream:
                while chunk:=stream.read(1024*1024):self.wfile.write(chunk)
            return
        if tail:return self.send_json(404,{'error':'Unknown route'})
        try:return self.send_json(200,state(code))
        except Exception as exc:return self.send_json(502,{'error':'Project metadata unavailable: '+str(exc)[:180]})
    def do_POST(self):
        code,tail=self.route()
        if not code or tail!=['prepare']:return self.send_json(404,{'error':'Unknown preparation route'})
        with LOCK:
            if JOBS.get(code,{}).get('status')=='queued':return self.send_json(202,{'status':'queued'})
            if sum(r.get('status')=='queued' for r in JOBS.values())>=8:return self.send_json(429,{'error':'Document queue busy; retry shortly'})
            JOBS[code]={'status':'queued'}
        POOL.submit(process,code)
        return self.send_json(202,{'status':'queued','projectCode':code})
def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8879);a=p.parse_args();CACHE.mkdir(parents=True,exist_ok=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
if __name__=='__main__':main()
