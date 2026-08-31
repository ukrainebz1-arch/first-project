#!/usr/bin/env python3
import argparse,csv,json,os
from collections import Counter

def read(p):
    if not os.path.exists(p):return []
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--confirmed',required=True);ap.add_argument('--likely',required=True);ap.add_argument('--output-dir',required=True);ap.add_argument('--chunks',type=int,default=16);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    rows=[];seen=set()
    for gate,path in [('CONFIRMED_20_PLUS',a.confirmed),('LIKELY_20_PLUS',a.likely)]:
        for r in read(path):
            k=r['group_key']
            if k in seen:continue
            seen.add(k);rr=dict(r);rr['size_gate']=gate;rows.append(rr)
    # Confirmed first, then likely; spread each group round-robin.
    rows.sort(key=lambda r:(0 if r['size_gate'].startswith('CONFIRMED') else 1,r.get('group_name','').lower()))
    chunks=[[] for _ in range(a.chunks)]
    for i,r in enumerate(rows):chunks[i%a.chunks].append(r)
    fields=list(rows[0].keys()) if rows else []
    with open(os.path.join(a.output_dir,'targets_universe.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    for i,c in enumerate(chunks):
        with open(os.path.join(a.output_dir,f'chunk_{i:02d}.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(c)
    m={'targets':len(rows),'confirmed':sum(r['size_gate'].startswith('CONFIRMED') for r in rows),'likely':sum(r['size_gate']=='LIKELY_20_PLUS' for r in rows),'chunks':a.chunks,'chunk_sizes':[len(x) for x in chunks]}
    json.dump(m,open(os.path.join(a.output_dir,'manifest.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(m,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
