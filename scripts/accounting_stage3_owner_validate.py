#!/usr/bin/env python3
import argparse,csv,glob,json,os,re,sys
from collections import Counter
URL=re.compile(r'^https?://',re.I)
CONF={'HIGH','MEDIUM_HIGH','MEDIUM','LOW'}
OWNERSHIP={'INDIVIDUAL_FAMILY_CONTROL','PARTNER_OWNED','CORPORATE_GROUP','FOUNDATION_CONTROL','PUBLIC_COMPANY','MIXED','UNRESOLVED'}

def csvrows(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def jsonl(p):
    out=[]
    with open(p,encoding='utf-8-sig') as f:
        for n,line in enumerate(f,1):
            if line.strip():
                try:out.append(json.loads(line))
                except Exception as e:raise ValueError(f'{p}:{n}: {e}')
    return out

def valid(o):
    e=[]
    for k in ['group_key','group_name','management','owners','ultimate_owner','ownership_structure','ownership_type','primary_decision_makers','confidence','evidence','review_note']:
        if k not in o:e.append('missing '+k)
    if o.get('confidence') not in CONF:e.append('bad confidence')
    if o.get('ownership_type') not in OWNERSHIP:e.append('bad ownership_type')
    for k in ['management','owners','primary_decision_makers','evidence']:
        if not isinstance(o.get(k),list):e.append(k+' must be list')
    for kind in ['management','owners','primary_decision_makers']:
        for i,x in enumerate(o.get(kind) or []):
            if not isinstance(x,dict):e.append(f'{kind}[{i}] not object');continue
            if not (x.get('name') or '').strip():e.append(f'{kind}[{i}] missing name')
            u=(x.get('url') or '').strip()
            if u and not URL.match(u):e.append(f'{kind}[{i}] bad url')
    for i,x in enumerate(o.get('owners') or []):
        s=x.get('share_pct')
        if s not in (None,''):
            try:
                v=float(s)
                if v<0 or v>100:e.append(f'owners[{i}] share out of range')
            except:e.append(f'owners[{i}] bad share')
    ev=o.get('evidence') or []; good=0
    for i,x in enumerate(ev):
        if isinstance(x,dict) and URL.match((x.get('url') or '').strip()):good+=1
        if not isinstance(x,dict) or not (x.get('fact') or '').strip():e.append(f'evidence[{i}] missing fact')
    if (o.get('management') or o.get('owners') or o.get('primary_decision_makers')) and good<1:e.append('claims require public evidence URL')
    if o.get('primary_decision_makers') and all(not URL.match((x.get('url') or '').strip()) for x in o['primary_decision_makers']):
        if good<1:e.append('primary DM lacks URL support')
    return e

def chunk(a):
    inp=csvrows(a.input_csv); keys=[r['group_key'] for r in inp]; objs=jsonl(a.result_jsonl); seen=[];errs=[]
    for o in objs:
        seen.append(o.get('group_key'));v=valid(o)
        if v:errs.append({'group_key':o.get('group_key'),'errors':v})
    if len(objs)!=len(inp):errs.append({'global':f'row count {len(objs)} != {len(inp)}'})
    if set(seen)!=set(keys):errs.append({'global':'key mismatch','missing':sorted(set(keys)-set(seen)),'extra':sorted(set(seen)-set(keys))})
    if len(seen)!=len(set(seen)):errs.append({'global':'duplicate group_key'})
    print(json.dumps({'ok':not errs,'errors':errs},ensure_ascii=False,indent=2))
    if errs:sys.exit(2)

def merge(a):
    targets=csvrows(a.targets_csv); base={r['group_key']:r for r in targets}; expected=set(base)
    objs=[]
    for p in glob.glob(os.path.join(a.results_dir,'**','*.jsonl'),recursive=True):objs+=jsonl(p)
    seen=set(); valid_objs=[];errs=[]
    for o in objs:
        k=o.get('group_key')
        if k in seen:errs.append({'group_key':k,'errors':['duplicate']});continue
        seen.add(k);v=valid(o)
        if k not in expected:v.append('not in target universe')
        if v:errs.append({'group_key':k,'errors':v})
        else:valid_objs.append(o)
    missing=sorted(expected-seen);os.makedirs(a.output_dir,exist_ok=True)
    rows=[]
    for o in valid_objs:
        r=dict(base[o['group_key']])
        r.update({
          'management':'; '.join(f"{x.get('name','')} [{x.get('title','')}]" for x in o.get('management',[])),
          'owners':'; '.join(f"{x.get('name','')} ({'' if x.get('share_pct') is None else x.get('share_pct')})" for x in o.get('owners',[])),
          'ultimate_owner':o.get('ultimate_owner',''),'ownership_structure':o.get('ownership_structure',''),'ownership_type':o.get('ownership_type',''),
          'primary_dm':'; '.join(x.get('name','') for x in o.get('primary_decision_makers',[])),
          'primary_dm_roles':'; '.join(x.get('role','') for x in o.get('primary_decision_makers',[])),
          'owner_confidence':o.get('confidence',''),'owner_source_urls':' | '.join(x.get('url','') for x in o.get('evidence',[]) if isinstance(x,dict)),
          'owner_review_note':o.get('review_note','')})
        rows.append(r)
    if rows:
        with open(os.path.join(a.output_dir,'targets.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
    with open(os.path.join(a.output_dir,'owner_research_raw.jsonl'),'w',encoding='utf-8') as f:
        for o in valid_objs:f.write(json.dumps(o,ensure_ascii=False)+'\n')
    summary={'expected':len(expected),'seen':len(seen),'valid':len(valid_objs),'missing':len(missing),'invalid':len(errs),'ownership_types':dict(Counter(o.get('ownership_type') for o in valid_objs)),'missing_keys':missing,'errors':errs}
    with open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if missing or errs:sys.exit(3)

def main():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest='mode',required=True)
    c=s.add_parser('chunk');c.add_argument('--input-csv',required=True);c.add_argument('--result-jsonl',required=True)
    m=s.add_parser('merge');m.add_argument('--targets-csv',required=True);m.add_argument('--results-dir',required=True);m.add_argument('--output-dir',required=True)
    a=p.parse_args();chunk(a) if a.mode=='chunk' else merge(a)
if __name__=='__main__':main()
