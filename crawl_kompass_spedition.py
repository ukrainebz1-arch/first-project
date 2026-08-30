import argparse, csv, re, time
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE='https://at.kompass.com'
CATEGORY='https://at.kompass.com/x/producer/a/verschiffungsagenten-und-spediteure/75780/'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'

def page_url(n): return CATEGORY if n==1 else CATEGORY+f'page-{n}/'
def clean(t): return re.sub(r'\s+',' ',t or '').strip()

def parse_emp(text):
    # Prefer the public Kompass field around "Gesamtzahl Mitarbeiter".
    snippets=[]
    for m in re.finditer(r'Gesamtzahl\s+Mitarbeiter.{0,300}',text,re.I|re.S): snippets.append(clean(m.group(0)))
    blob=' | '.join(snippets[:4]) or text
    pats=[
      (r'Von\s+([\d\.]+)\s+bis\s+([\d\.]+)\s*Mitarbeiter', 'range'),
      (r'([\d\.]+)\s*(?:-|bis)\s*([\d\.]+)\s*Mitarbeiter', 'range'),
      (r'(?:Mehr als|Über)\s+([\d\.]+)\s*Mitarbeiter', 'over'),
      (r'([\d\.]+)\s*Mitarbeiter', 'exact')]
    for p,k in pats:
        m=re.search(p,blob,re.I)
        if m:
            nums=[int(x.replace('.','')) for x in m.groups() if x]
            if k=='range': return nums[0],nums[1],clean(m.group(0)),k
            if k=='over': return nums[0]+1,None,clean(m.group(0)),k
            return nums[0],nums[0],clean(m.group(0)),k
    return None,None,'',''

def goto(page,url,tries=3):
    err=''
    for i in range(tries):
        try:
            resp=page.goto(url,wait_until='domcontentloaded',timeout=45000)
            status=resp.status if resp else 0
            page.wait_for_timeout(900)
            text=page.locator('body').inner_text(timeout=10000)
            if len(text)>300 and status in (0,200): return status,text
            err=f'status={status} textlen={len(text)} title={page.title()}'
        except Exception as e: err=repr(e)
        page.wait_for_timeout(1200*(i+1))
    raise RuntimeError(f'{url}: {err}')

def company_links(page,n):
    status,text=goto(page,page_url(n))
    hrefs=page.locator('a').evaluate_all("els => els.map(e => e.href)")
    out=[];seen=set()
    for h in hrefs:
        if re.match(r'https://at\.kompass\.com/c/[^/]+/at\d+/?(?:\?.*)?$',h or ''):
            h=(h or '').split('?')[0]
            if h not in seen: seen.add(h);out.append(h)
    print(f'LIST_PAGE={n} STATUS={status} BODY={len(text)} LINKS={len(out)} TITLE={page.title()}',flush=True)
    return out

def parse_profile(page,url):
    try:
        status,text=goto(page,url)
        name=''
        try: name=clean(page.locator('h1').first.inner_text(timeout=3000))
        except: pass
        name=re.sub(r'\s*[•|]\s*.*$','',name).strip()
        lo,hi,evidence,kind=parse_emp(text)
        city=''
        m=re.search(r'\b(\d{4})\s+([A-ZÄÖÜa-zäöüß][A-Za-zÄÖÜäöüß .\-/]{2,60})\s*-\s*Österreich',text)
        if m: city=clean(m.group(1)+' '+m.group(2))
        return {'kompass_url':url,'kompass_name':name,'kompass_place':city,'employee_min':lo or '', 'employee_max':hi or '', 'employee_evidence':evidence,'employee_kind':kind,'http_status':status,'error':''}
    except Exception as e:
        return {'kompass_url':url,'kompass_name':'','kompass_place':'','employee_min':'','employee_max':'','employee_evidence':'','employee_kind':'','http_status':'','error':repr(e)}

def write_rows(out,rows):
    fields=['kompass_url','kompass_name','kompass_place','employee_min','employee_max','employee_evidence','employee_kind','http_status','error']
    with open(out,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--page',type=int,required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
        ctx=browser.new_context(user_agent=UA,locale='de-AT',timezone_id='Europe/Vienna',viewport={'width':1440,'height':1000})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page=ctx.new_page()
        links=company_links(page,args.page)
        if not links: raise RuntimeError(f'No Kompass company links found on page {args.page}')
        rows=[]
        for i,u in enumerate(links,1):
            rows.append(parse_profile(page,u))
            # durable inside-job checkpoint file after every profile; workflow commits completed page.
            write_rows(args.out,rows)
            if i%10==0: print(f'PAGE={args.page} PROFILE={i}/{len(links)} EMP={sum(bool(r["employee_min"]) for r in rows)}',flush=True)
        browser.close()
    write_rows(args.out,rows)
    print(f'PAGE={args.page} LINKS={len(links)} EMPLOYEE_RANGES={sum(bool(r["employee_min"]) for r in rows)} OUT={args.out}')
if __name__=='__main__': main()
