#!/usr/bin/env python3
import argparse,csv,json,os,re
from urllib.parse import urlparse
from collections import defaultdict,Counter

NETWORK_TERMS=('nexia','moore-global','etl-steuerberatung','treuhand-union','ecovis','rsm','kpmg','ey.com','deloitte','pwc','bdo-global')
VERDICT_RANK={'CONFIRMED_30_PLUS':5,'CONFIRMED_20_29':4,'CONFIRMED_20_PLUS':4,'LIKELY_20_PLUS':3,'BELOW_20':2,'UNRESOLVED':1}

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def domain(u):
    u=(u or '').strip()
    if not u:return ''
    if '://' not in u:u='https://'+u
    try:
        h=urlparse(u).netloc.lower().split(':')[0]
        return h[4:] if h.startswith('www.') else h
    except:return ''
def primary(r):
    k=r.get('group_key','')
    return k[7:].strip().lower() if k.startswith('domain:') else ''
def websites(r):
    return {domain(u) for u in (r.get('websites') or '').split(' | ') if domain(u)}
def n(v):
    try:return int(float(v))
    except:return 0

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    rows=read(a.input);by={r['group_key']:r for r in rows};keys=list(by)
    parent={k:k for k in keys}
    def find(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parent[b]=a
    dkeys=defaultdict(set)
    for r in rows:
        p=primary(r)
        if p:dkeys[p].add(r['group_key'])
        for d in websites(r):dkeys[d].add(r['group_key'])
    merges=[]
    for d,ks in dkeys.items():
        if len(ks)!=2:continue
        if any(t in d for t in NETWORK_TERMS):continue
        # Strong alias condition: the shared domain is the primary group key of at least one member.
        if not any(primary(by[k])==d for k in ks):continue
        x,y=sorted(ks);union(x,y);merges.append({'domain':d,'a':x,'b':y})
    comps=defaultdict(list)
    for k in keys:comps[find(k)].append(by[k])
    out=[]
    for members in comps.values():
        members.sort(key=lambda r:(-VERDICT_RANK.get(r.get('agent_verdict',''),0),-n(r.get('agent_employee_low')),-n(r.get('legal_entities_count')),r.get('group_name','').lower()))
        c=dict(members[0]);verdict=c.get('agent_verdict','')
        c['economic_component_size']=len(members)
        c['economic_component_group_keys']=' | '.join(r['group_key'] for r in members)
        c['economic_component_names']=' | '.join(dict.fromkeys(r.get('group_name','') for r in members if r.get('group_name')))
        c['economic_dedup_rule']='DIRECT_SHARED_PRIMARY_DOMAIN' if len(members)>1 else 'SINGLE_GROUP'
        c['websites']=' | '.join(dict.fromkeys(u.strip() for r in members for u in (r.get('websites') or '').split(' | ') if u.strip()))
        c['cities']=' | '.join(dict.fromkeys(x.strip() for r in members for x in (r.get('cities') or '').split(' | ') if x.strip()))
        c['member_entities']=' | '.join(dict.fromkeys(x.strip() for r in members for x in (r.get('member_entities') or '').split(' | ') if x.strip()))
        c['agent_source_urls']=' | '.join(dict.fromkeys(x.strip() for r in members for x in (r.get('agent_source_urls') or '').split(' | ') if x.strip()))
        c['legal_entities_count']=sum(max(1,n(r.get('legal_entities_count'))) for r in members)
        c['locations_count']=max(n(r.get('locations_count')) for r in members)
        if len(members)>1:c['agent_count_scope']='AUSTRIA_GROUP'
        out.append(c)
    out.sort(key=lambda r:(-VERDICT_RANK.get(r.get('agent_verdict',''),0),r.get('group_name','').lower()))
    fields=list(out[0].keys()) if out else []
    def write(name,rs):
        with open(os.path.join(a.output_dir,name),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rs)
    write('stage2_economic_groups_all.csv',out)
    confirmed=[r for r in out if r.get('agent_verdict') in {'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS'}]
    likely=[r for r in out if r.get('agent_verdict')=='LIKELY_20_PLUS']
    write('stage3_size_verified_targets_economic.csv',confirmed)
    write('stage2_still_likely_20plus_economic.csv',likely)
    summary={'input_audited_groups':len(rows),'economic_groups':len(out),'merged_groups_removed':len(rows)-len(out),'merged_components':sum(len(v)>1 for v in comps.values()),'confirmed_economic_targets':len(confirmed),'likely_economic_targets':len(likely),'merge_domains':merges}
    json.dump(summary,open(os.path.join(a.output_dir,'economic_dedup_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
