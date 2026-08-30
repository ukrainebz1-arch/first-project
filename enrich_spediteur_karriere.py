import csv, os, re, json, time, unicodedata, urllib.parse
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz

INFILE=os.environ.get('WKO_CSV','wko_input/wko_spediteur_standorte.csv')
OUTDIR=os.environ.get('OUTDIR','size_out')
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
    stop={'spedition','speditions','logistik','logistics','transport','transporte','international','internationale','austria','osterreich','und','co','gesellschaft'}
    return {t for t in ascii_norm(s).split() if len(t)>=3 and t not in stop}

def parse_xml_urls(text):
    # works for both urlset and sitemapindex
    return re.findall(r'<loc>(.*?)</loc>',text,re.I|re.S)

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
    pats=[
      r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*[-–]\s*([0-9\.]+)',
      r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*(?:\+|plus)',
    ]
    m=re.search(pats[0],text,re.I)
    if m: return int(m.group(1).replace('.','')),int(m.group(2).replace('.','')),m.group(0)
    m=re.search(pats[1],text,re.I)
    if m:
        v=int(m.group(1).replace('.','')); return v,None,m.group(0)
    # Natural language e.g. rund 80 MitarbeiterInnen
    m=re.search(r'\b(?:rund|ca\.?|circa|etwa|über|mehr als)?\s*([0-9]{2,5})\s+Mitarbeiter(?:innen|Innen|:innen|\*innen)?\b',text,re.I)
    if m:
        v=int(m.group(1)); return v,v,m.group(0)
    return None,None,''

def parse_profile(sess,url):
    r=sess.get(url,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9'},timeout=45)
    if r.status_code!=200: return None
    soup=BeautifulSoup(r.text,'html.parser')
    text=clean(soup.get_text(' ',strip=True))
    h1=soup.find('h1'); pname=clean(h1.get_text(' ',strip=True)) if h1 else ''
    lo,hi,ev=parse_employee_range(text)
    jobs=None
    for pat in [r'(\d+)\s+aktuelle offene Jobs',r'Aktuelle Jobs\s*(\d+)',r'(\d+)\s+Jobs\b']:
        m=re.search(pat,text,re.I)
        if m:
            try: jobs=int(m.group(1)); break
            except: pass
    return {'profile_name':pname,'emp_min':lo,'emp_max':hi,'employee_evidence':ev,'jobs':jobs,'text':text[:20000]}

with open(INFILE,encoding='utf-8-sig',newline='') as f: raw=list(csv.DictReader(f))
agg={}
for r in raw:
    n=clean(r['company_name']); g=agg.setdefault(n,{'company_name':n,'wko_rows':0,'states':set(),'places':set()})
    g['wko_rows']+=1; g['states'].add(r['bundesland']);
    if r.get('place'): g['places'].add(r['place'])
companies=list(agg.values())
for g in companies:
    g['states']='; '.join(sorted(g['states'])); g['places']=' | '.join(sorted(g['places']))

sess=requests.Session()
urls=fetch_sitemap_urls(sess,SITEMAP)
firm_urls=[u for u in urls if '/f/' in u]
print('WKO unique names',len(companies),'karriere urls',len(firm_urls),flush=True)
# index url slugs/tokens
indexed=[]
for u in firm_urls:
    slug=urllib.parse.unquote(u.rstrip('/').split('/f/',1)[-1]).replace('-',' ')
    indexed.append((u,ascii_norm(slug),token_set(slug)))

matches=[]
for idx,c in enumerate(companies,1):
    cn=c['company_name']; cnorm=ascii_norm(cn); ct=token_set(cn)
    cands=[]
    for u,snorm,st in indexed:
        inter=len(ct & st)
        if ct and inter==0: continue
        # cheap token gate, then fuzzy
        score=max(fuzz.token_set_ratio(cnorm,snorm),fuzz.ratio(cnorm,snorm))
        if score>=68 or (inter>=2 and score>=55): cands.append((score,u))
    cands=sorted(cands,reverse=True)[:5]
    best=None
    for score,u in cands:
        try:
            p=parse_profile(sess,u)
        except Exception as e:
            continue
        if not p: continue
        confirm=max(fuzz.token_set_ratio(cnorm,ascii_norm(p['profile_name'])),fuzz.ratio(cnorm,ascii_norm(p['profile_name'])))
        # Require strong name agreement; location helps weak names
        loc_hit=any(citypart.lower() in p['text'].lower() for citypart in re.findall(r'\b\d{4}\s+([^|;]+)',c['places'])[:4])
        if confirm>=72 or (confirm>=60 and loc_hit):
            cand=(confirm,score,u,p,loc_hit)
            if best is None or cand[0]>best[0]: best=cand
        time.sleep(0.03)
    rec={**c,'karriere_url':'','karriere_name':'','karriere_match_score':'','karriere_emp_min':'','karriere_emp_max':'','karriere_employee_evidence':'','karriere_jobs':'','karriere_location_hit':''}
    if best:
        confirm,score,u,p,loc_hit=best
        rec.update({'karriere_url':u,'karriere_name':p['profile_name'],'karriere_match_score':round(confirm,1),'karriere_emp_min':p['emp_min'] if p['emp_min'] is not None else '', 'karriere_emp_max':p['emp_max'] if p['emp_max'] is not None else '', 'karriere_employee_evidence':p['employee_evidence'], 'karriere_jobs':p['jobs'] if p['jobs'] is not None else '', 'karriere_location_hit':loc_hit})
    matches.append(rec)
    if idx%100==0: print('processed',idx,'matches',sum(bool(x['karriere_url']) for x in matches),flush=True)

fields=list(matches[0].keys())
with open(os.path.join(OUTDIR,'karriere_matches.csv'),'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(matches)
summary={'wko_unique_names':len(companies),'karriere_sitemap_urls':len(firm_urls),'matched_profiles':sum(bool(x['karriere_url']) for x in matches),'with_employee_range':sum(x['karriere_emp_min']!='' for x in matches)}
with open(os.path.join(OUTDIR,'karriere_summary.json'),'w',encoding='utf-8') as f: json.dump(summary,f,ensure_ascii=False,indent=2)
print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
