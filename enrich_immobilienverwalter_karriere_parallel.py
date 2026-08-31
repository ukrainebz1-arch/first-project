import csv,os,re,json,unicodedata,urllib.parse,concurrent.futures,threading
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
INFILE=os.environ.get('WKO_CSV','iv_size_input/iv_size_input.csv');OUT=os.environ.get('OUTDIR','iv_karriere_parallel');os.makedirs(OUT,exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36';SM='https://www.karriere.at/static/sitemaps/sitemap-firmen-https.xml'
def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def norm(s):
 s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower().replace('&',' und ');s=re.sub(r'\b(gesellschaft mit beschrankter haftung|gesellschaft m b h|ges m b h|gesmbh|gmbh|mbh|ag|kg|og|e u|eu|co)\b',' ',s);return clean(re.sub(r'[^a-z0-9]+',' ',s))
STOP={'immobilien','immobilienverwaltung','hausverwaltung','liegenschaftsverwaltung','verwaltung','real','realitaten','realitaeten','management','service','services','austria','osterreich','und','co','gesellschaft','group','gruppe'}
def toks(s):return {x for x in norm(s).split() if len(x)>=3 and x not in STOP}
def getxml(u,d=0):
 r=requests.get(u,headers={'User-Agent':UA},timeout=60);r.raise_for_status();z=re.findall(r'<loc>(.*?)</loc>',r.text,re.I|re.S)
 if d<2 and z and sum(x.lower().endswith('.xml') for x in z)>=max(1,len(z)//2):
  out=[]
  for x in z:
   if x.lower().endswith('.xml'):
    try:out+=getxml(x,d+1)
    except:pass
  return out
 return z
def erange(t):
 t=clean(t)
 m=re.search(r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*[-–]\s*([0-9\.]+)',t,re.I)
 if m:return int(m.group(1).replace('.','')),int(m.group(2).replace('.','')),m.group(0)
 m=re.search(r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*(?:\+|plus)',t,re.I)
 if m:return int(m.group(1).replace('.','')),None,m.group(0)
 m=re.search(r'\b(?:rund|ca\.?|circa|etwa|über|mehr als)?\s*([0-9]{2,5})\s+Mitarbeiter(?:innen|Innen|:innen|\*innen)?\b',t,re.I)
 return (int(m.group(1)),int(m.group(1)),m.group(0)) if m else (None,None,'')
def fetch_profile(u):
 try:
  r=requests.get(u,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9'},timeout=25)
  if r.status_code!=200:return u,None
  s=BeautifulSoup(r.text,'html.parser');text=clean(s.get_text(' ',strip=True));h=s.find('h1');name=clean(h.get_text(' ',strip=True)) if h else '';lo,hi,ev=erange(text);jobs=''
  for p in [r'(\d+)\s+aktuelle offene Jobs',r'Aktuelle Jobs\s*(\d+)',r'(\d+)\s+Jobs\b']:
   m=re.search(p,text,re.I)
   if m:jobs=int(m.group(1));break
  return u,{'name':name,'lo':lo,'hi':hi,'ev':ev,'jobs':jobs,'text':text[:18000]}
 except:return u,None
with open(INFILE,encoding='utf-8-sig',newline='') as f:raw=list(csv.DictReader(f))
agg={}
for r in raw:
 n=clean(r['company_name']);g=agg.setdefault(n,{'company_name':n,'wko_rows':0,'states':set(),'places':set()});g['wko_rows']+=1;g['states'].add(r.get('bundesland',''));g['places'].add(r.get('place','')) if r.get('place') else None
cs=list(agg.values())
for g in cs:g['states']='; '.join(sorted(x for x in g['states'] if x));g['places']=' | '.join(sorted(x for x in g['places'] if x))
urls=[u for u in getxml(SM) if '/f/' in u];idx=[];inv=defaultdict(set)
for i,u in enumerate(urls):
 slug=urllib.parse.unquote(u.rstrip('/').split('/f/',1)[-1]).replace('-',' ');sn=norm(slug);st=toks(slug);idx.append((u,sn,st));
 for t in st:inv[t].add(i)
short={};need=set()
for c in cs:
 cn=norm(c['company_name']);ct=toks(c['company_name']);cand=set()
 for t in ct:cand|=inv.get(t,set())
 if not cand:
  first=cn.split()[0] if cn.split() else '';cand={i for i,(_,sn,_) in enumerate(idx) if first and first in sn}
 scored=[]
 for i in cand:
  u,sn,st=idx[i];sc=max(fuzz.token_set_ratio(cn,sn),fuzz.ratio(cn,sn));inter=len(ct&st)
  if sc>=70 or (inter>=2 and sc>=58):scored.append((sc,u))
 scored=sorted(scored,reverse=True)[:2];short[c['company_name']]=scored;need.update(u for _,u in scored)
print('companies',len(cs),'sitemap_profiles',len(urls),'unique_candidate_profiles',len(need),flush=True)
profiles={}
with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
 for i,(u,p) in enumerate(ex.map(fetch_profile,sorted(need)),1):
  profiles[u]=p
  if i%200==0:print('fetched',i,'/',len(need),flush=True)
out=[]
for c in cs:
 cn=norm(c['company_name']);best=None
 for sc,u in short[c['company_name']]:
  p=profiles.get(u)
  if not p:continue
  conf=max(fuzz.token_set_ratio(cn,norm(p['name'])),fuzz.ratio(cn,norm(p['name'])));cities=re.findall(r'\b\d{4}\s+([^|;]+)',c['places']);lh=any(x.strip().casefold() in p['text'].casefold() for x in cities[:8] if x.strip())
  if conf>=74 or (conf>=62 and lh):
   z=(conf,u,p,lh)
   if best is None or z[0]>best[0]:best=z
 rec={**c,'karriere_url':'','karriere_name':'','karriere_match_score':'','karriere_emp_min':'','karriere_emp_max':'','karriere_employee_evidence':'','karriere_jobs':'','karriere_location_hit':''}
 if best:
  conf,u,p,lh=best;rec.update({'karriere_url':u,'karriere_name':p['name'],'karriere_match_score':round(conf,1),'karriere_emp_min':p['lo'] if p['lo'] is not None else '','karriere_emp_max':p['hi'] if p['hi'] is not None else '','karriere_employee_evidence':p['ev'],'karriere_jobs':p['jobs'],'karriere_location_hit':lh})
 out.append(rec)
fields=list(out[0]);
with open(os.path.join(OUT,'karriere_matches.csv'),'w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
summary={'wko_unique_names':len(cs),'karriere_sitemap_urls':len(urls),'candidate_profiles_fetched':len(need),'matched_profiles':sum(bool(x['karriere_url']) for x in out),'with_employee_range':sum(x['karriere_emp_min']!='' for x in out)}
with open(os.path.join(OUT,'karriere_summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
