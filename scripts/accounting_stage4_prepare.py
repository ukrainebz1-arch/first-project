#!/usr/bin/env python3
import argparse,csv,json,os

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output-dir',required=True);ap.add_argument('--chunks',type=int,default=16);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    rows=list(csv.DictReader(open(a.input,encoding='utf-8-sig',newline='')))
    # Only rows with an identified primary DM can have person-specific contact research.
    eligible=[r for r in rows if (r.get('primary_dm') or '').strip()]
    chunks=[[] for _ in range(a.chunks)]
    for i,r in enumerate(eligible):chunks[i%a.chunks].append(r)
    fields=list(rows[0].keys()) if rows else []
    for i,c in enumerate(chunks):
        with open(os.path.join(a.output_dir,f'chunk_{i:02d}.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(c)
    with open(os.path.join(a.output_dir,'eligible_targets.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(eligible)
    m={'all_targets':len(rows),'eligible_primary_dm':len(eligible),'without_primary_dm':len(rows)-len(eligible),'chunks':a.chunks,'chunk_sizes':[len(x) for x in chunks]}
    json.dump(m,open(os.path.join(a.output_dir,'manifest.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(m,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
