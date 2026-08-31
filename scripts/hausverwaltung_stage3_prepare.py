#!/usr/bin/env python3
import argparse,csv,json,os

def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--output-dir',required=True)
    ap.add_argument('--chunks',type=int,default=16)
    ap.add_argument('--include-secondary',action='store_true')
    a=ap.parse_args()
    os.makedirs(a.output_dir,exist_ok=True)
    rows=[]; seen=set()
    for r in read_csv(a.input):
        main=(r.get('process_sales_include','').lower()=='yes')
        secondary=(r.get('process_fit_class')=='SECONDARY_PROCESS_TARGET')
        if not main and not (a.include_secondary and secondary):
            continue
        key=(r.get('group_key') or r.get('company_name') or '').strip()
        if not key or key in seen: continue
        seen.add(key)
        rr={
            'group_key':key,
            'group_name':(r.get('company_name') or key).strip(),
            'company_name':(r.get('company_name') or key).strip(),
            'websites':' | '.join(x for x in [(r.get('website') or '').strip(),(r.get('all_websites') or '').strip()] if x),
            'wko_url':(r.get('profile_url') or '').strip(),
            'states_seen':r.get('states_seen',''),
            'addresses':r.get('addresses',''),
            'process_fit_class':r.get('process_fit_class','PRIMARY_CORE'),
            'process_fit_reason':r.get('process_fit_reason',''),
            'size_class':r.get('agent_class') or r.get('size_class_strict_v2') or r.get('size_class_strict') or '',
            'size_confidence':r.get('confidence',''),
            'stage3_scope':'MAIN' if main else 'SECONDARY'
        }
        rows.append(rr)
    rows.sort(key=lambda r:(0 if r['stage3_scope']=='MAIN' else 1,r['group_name'].lower()))
    fields=list(rows[0].keys()) if rows else []
    def write(path,rs):
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            if fields:
                w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rs)
    write(os.path.join(a.output_dir,'targets_universe.csv'),rows)
    chunks=[[] for _ in range(a.chunks)]
    for i,r in enumerate(rows):chunks[i%a.chunks].append(r)
    for i,c in enumerate(chunks):write(os.path.join(a.output_dir,f'chunk_{i:02d}.csv'),c)
    manifest={'targets':len(rows),'main':sum(r['stage3_scope']=='MAIN' for r in rows),'secondary':sum(r['stage3_scope']=='SECONDARY' for r in rows),'chunks':a.chunks,'chunk_sizes':[len(c) for c in chunks]}
    with open(os.path.join(a.output_dir,'manifest.json'),'w',encoding='utf-8') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
