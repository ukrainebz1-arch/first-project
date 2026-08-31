import csv, glob, json, os
from datetime import datetime, timezone

PARTS_DIR=os.environ.get('PARTS_DIR','parts')
BASE_CSV=os.environ.get('BASE_CSV','data/wko-immobilienverwalter/wko_immobilienverwalter_austria_raw_by_state.csv')
OUT_DIR=os.environ.get('OUT_DIR','data/hausverwaltung/coverage')
os.makedirs(OUT_DIR,exist_ok=True)
STATES={'burgenland','kärnten','niederösterreich','oberösterreich','salzburg','steiermark','tirol','vorarlberg','wien'}

def read_csv(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_csv(p,rows,fields):
    with open(p,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

summaries=[]
for p in glob.glob(os.path.join(PARTS_DIR,'**','*_summary.json'),recursive=True):
    with open(p,encoding='utf-8') as f:summaries.append(json.load(f))
found={s['state'] for s in summaries if s.get('query_term')=='hausverwalter'}
invalid=[s for s in summaries if int(s.get('collected',-1))!=int(s.get('wko_live_total',-2))]
if found!=STATES or len(summaries)!=9 or invalid:
    raise RuntimeError(f'coverage validation failed summaries={len(summaries)} found={sorted(found)} invalid={invalid}')

rows=[]
for p in glob.glob(os.path.join(PARTS_DIR,'**','*_part.csv'),recursive=True):rows.extend(read_csv(p))
expected=sum(int(s['wko_live_total']) for s in summaries)
if len(rows)!=expected:raise RuntimeError(f'raw mismatch {len(rows)} != {expected}')

base=read_csv(BASE_CSV)
base_ids={r.get('firmaid','') for r in base if r.get('firmaid')}
seen={}
for r in rows:seen[r['firmaid']]=r
missing=[r for fid,r in seen.items() if fid not in base_ids]
missing.sort(key=lambda r:(r.get('company_name','').casefold(),r.get('state','')))

raw_fields=['firmaid','company_name','business_label','street','postal_code','city','address','phones','email','all_emails','website','all_websites','state','query_term','profile_url']
write_csv(os.path.join(OUT_DIR,'wko_hausverwalter_austria_raw.csv'),rows,raw_fields)
write_csv(os.path.join(OUT_DIR,'wko_hausverwalter_missing_vs_immobilienverwalter.csv'),missing,raw_fields)

summary={
 'generated_at_utc':datetime.now(timezone.utc).isoformat(),
 'query':'hausverwalter',
 'validated_states':9,
 'raw_rows':len(rows),
 'sum_live_wko_counts':expected,
 'unique_hausverwalter_firmaids':len(seen),
 'base_immobilienverwalter_firmaids':len(base_ids),
 'missing_firmaids_vs_base':len(missing),
 'states':sorted(summaries,key=lambda x:x['state']),
 'note':'Coverage audit only. Missing Hausverwalter rows must be reviewed before adding to the canonical market universe.'
}
with open(os.path.join(OUT_DIR,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False,indent=2))
