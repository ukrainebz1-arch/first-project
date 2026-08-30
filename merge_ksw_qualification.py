import csv,glob,os,json
INDIR=os.environ.get('INDIR','chunks');OUTDIR=os.environ.get('OUTDIR','final');os.makedirs(OUTDIR,exist_ok=True)
files=sorted(glob.glob(os.path.join(INDIR,'ksw_qualified_chunk_*.csv')))
if len(files)!=32:raise SystemExit(f'expected 32 chunks got {len(files)}')
rows=[]
for p in files:
 with open(p,encoding='utf-8-sig',newline='') as f:rows.extend(csv.DictReader(f))
rank={'CONFIRMED_30_PLUS':0,'CONFIRMED_20_29':1,'LIKELY_20_PLUS':2,'POSSIBLE_20_PLUS':3,'NO_20PLUS_EVIDENCE':4}
rows.sort(key=lambda r:(rank.get(r['qualification_status'],9),-int(float(r.get('employee_low') or 0)),r['group_name'].lower()))

def write(name,sel):
 if not sel:return
 with open(os.path.join(OUTDIR,name),'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(sel[0].keys()));w.writeheader();w.writerows(sel)
write('ksw_all_groups_qualified.csv',rows)
confirmed30=[r for r in rows if r['qualification_status']=='CONFIRMED_30_PLUS']
confirmed20=[r for r in rows if r['qualification_status'] in ('CONFIRMED_30_PLUS','CONFIRMED_20_29')]
review=[r for r in rows if r['qualification_status'] in ('CONFIRMED_30_PLUS','CONFIRMED_20_29','LIKELY_20_PLUS','POSSIBLE_20_PLUS')]
write('ksw_confirmed_30plus.csv',confirmed30);write('ksw_confirmed_20plus.csv',confirmed20);write('ksw_manual_review_candidates.csv',review)
summary={'all_groups':len(rows),'confirmed_30plus':len(confirmed30),'confirmed_20plus':len(confirmed20),'manual_review_candidates':len(review)}
with open(os.path.join(OUTDIR,'summary.json'),'w') as f:json.dump(summary,f,indent=2)
print(json.dumps(summary,indent=2))
