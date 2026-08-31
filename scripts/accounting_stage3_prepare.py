#!/usr/bin/env python3
import argparse,csv,json,os

def read(p):
    if not p or not os.path.exists(p):return []
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--confirmed',required=True);ap.add_argument('--likely',required=True);ap.add_argument('--supplement');ap.add_argument('--output-dir',required=True);ap.add_argument('--chunks',type=int,default=16);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    rows=[];seen=set();source_counts={'ksw_confirmed':0,'ksw_likely':0,'wko_supplement':0}
    for gate,path,label in [('CONFIRMED_20_PLUS',a.confirmed,'ksw_confirmed'),('LIKELY_20_PLUS',a.likely,'ksw_likely')]:
        for r in read(path):
            k=r['group_key']
            if k in seen:continue
            seen.add(k);rr=dict(r);rr['size_gate']=gate;rr['market_source']='KSW';rows.append(rr);source_counts[label]+=1
    for r in read(a.supplement):
        k=r['group_key']
        if k in seen:continue
        v=r.get('agent_verdict','')
        if v not in {'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS','LIKELY_20_PLUS'}:continue
        seen.add(k);rr=dict(r);rr['size_gate']='LIKELY_20_PLUS' if v=='LIKELY_20_PLUS' else 'CONFIRMED_20_PLUS';rr['market_source']='WKO_ONLY';rows.append(rr);source_counts['wko_supplement']+=1
    rows.sort(key=lambda r:(0 if r['size_gate'].startswith('CONFIRMED') else 1,r.get('group_name','').lower()))
    chunks=[[] for _ in range(a.chunks)]
    for i,r in enumerate(rows):chunks[i%a.chunks].append(r)
    fields=[]
    for r in rows:
        for k in r:
            if k not in fields:fields.append(k)
    def write(path,rs):
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            if fields:
                w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rs)
    write(os.path.join(a.output_dir,'targets_universe.csv'),rows)
    for i,c in enumerate(chunks):write(os.path.join(a.output_dir,f'chunk_{i:02d}.csv'),c)
    m={'targets':len(rows),'confirmed':sum(r['size_gate'].startswith('CONFIRMED') for r in rows),'likely':sum(r['size_gate']=='LIKELY_20_PLUS' for r in rows),'source_counts':source_counts,'chunks':a.chunks,'chunk_sizes':[len(x) for x in chunks]}
    json.dump(m,open(os.path.join(a.output_dir,'manifest.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(m,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
