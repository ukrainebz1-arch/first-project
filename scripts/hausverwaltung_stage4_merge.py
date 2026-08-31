#!/usr/bin/env python3
import argparse,csv,glob,json,os,re
from collections import defaultdict

PHONE_RANK={'A_MOBILE_PUBLIC':1,'B_DIRECT_DIAL':2,'C_PERSON_BOUND_OFFICE':3,'D_MANAGEMENT_LINE':4,'E_CENTRAL_FALLBACK':5,'NONE':9}
EMAIL_RANK={'A_PERSONAL_VERIFIED':1,'B_PERSONAL_INFERRED':2,'C_MANAGEMENT_NAMED':3,'D_GENERAL_FALLBACK':4,'NONE':9}
GENERIC_PREFIX=('info@','office@','kontakt@','contact@','service@','support@','verwaltung@','hausverwaltung@','sekretariat@','mail@','hello@','presse@','press@','marketing@','jobs@','karriere@','bewerbung@')


def read(path):
    try:
        with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    except:return []
def write(path,rows,fields):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def people(s):return [re.sub(r'\s+',' ',x).strip() for x in (s or '').split(';') if len(x.strip().split())>=2]
def norm(s):return re.sub(r'[^a-z0-9äöüß]+',' ',(s or '').lower()).strip()
def source_ok(h):return h.get('source_kind') in {'official_html','official_pdf','external_page','external_pdf'} and int(float(h.get('score') or 0))>=70
def generic_email(e):return (e or '').lower().startswith(GENERIC_PREFIX)

def best_phone(hits):
    cand=[]
    for h in hits:
        if h.get('contact_type')!='phone' or not source_ok(h):continue
        cls=h.get('contact_class','NONE');score=int(float(h.get('score') or 0))
        if cls=='A_MOBILE_PUBLIC' and score>=95:cand.append(h)
        elif cls=='B_DIRECT_DIAL' and score>=90:cand.append(h)
        elif cls=='C_PERSON_BOUND_OFFICE' and score>=80:cand.append(h)
        elif cls=='D_MANAGEMENT_LINE' and score>=70:cand.append(h)
    return sorted(cand,key=lambda h:(PHONE_RANK.get(h.get('contact_class'),9),-int(float(h.get('score') or 0)),-int(float(h.get('source_count') or 1))))[0] if cand else None

