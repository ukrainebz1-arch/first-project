#!/usr/bin/env python3
import argparse,csv,json,os,re

PHONE_TYPES={'A_MOBILE_PUBLIC','B_DIRECT_DIAL','C_PERSON_BOUND_OFFICE','D_MANAGEMENT_LINE','E_CENTRAL_FALLBACK','NONE'}
EMAIL_TYPES={'A_PERSONAL_VERIFIED','B_PERSONAL_INFERRED','C_MANAGEMENT_NAMED','D_GENERAL_FALLBACK','NONE'}
GENERIC=('info@','office@','kontakt@','contact@','service@','support@','verwaltung@','hausverwaltung@','sekretariat@','mail@','hello@','presse@','press@','marketing@','jobs@','karriere@','bewerbung@')
OVERRIDE_MAP={
 'primary_dm':'override_primary_dm','primary_dm_role':'override_primary_dm_role','direct_phone':'override_direct_phone','phone_type':'override_phone_type','phone_verified':'override_phone_verified','phone_source_url':'override_phone_source_url','personal_email':'override_personal_email','email_type':'override_email_type','email_verified':'override_email_verified','email_source_url':'override_email_source_url','secondary_phone':'override_secondary_phone','secondary_email':'override_secondary_email','fallback_company_phone':'override_fallback_company_phone','fallback_company_email':'override_fallback_company_email','contact_confidence':'contact_confidence','research_notes':'research_notes'}

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,fields):
    os.makedirs(os.path.dirname(p),exist_ok=True)
    with open(p,'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def val(x):return (x or '').strip()
def is_none(x):return val(x).lower() in ('','none','n/a','na')
def generic_email(e):return val(e).lower().startswith(GENERIC)
def metrics(rs):
    return {'rows':len(rs),'companies_with_public_mobile':sum(r['phone_type']=='A_MOBILE_PUBLIC' for r in rs),'companies_with_direct_dial':sum(r['phone_type']=='B_DIRECT_DIAL' for r in rs),'companies_with_person_bound_phone':sum(r['phone_type']=='C_PERSON_BOUND_OFFICE' for r in rs),'companies_with_verified_personal_email':sum(r['email_type']=='A_PERSONAL_VERIFIED' and r['email_verified']=='yes' for r in rs),'companies_with_inferred_personal_email':sum(r['email_type']=='B_PERSONAL_INFERRED' for r in rs),'companies_with_only_fallback':sum(is_none(r['direct_phone']) and is_none(r['personal_email']) and (not is_none(r['fallback_company_phone']) or not is_none(r['fallback_company_email'])) for r in rs),'companies_with_no_public_contact':sum(is_none(r['direct_phone']) and is_none(r['personal_email']) and is_none(r['fallback_company_phone']) and is_none(r['fallback_company_email']) for r in rs)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--machine-master',required=True);ap.add_argument('--overrides',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args()
    base=read(a.machine_master); ovs=read(a.overrides); by={r['no']:r for r in ovs}
    errors=[]
    if len(base)!=99:errors.append(f'expected 99 machine rows, got {len(base)}')
    if len(ovs)!=99:errors.append(f'expected 99 manual rows, got {len(ovs)}')
    out=[]
    for r0 in base:
        r=dict(r0);o=by.get(r['no'])
        if not o:errors.append(f'#{r["no"]} missing manual override row');continue
        if val(o.get('manual_reviewed')).lower()!='yes':errors.append(f'#{r["no"]} manual_reviewed != yes')
        for dst,src in OVERRIDE_MAP.items():
            if val(o.get(src)):r[dst]=val(o[src])
        addsrc=val(o.get('additional_source_urls'))
        if addsrc:
            prior=val(r.get('checked_source_urls'));r['checked_source_urls']=' | '.join(dict.fromkeys([x for x in (prior+' | '+addsrc).split(' | ') if x]))
        r['manual_reviewed']='yes';r['research_complete']='yes'
        # Normalize explicit absence.
        for k in ('direct_phone','personal_email','fallback_company_phone','fallback_company_email'):
            if is_none(r.get(k)):r[k]='none'
        if r.get('phone_type') not in PHONE_TYPES:errors.append(f'#{r["no"]} invalid phone_type {r.get("phone_type")}')
        if r.get('email_type') not in EMAIL_TYPES:errors.append(f'#{r["no"]} invalid email_type {r.get("email_type")}')
        if r['direct_phone']=='none' and r.get('phone_type') not in ('NONE',):errors.append(f'#{r["no"]} no direct phone but phone_type={r.get("phone_type")}')
        if r['direct_phone']!='none' and r.get('phone_type') in ('NONE','E_CENTRAL_FALLBACK'):errors.append(f'#{r["no"]} central/NONE cannot be direct_phone')
        if r['direct_phone']!='none' and (r.get('phone_verified')!='yes' or not val(r.get('phone_source_url'))):errors.append(f'#{r["no"]} direct phone lacks verified/source')
        if r['personal_email']=='none' and r.get('email_type')!='NONE':errors.append(f'#{r["no"]} no personal email but email_type={r.get("email_type")}')
        if r['personal_email']!='none' and r.get('email_type')=='NONE':errors.append(f'#{r["no"]} email present but type NONE')
        if r.get('email_type')=='A_PERSONAL_VERIFIED' and (r.get('email_verified')!='yes' or generic_email(r['personal_email']) or not val(r.get('email_source_url'))):errors.append(f'#{r["no"]} invalid verified personal email')
        if r.get('email_type')=='B_PERSONAL_INFERRED' and r.get('email_verified')!='no':errors.append(f'#{r["no"]} inferred email must not be verified')
        if r.get('email_type') in ('C_MANAGEMENT_NAMED','D_GENERAL_FALLBACK') and r.get('email_verified') not in ('yes','no'):errors.append(f'#{r["no"]} invalid email_verified')
        if not val(r.get('primary_dm')):errors.append(f'#{r["no"]} missing primary_dm')
        if not val(r.get('checked_source_urls')) and not val(r.get('stage3_source_urls')):errors.append(f'#{r["no"]} missing sources')
        if val(r.get('contact_confidence')) not in ('HIGH','MEDIUM_HIGH','MEDIUM'):errors.append(f'#{r["no"]} invalid final confidence')
        # Rebuild concise final summary.
        s=[]
        if r['direct_phone']!='none':s.append(f'{r["phone_type"]}: {r["direct_phone"]}')
        if r['personal_email']!='none':s.append(f'{r["email_type"]}: {r["personal_email"]}')
        if not s:s.append('NO_DIRECT_CONTACT_FOUND')
        if r['fallback_company_phone']!='none' or r['fallback_company_email']!='none':s.append('fallback saved')
        r['contact_summary']='; '.join(s)
        out.append(r)
    scopes={'MAIN':sum(r.get('stage3_scope')=='MAIN' for r in out),'SECONDARY':sum(r.get('stage3_scope')=='SECONDARY' for r in out)}
    if scopes!={'MAIN':90,'SECONDARY':9}:errors.append(f'bad scope counts {scopes}')
    missing_class=sum(not val(r.get('phone_type')) or not val(r.get('email_type')) for r in out)
    missing_sources=sum(not val(r.get('checked_source_urls')) and not val(r.get('stage3_source_urls')) for r in out)
    gate={'expected':99,'rows':len(out),'research_complete':sum(r.get('research_complete')=='yes' for r in out),'missing_primary_dm':sum(not val(r.get('primary_dm')) for r in out),'missing_contact_classification':missing_class,'missing_sources':missing_sources,'manual_review_complete':sum(r.get('manual_reviewed')=='yes' for r in out)}
    gate_pass=(gate=={'expected':99,'rows':99,'research_complete':99,'missing_primary_dm':0,'missing_contact_classification':0,'missing_sources':0,'manual_review_complete':99}) and not errors
    summary={'stage4_status':'FINAL' if gate_pass else 'BLOCKED','quality_gate_passed':gate_pass,**gate,'overall':metrics(out),'MAIN':metrics([r for r in out if r.get('stage3_scope')=='MAIN']),'SECONDARY':metrics([r for r in out if r.get('stage3_scope')=='SECONDARY']),'errors':errors[:100]}
    os.makedirs(a.output_dir,exist_ok=True)
    with open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    if not gate_pass:
        print(json.dumps(summary,ensure_ascii=False,indent=2));raise SystemExit('Stage 4 final quality gate BLOCKED')
    fields=['no','company_name','stage3_scope','primary_dm','primary_dm_role','direct_phone','phone_type','phone_verified','phone_source_url','personal_email','email_type','email_verified','email_source_url','secondary_phone','secondary_email','fallback_company_phone','fallback_company_email','website','contact_summary','contact_confidence','research_notes','stage3_owner_summary','stage3_source_urls','research_complete','manual_reviewed','checked_source_count','checked_source_urls','machine_selected_sources']
    write(os.path.join(a.output_dir,'stage4_master_99.csv'),out,fields)
    write(os.path.join(a.output_dir,'stage4_main_90.csv'),[r for r in out if r['stage3_scope']=='MAIN'],fields)
    write(os.path.join(a.output_dir,'stage4_secondary_9.csv'),[r for r in out if r['stage3_scope']=='SECONDARY'],fields)
    open(os.path.join(a.output_dir,'README.md'),'w',encoding='utf-8').write('# Hausverwaltung Stage 4 — FINAL\n\n`stage4_master_99.csv` is the Stage-4 source of truth. All 99 rows passed manual/agent verification and the final quality gate. Central numbers are fallback only; inferred e-mails are never marked verified. See `summary.json` for coverage statistics.\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
