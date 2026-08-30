import csv, os, re, json, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

INFILE=os.environ.get('WKO_CSV','wko_input/wko_spediteur_standorte.csv')
OUTDIR=os.environ.get('OUTDIR','website_size_out')
os.makedirs(OUTDIR,exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
KEYS=('über uns','ueber uns','unternehmen','about','company','karriere','career','jobs','team','wir über uns','portrait','profil','geschichte','history')

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def root_domain(url):
    try:
        h=urllib.parse.urlparse(url if '://' in url else 'https://'+url).netloc.lower().split('@')[-1].split(':')[0]
        if h.startswith('www.'):h=h[4:]
        return h
    except:return ''

def mentions(text,url):
    text=clean(text); out=[]; seen=set()
    patterns=[
      (r'\b(?:über|mehr als)\s+([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\b','over'),
      (r'\b(?:rund|ca\.?|circa|etwa|knapp|approximately|around)\s+([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\b','approx'),
      (r'\b([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\b','exact'),
      (r'\b(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\s*[:\-]?\s*(?:rund|ca\.?|circa|etwa|approximately)?\s*([0-9\.]{1,7})\b','exact'),
    ]
    for pat,k in patterns:
        for m in re.finditer(pat,text,re.I):
            try:v=int(m.group(1).replace('.',''))
            except:continue
            if v<2 or v>250000:continue
            a=max(0,m.start()-190);b=min(len(text),m.end()+190);ctx=clean(text[a:b]);key=(v,ctx,url)
            if key not in seen:seen.add(key);out.append({'value':v,'kind':k,'url':url,'context':ctx})
    return out

def fetch_text(sess,url):
    r=sess.get(url,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.6'},timeout=25,allow_redirects=True)
    if r.status_code!=200 or 'text/html' not in r.headers.get('content-type','').lower(): return None,None,None
    s=BeautifulSoup(r.text,'html.parser')
    for t in s(['script','style','noscript']):t.decompose()
    text=clean(s.get_text(' ',strip=True))
    return r.url,s,text

def crawl_one(entry):
    name,site,domain=entry
    sess=requests.Session()
    starts=[]
    for candidate in [site, site.replace('http://','https://') if site.startswith('http://') else site]:
        if candidate and candidate not in starts:starts.append(candidate)
    pages=[]; allm=[]; status=''
    soup=None;base=None
    for st in starts:
        try:
            final,soup,text=fetch_text(sess,st)
            if text:
                base=final;pages.append(final);allm+=mentions(text,final);status='200';break
        except Exception as e:status='ERR'
    if soup and base:
        links=[]
        for a in soup.find_all('a',href=True):
            label=clean(a.get_text(' ',strip=True)).lower(); href=a.get('href','')
            if any(k in label or k in href.lower() for k in KEYS):
                u=urllib.parse.urljoin(base,href)
                if root_domain(u)==root_domain(base) and u not in links and u not in pages:links.append(u)
        # cap pages so this remains polite and scalable
        for u in links[:5]:
            try:
                final,ss,text=fetch_text(sess,u)
                if text:
                    pages.append(final);allm+=mentions(text,final)
            except:pass
    return {'company_name':name,'website':site,'domain':domain,'http_status':status,'pages_crawled':' | '.join(pages),'mentions':allm}

with open(INFILE,encoding='utf-8-sig',newline='') as f: raw=list(csv.DictReader(f))
entries={}
for r in raw:
    n=clean(r['company_name']); sites=[x.strip() for x in (r.get('website') or '').split('|') if x.strip()]
    for site in sites:
        d=root_domain(site)
        if d and d not in {'facebook.com','linkedin.com','instagram.com'}:
            # one company+domain pair
            entries[(n,d)]=(n,site,d)
print('company-domain pairs',len(entries),flush=True)
results=[]
with ThreadPoolExecutor(max_workers=12) as ex:
    futs={ex.submit(crawl_one,e):e for e in entries.values()}
    for i,f in enumerate(as_completed(futs),1):
        results.append(f.result())
        if i%50==0:print('crawled',i,'with mentions',sum(bool(x['mentions']) for x in results),flush=True)
rows=[]
for x in results:
    ms=x['mentions'];vals=[m['value'] for m in ms]
    rows.append({'company_name':x['company_name'],'website':x['website'],'domain':x['domain'],'http_status':x['http_status'],'pages_crawled':x['pages_crawled'],'employee_best_numeric_mention':max(vals) if vals else '','employee_evidence_contexts':' || '.join(f"{m['value']} [{m['kind']}] {m['url']} :: {m['context']}" for m in ms[:10]),'mentions_count':len(ms)})
rows.sort(key=lambda x:(x['company_name'].casefold(),x['domain']))
fields=list(rows[0].keys()) if rows else []
with open(os.path.join(OUTDIR,'website_employee_mentions.csv'),'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
summary={'company_domain_pairs':len(entries),'crawled':len(results),'with_employee_mentions':sum(bool(x['mentions']) for x in results),'numeric_mentions_20plus':sum(any(m['value']>=20 for m in x['mentions']) for x in results),'numeric_mentions_30plus':sum(any(m['value']>=30 for m in x['mentions']) for x in results)}
with open(os.path.join(OUTDIR,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