def best_email(hits):
    cand=[]
    for h in hits:
        if h.get('contact_type')!='email' or not source_ok(h):continue
        cls=h.get('contact_class','NONE');score=int(float(h.get('score') or 0))
        # Worker gives 96+ only when public address itself matches the person's name.
        if cls=='A_PERSONAL_VERIFIED' and score>=90 and not generic_email(h.get('contact')):cand.append(h)
        elif cls=='C_MANAGEMENT_NAMED' and score>=70:cand.append(h)
    return sorted(cand,key=lambda h:(EMAIL_RANK.get(h.get('contact_class'),9),-int(float(h.get('score') or 0)),-int(float(h.get('source_count') or 1))))[0] if cand else None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--targets',required=True);ap.add_argument('--results-dir',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    targets=read(a.targets)
    evidence=[];coverage=[]
    for p in glob.glob(os.path.join(a.results_dir,'**','evidence.csv'),recursive=True):evidence+=read(p)
    for p in glob.glob(os.path.join(a.results_dir,'**','coverage.csv'),recursive=True):coverage+=read(p)
    cov={r['no']:r for r in coverage}; by=defaultdict(list)
    for h in evidence:by[h.get('no','')].append(h)
    # Preserve full discovery evidence for later agent/manual verification.
    efields=['no','company_name','stage3_scope','primary_dm','primary_dm_role','person','contact_type','contact','contact_class','score','source_count','source_url','all_source_urls','source_kind','query','context']
    write(os.path.join(a.output_dir,'machine_evidence.csv'),evidence,efields)
    out=[];queue=[]
    for r in targets:
        no=r['no'];hs=by.get(no,[]);c=cov.get(no,{})
        person_hits=defaultdict(list)
        for h in hs:person_hits[norm(h.get('person'))].append(h)
        phs=[];ems=[]
        for p in people(r.get('primary_dm')):
            bp=best_phone(person_hits.get(norm(p),[]));be=best_email(person_hits.get(norm(p),[]))
            if bp:phs.append(bp)
            if be:ems.append(be)
        bp=sorted(phs,key=lambda h:(PHONE_RANK.get(h.get('contact_class'),9),-int(float(h.get('score') or 0))))[0] if phs else None
        be=sorted(ems,key=lambda h:(EMAIL_RANK.get(h.get('contact_class'),9),-int(float(h.get('score') or 0))))[0] if ems else None
        # Secondary candidates from other Primary DMs or lower-ranked evidence.
        secph=[h for h in phs if not bp or (h.get('contact'),h.get('person'))!=(bp.get('contact'),bp.get('person'))]
        secem=[h for h in ems if not be or (h.get('contact'),h.get('person'))!=(be.get('contact'),be.get('person'))]
        fp=[x.strip() for x in (c.get('fallback_phones') or '').split(' | ') if x.strip()]
        fe=[x.strip() for x in (c.get('fallback_emails') or '').split(' | ') if x.strip() and generic_email(x.strip())]
        direct_phone=bp.get('contact','') if bp else 'none'; phone_type=bp.get('contact_class','NONE') if bp else 'NONE'
        personal_email=be.get('contact','') if be else 'none'; email_type=be.get('contact_class','NONE') if be else 'NONE'
        srcs=[x for x in (c.get('checked_source_urls') or '').split(' | ') if x]
        selected=[x for x in [bp.get('source_url') if bp else '',be.get('source_url') if be else ''] if x]
        selected=list(dict.fromkeys(selected))
        conf='HIGH' if (bp and bp.get('contact_class') in ('A_MOBILE_PUBLIC','B_DIRECT_DIAL')) or (be and be.get('contact_class')=='A_PERSONAL_VERIFIED') else ('MEDIUM_HIGH' if bp or be else 'MEDIUM')
        summary=[]
        if bp:summary.append(f'{bp.get("person")}: {phone_type} {direct_phone}')
        if be:summary.append(f'{be.get("person")}: {email_type} {personal_email}')
        if not summary:summary.append('NO_DIRECT_CONTACT_FOUND in machine pass; manual/agent verification required')
        notes=f'Machine discovery checked {c.get("checked_source_count","0")} fetched public sources plus exact-name searches/PDF discovery. Snippet-only evidence is not treated as verified. Manual review pending.'
        rr={'no':no,'company_name':r.get('company_name',''),'stage3_scope':r.get('stage3_scope',''),'primary_dm':r.get('primary_dm',''),'primary_dm_role':r.get('primary_dm_role',''),'direct_phone':direct_phone,'phone_type':phone_type,'phone_verified':'yes' if bp else 'no','phone_source_url':bp.get('source_url','') if bp else '','personal_email':personal_email,'email_type':email_type,'email_verified':'yes' if be and email_type!='B_PERSONAL_INFERRED' else 'no','email_source_url':be.get('source_url','') if be else '','secondary_phone':' | '.join(f'{h.get("person")}: {h.get("contact")} [{h.get("contact_class")}]' for h in secph[:4]),'secondary_email':' | '.join(f'{h.get("person")}: {h.get("contact")} [{h.get("contact_class")}]' for h in secem[:4]),'fallback_company_phone':fp[0] if fp else 'none','fallback_company_email':fe[0] if fe else 'none','website':r.get('website',''),'contact_summary':' ; '.join(summary),'contact_confidence':conf,'research_notes':notes,'stage3_owner_summary':r.get('ultimate_control','')+' | '+r.get('immediate_owners',''),'stage3_source_urls':r.get('source_urls',''),'research_complete':'machine_only','manual_reviewed':'no','checked_source_count':c.get('checked_source_count','0'),'checked_source_urls':' | '.join(srcs),'machine_selected_sources':' | '.join(selected)}
        out.append(rr)
        queue.append({'no':no,'company_name':r.get('company_name',''),'stage3_scope':r.get('stage3_scope',''),'primary_dm':r.get('primary_dm',''),'machine_direct_phone':direct_phone,'machine_phone_type':phone_type,'machine_personal_email':personal_email,'machine_email_type':email_type,'fallback_company_phone':rr['fallback_company_phone'],'fallback_company_email':rr['fallback_company_email'],'candidate_evidence_count':str(len(hs)),'manual_reviewed':'no','override_primary_dm':'','override_primary_dm_role':'','override_direct_phone':'','override_phone_type':'','override_phone_verified':'','override_phone_source_url':'','override_personal_email':'','override_email_type':'','override_email_verified':'','override_email_source_url':'','override_secondary_phone':'','override_secondary_email':'','override_fallback_company_phone':'','override_fallback_company_email':'','contact_confidence':'','research_notes':'','additional_source_urls':''})
    fields=['no','company_name','stage3_scope','primary_dm','primary_dm_role','direct_phone','phone_type','phone_verified','phone_source_url','personal_email','email_type','email_verified','email_source_url','secondary_phone','secondary_email','fallback_company_phone','fallback_company_email','website','contact_summary','contact_confidence','research_notes','stage3_owner_summary','stage3_source_urls','research_complete','manual_reviewed','checked_source_count','checked_source_urls','machine_selected_sources']
    qfields=list(queue[0].keys()) if queue else []
    write(os.path.join(a.output_dir,'stage4_machine_master_99.csv'),out,fields)
    write(os.path.join(a.output_dir,'manual_review_queue.csv'),queue,qfields)
    # manual_overrides starts as the queue itself; future agent/manual passes update rows in place.
    write(os.path.join(a.output_dir,'manual_overrides.csv'),queue,qfields)
    main=[r for r in out if r['stage3_scope']=='MAIN'];sec=[r for r in out if r['stage3_scope']=='SECONDARY']
    def metrics(rs):
        return {'rows':len(rs),'with_public_mobile':sum(r['phone_type']=='A_MOBILE_PUBLIC' for r in rs),'with_direct_dial':sum(r['phone_type']=='B_DIRECT_DIAL' for r in rs),'with_person_bound_phone':sum(r['phone_type']=='C_PERSON_BOUND_OFFICE' for r in rs),'with_verified_personal_email':sum(r['email_type']=='A_PERSONAL_VERIFIED' and r['email_verified']=='yes' for r in rs),'with_inferred_personal_email':sum(r['email_type']=='B_PERSONAL_INFERRED' for r in rs),'only_fallback':sum(r['direct_phone']=='none' and r['personal_email']=='none' and (r['fallback_company_phone']!='none' or r['fallback_company_email']!='none') for r in rs),'no_public_contact':sum(r['direct_phone']=='none' and r['personal_email']=='none' and r['fallback_company_phone']=='none' and r['fallback_company_email']=='none' for r in rs)}
    summary={'stage4_status':'MACHINE_DISCOVERY_COMPLETE_MANUAL_REVIEW_PENDING','expected':99,'rows':len(out),'machine_research_complete':sum(r['research_complete']=='machine_only' for r in out),'manual_review_complete':0,'missing_primary_dm':sum(not r['primary_dm'] for r in out),'missing_contact_classification':sum(not r['phone_type'] or not r['email_type'] for r in out),'missing_sources':sum(not (r['checked_source_urls'] or r['stage3_source_urls']) for r in out),'overall':metrics(out),'MAIN':metrics(main),'SECONDARY':metrics(sec),'quality_gate_passed':False,'final_master_written':False}
    with open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
    readme='''# Hausverwaltung Stage 4 — machine discovery checkpoint\n\nSource of truth input: `data/hausverwaltung/stage3_owners/stage3_master_99.csv`.\n\nThis checkpoint is **not** the final Stage 4. Automated discovery is conservative: search snippets are evidence only, central numbers are fallback only, and guessed e-mails are never verified. `manual_review_queue.csv` / `manual_overrides.csv` must be completed by agent/manual verification before `stage4_master_99.csv` can be emitted and the final quality gate can pass.\n\nFiles:\n- `stage4_machine_master_99.csv` — 99-row machine checkpoint\n- `machine_evidence.csv` — raw/candidate public evidence\n- `manual_review_queue.csv` — ordered MAIN-first verification queue\n- `manual_overrides.csv` — editable curated override layer\n- `chunks/` — persisted worker checkpoints\n- `summary.json` — machine-pass metrics and explicit non-final gate\n'''
    open(os.path.join(a.output_dir,'README.md'),'w',encoding='utf-8').write(readme)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
