import argparse,csv,os,re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

BASE='https://at.kompass.com'
CATEGORY='https://at.kompass.com/x/service/a/erschliessung-verwaltung-und-verkauf-von-immobilien/80860/'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139 Safari/537.36'

def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def page_url(n):return CATEGORY if n==1 else CATEGORY+f'page-{n}/'
def write(out,rows):
    os.makedirs(os.path.dirname(out),exist_ok=True)
    fields=['list_page','kompass_url','kompass_name','list_context']
    with open(out,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def load(page,url,tries=3):
    err=''
    for i in range(tries):
        try:
            resp=page.goto(url,wait_until='domcontentloaded',timeout=45000)
            status=resp.status if resp else 0
            page.wait_for_timeout(700)
            txt=page.locator('body').inner_text(timeout=10000)
            if status in (0,200) and len(txt)>300:return status,txt
            err=f'status={status} len={len(txt)} title={page.title()}'
        except Exception as e:err=repr(e)
        page.wait_for_timeout(1200*(i+1))
    raise RuntimeError(f'{url}: {err}')

def extract(page,n):
    status,body=load(page,page_url(n))
    items=page.locator('a').evaluate_all("""els => els.map(a => ({href:a.href, text:(a.innerText||a.textContent||'').trim(), parent:(a.parentElement && a.parentElement.innerText || '').trim()}))""")
    out=[];seen=set()
    for x in items:
        h=(x.get('href') or '').split('?')[0].split('#')[0]
        if not re.match(r'https://at\.kompass\.com/c/[^/]+/at[^/]+/?$',h,re.I):continue
        if h in seen:continue
        seen.add(h)
        name=clean(x.get('text',''))
        ctx=clean(x.get('parent',''))[:600]
        # Profile anchors normally carry company name. If empty, retain URL for later fallback.
        out.append({'list_page':n,'kompass_url':h,'kompass_name':name,'list_context':ctx})
    print(f'PAGE {n} status={status} links={len(out)} title={page.title()}',flush=True)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start-page',type=int,default=1);ap.add_argument('--end-page',type=int,default=100);ap.add_argument('--out',required=True);ap.add_argument('--stop-after-empty',type=int,default=2);args=ap.parse_args()
    rows=[];seen=set();empty=0
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
        ctx=browser.new_context(user_agent=UA,locale='de-AT',timezone_id='Europe/Vienna',viewport={'width':1440,'height':1000})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page=ctx.new_page()
        for n in range(args.start_page,args.end_page+1):
            try:items=extract(page,n)
            except Exception as e:
                print('PAGE_FAIL',n,repr(e),flush=True);items=[]
            new=0
            for r in items:
                if r['kompass_url'] not in seen:
                    seen.add(r['kompass_url']);rows.append(r);new+=1
            write(args.out,rows)
            print(f'INDEX pages_through={n} total_unique={len(rows)} new={new}',flush=True)
            if not items or new==0:empty+=1
            else:empty=0
            if empty>=args.stop_after_empty:break
        browser.close()
    write(args.out,rows)
    print('DONE unique_profiles',len(rows),'out',args.out)
if __name__=='__main__':main()
