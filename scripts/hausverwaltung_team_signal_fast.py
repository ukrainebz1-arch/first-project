import csv,re,concurrent.futures,urllib.parse,requests
from bs4 import BeautifulSoup
SRC='data/hausverwaltung/size_strict_v2/size_screening_strict_v2.csv'
UA={'User-Agent':'Mozilla/5.0'}
GEN={'office','info','kontakt','contact','hausverwaltung','verwaltung','immobilien','service','support','mail','datenschutz','karriere','jobs','bewerbung','buchhaltung','rechnung'}
PATHS=['','team','ueber-uns','uber-uns','unternehmen','kontakt']
def get(u):
 try:
  r=requests.get(u,headers=UA,timeout=5,allow_redirects=True)
  if r.status_code==200 and 'html' in r.headers.get('content-type','').lower(): return r.url,r.text[:1200000]
 except: pass
 return u,''
def score_row(r):
 base=(r.get('website') or '').strip()
 if not base:return None
 if not re.match(r'^https?://',base): base='https://'+base.lstrip('/')
 seen=[]; texts=[]
 for p in PATHS:
  u=base if not p else urllib.parse.urljoin(base.rstrip('/')+'/',p+'/')
  ru,t=get(u)
  if t and ru not in seen:seen.append(ru);texts.append(t)
 blob=' '.join(texts)
 em=set()
 for e in re.findall(r'[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}',blob):
  e=e.lower(); local=e.split('@')[0]
  if local not in GEN and len(local)>2: em.add(e)
 soup=BeautifulSoup(blob,'html.parser'); names=set()
 bad=('team','kontakt','unternehmen','verwaltung','immobilien','buchhaltung','technik','assistenz','geschäftsführung','geschaftsfuhrung','leitung','sekretariat','service','karriere','über uns','ueber uns')
 for tag in soup.find_all(['h2','h3','h4','h5','strong']):
  t=' '.join(tag.get_text(' ',strip=True).split())
  if 5<=len(t)<=55 and not any(x in t.lower() for x in bad) and not re.search(r'\d',t):
   ws=t.split()
   if 2<=len(ws)<=5 and sum(w[:1].isupper() for w in ws)>=2:names.add(t)
 signal=3*len(em)+min(len(names),25)
 return {'company_name':r['company_name'],'website':r.get('website',''),'personal_emails':len(em),'name_headings':len(names),'signal':signal,'urls':' | '.join(seen),'emails':' | '.join(sorted(em))}
def main():
 rows=list(csv.DictReader(open(SRC,encoding='utf-8-sig',newline='')))
 todo=[r for r in rows if r.get('size_class_strict_v2')=='U_NOT_PROVEN' and r.get('website')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex: out=[x for x in ex.map(score_row,todo) if x]
 out.sort(key=lambda x:(-x['signal'],-x['personal_emails'],-x['name_headings'],x['company_name']))
 fields=['company_name','website','personal_emails','name_headings','signal','urls','emails']
 with open('data/hausverwaltung/size_agent_first/team_signal_fast_all.csv','w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
 esc=[x for x in out if x['personal_emails']>=5 or x['name_headings']>=10 or x['signal']>=18]
 with open('data/hausverwaltung/size_agent_first/team_signal_fast_candidates.tsv','w',encoding='utf-8') as f:
  f.write('\t'.join(fields)+'\n')
  for x in esc:f.write('\t'.join(str(x[k]).replace('\t',' ').replace('\n',' ') for k in fields)+'\n')
 print('TODO',len(todo),'ALL',len(out),'ESCALATED',len(esc))
if __name__=='__main__':main()
