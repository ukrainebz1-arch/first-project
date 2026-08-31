#!/usr/bin/env python3
import argparse,csv,glob,json,os,re,sys
from collections import Counter
VERDICTS={'CONFIRMED_30_PLUS','LIKELY_30_PLUS_AUSTRIA_GROUP','CONFIRMED_20_29','BELOW_20','NON_CORE','DUPLICATE_EXISTING_CORE','UNRESOLVED'}
SCOPES={'AUSTRIA_GROUP','AUSTRIA_LEGAL_ENTITY','LOCAL_OFFICE','GLOBAL_NETWORK','UNKNOWN'}
CONF={'HIGH','MEDIUM_HIGH','MEDIUM','LOW'}
REL={'CORE','ADJACENT','NON_CORE','UNKNOWN'}
URL_RE=re.compile(r'^https?://',re.I)
REQUIRED=['candidate_key','company_name','prior_status','verdict','business_relevance','employee_low','employee_high','count_scope','confidence','research_summary','evidence','review_note','researcher_consensus']

def rows(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def load_jsonl(path):
    out=[]
    with open(path,encoding='utf-8-sig') as f:
        for n,line in enumerate(f,1):
            line=line.strip()
            if not line:continue
            try:out.append(json.loads(line))
            except Exception as e:raise ValueError(f'{path}:{n}: invalid JSON {e}')
    return out
def ni(v):
    if v in (None,''):return None
    if isinstance(v,bool):raise ValueError('boolean employee count')
    return int(v)
def validate(o):
    e=[]
    for k in REQUIRED:
        if k not in o:e.append('missing '+k)
    if o.get('verdict') not in VERDICTS:e.append('bad verdict')
    if o.get('count_scope') not in SCOPES:e.append('bad scope')
    if o.get('confidence') not in CONF:e.append('bad confidence')
    if o.get('business_relevance') not in REL:e.append('bad business_relevance')
    try:lo,hi=ni(o.get('employee_low')),ni(o.get('employee_high'))
    except Exception as ex:e.append(str(ex));lo=hi=None
    if lo is not None and lo<0:e.append('employee_low < 0')
    if hi is not None and hi<0:e.append('employee_high < 0')
    if lo is not None and hi is not None and lo>hi:e.append('employee_low > employee_high')
    ev=o.get('evidence');good=0
    if not isinstance(ev,list):e.append('evidence must be list');ev=[]
    for i,x in enumerate(ev):
        if not isinstance(x,dict):e.append(f'evidence[{i}] not object');continue
        if URL_RE.match((x.get('url') or '').strip()):good+=1
        if not (x.get('fact') or '').strip():e.append(f'evidence[{i}] missing fact')
    v=o.get('verdict');scope=o.get('count_scope')
    if v=='CONFIRMED_30_PLUS':
        if lo is None or lo<30:e.append('confirmed 30+ requires employee_low >=30')
        if scope not in {'AUSTRIA_GROUP','AUSTRIA_LEGAL_ENTITY'}:e.append('confirmed 30+ requires Austrian scope')
        if good<1:e.append('confirmed 30+ requires URL')
    if v=='LIKELY_30_PLUS_AUSTRIA_GROUP':
        if scope not in {'AUSTRIA_GROUP','AUSTRIA_LEGAL_ENTITY'}:e.append('likely 30+ requires Austrian scope')
        if good<1:e.append('likely 30+ requires URL')
    if v=='CONFIRMED_20_29':
        if lo is None or lo<20 or hi is None or hi>29:e.append('20-29 requires bounded count')
        if scope not in {'AUSTRIA_GROUP','AUSTRIA_LEGAL_ENTITY'}:e.append('20-29 requires Austrian scope')
        if good<1:e.append('20-29 requires URL')
    if v in {'BELOW_20','NON_CORE','DUPLICATE_EXISTING_CORE'} and good<1:e.append(v+' requires URL')
    if len((o.get('research_summary') or '').strip())<20:e.append('research_summary too short')
    return e

def chunk(a):
    inp=rows(a.input_csv);keys=[r['candidate_key'] for r in inp];objs=load_jsonl(a.result_jsonl);errs=[];seen=[]
    for o in objs:
        seen.append(o.get('candidate_key'));x=validate(o)
        if x:errs.append({'candidate_key':o.get('candidate_key'),'errors':x})
    if len(objs)!=len(inp):errs.append({'global':f'row count {len(objs)} != {len(inp)}'})
    if set(seen)!=set(keys):errs.append({'global':'candidate_key mismatch','missing':sorted(set(keys)-set(seen)),'extra':sorted(set(seen)-set(keys))})
    if len(seen)!=len(set(seen)):errs.append({'global':'duplicate candidate_key'})
    print(json.dumps({'ok':not errs,'input_rows':len(inp),'output_rows':len(objs),'errors':errs},ensure_ascii=False,indent=2))
    if errs:sys.exit(2)

def merge(a):
    cand=rows(a.candidate_csv);by={r['candidate_key']:r for r in cand};files=sorted(glob.glob(os.path.join(a.results_dir,'**','*.jsonl'),recursive=True));objs=[]
    for p in files:objs+=load_jsonl(p)
    seen=set();valid=[];errs=[]
    for o in objs:
        k=o.get('candidate_key')
        if k in seen:errs.append({'candidate_key':k,'errors':['duplicate across chunks']});continue
        seen.add(k);x=validate(o)
        if x:errs.append({'candidate_key':k,'errors':x});continue
        if k not in by:errs.append({'candidate_key':k,'errors':['not in candidate universe']});continue
        valid.append(o)
    missing=sorted(set(by)-seen);os.makedirs(a.output_dir,exist_ok=True);out=[]
    for o in valid:
        b=dict(by[o['candidate_key']]);ev=o.get('evidence') or []
        b.update({'agent_verdict':o['verdict'],'agent_business_relevance':o['business_relevance'],'agent_employee_low':'' if o.get('employee_low') is None else o['employee_low'],'agent_employee_high':'' if o.get('employee_high') is None else o['employee_high'],'agent_count_scope':o['count_scope'],'agent_confidence':o['confidence'],'agent_research_summary':o.get('research_summary',''),'agent_source_urls':' | '.join(x.get('url','') for x in ev if isinstance(x,dict)),'agent_source_facts':' | '.join(x.get('fact','') for x in ev if isinstance(x,dict)),'agent_review_note':o.get('review_note',''),'agent_researcher_consensus':o.get('researcher_consensus','')});out.append(b)
    out.sort(key=lambda r:(r.get('agent_verdict',''),r.get('company_name','').casefold()))
    fields=list(out[0]) if out else list(cand[0])
    def write(name,rr):
        with open(os.path.join(a.output_dir,name),'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rr)
    write('agent_recheck_all.csv',out)
    recovered=[r for r in out if r['agent_verdict'] in {'CONFIRMED_30_PLUS','LIKELY_30_PLUS_AUSTRIA_GROUP'} and r['agent_business_relevance'] in {'CORE','ADJACENT'}]
    write('recovered_30plus_candidates.csv',recovered)
    write('confirmed_30plus_only.csv',[r for r in recovered if r['agent_verdict']=='CONFIRMED_30_PLUS'])
    write('still_unresolved.csv',[r for r in out if r['agent_verdict']=='UNRESOLVED'])
    c=Counter(r['agent_verdict'] for r in out)
    summary={'candidate_expected':len(by),'agent_results_seen':len(seen),'agent_results_valid':len(valid),'missing':len(missing),'invalid':len(errs),'verdict_counts':dict(c),'recovered_30plus_candidates':len(recovered),'confirmed_30plus':c.get('CONFIRMED_30_PLUS',0),'likely_30plus_austria_group':c.get('LIKELY_30_PLUS_AUSTRIA_GROUP',0),'confirmed_20_29':c.get('CONFIRMED_20_29',0),'below_20':c.get('BELOW_20',0),'non_core':c.get('NON_CORE',0),'duplicate_existing_core':c.get('DUPLICATE_EXISTING_CORE',0),'unresolved':c.get('UNRESOLVED',0),'missing_keys':missing,'errors':errs}
    with open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if missing or errs:sys.exit(3)

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='mode',required=True)
    c=sub.add_parser('chunk');c.add_argument('--input-csv',required=True);c.add_argument('--result-jsonl',required=True)
    m=sub.add_parser('merge');m.add_argument('--candidate-csv',required=True);m.add_argument('--results-dir',required=True);m.add_argument('--output-dir',required=True)
    a=ap.parse_args();chunk(a) if a.mode=='chunk' else merge(a)
if __name__=='__main__':main()
