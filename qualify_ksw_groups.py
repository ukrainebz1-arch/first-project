import csv,os,re,hashlib,time,random
from urllib.parse import urlparse,urljoin,quote_plus
import requests
from bs4 import BeautifulSoup

CHUNK=int(os.environ.get('CHUNK','0')); CHUNKS=int(os.environ.get('CHUNKS','32'))
INPUT=os.environ.get('INPUT','input/ksw_legal_entity_groups.csv'); OUTDIR=os.environ.get('OUTDIR','out')
os.makedirs(OUTDIR,exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
SOCIAL={'linkedin.com','www.linkedin.com','facebook.com','instagram.com','xing.com','youtube.com'}

EXPLICIT_PATTERNS=[
 re.compile(r'(?i)(?:wir\s+)?(?:besch[aä]ftigen|z[aä]hlen|umfassen|haben|sind)\s+(?:derzeit\s+)?(?:rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{2,4})\+?\s+(?:mitarbeiter(?:innen)?|mitarbeiter:innen|mitarbeitende|besch[aä]ftigte|kolleg(?:innen|en))'),
 re.compile(r'(?i)(?:team|kanzlei|unternehmen|gruppe)\s+(?:mit|von|umfasst|besteht\s+aus|z[aä]hlt)\s+(?:rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{2,4})\+?\s+(?:mitarbeiter(?:innen)?|mitarbeiter:innen|mitarbeitende|besch[aä]ftigte|kolleg(?:innen|en))?'),
 re.compile(r'(?i)(?:rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)\s*(\d{2,4})\+?\s+(?:mitarbeiter(?:innen)?|mitarbeiter:innen|mitarbeitende|besch[aä]ftigte|kolleg(?:innen|en))'),
]
LI_RANGE=re.compile(r'(?i)(?:company size|unternehmensgr[oö][sß]e|größe|groesse)\s*[:\-]?\s*(\d{1,4})\s*[–—-]\s*(\d{1,5})\s*(?:employees|besch[aä]ftigte|mitarbeiter)')
LI_VISIBLE=re.compile(r'(?i)(?:alle\s+)?([\d\.]{2,7})\s+mitarbeiter(?::innen)?\s+anzeigen|([\d,.]{2,7})\s+employees')
KARR_RANGE=re.compile(r'(?i)mitarbeiter\*?innenanzahl\s*(\d{1,4})\s*[–—-]\s*(\d{1,5})')

BAD_CONTEXT=['mandant','kunde','klient','bis zu','max.','maximal','jahresdurchschnitt','grenzwert','ug b','ugb','umsatz','bilanzsumme']

def host(u):
    u=(u or '').split(' | ')[0].strip()
    if not u:return ''
    try:return re.sub(r'^www\.','',urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0])
    except:return ''

def safe_get(u,timeout=14):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and 'text/html' in r.headers.get('content-type',''):
            r.encoding=r.apparent_encoding or r.encoding;return r.url,r.text[:2500000]
    except:pass
    return '',''

def text(html):return re.sub(r'\s+',' ',BeautifulSoup(html or '','html.parser').get_text(' ',strip=True))

def valid_num(n,ctx):
    if n<10 or n>10000 or 1900<=n<=2100:return False
    low=ctx.lower()
    if any(b in low for b in BAD_CONTEXT):return False
    return True

def extract_explicit(txt):
    vals=[]
    for pat in EXPLICIT_PATTERNS:
        for m in pat.finditer(txt):
            n=int(m.group(1));ctx=txt[max(0,m.start()-90):min(len(txt),m.end()+90)]
            if valid_num(n,ctx):vals.append((n,ctx.strip()))
    return vals

