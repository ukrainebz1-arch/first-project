import csv
import hashlib
import json
import os
import random
import re
import time
import unicodedata
from collections import Counter, defaultdict
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

CHUNK = int(os.environ.get('CHUNK','0'))
CHUNKS = int(os.environ.get('CHUNKS','16'))
INPUT = os.environ.get('INPUT','input/wko_bookkeeping_austria_combined.csv')
OUTDIR = os.environ.get('OUTDIR','out')
os.makedirs(OUTDIR, exist_ok=True)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
HEADERS = {'User-Agent': UA, 'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
SOCIAL = {'facebook.com','instagram.com','linkedin.com','xing.com','youtube.com','tiktok.com'}
GENERIC_MAIL = {'gmail.com','gmx.at','gmx.net','outlook.com','hotmail.com','aon.at','icloud.com','yahoo.com','yahoo.de'}
LEGAL_RE = re.compile(r'\b(gmbh|gesmbh|mbh|kg|og|ag|se|flexco|e\.?u\.?)\b', re.I)
GENERIC_NAME = {'steuerberatung','steuerberater','buchhaltung','bilanzbuchhaltung','wirtschaftstreuhand','wirtschaftspruefung','wirtschaftsprüfung','kanzlei','consulting','beratung','services','service','austria','österreich','oesterreich','gmbh','kg','og','ag','mbh','gesmbh','eu','e.u'}

EMP_PATTERNS = [
    re.compile(r'(?i)(?:über|mehr als|rund|ca\.?|circa|etwa|knapp|mehr als)?\s*(\d{2,4})\+?\s*(?:mitarbeiter(?:innen)?|mitarbeiter:innen|mitarbeitende|beschäftigte|beschaeftigte|kolleg(?:en|innen)|teammitglieder)'),
    re.compile(r'(?i)(?:team|belegschaft|unternehmen)\s+(?:von|mit|umfasst|besteht aus)\s+(?:über|mehr als|rund|ca\.?|circa|etwa)?\s*(\d{2,4})'),
]
LINKEDIN_RANGE = re.compile(r'(?i)(?:größe|groesse|company size|size)\s*[:\-]?\s*(\d{1,4})\s*[–—-]\s*(\d{1,5})\s*(?:beschäftigte|employees|mitarbeiter)')
LINKEDIN_SHOW = re.compile(r'(?i)(?:alle\s+)?([\d\.]{2,7})\s+mitarbeiter(?::innen)?\s+anzeigen|([\d,.]{2,7})\s+employees')
LOC_RE = re.compile(r'(?i)(\d{1,3})\s+standorte')
EMAIL_RE = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')


def norm(s):
    s = unicodedata.normalize('NFKD', s or '')
    s = ''.join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def host(url):
    if not url: return ''
    try:
        u = url if '://' in url else 'https://'+url
        h = urlparse(u).netloc.lower().split(':')[0]
        return re.sub(r'^www\.','',h)
    except: return ''

def maildomain(email):
    try: return email.lower().split('@',1)[1].strip()
    except: return ''

def phonekey(s):
    d = re.sub(r'\D','',s or '')
    return d[-9:] if len(d)>=9 else ''

def namebase(s):
    t = norm(s)
    toks=[x for x in t.split() if x not in GENERIC_NAME and len(x)>1]
    return ' '.join(toks)

def tokens(s):
    return set(namebase(s).split())

def safe_get(url, timeout=10):
    try:
        r=requests.get(url,headers=HEADERS,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and 'text/html' in r.headers.get('content-type',''):
            r.encoding = r.apparent_encoding or r.encoding
            return r.url, r.text[:2_000_000]
    except Exception:
        pass
    return '', ''

def evidence_from_text(text):
    txt = re.sub(r'\s+',' ',BeautifulSoup(text or '', 'html.parser').get_text(' ', strip=True))
    counts=[]
    for p in EMP_PATTERNS:
        for m in p.finditer(txt):
            try:
                n=int(m.group(1).replace('.',''))
                if 10 <= n <= 10000: counts.append(n)
            except: pass
    ranges=[]
    for m in LINKEDIN_RANGE.finditer(txt):
        try:
            a,b=int(m.group(1)),int(m.group(2));
            if 1<=a<=b<=100000: ranges.append((a,b))
        except: pass
    shown=[]
    for m in LINKEDIN_SHOW.finditer(txt):
        raw=m.group(1) or m.group(2)
        try:
            n=int(re.sub(r'\D','',raw));
            if 1<=n<=100000: shown.append(n)
        except: pass
    locs=[int(x) for x in LOC_RE.findall(txt) if x.isdigit() and int(x)<=500]
    return counts, ranges, shown, locs, txt[:5000]

def crawl_site(url):
    out={'site_urls':[], 'site_counts':[], 'site_ranges':[], 'site_shown':[], 'locations':[], 'team_emails':0, 'team_profiles':0, 'job_links':0, 'site_text_sample':''}
    if not url or host(url) in SOCIAL: return out
    final, html = safe_get(url)
    if not html: return out
    basehost=host(final)
    pages=[(final,html)]
    soup=BeautifulSoup(html,'html.parser')
    cand=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(final,a['href'])
        if host(href)!=basehost: continue
        label=norm((a.get_text(' ',strip=True)+' '+href))
        if any(k in label for k in ['team','mitarbeiter','karriere','career','jobs','stellen','unternehmen','uber uns','ueber uns','kanzlei','standorte','about']):
            cand.append(href.split('#')[0])
    seen={final.split('#')[0]}
    for u in cand:
        if len(pages)>=7: break
        if u in seen: continue
        seen.add(u)
        fu,h=safe_get(u)
        if h: pages.append((fu,h))
        time.sleep(random.uniform(.05,.15))
    emails=set(); profiles=set(); jobs=set(); samples=[]
    for u,h in pages:
        counts,ranges,shown,locs,txt=evidence_from_text(h)
        out['site_counts']+=counts; out['site_ranges']+=ranges; out['site_shown']+=shown; out['locations']+=locs
        out['site_urls'].append(u); samples.append(txt[:1200])
        bs=BeautifulSoup(h,'html.parser')
        for e in EMAIL_RE.findall(bs.get_text(' ',strip=True)):
            if maildomain(e)==basehost or maildomain(e).endswith('.'+basehost): emails.add(e.lower())
        for a in bs.find_all('a',href=True):
            href=urljoin(u,a['href']); lab=norm(a.get_text(' ',strip=True)+' '+href)
            if host(href)==basehost and any(k in lab for k in ['/team/','/mitarbeiter/','/person/','/people/','teammitglied']): profiles.add(href.split('#')[0])
            if host(href)==basehost and any(k in lab for k in ['job','stelle','karriere','career','vacancy']): jobs.add(href.split('#')[0])
    out['team_emails']=len(emails); out['team_profiles']=len(profiles); out['job_links']=len(jobs); out['site_text_sample']=' | '.join(samples)[:4000]
    return out

def bing_search(q):
    url='https://www.bing.com/search?q='+quote_plus(q)+'&count=10&setlang=de-AT'
    try:
        r=requests.get(url,headers=HEADERS,timeout=12)
        if r.status_code!=200: return [], f'bing:{r.status_code}'
        soup=BeautifulSoup(r.text,'html.parser'); res=[]
        for li in soup.select('li.b_algo')[:10]:
            a=li.select_one('h2 a') or li.find('a',href=True)
            if not a: continue
            title=a.get_text(' ',strip=True); href=a.get('href','')
            p=li.select_one('.b_caption p') or li.find('p')
            snippet=p.get_text(' ',strip=True) if p else ''
            res.append((title,href,snippet))
        return res, 'bing:ok'
    except Exception as e:
        return [], 'bing:error'

def ddg_search(q):
    url='https://html.duckduckgo.com/html/?q='+quote_plus(q)
    try:
        r=requests.get(url,headers=HEADERS,timeout=12)
        if r.status_code!=200: return [], f'ddg:{r.status_code}'
        soup=BeautifulSoup(r.text,'html.parser'); res=[]
        for x in soup.select('.result')[:10]:
            a=x.select_one('.result__a')
            if not a: continue
            title=a.get_text(' ',strip=True); href=a.get('href','')
            sn=x.select_one('.result__snippet'); snippet=sn.get_text(' ',strip=True) if sn else ''
            res.append((title,href,snippet))
        return res,'ddg:ok'
    except Exception:
        return [],'ddg:error'

def result_matches(row,title,snippet,url):
    nt=tokens(row['company_name'])
    if not nt: return True
    hay=norm(title+' '+snippet+' '+url)
    hits=sum(1 for t in nt if len(t)>=3 and t in hay)
    city=norm(row.get('city',''))
    return hits>=max(1,min(2,len(nt))) or (hits>=1 and city and city in hay)

def search_evidence(row):
    q=f'"{row["company_name"]}" {row.get("city","")} Mitarbeiter LinkedIn Steuerberatung Buchhaltung'
    results,engine=bing_search(q)
    if not results:
        results,engine=ddg_search(q)
    matched=[]; discovered=[]; alltext=[]
    for title,url,snip in results:
        if not result_matches(row,title,snip,url): continue
        matched.append(url); alltext.append(title+' '+snip)
        h=host(url)
        if h and h not in SOCIAL and 'wko.at' not in h and 'firmenabc.at' not in h and 'herold.at' not in h and 'google.' not in h and 'bing.com' not in h:
            discovered.append(h)
    txt=' | '.join(alltext)
    counts,ranges,shown,locs,_=evidence_from_text(txt)
    return {'search_urls':matched[:8], 'search_counts':counts, 'search_ranges':ranges, 'search_shown':shown, 'search_locations':locs, 'discovered_domains':discovered[:5], 'search_text':txt[:4000], 'engine':engine}

def classify(row, gf, site, sea):
    counts=[]; ranges=[]; shown=[]; locs=[]
    counts += site['site_counts'] + sea['search_counts']
    ranges += site['site_ranges'] + sea['search_ranges']
    shown += site['site_shown'] + sea['search_shown']
    locs += site['locations'] + sea['search_locations']
    max_count=max(counts+shown+[0])
    max_loc=max(locs+[0])
    low=high=0; confidence='LOW'; status='UNRESOLVED'; reasons=[]
    if max_count>=30:
        low=high=max_count; confidence='HIGH'; status='CONFIRMED_30_PLUS'; reasons.append(f'explicit employee signal {max_count}')
    elif max_count>=20:
        low=high=max_count; confidence='HIGH'; status='CONFIRMED_20_29'; reasons.append(f'explicit employee signal {max_count}')
    elif any(a>=30 for a,b in ranges):
        a,b=max(ranges,key=lambda x:x[0]); low,high=a,b; confidence='HIGH'; status='CONFIRMED_30_PLUS'; reasons.append(f'employee range {a}-{b}')
    elif any(a>=20 for a,b in ranges):
        a,b=max(ranges,key=lambda x:x[0]); low,high=a,b; confidence='HIGH'; status='CONFIRMED_20_PLUS'; reasons.append(f'employee range {a}-{b}')
    elif site['team_emails']>=30 or site['team_profiles']>=30:
        n=max(site['team_emails'],site['team_profiles']); low=n; high=n; confidence='HIGH'; status='CONFIRMED_30_PLUS'; reasons.append(f'at least {n} staff profiles/emails on official site')
    elif site['team_emails']>=20 or site['team_profiles']>=20:
        n=max(site['team_emails'],site['team_profiles']); low=n; high=n; confidence='HIGH'; status='CONFIRMED_20_PLUS'; reasons.append(f'at least {n} staff profiles/emails on official site')
    else:
        range1150=next(((a,b) for a,b in ranges if a<=19 and b>=20),None)
        strong=sum([gf['group_entries']>=3, max_loc>=3, site['job_links']>=3, site['team_emails']>=12, site['team_profiles']>=12])
        if range1150 and strong>=1:
            low,high=20,range1150[1]; confidence='MEDIUM'; status='LIKELY_20_PLUS'; reasons.append(f'LinkedIn/search range {range1150[0]}-{range1150[1]} plus scale signal')
        elif strong>=2:
            low,high=20,50; confidence='MEDIUM'; status='LIKELY_20_PLUS'; reasons.append('multiple independent scale signals')
        elif max_count>0 and max_count<20:
            low=high=max_count; confidence='MEDIUM'; status='BELOW_20_SIGNAL'; reasons.append(f'explicit small employee signal {max_count}')
        elif gf['person_like'] and not row.get('website') and gf['group_entries']==1:
            status='LOW_LIKELIHOOD_SOLO'; reasons.append('individual practitioner, no website/group scale signal')
        else:
            status='UNRESOLVED'; reasons.append('no reliable 20+ evidence found')
    if gf['group_entries']>1: reasons.append(f'{gf["group_entries"]} WKO entries share group identifier')
    if max_loc: reasons.append(f'up to {max_loc} locations mentioned')
    if site['job_links']: reasons.append(f'{site["job_links"]} career/job links found')
    return status,confidence,low,high,'; '.join(reasons)

def main():
    with open(INPUT,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    dom_count=Counter(); phone_count=Counter(); emaildom_count=Counter(); name_count=Counter()
    for r in rows:
        d=host(r.get('website',''))
        if d and d not in SOCIAL: dom_count[d]+=1
        p=phonekey(r.get('phones',''))
        if p: phone_count[p]+=1
        ed=maildomain(r.get('email',''))
        if ed and ed not in GENERIC_MAIL: emaildom_count[ed]+=1
        nb=namebase(r.get('company_name',''))
        if nb: name_count[nb]+=1
    selected=[]
    for r in rows:
        h=int(hashlib.sha1(r['firmaid'].encode()).hexdigest()[:8],16)%CHUNKS
        if h==CHUNK: selected.append(r)
    print(f'chunk {CHUNK}/{CHUNKS}: {len(selected)} of {len(rows)} rows',flush=True)
    output=[]
    for idx,r in enumerate(selected,1):
        d=host(r.get('website','')); p=phonekey(r.get('phones','')); ed=maildomain(r.get('email','')); nb=namebase(r.get('company_name',''))
        group_entries=max(dom_count.get(d,0) if d and d not in SOCIAL else 0, phone_count.get(p,0) if p else 0, emaildom_count.get(ed,0) if ed and ed not in GENERIC_MAIL else 0, name_count.get(nb,0) if nb else 0, 1)
        person_like=not bool(LEGAL_RE.search(r.get('company_name',''))) and len(norm(r.get('company_name','')).split())<=6
        gf={'group_entries':group_entries,'person_like':person_like}
        deep=bool(LEGAL_RE.search(r.get('company_name',''))) or bool(r.get('website')) or group_entries>=2
        site=crawl_site(r.get('website','')) if r.get('website') else {'site_urls':[], 'site_counts':[], 'site_ranges':[], 'site_shown':[], 'locations':[], 'team_emails':0, 'team_profiles':0, 'job_links':0, 'site_text_sample':''}
        sea={'search_urls':[], 'search_counts':[], 'search_ranges':[], 'search_shown':[], 'search_locations':[], 'discovered_domains':[], 'search_text':'', 'engine':'not_searched'}
        # Avoid spending search-engine requests on obvious solo practitioners; every row is still classified.
        if deep:
            sea=search_evidence(r)
            time.sleep(random.uniform(.12,.35))
        status,conf,emin,emax,reason=classify(r,gf,site,sea)
        discovered_domain = d or (sea['discovered_domains'][0] if sea['discovered_domains'] else '')
        rr=dict(r)
        rr.update({
            'legal_entity': 'yes' if LEGAL_RE.search(r.get('company_name','')) else 'no',
            'person_like': 'yes' if person_like else 'no',
            'group_entries_signal': group_entries,
            'original_domain': d,
            'discovered_domain': discovered_domain,
            'site_team_emails': site['team_emails'],
            'site_team_profiles': site['team_profiles'],
            'site_job_links': site['job_links'],
            'max_location_signal': max(site['locations']+sea['search_locations']+[0]),
            'explicit_employee_signals': ' | '.join(map(str,site['site_counts']+sea['search_counts']+site['site_shown']+sea['search_shown'])),
            'employee_range_signals': ' | '.join(f'{a}-{b}' for a,b in site['site_ranges']+sea['search_ranges']),
            'qualification_status': status,
            'confidence': conf,
            'employee_estimate_min': emin,
            'employee_estimate_max': emax,
            'qualification_reason': reason,
            'research_engine': sea['engine'],
            'source_urls': ' | '.join(dict.fromkeys(site['site_urls']+sea['search_urls']))[:8000],
            'evidence_snippet': (site['site_text_sample']+' | '+sea['search_text'])[:5000],
        })
        output.append(rr)
        if idx%25==0 or idx==len(selected): print(f'chunk {CHUNK}: {idx}/{len(selected)}',flush=True)
    fields=list(output[0].keys()) if output else []
    path=os.path.join(OUTDIR,f'qualified_chunk_{CHUNK:02d}.csv')
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(output)
    with open(os.path.join(OUTDIR,f'summary_{CHUNK:02d}.json'),'w',encoding='utf-8') as f:
        json.dump({'chunk':CHUNK,'rows':len(output),'status_counts':Counter(x['qualification_status'] for x in output)},f,ensure_ascii=False,indent=2)

if __name__=='__main__': main()
