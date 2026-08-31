#!/usr/bin/env python3
import csv,json,re,sys,unicodedata
from pathlib import Path
from urllib.parse import urlparse

INPUT=Path('data/spedition/agent_recheck/search_evidence/all_search_results.jsonl')
OUTDIR=Path('data/spedition/stage2_agent_final')

HIGH_DOMAINS={
 'wko.at':100,'firmen.wko.at':100,'justizonline.gv.at':100,'evi.gv.at':100,
 'linkedin.com':55,'karriere.at':50,'herold.at':45,'firmenabc.at':45,'compass.at':45,'kompass.com':42,
}
OFFICIAL_HINTS=('unternehmen','company','group','logistik','logistics','spedition','transport','cargo','freight','rail','post','hafen')
EMP_WORDS=r'(?:mitarbeiter(?:innen)?|besch[aä]ftigte|arbeitnehmer|employees?|persons?|personal|mitarbeitenden)'
NUM=r'(?:\d{1,3}(?:[ .]\d{3})*|\d{1,4})'
PATTERNS=[
 re.compile(rf'(?P<a>{NUM})\s*(?:-|–|bis|to)\s*(?P<b>{NUM})\s*{EMP_WORDS}',re.I),
 re.compile(rf'{EMP_WORDS}\s*(?P<a>{NUM})\s*(?:-|–|bis|to)\s*(?P<b>{NUM})',re.I),
 re.compile(rf'(?:rund|ca\.?|circa|etwa|über|mehr als|mehr als rund|approximately|about|around|over)?\s*(?P<a>{NUM})\+?\s*{EMP_WORDS}',re.I),
 re.compile(rf'{EMP_WORDS}\s*(?:von|:)?\s*(?:rund|ca\.?|circa|etwa|über|mehr als|approximately|about|around|over)?\s*(?P<a>{NUM})\+?',re.I),
]
BANDS=re.compile(r'\b(1\s*[-–]\s*10|11\s*[-–]\s*20|11\s*[-–]\s*30|20\s*[-–]\s*30|21\s*[-–]\s*50|31\s*[-–]\s*50|51\s*[-–]\s*100|101\s*[-–]\s*200|101\s*[-–]\s*500|201\s*[-–]\s*500|501\s*[-–]\s*1[.,]?000|1[.,]?001\s*[-–]\s*5[.,]?000)\b',re.I)

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def ascii_norm(s):
 s=unicodedata.normalize('NFKD',clean(s)).encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]+',' ',s).strip()
def tokens(name):
 stop={'gmbh','gesmbh','gesellschaft','mbh','kg','ag','og','eu','e','u','co','und','spedition','logistik','logistics','transport','transporte','internationale','international'}
 return [x for x in ascii_norm(name).split() if len(x)>2 and x not in stop]
def host(url):
 try:
  h=(urlparse(url).hostname or '').lower()
  return h[4:] if h.startswith('www.') else h
 except: return ''
def source_score(url):
 h=host(url)
 for d,s in HIGH_DOMAINS.items():
  if h==d or h.endswith('.'+d): return s
 return 65 if any(x in h for x in OFFICIAL_HINTS) else 25

def parse_int(s):
 s=re.sub(r'[^0-9]','',s or '')
 try:return int(s)
 except:return None

def emp_signals(text):
 out=[]
 for p in PATTERNS:
  for m in p.finditer(text):
   a=parse_int(m.groupdict().get('a')); b=parse_int(m.groupdict().get('b'))
   if a is None: continue
   vals=(a,b if b is not None else a)
   if vals not in out: out.append(vals)
 for m in BANDS.finditer(text):
  z=m.group(1).replace('.','').replace(',','')
  ns=[int(x) for x in re.findall(r'\d+',z)]
  if len(ns)>=2:
   vals=(ns[0],ns[1])
   if vals not in out: out.append(vals)
 return out

def relevance(name,hit,states,places):
 text=ascii_norm((hit.get('title') or '')+' '+(hit.get('snippet') or ''))
 nt=tokens(name)
 matched=sum(1 for t in nt if t in text)
 ratio=matched/max(1,len(nt))
 loc=0
 for x in (states or '').split(';')+(places or '').replace('|',';').split(';'):
  q=ascii_norm(x)
  if q and q in text: loc=1; break
 austria=1 if ('osterreich' in text or 'austria' in text or 'austrian' in text) else 0
 exact=1 if ascii_norm(name) in text else 0
 return ratio,exact,austria,loc

def main():
 OUTDIR.mkdir(parents=True,exist_ok=True)
 rows=[]
 for line in INPUT.open(encoding='utf-8'):
  if not line.strip(): continue
  o=json.loads(line); name=o.get('company_name',''); hits=o.get('results') or []
  scored=[]; allnums=[]
  for h in hits:
   text=clean((h.get('title') or '')+' — '+(h.get('snippet') or ''))
   nums=emp_signals(text)
   ratio,exact,at,loc=relevance(name,h,o.get('states',''),o.get('places',''))
   ss=source_score(h.get('url',''))
   rel=int(40*ratio)+20*exact+12*at+8*loc
   numboost=25 if nums else 0
   score=ss+rel+numboost
   if ratio>=0.34 or exact or (at and ratio>0):
    scored.append((score,h,nums,ratio,exact,at,loc,ss))
    for a,b in nums: allnums.append((a,b,score,h.get('url',''),text))
  scored.sort(key=lambda x:x[0],reverse=True)
  allnums.sort(key=lambda x:x[2],reverse=True)
  top=scored[:5]
  max_emp=max([b for a,b,*_ in allnums],default='')
  max_rel_emp=max([b for a,b,score,*_ in allnums if score>=80],default='')
  ge31=sum(1 for a,b,score,*_ in allnums if b>=31 and score>=80)
  le30=sum(1 for a,b,score,*_ in allnums if b<=30 and score>=80)
  rec={
   'candidate_key':o.get('candidate_key',''),'company_name':name,'states':o.get('states',''),'places':o.get('places',''),'websites':o.get('websites',''),'wko_urls':o.get('wko_urls',''),
   'search_hits':len(hits),'relevant_hits':len(scored),'max_employee_signal':max_emp,'max_relevant_employee_signal':max_rel_emp,'strong_31plus_signals':ge31,'strong_30_or_below_signals':le30,
  }
  for i,x in enumerate(top,1):
   score,h,nums,ratio,exact,at,loc,ss=x
   rec[f'evidence_{i}_score']=score; rec[f'evidence_{i}_source_score']=ss; rec[f'evidence_{i}_url']=h.get('url',''); rec[f'evidence_{i}_title']=h.get('title',''); rec[f'evidence_{i}_snippet']=h.get('snippet',''); rec[f'evidence_{i}_employee_signals']=' | '.join(f'{a}-{b}' for a,b in nums)
  rows.append(rec)
 fields=[]
 for r in rows:
  for k in r:
   if k not in fields: fields.append(k)
 with (OUTDIR/'evidence_signal_index.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
 ranked=sorted(rows,key=lambda r:(int(r.get('strong_31plus_signals') or 0),int(r.get('max_relevant_employee_signal') or 0),int(r.get('relevant_hits') or 0)),reverse=True)
 with (OUTDIR/'agent_review_priority.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(ranked)
 summary={'rows':len(rows),'with_relevant_hits':sum(bool(r['relevant_hits']) for r in rows),'with_strong_31plus_signal':sum(bool(r['strong_31plus_signals']) for r in rows),'with_any_employee_signal':sum(r['max_employee_signal']!='' for r in rows)}
 (OUTDIR/'signal_index_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