def crawl(row):
    website=(row.get('websites') or '').split(' | ')[0].strip()
    out={'official_counts':[],'team_profiles':0,'team_emails':0,'job_links':0,'official_urls':[]}
    if not website:return out
    u=website if '://' in website else 'https://'+website
    fu,html=safe_get(u)
    if not html:return out
    bh=host(fu);pages=[(fu,html)];seen={fu.split('#')[0]};cand=[]
    bs=BeautifulSoup(html,'html.parser')
    for a in bs.find_all('a',href=True):
        href=urljoin(fu,a['href']).split('#')[0];lab=(a.get_text(' ',strip=True)+' '+href).lower()
        if host(href)==bh and any(k in lab for k in ['team','mitarbeiter','people','kanzlei','unternehmen','ueber-uns','uber-uns','about','karriere','career','jobs','stellen','standort']):cand.append(href)
    for href in cand:
        if len(pages)>=8:break
        if href in seen:continue
        seen.add(href);uu,hh=safe_get(href)
        if hh:pages.append((uu,hh))
        time.sleep(random.uniform(.03,.10))
    profiles=set();emails=set();jobs=set()
    for uu,hh in pages:
        tt=text(hh);out['official_counts']+=extract_explicit(tt);out['official_urls'].append(uu)
        b=BeautifulSoup(hh,'html.parser')
        for a in b.find_all('a',href=True):
            href=urljoin(uu,a['href']).split('#')[0];lab=(a.get_text(' ',strip=True)+' '+href).lower()
            if host(href)==bh and any(k in lab for k in ['/team/','/mitarbeiter/','/people/','/person/','teammitglied']):profiles.add(href)
            if host(href)==bh and any(k in lab for k in ['karriere','career','jobs','stellenangebot','job/']):jobs.add(href)
        for e in re.findall(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',tt):
            if e.lower().endswith('@'+bh) or e.lower().split('@')[-1].endswith('.'+bh):emails.add(e.lower())
    out['team_profiles']=len(profiles);out['team_emails']=len(emails);out['job_links']=len(jobs)
    return out

def search(q):
    for base in ['https://www.bing.com/search?q=','https://html.duckduckgo.com/html/?q=']:
        try:
            r=requests.get(base+quote_plus(q),headers=H,timeout=14)
            if r.status_code!=200:continue
            b=BeautifulSoup(r.text,'html.parser');items=[]
            if 'bing.com' in base:
                nodes=b.select('li.b_algo')[:10]
                for x in nodes:
                    a=x.select_one('h2 a');p=x.select_one('.b_caption p')
                    if a:items.append((a.get_text(' ',strip=True),a.get('href',''),p.get_text(' ',strip=True) if p else ''))
            else:
                for x in b.select('.result')[:10]:
                    a=x.select_one('.result__a');p=x.select_one('.result__snippet')
                    if a:items.append((a.get_text(' ',strip=True),a.get('href',''),p.get_text(' ',strip=True) if p else ''))
            if items:return items
        except:pass
    return []

def search_evidence(row):
    name=row['group_name'];queries=[f'"{name}" Mitarbeiter Steuerberatung',f'"{name}" LinkedIn employees',f'"{name}" Mitarbeiter karriere.at']
    texts=[];urls=[]
    for q in queries:
        for t,u,s in search(q):
            hay=(t+' '+s).lower();tokens=[x for x in re.findall(r'[a-zA-ZäöüÄÖÜß0-9]+',name.lower()) if len(x)>=4][:5]
            if tokens and not any(tok in hay for tok in tokens):continue
            texts.append(t+' '+s);urls.append(u)
        time.sleep(random.uniform(.08,.18))
    txt=' | '.join(texts)
    explicit=extract_explicit(txt)
    ranges=[]
    for pat in [LI_RANGE,KARR_RANGE]:
        for m in pat.finditer(txt):
            try:
                a,b=int(m.group(1)),int(m.group(2))
                if 1<=a<=b<=100000:ranges.append((a,b))
            except:pass
    visible=[]
    for m in LI_VISIBLE.finditer(txt):
        raw=m.group(1) or m.group(2)
        try:
            n=int(re.sub(r'\D','',raw))
            if 1<=n<=100000:visible.append(n)
        except:pass
    return {'explicit':explicit,'ranges':ranges,'visible':visible,'urls':list(dict.fromkeys(urls))[:12],'text':txt[:7000]}

def classify(row,site,sea):
    official=[n for n,_ in site['official_counts']]
    searchvals=[n for n,_ in sea['explicit']]
    best_off=max(official+[0]);best_search=max(searchvals+[0]);best_vis=max(sea['visible']+[0])
    # official site dominates
    if best_off>=30:return 'CONFIRMED_30_PLUS','HIGH',best_off,best_off,'official explicit employee count'
    if best_off>=20:return 'CONFIRMED_20_29','HIGH',best_off,best_off,'official explicit employee count'
    if site['team_profiles']>=30 or site['team_emails']>=30:
        n=max(site['team_profiles'],site['team_emails']);return 'CONFIRMED_30_PLUS','HIGH',n,n,'official team/profile lower bound'
    if site['team_profiles']>=20 or site['team_emails']>=20:
        n=max(site['team_profiles'],site['team_emails']);return 'CONFIRMED_20_29','HIGH',n,n,'official team/profile lower bound'
    # search explicit counts need corroboration by domain/company match via query; medium-high
    if best_search>=30:return 'CONFIRMED_30_PLUS','MEDIUM_HIGH',best_search,best_search,'explicit employee count in matched search result'
    if best_search>=20:return 'CONFIRMED_20_29','MEDIUM_HIGH',best_search,best_search,'explicit employee count in matched search result'
    if best_vis>=30:return 'CONFIRMED_30_PLUS','MEDIUM_HIGH',best_vis,best_vis,'LinkedIn visible employees'
    if best_vis>=20:return 'CONFIRMED_20_29','MEDIUM_HIGH',best_vis,best_vis,'LinkedIn visible employees'
    # company-size bands
    if any(a>=51 for a,b in sea['ranges']):
        a,b=max(sea['ranges'],key=lambda x:x[0]);return 'CONFIRMED_30_PLUS','MEDIUM_HIGH',a,b,'company-size band'
    if any(a>=31 for a,b in sea['ranges']):
        a,b=max(sea['ranges'],key=lambda x:x[0]);return 'CONFIRMED_30_PLUS','MEDIUM_HIGH',a,b,'company-size band'
    if any(a<=20 and b>=50 for a,b in sea['ranges']) and (site['team_profiles']>=12 or site['job_links']>=2 or int(row.get('locations_count') or 0)>=3):
        a,b=max(sea['ranges'],key=lambda x:x[1]);return 'LIKELY_20_PLUS','MEDIUM',20,b,'11–50/size band plus scale corroboration'
    # candidate for manual followup when it has strong scale signals
    scale=sum([int(row.get('legal_entities_count') or 0)>=2,int(row.get('locations_count') or 0)>=3,site['job_links']>=2,site['team_profiles']>=10,site['team_emails']>=10])
    if scale>=2:return 'POSSIBLE_20_PLUS','LOW_MEDIUM',0,0,'multiple scale signals; manual verification needed'
    return 'NO_20PLUS_EVIDENCE','LOW',0,0,'no reliable 20+ evidence found'

def main():
    with open(INPUT,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    sel=[r for r in rows if int(hashlib.sha1(r['group_key'].encode()).hexdigest()[:8],16)%CHUNKS==CHUNK]
    out=[]
    for i,r in enumerate(sel,1):
        site=crawl(r);sea=search_evidence(r);status,conf,lo,hi,reason=classify(r,site,sea)
        rr=dict(r);rr.update({'qualification_status':status,'confidence':conf,'employee_low':lo,'employee_high':hi,'reason':reason,
            'official_employee_evidence':' | '.join(f'{n}: {ctx[:180]}' for n,ctx in site['official_counts'][:8]),
            'site_team_profiles':site['team_profiles'],'site_team_emails':site['team_emails'],'site_job_links':site['job_links'],
            'search_employee_evidence':' | '.join(f'{n}: {ctx[:180]}' for n,ctx in sea['explicit'][:8]),
            'search_size_ranges':' | '.join(f'{a}-{b}' for a,b in sea['ranges']),'linkedin_visible':' | '.join(map(str,sea['visible'])),
            'evidence_urls':' | '.join(list(dict.fromkeys(site['official_urls']+sea['urls']))[:20])})
        out.append(rr)
        print(CHUNK,i,len(sel),r['group_name'],status,lo,hi,flush=True)
        time.sleep(random.uniform(.08,.18))
    path=os.path.join(OUTDIR,f'ksw_qualified_chunk_{CHUNK:02d}.csv')
    if out:
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(out[0].keys()));w.writeheader();w.writerows(out)
if __name__=='__main__':main()
