#!/usr/bin/env python3
import argparse, csv, glob, json, os, re, sys
from collections import Counter

VERDICTS = {
    'CONFIRMED_30_PLUS', 'CONFIRMED_20_29', 'CONFIRMED_20_PLUS',
    'LIKELY_20_PLUS', 'BELOW_20', 'UNRESOLVED'
}
SCOPES = {'AUSTRIA_GROUP','AUSTRIA_LEGAL_ENTITY','LOCAL_OFFICE','GLOBAL_NETWORK','UNKNOWN'}
CONF = {'HIGH','MEDIUM_HIGH','MEDIUM','LOW'}
PROMOTED = {'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS'}
URL_RE = re.compile(r'^https?://', re.I)

REQUIRED = ['group_key','group_name','prior_status','verdict','employee_low','employee_high',
            'count_scope','confidence','research_summary','evidence','review_note','researcher_consensus']

def load_jsonl(path):
    out=[]
    with open(path,encoding='utf-8-sig') as f:
        for n,line in enumerate(f,1):
            line=line.strip()
            if not line: continue
            try: obj=json.loads(line)
            except Exception as e: raise ValueError(f'{path}:{n}: invalid JSON: {e}')
            out.append(obj)
    return out

def normalize_int(v):
    if v in (None,''): return None
    if isinstance(v,bool): raise ValueError('boolean is not an employee count')
    try: return int(v)
    except: raise ValueError(f'invalid integer {v!r}')

def validate_obj(obj, strict=True):
    errors=[]
    for k in REQUIRED:
        if k not in obj: errors.append(f'missing {k}')
    if obj.get('verdict') not in VERDICTS: errors.append(f"bad verdict {obj.get('verdict')}")
    if obj.get('count_scope') not in SCOPES: errors.append(f"bad scope {obj.get('count_scope')}")
    if obj.get('confidence') not in CONF: errors.append(f"bad confidence {obj.get('confidence')}")
    try: lo=normalize_int(obj.get('employee_low')); hi=normalize_int(obj.get('employee_high'))
    except ValueError as e: errors.append(str(e)); lo=hi=None
    if lo is not None and lo < 0: errors.append('employee_low < 0')
    if hi is not None and hi < 0: errors.append('employee_high < 0')
    if lo is not None and hi is not None and lo > hi: errors.append('employee_low > employee_high')
    evidence=obj.get('evidence')
    if not isinstance(evidence,list): errors.append('evidence must be list'); evidence=[]
    good_urls=0
    for i,e in enumerate(evidence):
        if not isinstance(e,dict): errors.append(f'evidence[{i}] not object'); continue
        u=(e.get('url') or '').strip(); fact=(e.get('fact') or '').strip()
        if URL_RE.match(u): good_urls += 1
        if not fact: errors.append(f'evidence[{i}] missing fact')
    verdict=obj.get('verdict')
    scope=obj.get('count_scope')
    if verdict in PROMOTED:
        if lo is None or lo < 20: errors.append('promoted verdict requires employee_low >=20')
        if verdict == 'CONFIRMED_30_PLUS' and lo is not None and lo < 30: errors.append('CONFIRMED_30_PLUS requires employee_low >=30')
        if verdict == 'CONFIRMED_20_29' and (lo is None or lo < 20 or hi is None or hi > 29): errors.append('CONFIRMED_20_29 requires bounded 20-29 evidence')
        if good_urls < 1: errors.append('promoted verdict requires source URL')
        if scope not in {'AUSTRIA_GROUP','AUSTRIA_LEGAL_ENTITY'}:
            errors.append('promoted verdict cannot rely on local-office/global-network/unknown scope')
    if verdict == 'BELOW_20' and good_urls < 1:
        errors.append('BELOW_20 requires at least one source URL')
    if strict and len((obj.get('research_summary') or '').strip()) < 20:
        errors.append('research_summary too short')
    return errors

