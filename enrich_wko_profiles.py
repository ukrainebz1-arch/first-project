import csv, os, re, json, time, random
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

SHARD=int(os.environ.get('SHARD','0')); SHARDS=int(os.environ.get('SHARDS','24'))
SRC=os.environ.get('SRC','source/wko_bookkeeping_austria_combined.csv')
OUT=os.environ.get('OUT','wko_profile_out')
os.makedirs(OUT,exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'

with open(SRC,encoding='utf-8-sig',newline='') as f:
    rows=list(csv.DictReader(f))
rows=[r for i,r in enumerate(rows) if i%SHARDS==SHARD]
print('SHARD',SHARD,'ROWS',len(rows),flush=True)

def clean(x): return re.sub(r'\s+',' ',x or '').strip()

def extract(html, base):
    soup=BeautifulSoup(html,'html.parser')
    emails=[]; phones=[]; externals=[]; linkedin=[]
    for a in soup.find_all('a',href=True):
        h=(a.get('href') or '').strip(); low=h.lower()
        if low.startswith('mailto:'):
            v=h.split(':',1)[1].split('?',1)[0].strip()
            if v and v not in emails: emails.append(v)
        elif low.startswith('tel:'):
            v=clean(h.split(':',1)[1])
            if v and v not in phones: phones.append(v)
        elif low.startswith('http') or low.startswith('//'):
            u=urljoin(base,h); host=urlparse(u).netloc.lower().replace('www.','')
            if 'linkedin.com' in host:
                if u not in linkedin: linkedin.append(u)
            elif not any(x in host for x in ['firmen.wko.at','wko.at','google.','facebook.com','instagram.com','youtube.com','xing.com']):
                if u not in externals: externals.append(u)
    text=clean(soup.get_text(' ',strip=True))
    return emails,phones,externals,linkedin,text[:8000]

fields=['firmaid','company_name','city','profile_url','profile_status','profile_email','profile_phones','profile_website','all_external_links','linkedin_url','profile_text_sample']
path=os.path.join(OUT,f'wko_profile_{SHARD:02d}.csv')
with sync_playwright() as p, open(path,'w',encoding='utf-8-sig',newline='') as out:
    browser=p.chromium.launch(headless=True,args=['--disable-blink-features=AutomationControlled'])
    ctx=browser.new_context(user_agent=UA,locale='de-AT',timezone_id='Europe/Vienna',viewport={'width':1365,'height':900},extra_http_headers={'Accept-Language':'de-AT,de;q=0.9,en;q=0.5'})
    page=ctx.new_page(); page.set_default_timeout(25000)
    w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
    for j,r in enumerate(rows):
        status=''; html=''; err=''
        for attempt in range(2):
            try:
                resp=page.goto(r['profile_url'],wait_until='domcontentloaded',timeout=60000)
                status=str(resp.status if resp else '')
                page.wait_for_timeout(250)
                html=page.content()
                if resp and resp.status<400 and 'Error.aspx' not in page.url: break
            except Exception as e:
                err=repr(e)[:200]
                page.wait_for_timeout(500)
        emails=phones=externals=linkedin=[]; text=''
        if html:
            emails,phones,externals,linkedin,text=extract(html,r['profile_url'])
        w.writerow({
            'firmaid':r['firmaid'],'company_name':r['company_name'],'city':r['city'],'profile_url':r['profile_url'],
            'profile_status':status or err,'profile_email':' | '.join(emails),'profile_phones':' | '.join(phones),
            'profile_website':externals[0] if externals else '', 'all_external_links':' | '.join(externals),
            'linkedin_url':linkedin[0] if linkedin else '', 'profile_text_sample':text,
        })
        if (j+1)%25==0: print('PROGRESS',SHARD,j+1,'/',len(rows),flush=True)
        page.wait_for_timeout(random.randint(120,280))
    browser.close()
print('DONE',path,flush=True)
