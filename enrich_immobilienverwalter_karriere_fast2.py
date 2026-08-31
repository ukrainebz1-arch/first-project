import csv,os,re,json,time,unicodedata,urllib.parse
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
INFILE=os.environ.get('WKO_CSV','iv_size_input/iv_size_input.csv'); OUTDIR=os.environ.get('OUTDIR','iv_karriere_fast2'); os.makedirs(OUTDIR,exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'; SITEMAP='https://www.karriere.at/static/sitemaps/sitemap-firmen-https.xml'
def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def norm(s):
 s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower().replace('&',' und '); s=re.sub(r'\b(gesellschaft mit beschrankter haftung|gesellschaft m b h|ges m b h|gesmbh|gmbh|mbh|ag|kg|og|e u|eu|co)\b',' ',s); return clean(re.sub(r'[^a-z0-9]+',' ',s))
STOP={'immobilien','immobilienverwaltung','hausverwaltung','liegenschaftsverwaltung','verwaltung','real','realitaten','realitaeten','management','service','services','austria','osterreich','und','co','gesellschaft','group','gruppe'}
def toks(s):return {x for x in norm(s).split() if len(x)>=3 and x not in STOP}
def locs(x):return re.findall(r'<loc>(.*?)</loc>',x,re.I|re.S)
def sitemap(sess,u,depth=0):
 r=sess.get(u,headers={'User-Agent':UA},timeout=60); r.raise_for_status(); z=locs(r.text)
 if depth<2 and z and all(v.lower().endswith('.xml') for v in z[:min(3,len(z))]):
  out=[]
  for v in z:
   try:out+=sitemap(sess,v,depth+1)
   except Exception:pass
  return out
 return z
def erange(t):
 t=clean(t)
 for pat,kind in [(r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*[-–]\s*([0-9\.]+)','range'),(r'(?:Anzahl der Mitarbeiter\*?innen|Mitarbeiter\*?innen|Mitarbeiter:innen|Mitarbeiter)\s*[:\n ]+([0-9\.]+)\s*(?:\+|plus)','plus')]:
  m=re.search(pat,t,re.I)
  if m:
   lo=int(m.group(1).replace('.','')); hi=int(m.group(2).replace('.','')) if kind=='range' else None; return lo,hi,m.group(0)
 m=re.search(r'\b(?:rund|ca\.?|circa|etwa|über|mehr als)?\s*([0-9]{2,5})\s+Mitarbeiter(?:innen|Innen|:innen|\*innen)?\b',t,re.I)
 if m:return int(m.group(1)),int(m.group(1)),m.group(0)
 return None,None,''
def profile(sess,u,cache):
 if u in cache:return cache[u]
 try:r=sess.get(u,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9'},timeout=20)
 except Exception:cache[u]=None;return None
 if r.status_code!=200:cache[u]=None;return None
 s=BeautifulSoup(r.text,'html.parser'); text=clean(s.get_text(' ',strip=True)); h=s.find('h1'); name=clean(h.get_text(' ',strip=True)) if h else ''; lo,hi,ev=erange(text); jobs=''
 for p in [r'(\d+)\s+aktuelle offene Jobs',r'Aktuelle Jobs\s*(\d+)',r'(\d+)\s+Jobs\b']:
  m=re.search(p,text,re.I)
  if m:jobs=int(m.group(1));break
 cache[u]={'name':name,'lo':lo,'hi':hi,'ev':ev,'jobs':jobs,'text':text[:15000]};return cache[u]
with open(INFILE,encoding='utf-8-sig',newline='') as f:raw=list(csv.DictReader(f))
agg={}
for r in raw:
 n=clean(r['company_name']); g=agg.setdefault(n,{'company_name':n,'wko_rows':0,'states':set(),'places':set()});g['wko_rows']+=1;g['states'].add(r.get('bundesland',''));g['places'].add(r.get('place','')) if r.get('place') else None
companies=list(agg.values())
for g in companies:g['states']='; '.join(sorted(x for x in g['states'] if x));g['places']=' | '.join(sorted(x for x in g['places'] if x))
s=requests.Session(); urls=[u for u in sitemap(s,SITEMAP) if '/f/' in u]; print('companies',len(companies),'profiles',len(urls),flush=True)
idx=[];inv=defaultdict(set)
for i,u in enumerate(urls):
 slug=urllib.parse.unquote(u.rstrip('/').split('/f/',1)[-1]).replace('-',' '); sn=norm(slug); st=toks(slug);idx.append((u,sn,st)); [inv[t].add(i) for t in st]
cache={};out=[]
for num,c in enumerate(companies,1):
 cn=norm(c['company_name']);ct=toks(c['company_name']);cand=set()
 for t in ct:cand|=inv.get(t,set())
 if not cand:
  first=cn.split()[0] if cn.split() else '';cand={i for i,(_,sn,_) in enumerate(idx) if first and first in sn}
 scored=[]
 for i in cand:
  u,sn,st=idx[i];sc=max(fuzz.token_set_ratio(cn,sn),fuzz.ratio(cn,sn)); inter=len(ct&st)
  if sc>=70 or (inter>=2 and sc>=58):scored.append((sc,u))
 scored.sort(reverse=True); rec={**c,'karriere_url':'','karriere_name':'','karriere_match_score':'','karriere_emp_min':'','karriere_emp_max':'','karriere_employee_evidence':'','karriere_jobs':'','karriere_location_hit':''}; best=None
 for sc,u in scored[:2]:
  p=profile(s,u,cache)
  if not p:continue
  conf=max(fuzz.token_set_ratio(cn,norm(p['name'])),fuzz.ratio(cn,norm(p['name']))); cities=re.findall(r'\b\d{4}\s+([^|;]+)',c['places']);lh=any(x.strip().casefold() in p['text'].casefold() for x in cities[:8] if x.strip())
  if conf>=74 or (conf>=62 and lh):
   z=(conf,u,p,lh)
   if best is None or z[0]>best[0]:best=z
 if best:
  conf,u,p,lh=best; rec.update({'karriere_url':u,'karriere_name':p['name'],'karriere_match_score':round(conf,1),'karriere_emp_min':p['lo'] if p['lo'] is not None else '','karriere_emp_max':p['hi'] if p['hi'] is not None else '','karriere_employee_evidence':p['ev'],'karriere_jobs':p['jobs'],'karriere_location_hit':lh})
 out.append(rec)
 if num%100==0:print('processed',num,'matched',sum(bool(x['karriere_url']) for x in out),'ranges',sum(x['karriere_emp_min']!='' for x in out),'http_profiles',len(cache),flush=True)
fields=list(out[0]);
with open(os.path.join(OUTDIR,'karriere_matches.csv'),'w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
summary={'wko_unique_names':len(companies),'karriere_sitemap_urls':len(urls),'matched_profiles':sum(bool(x['karriere_url']) for x in out),'with_employee_range':sum(x['karriere_emp_min']!='' for x in out),'unique_profiles_fetched':len(cache)}
with open(os.path.join(OUTDIR,'karriere_summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
