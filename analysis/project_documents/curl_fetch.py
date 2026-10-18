"""Retrieve a selected public source PDF with curl; preserve TLS verification."""
import subprocess
from urllib.parse import urlsplit

def download(url,target):
    if urlsplit(url).scheme!='https' or urlsplit(url).hostname not in {'s3.infrawatch.ph','transparency.dpwh.gov.ph'}:
        raise ValueError('Only selected HTTPS document hosts are allowed')
    # Exact metadata URLs; do not follow redirects to an unreviewed host.
    run=subprocess.run(['curl','--silent','--show-error','--fail','--proto','=https','--connect-timeout','15','--max-time','90','--max-filesize',str(128*1024*1024),'--output',str(target),'--write-out','%{http_code}',url],capture_output=True,text=True)
    if run.returncode or run.stdout.strip()!='200':
        raise RuntimeError('curl HTTP '+run.stdout.strip()+' (exit '+str(run.returncode)+'): '+run.stderr.strip()[:300])
