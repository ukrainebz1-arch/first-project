#!/usr/bin/env python3
import argparse,csv,json,os,re
from collections import defaultdict

CONF={'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS'}
RANK={'CONFIRMED_30_PLUS':5,'CONFIRMED_20_29':4,'CONFIRMED_20_PLUS':4,'LIKELY_20_PLUS':3,'BELOW_20':2,'UNRESOLVED':1}
AGG_FIELDS=('websites','emails','phones','cities','member_entities','ksw_pages','evidence_urls','agent_source_urls','economic_component_group_keys','economic_component_names')

def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def num(v):
    try:return int(float(v))
    except:return 0

def add_pipe(old,new):
    vals=[]
    for x in (old,new):
        for y in (x or '').split(' | '):
            y=y.strip()
            if y and y not in vals:vals.append(y)
    return ' | '.join(vals)

def searchable(r):
    keys=('group_name','group_key','domain','websites','member_entities','economic_component_names','agent_source_urls','evidence_urls')
    return '\n'.join(r.get(k,'') or '' for k in keys)

def merge_members(members,canonical=''):
    members=sorted(members,key=lambda r:(-RANK.get(r.get('agent_verdict',''),0),-num(r.get('agent_employee_low')),r.get('group_name','').lower()))
    c=dict(members[0])
    if canonical:c['group_name']=canonical
    c['economic_component_size']=sum(max(1,num(r.get('economic_component_size'))) for r in members)
    for field in AGG_FIELDS:
        val=''
        for r in members:val=add_pipe(val,r.get(field,''))
        c[field]=val
    c['economic_dedup_rule']=add_pipe('MANUAL_AUDITED_CANONICAL_MERGE' if len(members)>1 or canonical else '',add_pipe(*(('', '') if False else ('','')))) if False else ('MANUAL_AUDITED_CANONICAL_MERGE' if len(members)>1 or canonical else c.get('economic_dedup_rule',''))
    c['legal_entities_count']=sum(max(1,num(r.get('legal_entities_count'))) for r in members)
    c['locations_count']=max([num(r.get('locations_count')) for r in members] or [0])
    c['manual_override_rule_ids']=' | '.join(dict.fromkeys(x.strip() for r in members for x in (r.get('manual_override_rule_ids') or '').split(' | ') if x.strip()))
    c['manual_override_reasons']=' | '.join(dict.fromkeys(x.strip() for r in members for x in (r.get('manual_override_reasons') or '').split(' | ') if x.strip()))
    c['manual_canonical_group']=canonical or c.get('manual_canonical_group','')
    if len(members)>1:c['agent_count_scope']='AUSTRIA_GROUP'
    return c

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--overrides',required=True)
    ap.add_argument('--output-dir',required=True)
    a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    rows=read_csv(a.input);rules=read_csv(a.overrides)
    if not rows:raise SystemExit('No economic rows')
    for r in rows:
        r['manual_override_rule_ids']=''
        r['manual_override_reasons']=''
        r['manual_canonical_group']=''
    audit=[]
    for rule in rules:
        rid=(rule.get('rule_id') or '').strip();action=(rule.get('action') or '').strip();pat=rule.get('match_regex') or ''
        try:rx=re.compile(pat)
        except Exception as e:raise SystemExit(f'Bad override regex {rid}: {e}')
        matches=[r for r in rows if rx.search(searchable(r))]
        required=(rule.get('required') or '').strip() in {'1','true','TRUE','yes','YES'}
        audit.append({'rule_id':rid,'action':action,'match_regex':pat,'match_count':len(matches),'matched_groups':' | '.join(r.get('group_name','') for r in matches[:20]),'required':int(required),'reason':rule.get('reason','')})
        if required and not matches:raise SystemExit(f'Required manual override matched zero rows: {rid}')
        for r in matches:
            r['manual_override_rule_ids']=add_pipe(r.get('manual_override_rule_ids',''),rid)
            r['manual_override_reasons']=add_pipe(r.get('manual_override_reasons',''),rule.get('reason',''))
            source=(rule.get('source_url') or '').strip()
            if source:r['agent_source_urls']=add_pipe(r.get('agent_source_urls',''),source)
            canonical=(rule.get('canonical_group_name') or '').strip()
            if canonical:r['manual_canonical_group']=canonical
            if action=='PROMOTE_MERGE':
                r['agent_verdict']=(rule.get('verdict') or 'CONFIRMED_30_PLUS').strip()
                if (rule.get('employee_low') or '').strip():r['agent_employee_low']=rule['employee_low'].strip()
                if (rule.get('employee_high') or '').strip():r['agent_employee_high']=rule['employee_high'].strip()
                r['agent_confidence']='HIGH'
                r['agent_count_scope']='AUSTRIA_GROUP' if canonical else (r.get('agent_count_scope') or 'AUSTRIA_ENTITY')
                r['agent_research_summary']='Manual audited promotion: '+(rule.get('reason') or '')
                r['agent_review_note']=add_pipe(r.get('agent_review_note',''),'MANUAL_AUDITED_PROMOTION')
            elif action=='DOWNGRADE_UNRESOLVED':
                r['agent_verdict']='UNRESOLVED';r['agent_employee_low']='';r['agent_employee_high']='';r['agent_confidence']='LOW';r['agent_count_scope']='UNKNOWN'
                r['agent_research_summary']='Manual QA downgrade: '+(rule.get('reason') or '')
                r['agent_review_note']=add_pipe(r.get('agent_review_note',''),'MANUAL_FALSE_POSITIVE_DOWNGRADE')
            elif action=='SET_BELOW_20':
                r['agent_verdict']='BELOW_20'
                r['agent_employee_low']=(rule.get('employee_low') or '').strip();r['agent_employee_high']=(rule.get('employee_high') or '').strip();r['agent_confidence']='HIGH';r['agent_count_scope']='AUSTRIA_ENTITY'
                r['agent_research_summary']='Manual audited below-20: '+(rule.get('reason') or '')
                r['agent_review_note']=add_pipe(r.get('agent_review_note',''),'MANUAL_BELOW_20')
            elif action=='CANONICAL_MERGE':
                pass
            else:raise SystemExit(f'Unknown override action {action} in {rid}')
    buckets=defaultdict(list)
    for i,r in enumerate(rows):
        key=('canonical',r['manual_canonical_group'].casefold()) if r.get('manual_canonical_group') else ('row',str(i))
        buckets[key].append(r)
    out=[]
    for (kind,key),members in buckets.items():
        out.append(merge_members(members,members[0].get('manual_canonical_group','') if kind=='canonical' else ''))
    out.sort(key=lambda r:(-RANK.get(r.get('agent_verdict',''),0),r.get('group_name','').lower()))
    base_fields=list(rows[0].keys())
    fields=base_fields
    def write(name,rs):
        with open(os.path.join(a.output_dir,name),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rs)
    write('stage2_economic_groups_all.csv',out)
    confirmed=[r for r in out if r.get('agent_verdict') in CONF]
    likely=[r for r in out if r.get('agent_verdict')=='LIKELY_20_PLUS']
    write('stage3_size_verified_targets_economic.csv',confirmed)
    write('stage2_still_likely_20plus_economic.csv',likely)
    afields=['rule_id','action','match_regex','match_count','matched_groups','required','reason']
    with open(os.path.join(a.output_dir,'manual_override_audit.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=afields);w.writeheader();w.writerows(audit)
    summary={
        'input_economic_groups':len(rows),'output_economic_groups':len(out),'manual_rules':len(rules),
        'manual_rules_matched':sum(x['match_count']>0 for x in audit),'manual_rule_matches_total':sum(x['match_count'] for x in audit),
        'manual_canonical_groups':sum(bool(r.get('manual_canonical_group')) for r in out),
        'confirmed_targets_after_overrides':len(confirmed),'likely_after_overrides':len(likely),
        'downshifted_or_below_rules':[x['rule_id'] for x in audit if x['action'] in {'DOWNGRADE_UNRESOLVED','SET_BELOW_20'}],
        'promotion_rules':[x['rule_id'] for x in audit if x['action']=='PROMOTE_MERGE']
    }
    json.dump(summary,open(os.path.join(a.output_dir,'manual_override_summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
