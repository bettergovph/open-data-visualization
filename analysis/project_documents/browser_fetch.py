"""Retrieve one requested public PDF through an isolated Chrome session."""
import os
from urllib.parse import urlsplit

HOSTS={'s3.infrawatch.ph','transparency.dpwh.gov.ph'}
def download(url, target, allow_unverified=False):
    from playwright.sync_api import sync_playwright
    if urlsplit(url).scheme!='https' or urlsplit(url).hostname not in HOSTS:
        raise ValueError('Browser retrieval is limited to the selected public document hosts')
    with sync_playwright() as p:
        browser=p.chromium.launch(channel=os.environ.get('DPWH_DOCUMENT_BROWSER_CHANNEL','chrome'),headless=os.environ.get('DPWH_DOCUMENT_BROWSER_VISIBLE')!='1',args=['--disable-http2'] if os.environ.get('DPWH_DOCUMENT_BROWSER_HTTP1')=='1' else [])
        try:
            context=browser.new_context(accept_downloads=True)
            page=context.new_page()
            # Establish portal cookies/browser context before requesting this PDF.
            try:page.goto('https://transparency.dpwh.gov.ph/nep',wait_until='domcontentloaded',timeout=30000)
            except Exception:pass
            if allow_unverified:
                cookies=context.cookies();context.close()
                context=browser.new_context(ignore_https_errors=True,accept_downloads=True)
                context.add_cookies(cookies);page=context.new_page()
            # Restrict browser document requests and redirects to this source host.
            expected_host=urlsplit(url).hostname
            context.route('**/*',lambda route: route.continue_() if urlsplit(route.request.url).scheme=='https' and urlsplit(route.request.url).hostname==expected_host else route.abort())
            # A browser navigation preserves the browser network stack and VPN policy.
            with page.expect_download(timeout=45000) as pending:
                try:page.goto(url,wait_until='commit',timeout=45000)
                except Exception as exc:
                    if 'Download is starting' not in str(exc) and 'ERR_ABORTED' not in str(exc):raise
            item=pending.value
            if item.failure():raise RuntimeError(item.failure())
            item.save_as(str(target))
        finally:browser.close()

def probe_portal():
    """Inspect public portal access without downloading any project documents."""
    import json
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True,args=['--disable-http2'])
        try:
            context=browser.new_context();page=context.new_page()
            try:
                response=page.goto('https://transparency.dpwh.gov.ph/nep',wait_until='domcontentloaded',timeout=30000)
                page.wait_for_timeout(3000)
                result={'status':response.status if response else None,'title':page.title(),'text':page.locator('body').inner_text()[:5000],'links':page.locator('a[href]').evaluate_all('(links)=>links.map(a=>({text:a.textContent,url:a.href})).slice(0,25)')}
            except Exception as exc:result={'error':type(exc).__name__+': '+str(exc)[:500]}
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:browser.close()

if __name__=='__main__':probe_portal()
