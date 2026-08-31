import csv, os, re, json, time, unicodedata, urllib.parse
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

INFILE=os.environ.get('WKO_CSV','iv_size_input/iv_size_input.csv')
OUTDIR=os.environ.get('OUTDIR','iv_karriere_fast')
os.makedirs(OUTDIR,exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
SITEMAP='https://www.karriere.at/static/sitemaps/sitemap-firmen-https.xml'

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def ascii_norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    s=s.replace('&',' und ')
    s=re.sub(r'\b(gesellschaft mit beschrankter haftung|gesellschaft m b h|ges m b h|gesmbh|gmbh|mbh|ag|kg|og|e u|eu|co)\b',' ',s)
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return clean(s)

def token_set(s):
    stop={'immobilien','immobilienverwaltung','hausverwaltung','liegenschaftsverwaltung','verwaltung','real','realitaten','realitaeten','management','service','services','austria','osterreich','und','co','gesellschaft','group','gruppe'}
    return {t for t in ascii_norm(s).split() if len(t)>=3 and t not in stop}

def parse_xml_urls(text): return re.findall(r'<loc>(.*?)</loc>',text,re.I|re.S)
def fetch_sitemap_urls(sess,url,depth=0):
    r=sess.get(url,headers={'User-Agent':UA},timeout=60); r.raise_for_status()
    urls=parse_xml_urls(r.text)
    if any(u.lower().endswith('.xml') for u in urls) and depth<2:
        out=[]
        for u in urls:
            if u.lower().endswith('.xml'):
                try: out.extend(fetch_sitemap_urls(sess,u,depth+1))
                except Exception as e: print('sitemap child fail',u,repr(e),flush=True)
        return out
    return urls

def parse_employee_range(text):
    text=clean(text)
    m=re.search(r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*[-–]\s*([0-9\.]+)',text,re.I)
    if m:return int(m.group(1).replace('.','')),int(m.group(2).replace('.','')),m.group(0)
    m=re.search(r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*(?:\+|plus)',text,re.I)
    if m:
        v=int(m.group(1).replace('.',''));return v,None,m.group(0)
    m=re.search(r'\b(?:rund|ca\.?|circa|etwa|über|mehr als)?\s*([0-9]{2,5})\s+Mitarbeiter(?:innen|Innen|:innen|\*innen)?\b',text,re.I)
    if m:
        v=int(m.group(1));return v,v,m.group(0)
    return None,None,''

def parse_profile(sess,url):
    r=sess.get(url,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9'},timeout=35)
    if r.status_code!=200:return None
    soup=BeautifulSoup(r.text,'html.parser'); text=clean(soup.get_text(' ',strip=True))
    h1=soup.find('h1'); pname=clean(h1.get_text(' ',strip=True)) if h1 else ''
    lo,hi,ev=parse_employee_range(text)
    jobs=None
    for pat in [r'(\d+)\s+aktuelle offene Jobs',r'Aktuelle Jobs\s*(\d+)',r'(\d+)\s+Jobs\b']:
        m=re.search(pat,text,re.I)
        if m:
            try:jobs=int(m.group(1));break
            except:pass
    return {'profile_name':pname,'emp_min':lo,'emp_max':hi,'employee_evidence':ev,'jobs':jobs,'text':text[:20000]}

with open(INFILE,encoding='utf-8-sig',newline='') as f: raw=list(csv.DictReader(f))
agg={}
for r in raw:
    n=clean(r['company_name']);g=agg.setdefault(n,{'company_name':n,'wko_rows':0,'states':set(),'places':set()})
    g['wko_rows']+=1;g['states'].add(r.get('bundesland',''))
    if r.get('place'):g['places'].add(r['place'])
companies=list(agg.values())
for g in companies:
    g['states']='; '.join(sorted(x for x in g['states'] if x));g['places']=' | '.join(sorted(g['places']))

sess=requests.Session(); urls=fetch_sitemap_urls(sess,SITEMAP); firm_urls=[u for u in urls if '/f/' in u]
print('WKO unique names',len(companies),'karriere urls',len(firm_urls),flush=True)
indexed=[]; inv=defaultdict(set)
for i,u in enumerate(firm_urls):
    slug=urllib.parse.unquote(u.rstrip('/').split('/f/',1)[-1]).replace('-',' ')
    sn=ascii_norm(slug);st=token_set(slug);indexed.append((u,sn,st))
    for t in st:inv[t].add(i)

matches=[]
for idx,c in enumerate(companies,1):
    cn=c['company_name'];cnorm=ascii_norm(cn);ct=token_set(cn)
    cand_idx=set()
    for t in ct:cand_idx.update(inv.get(t,set()))
    # Fallback for tokenless/generic names: compare only a cheap substring slice.
    if not cand_idx:
        first=cnorm.split()[0] if cnorm.split() else ''
        cand_idx={i for i,(_,sn,_) in enumerate(indexed) if first and first in sn}
    scored=[]
    for i in cand_idx:
        u,snorm,st=indexed[i]
        inter=len(ct & st)
        score=max(fuzz.token_set_ratio(cnorm,snorm),fuzz.ratio(cnorm,snorm))
        if score>=68 or (inter>=2 and score>=55):scored.append((score,u))
    scored=sorted(scored,reverse=True)[:5]
    best=None
    for score,u in scored:
        try:p=parse_profile(sess,u)
        except Exception:continue
        if not p:continue
        confirm=max(fuzz.token_set_ratio(cnorm,ascii_norm(p['profile_name'])),fuzz.ratio(cnorm,ascii_norm(p['profile_name'])))
        cities=[]
        for piece in c['places'].split('|'):
            m=re.match(r'\s*\d{4}\s+(.+)',piece.strip())
            if m:cities.append(m.group(1).strip())
        loc_hit=any(city.casefold() in p['text'].casefold() for city in cities[:8] if city)
        if confirm>=72 or (confirm>=60 and loc_hit):
            cand=(confirm,score,u,p,loc_hit)
            if best is None or cand[0]>best[0]:best=cand
        time.sleep(0.01)
    rec={**c,'karriere_url':'','karriere_name':'','karriere_match_score':'','karriere_emp_min':'','karriere_emp_max':'','karriere_employee_evidence':'','karriere_jobs':'','karriere_location_hit':''}
    if best:
        confirm,score,u,p,loc_hit=best
        rec.update({'karriere_url':u,'karriere_name':p['profile_name'],'karriere_match_score':round(confirm,1),'karriere_emp_min':p['emp_min'] if p['emp_min'] is not None else '', 'karriere_emp_max':p['emp_max'] if p['emp_max'] is not None else '', 'karriere_employee_evidence':p['employee_evidence'], 'karriere_jobs':p['jobs'] if p['jobs'] is not None else '', 'karriere_location_hit':loc_hit})
    matches.append(rec)
    if idx%100==0:print('processed',idx,'matches',sum(bool(x['karriere_url']) for x in matches),'ranges',sum(x['karriere_emp_min']!='' for x in matches),flush=True)

fields=list(matches[0].keys())
with open(os.path.join(OUTDIR,'karriere_matches.csv'),'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(matches)
summary={'wko_unique_names':len(companies),'karriere_sitemap_urls':len(firm_urls),'matched_profiles':sum(bool(x['karriere_url']) for x in matches),'with_employee_range':sum(x['karriere_emp_min']!='' for x in matches)}
with open(os.path.join(OUTDIR,'karriere_summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
