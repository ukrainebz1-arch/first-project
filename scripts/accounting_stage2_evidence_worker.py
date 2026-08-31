#!/usr/bin/env python3
import argparse,csv,json,os,re,time,random
from urllib.parse import urlparse,urljoin,quote_plus,unquote
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
SOCIAL=('linkedin.com','xing.com','facebook.com','instagram.com')
BAD=('mandant','kunde','klient','umsatz','bilanzsumme','grenzwert','max.','maximal','bis zu')
EMP=r'(?:mitarbeiter(?:innen)?|mitarbeiter:innen|mitarbeitende|besch[aä]ftigte|kolleg(?:innen|en)|employees)'
EXPLICIT=[
 re.compile(r'(?i)(?:wir\s+)?(?:besch[aä]ftigen|z[aä]hlen|umfassen|haben|sind)\s+(?:derzeit\s+)?(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{1,4})\+?\s+'+EMP),
 re.compile(r'(?i)(?:team|kanzlei|unternehmen|gruppe)\s+(?:mit|von|umfasst|besteht\s+aus|z[aä]hlt)\s+(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{1,4})\+?\s*'+EMP+r'?'),
 re.compile(r'(?i)(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)\s*(\d{2,4})\+?\s+'+EMP),
]
RANGE=re.compile(r'(?i)(?:company size|unternehmensgr[oö][sß]e|unternehmensgroesse|größe|groesse|mitarbeiter\*?innenanzahl)\s*[:\-]?\s*(\d{1,4})\s*[–—-]\s*(\d{1,5})')
VISIBLE=re.compile(r'(?i)(?:alle\s+)?([\d\.,]{2,8})\s+(?:mitarbeiter(?::innen)?\s+anzeigen|employees)')
WHOLE_TEAM=re.compile(r'(?i)(?:unser\s+(?:gesamtes\s+)?team|team\s+besteht\s+aus|wir\s+sind\s+ein\s+team\s+von)')

def host(u):
    try:return re.sub(r'^www\.','',urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0])
    except:return ''
def get(u,timeout=10):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and ('text/html' in r.headers.get('content-type','') or 'text/plain' in r.headers.get('content-type','')):
            r.encoding=r.apparent_encoding or r.encoding; return r.url,r.text[:1500000]
    except:pass
    return '',''
def txt(h):return re.sub(r'\s+',' ',BeautifulSoup(h or '','html.parser').get_text(' ',strip=True))
def valid_num(n,ctx):
    lo=ctx.lower()
    return 5<=n<=10000 and not 1900<=n<=2100 and not any(x in lo for x in BAD)
def explicit_counts(t):
    out=[]
    for p in EXPLICIT:
        for m in p.finditer(t):
            n=int(m.group(2));ctx=t[max(0,m.start()-120):min(len(t),m.end()+160)]
            if valid_num(n,ctx): out.append({'n':n,'approx':bool(m.group(1)),'context':ctx[:500]})
    return out
def ranges(t):
    out=[]
    for m in RANGE.finditer(t):
        a,b=int(m.group(1)),int(m.group(2))
        if 1<=a<=b<=100000:out.append((a,b))
    return out
def visibles(t):
    out=[]
    for m in VISIBLE.finditer(t):
        try:
            n=int(re.sub(r'\D','',m.group(1)))
            if 1<=n<=100000:out.append(n)
        except:pass
    return out
def search(q):
    for base in ['https://www.bing.com/search?q=','https://html.duckduckgo.com/html/?q=']:
        try:
            r=requests.get(base+quote_plus(q),headers=H,timeout=10)
            if r.status_code!=200:continue
            b=BeautifulSoup(r.text,'html.parser');res=[]
            if 'bing.com' in base:
                nodes=b.select('li.b_algo')[:8]
                for x in nodes:
                    a=x.select_one('h2 a');p=x.select_one('.b_caption p')
                    if a:res.append((a.get_text(' ',strip=True),a.get('href',''),p.get_text(' ',strip=True) if p else ''))
            else:
                for x in b.select('.result')[:8]:
                    a=x.select_one('.result__a');p=x.select_one('.result__snippet')
                    if a:
                        u=a.get('href','');m=re.search(r'[?&]uddg=([^&]+)',u)
                        if m:u=unquote(m.group(1))
                        res.append((a.get_text(' ',strip=True),u,p.get_text(' ',strip=True) if p else ''))
            if res:return res
        except:pass
    return []
