#!/usr/bin/env python3
import argparse,csv,json,os

def read(p):
    if not os.path.exists(p):return []
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def num(v):
    try:return int(float(v))
    except:return None
def write(p,rows,fields=None):
    os.makedirs(os.path.dirname(p),exist_ok=True)
    if fields is None:fields=list(rows[0].keys()) if rows else []
    with open(p,'w',encoding='utf-8-sig',newline='') as f:
        if not fields:return
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def bucket(r):
    v=r.get('agent_verdict') or r.get('qualification_status') or ''
    lo=num(r.get('agent_employee_low'));hi=num(r.get('agent_employee_high'))
    if v=='LIKELY_20_PLUS':return 'LIKELY_20_PLUS'
    if v not in {'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS'}:return 'EXCLUDED_OR_UNRESOLVED'
    if lo is not None and lo>=200:return '200_PLUS'
    if v=='CONFIRMED_20_29' or (lo is not None and lo<30 and hi is not None and hi<=29):return '20_29'
    if lo is not None and lo>=100:return '100_199'
    if lo is not None and lo>=50:return '50_99'
    if lo is not None and lo>=30:return '30_49'
    return 'CONFIRMED_20_PLUS_UNBOUNDED'
def priority(r):
    b=bucket(r)
    if b in {'30_49','50_99','100_199'}:return 'A_PRIORITY_30_200'
    if b=='20_29' or b=='CONFIRMED_20_PLUS_UNBOUNDED':return 'B_SECONDARY_20_PLUS'
    if b=='200_PLUS':return 'C_ENTERPRISE_200_PLUS'
    if b=='LIKELY_20_PLUS':return 'D_LIKELY_20_PLUS'
    return 'EXCLUDED_OR_UNRESOLVED'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--original',required=True);ap.add_argument('--stage2',required=True);ap.add_argument('--stage3',required=True);ap.add_argument('--contacts',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    original=read(a.original);s2={r['group_key']:r for r in read(a.stage2)};s3={r['group_key']:r for r in read(a.stage3)};ct={r['group_key']:r for r in read(a.contacts)}
    allrows=[]
    for base in original:
        k=base['group_key'];r=dict(base)
        if k in s2:
            z=s2[k]
            for key in ['agent_selection_reason','agent_research_mode','agent_verdict','agent_employee_low','agent_employee_high','agent_count_scope','agent_confidence','agent_research_summary','agent_source_urls','agent_source_facts','agent_review_note','agent_researcher_consensus']:
                r[key]=z.get(key,'')
        else:
            r.update({'agent_verdict':'NOT_SELECTED_FOR_DEEP_AUDIT','agent_employee_low':'','agent_employee_high':'','agent_count_scope':'','agent_confidence':'','agent_research_summary':'No strong Stage-2 scale signal selected this group for the 823-company deep audit.','agent_source_urls':'','agent_source_facts':'','agent_review_note':'','agent_researcher_consensus':''})
        if k in s3:
            z=s3[k]
            for key in ['size_gate','management','owners','ultimate_owner','ownership_structure','ownership_type','primary_dm','primary_dm_roles','owner_confidence','owner_source_urls','owner_review_note']:
                r[key]=z.get(key,'')
        else:
            for key in ['size_gate','management','owners','ultimate_owner','ownership_structure','ownership_type','primary_dm','primary_dm_roles','owner_confidence','owner_source_urls','owner_review_note']:r[key]=''
        if k in ct:
            z=ct[k]
            for key in ['best_direct_phone','best_phone_class','best_phone_score','best_phone_person','best_phone_sources','best_personal_email','best_email_class','best_email_score','best_email_person','best_email_sources','fallback_central_phone','fallback_generic_email']:
                r[key]=z.get(key,'')
        else:
            for key in ['best_direct_phone','best_phone_class','best_phone_score','best_phone_person','best_phone_sources','best_personal_email','best_email_class','best_email_score','best_email_person','best_email_sources','fallback_central_phone','fallback_generic_email']:r[key]=''
        r['size_bucket']=bucket(r);r['outreach_priority']=priority(r)
        r['all_size_sources']=r.get('agent_source_urls') or r.get('evidence_urls','')
        r['all_owner_sources']=r.get('owner_source_urls','')
        r['all_contact_sources']=' | '.join(x for x in [r.get('best_phone_sources',''),r.get('best_email_sources','')] if x)
        allrows.append(r)
    targets=[r for r in allrows if r['outreach_priority']!='EXCLUDED_OR_UNRESOLVED']
    targets.sort(key=lambda r:({'A_PRIORITY_30_200':0,'B_SECONDARY_20_PLUS':1,'C_ENTERPRISE_200_PLUS':2,'D_LIKELY_20_PLUS':3}.get(r['outreach_priority'],9),r.get('group_name','').lower()))
    allrows.sort(key=lambda r:r.get('group_name','').lower())
    write(os.path.join(a.output_dir,'Accounting_Steuerberatung_Austria_AI_Prospects_2026-08-31.csv'),targets)
    write(os.path.join(a.output_dir,'all_corporate_groups.csv'),allrows)
    write(os.path.join(a.output_dir,'priority_30_200.csv'),[r for r in targets if r['outreach_priority']=='A_PRIORITY_30_200'])
    write(os.path.join(a.output_dir,'20_29.csv'),[r for r in targets if r['size_bucket']=='20_29'])
    write(os.path.join(a.output_dir,'30_49.csv'),[r for r in targets if r['size_bucket']=='30_49'])
    write(os.path.join(a.output_dir,'50_99.csv'),[r for r in targets if r['size_bucket']=='50_99'])
    write(os.path.join(a.output_dir,'100_199.csv'),[r for r in targets if r['size_bucket']=='100_199'])
    write(os.path.join(a.output_dir,'200_plus.csv'),[r for r in targets if r['size_bucket']=='200_PLUS'])
    write(os.path.join(a.output_dir,'likely_20_plus.csv'),[r for r in targets if r['size_bucket']=='LIKELY_20_PLUS'])
    write(os.path.join(a.output_dir,'confirmed_20_plus_unbounded.csv'),[r for r in targets if r['size_bucket']=='CONFIRMED_20_PLUS_UNBOUNDED'])
    write(os.path.join(a.output_dir,'excluded_unresolved.csv'),[r for r in allrows if r['outreach_priority']=='EXCLUDED_OR_UNRESOLVED'])
    summary={
      'all_corporate_groups':len(allrows),'final_targets_confirmed_or_likely':len(targets),
      'priority_30_200':sum(r['outreach_priority']=='A_PRIORITY_30_200' for r in targets),
      'secondary_20_plus':sum(r['outreach_priority']=='B_SECONDARY_20_PLUS' for r in targets),
      'enterprise_200_plus':sum(r['outreach_priority']=='C_ENTERPRISE_200_PLUS' for r in targets),
      'likely_20_plus':sum(r['outreach_priority']=='D_LIKELY_20_PLUS' for r in targets),
      'with_primary_dm':sum(bool(r.get('primary_dm')) for r in targets),
      'with_direct_phone':sum(bool(r.get('best_direct_phone')) for r in targets),
      'with_personal_email':sum(bool(r.get('best_personal_email')) for r in targets),
      'with_phone_including_fallback':sum(bool(r.get('best_direct_phone') or r.get('fallback_central_phone')) for r in targets),
      'with_email_including_fallback':sum(bool(r.get('best_personal_email') or r.get('fallback_generic_email')) for r in targets),
      'size_bucket_counts':{b:sum(r['size_bucket']==b for r in targets) for b in sorted(set(r['size_bucket'] for r in targets))}
    }
    json.dump(summary,open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(summary,ensure_ascii=False,indent=2))
    methodology='''# Accounting / Steuerberatung Austria — final pipeline\n\nUniverse: complete KSW corporate-group universe (~2,780 economic groups) backed by the prior complete KSW scrape, with WKO work retained as supplemental context.\n\nStage 2: 823 groups with prior 20+ evidence or strong scale signals were re-audited against public web evidence. Official explicit employee statements and complete staff lower bounds dominate. LinkedIn 11–50 alone never confirms 20+. Global-network or foreign-parent headcount does not prove Austrian size.\n\nStage 3: confirmed and likely 20+ groups were researched for Austrian management, public ownership/share information and a Primary Decision Maker. Ownership is not inferred from surnames; unknown shares remain unknown. International networks use Austrian operational leadership rather than global owners.\n\nStage 4: public business contacts are searched around the named Primary DM. Ranking prioritizes public mobile, direct extension, named office number and personal e-mail. Generic company phone/e-mail is kept only as a clearly labelled fallback. No leaks or private-source data are used.\n'''
    open(os.path.join(a.output_dir,'METHODOLOGY.md'),'w',encoding='utf-8').write(methodology)
if __name__=='__main__':main()
