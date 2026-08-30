import csv, hashlib, os, re, time, random, unicodedata
from urllib.parse import quote_plus, urlparse
import requests
from bs4 import BeautifulSoup

CHUNK=int(os.environ.get('CHUNK','0')); CHUNKS=int(os.environ.get('CHUNKS','16'))
INPUT=os.environ.get('INPUT','input/ksw_all_groups_qualified.csv'); OUTDIR=os.environ.get('OUTDIR','out')
os.makedirs(OUTDIR,exist_ok=True)
HEAD={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/139 Safari/537.36','Accept-Language':'de-AT,de;q=0.9,en;q=0.8'}
GEN={'steuerberatung','steuerberater','wirtschaftsprufung','wirtschaftspruefung','gmbh','mbh','gesmbh','co','kg','og','holding','austria','osterreich','oesterreich','wirtschaftstreuhand','gesellschaft'}
RANGE=re.compile(r'(?i)(?:gr[oö]ße|groesse|company size|size)\s*[:\-]?\s*([\d.]+)\s*[–—-]\s*([\d.]+)\s*(?:beschäftigte|employees|mitarbeiter)')
VISIBLE=re.compile(r'(?i)(?:alle|view all|see all)?\s*([\d.]{2,6})\s+(?:mitarbeiter(?::innen)?|employees)(?:\s+anzeigen)?')
EXPLICIT=re.compile(r'(?i)(?:über|mehr als|rund|ca\.?|circa|etwa)?\s*(\d{2,4})\+?\s*(?:mitarbeiter(?::innen)?|mitarbeitende|beschäftigte|kolleg(?:en|innen))')

def norm(s):
 s=unicodedata.normalize('NFKD',s or ''); s=''.join(c for c in s if not unicodedata.combining(c)).lower(); return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',s)).strip()
def toks(name): return [x for x in norm(name).split() if len(x)>=4 and x not in GEN][:5]
def search(q):
 try:
  u='https://www.bing.com/search?q='+quote_plus(q)+'&count=10&setlang=de-AT'; r=requests.get(u,headers=HEAD,timeout=15)
  if r.status_code!=200: return []
  s=BeautifulSoup(r.text,'html.parser'); out=[]
  for li in s.select('li.b_algo')[:10]:
   a=li.select_one('h2 a'); p=li.select_one('.b_caption p')
   if a: out.append((a.get_text(' ',strip=True),a.get('href',''),p.get_text(' ',strip=True) if p else ''))
  return out
 except: return []
def matches(name,city,title,url,snip):
 hay=norm(title+' '+snip); tt=toks(name); hits=sum(1 for x in tt if x in hay); ch=norm(city)
 # LinkedIn company page and strong exact-ish name match
 return 'linkedin.com/company' in url and (hits>=min(2,max(1,len(tt))) or (hits>=1 and ch and ch in hay))
def parse(text):
 ranges=[]; vis=[]; expl=[]
 for m in RANGE.finditer(text):
  try: ranges.append((int(m.group(1).replace('.','')),int(m.group(2).replace('.',''))))
  except: pass
 for m in VISIBLE.finditer(text):
  try: vis.append(int(m.group(1).replace('.','')))
  except: pass
 for m in EXPLICIT.finditer(text):
  try:
   n=int(m.group(1));
   if 10<=n<=10000: expl.append(n)
  except: pass
 return ranges,vis,expl

def main():
 with open(INPUT,encoding='utf-8-sig',newline='') as f: rows=[r for r in csv.DictReader(f) if r.get('qualification_status')=='POSSIBLE_20_PLUS']
 sel=[r for r in rows if int(hashlib.sha1(r['group_key'].encode()).hexdigest()[:8],16)%CHUNKS==CHUNK]
 out=[]
 for i,r in enumerate(sel,1):
  name=r['group_name']; city=(r.get('cities') or '').split(' | ')[0][:60]
  qs=[f'"{name}" site:linkedin.com/company Mitarbeiter', f'"{name}" LinkedIn "51-200"', f'"{name}" LinkedIn employees {city}']
  found=[]
  for q in qs:
   for title,url,snip in search(q):
    if matches(name,city,title,url,snip): found.append((title,url,snip))
   if found: break
   time.sleep(random.uniform(.2,.5))
  text=' | '.join(t+' '+s for t,u,s in found); ranges,vis,expl=parse(text)
  low=0; high=0; status='NO_NEW_EVIDENCE'; evidence=''
  if ranges:
   a,b=max(ranges,key=lambda x:x[0]); low,high=a,b; evidence=f'LinkedIn size {a}-{b}'
   if a>=30: status='CONFIRMED_30_PLUS_LINKEDIN'
   elif a>=20: status='CONFIRMED_20_PLUS_LINKEDIN'
  vmax=max(vis+expl+[0])
  if vmax>=30 and status=='NO_NEW_EVIDENCE': low=high=vmax; status='CONFIRMED_30_PLUS_LINKEDIN'; evidence=f'LinkedIn visible/explicit {vmax}'
  elif 20<=vmax<30 and status=='NO_NEW_EVIDENCE': low=high=vmax; status='CONFIRMED_20_PLUS_LINKEDIN'; evidence=f'LinkedIn visible/explicit {vmax}'
  elif ranges and low<20 and vmax>=30: low=high=vmax; status='CONFIRMED_30_PLUS_LINKEDIN'; evidence=f'LinkedIn visible {vmax}'
  rr=dict(r); rr.update({'refine_status':status,'refine_low':low,'refine_high':high,'refine_evidence':evidence,'linkedin_urls':' | '.join(dict.fromkeys(u for t,u,s in found)),'linkedin_snippets':' | '.join(s for t,u,s in found)[:3000]}); out.append(rr)
  if i%10==0: print(CHUNK,i,len(sel),flush=True)
 fields=list(out[0].keys()) if out else list(rows[0].keys())+['refine_status','refine_low','refine_high','refine_evidence','linkedin_urls','linkedin_snippets']
 with open(f'{OUTDIR}/refine_{CHUNK:02d}.csv','w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
 print('done',CHUNK,len(out),flush=True)
if __name__=='__main__': main()