def csv_keys(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    return rows, [r['group_key'] for r in rows]

def chunk_mode(args):
    input_rows, keys = csv_keys(args.input_csv)
    objs=load_jsonl(args.result_jsonl)
    errors=[]; seen=[]
    for obj in objs:
        seen.append(obj.get('group_key'))
        errs=validate_obj(obj)
        if errs: errors.append({'group_key':obj.get('group_key'),'errors':errs})
    if len(objs)!=len(input_rows): errors.append({'global':f'row count {len(objs)} != {len(input_rows)}'})
    if set(seen)!=set(keys):
        errors.append({'global':'group_key set mismatch','missing':sorted(set(keys)-set(seen)),'extra':sorted(set(seen)-set(keys))})
    if len(seen)!=len(set(seen)): errors.append({'global':'duplicate group_key'})
    report={'ok':not errors,'input_rows':len(input_rows),'output_rows':len(objs),'errors':errors}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if errors: sys.exit(2)

def merge_mode(args):
    with open(args.original_csv,encoding='utf-8-sig',newline='') as f:
        original=list(csv.DictReader(f))
    by_key={r['group_key']:r for r in original}
    files=sorted(glob.glob(os.path.join(args.results_dir,'**','*.jsonl'),recursive=True))
    objs=[]
    for p in files: objs.extend(load_jsonl(p))
    validated=[]; errors=[]; seen=set()
    for obj in objs:
        k=obj.get('group_key')
        if k in seen: errors.append({'group_key':k,'errors':['duplicate across chunks']}); continue
        seen.add(k)
        errs=validate_obj(obj)
        if errs: errors.append({'group_key':k,'errors':errs}); continue
        if k not in by_key: errors.append({'group_key':k,'errors':['not in original universe']}); continue
        validated.append(obj)

    candidate_keys={r['group_key'] for r in original if r.get('qualification_status') in {
        'CONFIRMED_30_PLUS','CONFIRMED_20_29','LIKELY_20_PLUS','POSSIBLE_20_PLUS'}}
    missing=sorted(candidate_keys-seen)
    os.makedirs(args.output_dir,exist_ok=True)

    outrows=[]
    for obj in validated:
        base=dict(by_key[obj['group_key']])
        ev=obj.get('evidence') or []
        base.update({
            'agent_verdict':obj['verdict'],
            'agent_employee_low':'' if obj.get('employee_low') is None else obj.get('employee_low'),
            'agent_employee_high':'' if obj.get('employee_high') is None else obj.get('employee_high'),
            'agent_count_scope':obj['count_scope'],
            'agent_confidence':obj['confidence'],
            'agent_research_summary':obj.get('research_summary',''),
            'agent_source_urls':' | '.join(e.get('url','') for e in ev if isinstance(e,dict)),
            'agent_source_facts':' | '.join(e.get('fact','') for e in ev if isinstance(e,dict)),
            'agent_review_note':obj.get('review_note',''),
            'agent_researcher_consensus':obj.get('researcher_consensus',''),
        })
        outrows.append(base)
    outrows.sort(key=lambda r:(r.get('agent_verdict',''), r.get('group_name','').lower()))
    if outrows:
        with open(os.path.join(args.output_dir,'stage2_agent_verified_all.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(outrows[0].keys()));w.writeheader();w.writerows(outrows)
        confirmed=[r for r in outrows if r['agent_verdict'] in PROMOTED]
        with open(os.path.join(args.output_dir,'stage3_size_verified_targets.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(outrows[0].keys()));w.writeheader();w.writerows(confirmed)
        likely=[r for r in outrows if r['agent_verdict']=='LIKELY_20_PLUS']
        if likely:
            with open(os.path.join(args.output_dir,'stage2_still_likely_20plus.csv'),'w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(outrows[0].keys()));w.writeheader();w.writerows(likely)

    summary={
        'candidate_expected':len(candidate_keys),
        'agent_results_seen':len(seen),
        'agent_results_valid':len(validated),
        'missing':len(missing),
        'invalid':len(errors),
        'verdict_counts':dict(Counter(o['verdict'] for o in validated)),
        'stage3_confirmed_targets':sum(o['verdict'] in PROMOTED for o in validated),
        'still_likely_20plus':sum(o['verdict']=='LIKELY_20_PLUS' for o in validated),
        'below_20':sum(o['verdict']=='BELOW_20' for o in validated),
        'unresolved':sum(o['verdict']=='UNRESOLVED' for o in validated),
        'missing_group_keys':missing,
        'errors':errors,
    }
    with open(os.path.join(args.output_dir,'summary.json'),'w',encoding='utf-8') as f:
        json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if missing or errors: sys.exit(3)

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='mode',required=True)
    c=sub.add_parser('chunk'); c.add_argument('--input-csv',required=True); c.add_argument('--result-jsonl',required=True)
    m=sub.add_parser('merge'); m.add_argument('--original-csv',required=True); m.add_argument('--results-dir',required=True); m.add_argument('--output-dir',required=True)
    args=ap.parse_args()
    chunk_mode(args) if args.mode=='chunk' else merge_mode(args)

if __name__=='__main__': main()
