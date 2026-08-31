#!/usr/bin/env python3
import argparse,csv,json,os


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--output-dir',required=True)
    ap.add_argument('--chunk-size',type=int,default=10)
    a=ap.parse_args()
    os.makedirs(a.output_dir,exist_ok=True)
    with open(a.input,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    rows.sort(key=lambda r:(0 if r.get('stage3_scope')=='MAIN' else 1,int(r.get('no') or 999999)))
    if len(rows)!=99:
        raise SystemExit(f'Expected 99 Stage-3 rows, got {len(rows)}')
    missing=[r.get('no','') for r in rows if not (r.get('primary_dm') or '').strip()]
    if missing:
        raise SystemExit('Missing primary_dm: '+','.join(missing))
    fields=list(rows[0].keys())
    chunks=[]
    for start in range(0,len(rows),a.chunk_size):
        c=rows[start:start+a.chunk_size]
        lo=int(c[0]['no']); hi=int(c[-1]['no'])
        # Stable names requested for persistent checkpoints.
        name=f'chunk_{lo:03d}_{hi:03d}.csv'
        with open(os.path.join(a.output_dir,name),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(c)
        chunks.append({'file':name,'rows':len(c),'nos':[r['no'] for r in c],'scope_counts':{'MAIN':sum(r.get('stage3_scope')=='MAIN' for r in c),'SECONDARY':sum(r.get('stage3_scope')=='SECONDARY' for r in c)}})
    with open(os.path.join(a.output_dir,'targets.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    manifest={'source':'data/hausverwaltung/stage3_owners/stage3_master_99.csv','expected':99,'rows':len(rows),'main':sum(r.get('stage3_scope')=='MAIN' for r in rows),'secondary':sum(r.get('stage3_scope')=='SECONDARY' for r in rows),'missing_primary_dm':len(missing),'chunk_size':a.chunk_size,'chunks':chunks}
    with open(os.path.join(a.output_dir,'manifest.json'),'w',encoding='utf-8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
