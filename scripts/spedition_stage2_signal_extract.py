#!/usr/bin/env python3
import csv,json,re,unicodedata
from pathlib import Path
from urllib.parse import urlparse

INPUT=Path('data/spedition/agent_recheck/search_evidence/all_search_results.jsonl')
OUTDIR=Path('data/spedition/stage2_agent_final')
EMP_WORDS=('mitarbeiter','mitarbeiterinnen','beschäftigte','beschaeftigte','arbeitnehmer','employees','employee','mitarbeitenden','personal')
AU_WORDS=('österreich','oesterreich','austria','austrian')
HIGH_DOMAINS={
 'firmen.wko.at':100,'wko.at':95,'evi.gv.at':100,'justizonline.gv.at':100,
 'linkedin.com':58,'karriere.at':52,'herold.at':48,'firmenabc.at':47,'compass.at':47,'kompass.com':44,
}

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def anorm(s):
 s=unicodedata.normalize('NFKD',clean(s)).encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]+',' ',s).strip()
def host(u):
 try:
  h=(urlparse(u).hostname or '').lower(); return h[4:] if h.startswith('www.') else h
 except:return ''
def company_tokens(n):
 stop={'gmbh','gesmbh','gesellschaft','mbh','kg','ag','og','eu','co','und','spedition','speditions','logistik','logistics','transport','transporte','internationale','international','austria','osterreich'}
 return [x for x in anorm(n).split() if len(x)>2 and x not in stop]
def source_score(u):
 h=host(u)
 for d,s in HIGH_DOMAINS.items():
  if h==d or h.endswith('.'+d): return s
 return 35

def relevance(name,text):
 t=anorm(text); toks=company_tokens(name)
 if not toks:return 0,0
 m=sum(1 for x in toks if x in t); return m/max(1,len(toks)), int(anorm(name) in t)

def numeric_contexts(text):
 # Evidence extraction only; these are not final verdicts.
 out=[]
 for m in re.finditer(r'(?i)(.{0,85}(?:mitarbeiter(?:innen)?|besch[aä]ftigte|employees?|arbeitnehmer|personal).{0,85})',text):
  ctx=clean(m.group(1)); nums=[int(x.replace('.','')) for x in re.findall(r'\b\d{1,4}(?:\.\d{3})?\b',ctx)]
  out.append((ctx,nums))
 return out

def main():
 OUTDIR.mkdir(parents=True,exist_ok=True)
 rows=[]
 for line in INPUT.open(encoding='utf-8'):
  if not line.strip():continue
  o=json.loads(line); name=o.get('company_name',''); scored=[]
  for h in o.get('results') or []:
   title=clean(h.get('title','')); sn=clean(h.get('snippet','')); text=title+' — '+sn; low=text.lower()
   ratio,exact=relevance(name,text); emp=any(w in low for w in EMP_WORDS); au=any(w in low for w in AU_WORDS)
   contexts=numeric_contexts(text); nums=[n for _,ns in contexts for n in ns]
   s=source_score(h.get('url','')) + int(55*ratio) + 20*exact + 22*emp + 10*au + (18 if nums else 0)
   # Drop clearly unrelated results unless exact name or meaningful token overlap.
   if exact or ratio>=0.34:
    scored.append({'score':s,'source_score':source_score(h.get('url','')),'employee_keyword':int(emp),'austria_keyword':int(au),'numbers':'|'.join(map(str,nums[:8])),'url':h.get('url',''),'title':title,'snippet':sn})
  scored.sort(key=lambda x:x['score'],reverse=True)
  rec={'candidate_key':o.get('candidate_key',''),'company_name':name,'states':o.get('states',''),'places':o.get('places',''),'websites':o.get('websites',''),'wko_urls':o.get('wko_urls',''),'search_hits':len(o.get('results') or []),'relevant_hits':len(scored),'employee_keyword_hits':sum(x['employee_keyword'] for x in scored),'employee_number_hits':sum(bool(x['numbers']) for x in scored),'best_score':scored[0]['score'] if scored else 0}
  for i,x in enumerate(scored[:5],1):
   for k,v in x.items(): rec[f'evidence_{i}_{k}']=v
  rows.append(rec)
 fields=[]
 for r in rows:
  for k in r:
   if k not in fields:fields.append(k)
 with (OUTDIR/'evidence_signal_index.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 ranked=sorted(rows,key=lambda r:(int(r['employee_number_hits']),int(r['employee_keyword_hits']),int(r['best_score']),int(r['relevant_hits'])),reverse=True)
 with (OUTDIR/'agent_review_priority.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ranked)
 # Compact human/agent review file that is easy to read from GitHub.
 compact=[]
 for r in ranked[:300]:
  ev=[]
  for i in range(1,4):
   if not r.get(f'evidence_{i}_url'):continue
   sn=clean(r.get(f'evidence_{i}_snippet',''))[:360]
   ti=clean(r.get(f'evidence_{i}_title',''))[:180]
   ev.append(f"[{r.get(f'evidence_{i}_score','')}] {ti} :: {sn} :: {r.get(f'evidence_{i}_url','')}")
  compact.append({'candidate_key':r['candidate_key'],'company_name':r['company_name'],'states':r['states'],'places':r['places'],'websites':r['websites'],'employee_keyword_hits':r['employee_keyword_hits'],'employee_number_hits':r['employee_number_hits'],'best_score':r['best_score'],'evidence':' || '.join(ev)})
 cfields=list(compact[0]) if compact else []
 with (OUTDIR/'agent_review_top300.tsv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cfields,delimiter='\t');w.writeheader();w.writerows(compact)
 summary={'rows':len(rows),'with_relevant_hits':sum(bool(r['relevant_hits']) for r in rows),'with_employee_keyword_hit':sum(bool(r['employee_keyword_hits']) for r in rows),'with_employee_number_hit':sum(bool(r['employee_number_hits']) for r in rows),'top300_rows':len(compact)}
 (OUTDIR/'signal_index_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
