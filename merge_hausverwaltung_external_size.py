import csv,glob,json,os,re,urllib.parse
from collections import defaultdict
from datetime import datetime,timezone

STRICT=os.environ.get('STRICT_CSV','data/hausverwaltung/size_strict_v2/size_screening_strict_v2.csv')
CHUNK_GLOB=os.environ.get('CHUNK_GLOB','data/hausverwaltung/size_external/chunks/*_evidence.csv')
OUTDIR=os.environ.get('OUTDIR','data/hausverwaltung/size_external')
os.makedirs(OUTDIR,exist_ok=True)

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def domain(u):
    try:
        d=urllib.parse.urlparse(u).netloc.lower().split(':')[0]
        return d[4:] if d.startswith('www.') else d
    except:return ''
def website_domains(r):
    out=set()
    for field in ('website','all_websites'):
        for u in (r.get(field) or '').split('|'):
            d=domain(u.strip())
            if d:out.add(d)
    return out
def intval(v):
    try:return int(float(v))
    except:return None

def quality(ev,official_domains):
    d=domain(ev.get('source_url',''));m=ev.get('method','');rel=intval(ev.get('relevance_score')) or 0
    if d in official_domains:return 'HIGH_OFFICIAL'
    if m in {'SIZE_CAREER','SIZE_BUSINESS_SOCIAL_SNIPPET','SIZE_REPORT'} and rel>=50:return 'HIGH_INDEXED'
    if m=='SIZE_INDEXED_PDF' and rel>=67:return 'HIGH_PDF'
    if rel>=67:return 'MEDIUM_RELEVANT'
    return 'LOW_REVIEW'

strict=read(STRICT);by_no={str(i):r for i,r in enumerate(sorted(strict,key=lambda x:(x['company_name'].casefold(),x.get('firmaids',''))),1)}
evidence=[]
for p in sorted(glob.glob(CHUNK_GLOB)):
    try:evidence.extend(read(p))
    except Exception:pass
by=defaultdict(list)
for e in evidence:by[str(e.get('no',''))].append(e)
rows=[]
for no,r in by_no.items():
    official=website_domains(r);evs=[]
    for e in by.get(no,[]):
        lo=intval(e.get('employee_min'));hi=intval(e.get('employee_max'))
        if lo is None or hi is None or hi<20:continue
        ee=dict(e);ee['evidence_quality']=quality(ee,official);evs.append(ee)
    # unique source/value evidence
    uniq=[];seen=set()
    for e in evs:
        k=(e.get('source_url','').split('#')[0],e.get('employee_min'),e.get('employee_max'),e.get('claim_context',''))
        if k not in seen:seen.add(k);uniq.append(e)
    high=[e for e in uniq if e['evidence_quality'].startswith('HIGH')]
    medium=[e for e in uniq if e['evidence_quality']=='MEDIUM_RELEVANT']
    direct_high=[e for e in high if e.get('group_context')!='yes']
    group_high=[e for e in high if e.get('group_context')=='yes']
    independent_high=len({domain(e.get('source_url','')) or e.get('source_url','') for e in high})
    candidate=''
    if any((intval(e.get('employee_min')) or 0)>=31 for e in direct_high):candidate='EXT_A_CANDIDATE'
    elif any((intval(e.get('employee_max')) or 0)>=31 for e in group_high):candidate='EXT_B_GROUP_CANDIDATE'
    elif any(20<=(intval(e.get('employee_max')) or 0)<=30 or 20<=(intval(e.get('employee_min')) or 0)<=30 for e in direct_high):candidate='EXT_C_BORDERLINE_CANDIDATE'
    elif medium:candidate='EXT_REVIEW'
    rows.append({**r,
      'external_candidate':candidate,
      'external_20plus_evidence_count':len(uniq),'external_high_evidence_count':len(high),'external_independent_high_domains':independent_high,
      'external_evidence':' || '.join(f"{e['evidence_quality']}|{e.get('employee_min')}|{e.get('employee_max')}|{e.get('group_context')}|{e.get('method')}|{e.get('source_url')}|{e.get('claim_context','')[:600]}" for e in uniq[:16])})

order={'EXT_A_CANDIDATE':0,'EXT_B_GROUP_CANDIDATE':1,'EXT_C_BORDERLINE_CANDIDATE':2,'EXT_REVIEW':3,'':4}
rows.sort(key=lambda r:(order.get(r['external_candidate'],9),r['company_name'].casefold()))
fields=list(rows[0]) if rows else []
with open(os.path.join(OUTDIR,'external_size_candidates.csv'),'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
queue=[r for r in rows if r['external_candidate']]
with open(os.path.join(OUTDIR,'external_manual_review_queue.csv'),'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(queue)
counts=defaultdict(int)
for r in rows:counts[r['external_candidate'] or 'NO_20PLUS_SIGNAL']+=1
summary={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'chunk_files':len(glob.glob(CHUNK_GLOB)),'raw_evidence_rows':len(evidence),'candidate_counts':dict(counts),'review_queue':len(queue),'note':'External results are candidates until source-level validation; strict official/karriere/WKO evidence remains authoritative.'}
with open(os.path.join(OUTDIR,'external_summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False,indent=2))
