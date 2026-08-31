#!/usr/bin/env python3
import argparse,csv,json,os,re
from collections import defaultdict

CONF={'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS'}
RANK={'CONFIRMED_30_PLUS':5,'CONFIRMED_20_29':4,'CONFIRMED_20_PLUS':4,'LIKELY_20_PLUS':3,'BELOW_20':2,'UNRESOLVED':1}
AGG=('websites','emails','phones','cities','member_entities','ksw_pages','evidence_urls','agent_source_urls','economic_component_group_keys','economic_component_names')

def read(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def n(v):
    try:return int(float(v))
    except:return 0
def pipe(a,b):
    vals=[]
    for x in (a,b):
        for y in (x or '').split(' | '):
            y=y.strip()
            if y and y not in vals:vals.append(y)
    return ' | '.join(vals)
def text(r):
    return '\n'.join(r.get(k,'') or '' for k in ('group_name','group_key','domain','websites','member_entities','economic_component_names','agent_source_urls','evidence_urls'))
def merge(members,canonical=''):
    members=sorted(members,key=lambda r:(-RANK.get(r.get('agent_verdict',''),0),-n(r.get('agent_employee_low')),r.get('group_name','').lower()))
    c=dict(members[0])
    if canonical:c['group_name']=canonical
    c['economic_component_size']=sum(max(1,n(r.get('economic_component_size'))) for r in members)
    for f in AGG:
        v=''
        for r in members:v=pipe(v,r.get(f,''))
        c[f]=v
    c['legal_entities_count']=sum(max(1,n(r.get('legal_entities_count'))) for r in members)
    c['locations_count']=max([n(r.get('locations_count')) for r in members] or [0])
    c['manual_override_rule_ids']=' | '.join(dict.fromkeys(x.strip() for r in members for x in (r.get('manual_override_rule_ids') or '').split(' | ') if x.strip()))
    c['manual_override_reasons']=' | '.join(dict.fromkeys(x.strip() for r in members for x in (r.get('manual_override_reasons') or '').split(' | ') if x.strip()))
    c['manual_canonical_group']=canonical or c.get('manual_canonical_group','')
    if canonical or len(members)>1:
        c['economic_dedup_rule']='MANUAL_AUDITED_CANONICAL_MERGE'
        c['agent_count_scope']='AUSTRIA_GROUP'
    return c

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--overrides',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    rows=read(a.input);rules=read(a.overrides)
    if not rows:raise SystemExit('No economic rows')
    for r in rows:r.update(manual_override_rule_ids='',manual_override_reasons='',manual_canonical_group='')
    audit=[]
    for rule in rules:
        rid=(rule.get('rule_id') or '').strip();action=(rule.get('action') or '').strip();rx=re.compile(rule.get('match_regex') or '')
        matches=[r for r in rows if rx.search(text(r))];required=(rule.get('required') or '').strip().lower() in {'1','true','yes'}
        audit.append({'rule_id':rid,'action':action,'match_regex':rule.get('match_regex',''),'match_count':len(matches),'matched_groups':' | '.join(r.get('group_name','') for r in matches[:30]),'required':int(required),'reason':rule.get('reason','')})
        if required and not matches:raise SystemExit(f'Required manual override matched zero rows: {rid}')
        for r in matches:
            r['manual_override_rule_ids']=pipe(r.get('manual_override_rule_ids',''),rid);r['manual_override_reasons']=pipe(r.get('manual_override_reasons',''),rule.get('reason',''))
            src=(rule.get('source_url') or '').strip()
            if src:r['agent_source_urls']=pipe(r.get('agent_source_urls',''),src)
            canonical=(rule.get('canonical_group_name') or '').strip()
            if canonical:r['manual_canonical_group']=canonical
            if action=='PROMOTE_MERGE':
                r['agent_verdict']=(rule.get('verdict') or 'CONFIRMED_30_PLUS').strip();r['agent_employee_low']=(rule.get('employee_low') or r.get('agent_employee_low','')).strip();r['agent_employee_high']=(rule.get('employee_high') or r.get('agent_employee_high','')).strip();r['agent_confidence']='HIGH';r['agent_count_scope']='AUSTRIA_GROUP' if canonical else 'AUSTRIA_ENTITY';r['agent_research_summary']='Manual audited promotion: '+(rule.get('reason') or '');r['agent_review_note']=pipe(r.get('agent_review_note',''),'MANUAL_AUDITED_PROMOTION')
            elif action=='DOWNGRADE_UNRESOLVED':
                r['agent_verdict']='UNRESOLVED';r['agent_employee_low']='';r['agent_employee_high']='';r['agent_confidence']='LOW';r['agent_count_scope']='UNKNOWN';r['agent_research_summary']='Manual QA downgrade: '+(rule.get('reason') or '');r['agent_review_note']=pipe(r.get('agent_review_note',''),'MANUAL_FALSE_POSITIVE_DOWNGRADE')
            elif action=='SET_BELOW_20':
                r['agent_verdict']='BELOW_20';r['agent_employee_low']=(rule.get('employee_low') or '').strip();r['agent_employee_high']=(rule.get('employee_high') or '').strip();r['agent_confidence']='HIGH';r['agent_count_scope']='AUSTRIA_ENTITY';r['agent_research_summary']='Manual audited below-20: '+(rule.get('reason') or '');r['agent_review_note']=pipe(r.get('agent_review_note',''),'MANUAL_BELOW_20')
            elif action!='CANONICAL_MERGE':raise SystemExit(f'Unknown override action {action} in {rid}')
    buckets=defaultdict(list)
    for i,r in enumerate(rows):buckets[('canonical',r['manual_canonical_group'].casefold()) if r.get('manual_canonical_group') else ('row',str(i))].append(r)
    out=[merge(ms,ms[0].get('manual_canonical_group','') if kind=='canonical' else '') for (kind,_),ms in buckets.items()]
    out.sort(key=lambda r:(-RANK.get(r.get('agent_verdict',''),0),r.get('group_name','').lower()))
    fields=list(rows[0].keys())
    def write(name,rs):
        with open(os.path.join(a.output_dir,name),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rs)
    write('stage2_economic_groups_all.csv',out)
    confirmed=[r for r in out if r.get('agent_verdict') in CONF];likely=[r for r in out if r.get('agent_verdict')=='LIKELY_20_PLUS']
    write('stage3_size_verified_targets_economic.csv',confirmed);write('stage2_still_likely_20plus_economic.csv',likely)
    with open(os.path.join(a.output_dir,'manual_override_audit.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['rule_id','action','match_regex','match_count','matched_groups','required','reason']);w.writeheader();w.writerows(audit)
    s={'input_economic_groups':len(rows),'output_economic_groups':len(out),'manual_rules':len(rules),'manual_rules_matched':sum(x['match_count']>0 for x in audit),'manual_rule_matches_total':sum(x['match_count'] for x in audit),'confirmed_targets_after_overrides':len(confirmed),'likely_after_overrides':len(likely),'promotion_rules':[x['rule_id'] for x in audit if x['action']=='PROMOTE_MERGE'],'downshifted_or_below_rules':[x['rule_id'] for x in audit if x['action'] in {'DOWNGRADE_UNRESOLVED','SET_BELOW_20'}]}
    json.dump(s,open(os.path.join(a.output_dir,'manual_override_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(s,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