def company_match(name,hay):
    toks=[x.lower() for x in re.findall(r'[A-Za-zÄÖÜäöüß0-9]+',name) if len(x)>=4 and x.lower() not in {'gmbh','steuerberatung','wirtschaftsprüfung','wirtschaftspruefung','gesellschaft'}][:5]
    h=hay.lower();return not toks or any(t in h for t in toks)

def collect(row):
    official=[];profiles=set();emails=set();jobs=set();seen=set()
    sites=[x.strip() for x in (row.get('websites') or '').split(' | ') if x.strip()]
    for site in sites[:2]:
        u=site if '://' in site else 'https://'+site;fu,html=get(u)
        if not html:continue
        bh=host(fu);queue=[(fu,html)]
        while queue and len(official)<10:
            uu,hh=queue.pop(0)
            if uu in seen:continue
            seen.add(uu);t=txt(hh);b=BeautifulSoup(hh,'html.parser')
            official.append({'url':uu,'text':t[:300000],'counts':explicit_counts(t),'ranges':ranges(t),'visible':visibles(t),'whole_team':bool(WHOLE_TEAM.search(t))})
            links=[]
            for a in b.find_all('a',href=True):
                href=urljoin(uu,a['href']).split('#')[0];lab=(a.get_text(' ',strip=True)+' '+href).lower()
                if host(href)!=bh:continue
                if any(k in lab for k in ['team','mitarbeiter','people','person','kanzlei','unternehmen','ueber-uns','uber-uns','about','karriere','career','jobs']):links.append(href)
                if any(k in lab for k in ['/team/','/mitarbeiter/','/people/','/person/','teammitglied','/experten/','/expertinnen/']):profiles.add(href)
                if any(k in lab for k in ['karriere','career','jobs','stellen']):jobs.add(href)
            for e in re.findall(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',t):
                dom=e.lower().split('@')[-1]
                if bh and (dom==bh or dom.endswith('.'+bh)) and not any(x in e.lower() for x in ['office@','info@','kanzlei@','kontakt@','mail@','bewerbung@']):emails.add(e.lower())
            for href in links[:12]:
                if href not in seen and len(queue)+len(official)<10:
                    u2,h2=get(href)
                    if h2:queue.append((u2,h2))
    name=row['group_name'];sr=[]
    qs=[f'"{name}" Mitarbeiter',f'"{name}" LinkedIn employees',f'"{name}" karriere.at Mitarbeiter',f'"{name}" kununu Mitarbeiter',f'"{name}" Team']
    for q in qs:
        for title,u,snip in search(q):
            if not u or not company_match(name,title+' '+snip):continue
            if u not in [x['url'] for x in sr]:sr.append({'url':u,'title':title,'snippet':snip,'counts':explicit_counts(title+' '+snip),'ranges':ranges(title+' '+snip),'visible':visibles(title+' '+snip)})
        time.sleep(random.uniform(.03,.08))
    fetched=[]
    for x in sr[:14]:
        h=host(x['url'])
        if any(s in h for s in SOCIAL):continue
        uu,hh=get(x['url'],8)
        if hh:
            t=txt(hh);fetched.append({'url':uu,'host':host(uu),'counts':explicit_counts(t),'ranges':ranges(t),'visible':visibles(t),'text':t[:150000]})
        if len(fetched)>=5:break
    return {'official':official,'profiles':len(profiles),'emails':len(emails),'jobs':len(jobs),'search':sr[:20],'fetched':fetched}

def ev(url,typ,fact,supports):return {'url':url,'source_type':typ,'fact':fact[:450],'supports':supports[:450]}
def result(row,r):
    evidence=[];scope='AUSTRIA_GROUP' if int(float(row.get('legal_entities_count') or 0))>1 else 'AUSTRIA_LEGAL_ENTITY'
    # Official explicit counts.
    vals=[]
    for p in r['official']:
        for c in p['counts']:vals.append((c['n'],c['approx'],p['url'],c['context'],p['whole_team']))
    if vals:
        n,approx,u,ctx,whole=max(vals,key=lambda x:x[0]);evidence=[ev(u,'official_site',f'Official site employee statement around {n}.',ctx)]
        if n>=30:return make(row,'CONFIRMED_30_PLUS',n,None,scope,'HIGH',f'Official Austrian company/group page states approximately or explicitly {n} employees.',evidence,'Official-site employee statement is sufficient for a 30+ lower bound.')
        if n>=20:
            if not approx and whole:return make(row,'CONFIRMED_20_29',n,n,scope,'HIGH',f'Official whole-team statement gives {n} employees.',evidence,'Exact official whole-team count bounds the company to 20–29.')
            return make(row,'CONFIRMED_20_PLUS',n,None,scope,'HIGH',f'Official Austrian company/group page proves at least {n} employees.',evidence,'Official count proves 20+, but does not safely bound an upper limit.')
        if n<20 and whole and not approx:return make(row,'BELOW_20',n,n,scope,'HIGH',f'Official whole-team statement gives {n} employees.',evidence,'Explicit whole-team count supports below 20.')
    # Official complete staff lower bounds.
    lb=max(r['profiles'],r['emails'])
    first_url=r['official'][0]['url'] if r['official'] else ''
    if first_url and lb>=30:
        evidence=[ev(first_url,'official_site',f'Official site exposes at least {lb} distinct staff profiles/personal company-domain emails.','Counted as a staff lower bound, not an exact total.')]
        return make(row,'CONFIRMED_30_PLUS',lb,None,scope,'HIGH',f'Official site provides a direct staff lower bound of at least {lb}.',evidence,'Staff-page lower bound alone proves 30+; no upper bound assumed.')
    if first_url and lb>=20:
        evidence=[ev(first_url,'official_site',f'Official site exposes at least {lb} distinct staff profiles/personal company-domain emails.','Counted as a staff lower bound, not an exact total.')]
        return make(row,'CONFIRMED_20_PLUS',lb,None,scope,'HIGH',f'Official site provides a direct staff lower bound of at least {lb}.',evidence,'Staff-page lower bound proves 20+ but not 30+ unless count reaches 30.')
    # LinkedIn / employer-profile evidence from matched search results.
    strong=[];weak=[]
    for x in r['search']:
        h=host(x['url']);typ='linkedin' if 'linkedin.com' in h else ('karriere' if 'karriere.at' in h else ('kununu' if 'kununu.' in h else 'other'))
        for a,b in x['ranges']:
            item=(a,b,x['url'],typ,x['title']+' '+x['snippet'])
            (strong if (a>=31 or a>=51) else weak).append(item)
        for n in x['visible']:
            item=(n,n,x['url'],typ,x['title']+' '+x['snippet'])
            (strong if n>=30 else weak).append(item)
    if strong:
        a,b,u,typ,ctx=max(strong,key=lambda x:x[0]);evidence=[ev(u,typ,f'Matched company profile/search evidence shows {a}-{b} employees or visible staff.',ctx)]
        return make(row,'CONFIRMED_30_PLUS',max(30,a),b if b>a else None,scope,'MEDIUM_HIGH',f'Matched Austrian employer/company profile supplies a 30+ lower bound ({a}-{b}).',evidence,'Company-size/visible-employee evidence is tied to the matching company name; scope retained as Austrian group/entity.')
    # Fetched independent pages with explicit counts are corroboration; conservative unless clearly employer platform/press.
    fvals=[]
    for p in r['fetched']:
        for c in p['counts']:fvals.append((c['n'],p['url'],p['host'],c['context']))
    if fvals:
        n,u,h,ctx=max(fvals,key=lambda x:x[0]);typ='karriere' if 'karriere.at' in h else ('kununu' if 'kununu.' in h else 'other');evidence=[ev(u,typ,f'Fetched matched page contains employee count {n}.',ctx)]
        if n>=30:return make(row,'CONFIRMED_30_PLUS',n,None,scope,'MEDIUM_HIGH',f'Fetched matched external employer/company page explicitly reports {n} employees.',evidence,'External explicit count corroborates a 30+ Austrian employer; retained with medium-high confidence.')
        if n>=20:return make(row,'CONFIRMED_20_PLUS',n,None,scope,'MEDIUM_HIGH',f'Fetched matched external employer/company page explicitly reports {n} employees.',evidence,'External explicit count proves 20+ but not an upper bound.')
    # Search snippets / scale signals only -> likely, never confirmed.
    snippet_vals=[]
    for x in r['search']:
        for c in x['counts']:snippet_vals.append((c['n'],x['url'],x['title']+' '+x['snippet']))
    prior_urls=[x.strip() for x in (row.get('evidence_urls') or '').split(' | ') if x.strip().startswith('http')]
    signals=sum([lb>=12,r['jobs']>=2,int(float(row.get('locations_count') or 0))>=3,int(float(row.get('legal_entities_count') or 0))>=2])
    if snippet_vals and max(x[0] for x in snippet_vals)>=20:
        n,u,ctx=max(snippet_vals,key=lambda x:x[0]);evidence=[ev(u,'other',f'Matched search evidence mentions {n} employees.',ctx)]
        return make(row,'LIKELY_20_PLUS',20,None,scope,'MEDIUM',f'Matched public search evidence mentions {n} employees, but the underlying source was not strong enough for confirmation.',evidence,'Kept as likely rather than confirmed because snippet-only evidence can be stale or scope-ambiguous.')
    if weak and signals>=1:
        a,b,u,typ,ctx=max(weak,key=lambda x:x[1]);evidence=[ev(u,typ,f'Company-size evidence {a}-{b} plus independent scale signal(s).',ctx)]
        return make(row,'LIKELY_20_PLUS',20,b,scope,'MEDIUM',f'An 11–50-type company-size band is combined with {signals} independent scale signal(s).',evidence,'11–50 alone is not confirmation; therefore verdict remains likely.')
    if row.get('prior_status') in {'CONFIRMED_30_PLUS','CONFIRMED_20_29'} and prior_urls:
        evidence=[ev(prior_urls[0],'other','Prior Stage 2 evidence URL retained, but fresh audit did not independently reproduce a decisive count.','Historical evidence preserved for follow-up.')]
        return make(row,'LIKELY_20_PLUS',20,None,scope,'MEDIUM',f'Prior automated pass classified this as {row.get("prior_status")}, but the fresh audit did not recover decisive evidence.',evidence,'Downgraded to likely rather than carrying prior confirmation forward blindly.')
    if signals>=2 and (r['search'] or first_url):
        u=(r['search'][0]['url'] if r['search'] else first_url);evidence=[ev(u,'other',f'{signals} scale signals: staff lower bound={lb}, jobs={r["jobs"]}, locations={row.get("locations_count")}, legal entities={row.get("legal_entities_count")}.','Signals suggest 20+ but do not prove it.')]
        return make(row,'LIKELY_20_PLUS',20,None,scope,'LOW',f'Multiple independent scale signals make 20+ plausible, without a clean employee-count source.',evidence,'Retained for Stage 3/secondary review as likely, not confirmed.')
    return make(row,'UNRESOLVED',None,None,'UNKNOWN','LOW','Fresh public-web audit did not find reliable evidence sufficient to prove or disprove 20 employees.',[],'No unsupported promotion or below-20 conclusion was made.')

def make(row,verdict,lo,hi,scope,conf,summary,evidence,note):
    return {'group_key':row['group_key'],'group_name':row['group_name'],'prior_status':row.get('prior_status',''),'verdict':verdict,'employee_low':lo,'employee_high':hi,'count_scope':scope,'confidence':conf,'research_summary':summary,'evidence':evidence,'review_note':note,'researcher_consensus':'SINGLE'}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-jsonl',required=True);args=ap.parse_args()
    rows=list(csv.DictReader(open(args.input_csv,encoding='utf-8-sig',newline='')));os.makedirs(os.path.dirname(args.output_jsonl) or '.',exist_ok=True)
    with open(args.output_jsonl,'w',encoding='utf-8') as out:
        for i,row in enumerate(rows,1):
            try:r=collect(row);obj=result(row,r)
            except Exception as e:obj=make(row,'UNRESOLVED',None,None,'UNKNOWN','LOW',f'Public-web evidence worker encountered {type(e).__name__}; no reliable conclusion was promoted.',[],'Execution error forced a safe unresolved verdict.')
            out.write(json.dumps(obj,ensure_ascii=False)+'\n');out.flush();print(f'{i}/{len(rows)} {row["group_name"]} -> {obj["verdict"]} {obj["employee_low"]}',flush=True)
            time.sleep(random.uniform(.03,.10))
if __name__=='__main__':main()
