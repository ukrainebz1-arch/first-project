#!/usr/bin/env python3
import argparse,csv,hashlib,json,os,re,unicodedata
from collections import defaultdict

def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def norm(s):
    s=unicodedata.normalize('NFKD',clean(s)).encode('ascii','ignore').decode().lower()
    s=s.replace('&',' und ')
    s=re.sub(r'\b(gesellschaft mit beschrankter haftung|gesellschaft m b h|ges m b h|gesmbh|gmbh|mbh|ag|kg|og|e u|eu|co)\b',' ',s)
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return clean(s)
def joinvals(vals,sep=' | '): return sep.join(sorted({clean(x) for x in vals if clean(x)}))
def key(name): return 'sped_' + hashlib.sha1(name.encode('utf-8')).hexdigest()[:14]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--wko',required=True)
    ap.add_argument('--core-targets',required=True)
    ap.add_argument('--output-dir',required=True)
    ap.add_argument('--chunks',type=int,default=32)
    a=ap.parse_args(); os.makedirs(a.output_dir,exist_ok=True)
    with open(a.core_targets,encoding='utf-8-sig',newline='') as f:
        core=list(csv.DictReader(f))
    core_norm={norm(r.get('company','')) for r in core if r.get('company')}
    with open(a.wko,encoding='utf-8-sig',newline='') as f:
        raw=list(csv.DictReader(f))
    agg={}
    for r in raw:
        name=clean(r.get('company_name',''))
        if not name: continue
        g=agg.setdefault(name,{'company_name':name,'states':set(),'places':set(),'addresses':set(),'phones':set(),'emails':set(),'websites':set(),'wko_urls':set(),'firmaids':set(),'wko_rows':0})
        g['wko_rows']+=1
        if r.get('bundesland'): g['states'].add(r['bundesland'])
        if r.get('place'): g['places'].add(r['place'])
        if r.get('street'): g['addresses'].add((r.get('street','')+', '+r.get('place','')).strip(', '))
        if r.get('phone'): g['phones'].add(r['phone'])
        if r.get('email'): g['emails'].add(r['email'])
        if r.get('website'): g['websites'].add(r['website'])
        if r.get('profile_url'): g['wko_urls'].add(r['profile_url'])
        if r.get('firmaid'): g['firmaids'].add(r['firmaid'])
    candidates=[]; excluded=[]
    for name,g in sorted(agg.items(),key=lambda kv:kv[0].casefold()):
        row={'candidate_key':key(name),'company_name':name,'prior_status':'NOT_IN_CORE_118','states':joinvals(g['states'],'; '),'places':joinvals(g['places']),'addresses':joinvals(g['addresses']),'phones':joinvals(g['phones']),'emails':joinvals(g['emails']),'websites':joinvals(g['websites']),'wko_urls':joinvals(g['wko_urls']),'firmaids':joinvals(g['firmaids']),'wko_rows':str(g['wko_rows'])}
        if norm(name) in core_norm: excluded.append(row)
        else: candidates.append(row)
    # Round-robin alphabetical list so each chunk gets a broad mix.
    chunks=[[] for _ in range(a.chunks)]
    for i,r in enumerate(candidates): chunks[i%a.chunks].append(r)
    fields=list(candidates[0]) if candidates else []
    def write(path,rows):
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    write(os.path.join(a.output_dir,'candidate_universe.csv'),candidates)
    write(os.path.join(a.output_dir,'excluded_existing_core_name_matches.csv'),excluded)
    for i,c in enumerate(chunks): write(os.path.join(a.output_dir,f'chunk_{i:02d}.csv'),c)
    manifest={'wko_rows':len(raw),'wko_unique_names':len(agg),'existing_core_name_matches_excluded':len(excluded),'agent_candidate_rows':len(candidates),'chunks':a.chunks,'chunk_sizes':[len(c) for c in chunks]}
    with open(os.path.join(a.output_dir,'manifest.json'),'w',encoding='utf-8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
