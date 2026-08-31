#!/usr/bin/env python3
import argparse, csv, json, os, re
from collections import Counter, defaultdict

PRIOR_CANDIDATE_STATUSES = {
    'CONFIRMED_30_PLUS', 'CONFIRMED_20_29', 'LIKELY_20_PLUS', 'POSSIBLE_20_PLUS',
}

SANITY_TERMS = [
    'ARTUS','RTG','KPS','CONTAX','ECOVIS','Gneist','RSM','Steuer & Service',
    'Schweitzer','Steuerviertel','Accurata','Geyer','HEW','FP Steuer','AWT',
    'Gerstgrasser','GSV','Writzmann','EOS','KMB','zobl','Prodinger','APP','FUSSEIS',
    'Grazer Treuhand','Schneider','LLP','Pfeiffer Hiebl','Gaun','MOORE','Raml','LBG',
    'TPA','EY','Ernst & Young','KPMG','Fidas','COUNT IT','HGC','RKP','KRW','Klinger'
]

KEEP_FIELDS = [
    'group_key','group_name','domain','websites','cities','legal_entities_count',
    'ksw_listings_count','locations_count','member_entities','qualification_status',
    'confidence','employee_low','employee_high','reason','official_employee_evidence',
    'site_team_profiles','site_team_emails','site_job_links','search_employee_evidence',
    'search_size_ranges','linkedin_visible','evidence_urls'
]

def compact(value, limit=6000):
    value = (value or '').replace('\x00', '').strip()
    return value if len(value) <= limit else value[:limit] + ' …[truncated]'

def n(row, key):
    try:
        return float((row.get(key) or '').strip())
    except Exception:
        return 0.0

def selection_reasons(r):
    reasons=[]
    status=(r.get('qualification_status') or '').strip()
    if status in PRIOR_CANDIDATE_STATUSES:
        reasons.append('PRIOR_STAGE2_CANDIDATE')
    if n(r,'site_team_profiles') >= 10: reasons.append('TEAM_PROFILES_10_PLUS')
    if n(r,'site_team_emails') >= 10: reasons.append('TEAM_EMAILS_10_PLUS')
    if n(r,'site_job_links') >= 3: reasons.append('JOB_LINKS_3_PLUS')
    if n(r,'ksw_listings_count') >= 3: reasons.append('KSW_LISTINGS_3_PLUS')
    if n(r,'locations_count') >= 3: reasons.append('LOCATIONS_3_PLUS')
    if n(r,'legal_entities_count') >= 2: reasons.append('LEGAL_ENTITIES_2_PLUS')
    hay=' '.join([r.get('group_name',''),r.get('member_entities',''),r.get('websites','')]).lower()
    hits=[t for t in SANITY_TERMS if t.lower() in hay]
    if hits: reasons.append('SANITY_SEED:' + '|'.join(hits))
    return reasons

def select_candidates(rows):
    out=[]
    for r in rows:
        reasons=selection_reasons(r)
        if not reasons:
            continue
        rr={k:compact(r.get(k,'')) for k in KEEP_FIELDS}
        rr['prior_status']=rr.pop('qualification_status')
        rr['prior_confidence']=rr.pop('confidence')
        rr['prior_employee_low']=rr.pop('employee_low')
        rr['prior_employee_high']=rr.pop('employee_high')
        rr['prior_reason']=rr.pop('reason')
        rr['selection_reason']=';'.join(reasons)
        rr['research_mode']='DEEP_RESEARCH' if rr['prior_status'] in {'POSSIBLE_20_PLUS','LIKELY_20_PLUS','NO_20PLUS_EVIDENCE'} else 'VERIFY_PRIOR'
        out.append(rr)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--output-dir',required=True)
    ap.add_argument('--chunks',type=int,default=32)
    args=ap.parse_args()
    os.makedirs(args.output_dir,exist_ok=True)

    with open(args.input,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    candidates=select_candidates(rows)

    # Balance old statuses and recovered false-negative candidates across chunks.
    buckets=defaultdict(list)
    for r in candidates:
        key=r['prior_status'] if r['prior_status'] in PRIOR_CANDIDATE_STATUSES else 'RECOVERED_NO_EVIDENCE'
        buckets[key].append(r)
    for v in buckets.values():
        v.sort(key=lambda x:(x['group_name'].lower(),x['group_key']))
    ordered=[]
    priority=['POSSIBLE_20_PLUS','LIKELY_20_PLUS','RECOVERED_NO_EVIDENCE','CONFIRMED_30_PLUS','CONFIRMED_20_29']
    while any(buckets.get(s) for s in priority):
        for s in priority:
            if buckets.get(s): ordered.append(buckets[s].pop(0))

    chunks=[[] for _ in range(args.chunks)]
    for i,r in enumerate(ordered): chunks[i % args.chunks].append(r)
    fieldnames=list(candidates[0].keys()) if candidates else []

    candidate_path=os.path.join(args.output_dir,'candidate_universe.csv')
    with open(candidate_path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fieldnames); w.writeheader(); w.writerows(candidates)

    for i,chunk in enumerate(chunks):
        path=os.path.join(args.output_dir,f'chunk_{i:02d}.csv')
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fieldnames); w.writeheader(); w.writerows(chunk)

    summary={
        'source_rows':len(rows),'candidate_rows':len(candidates),'chunks':args.chunks,
        'status_counts':dict(Counter(r['prior_status'] for r in candidates)),
        'selection_reason_counts':dict(Counter(reason.split(':')[0] for r in candidates for reason in r['selection_reason'].split(';'))),
        'chunk_sizes':[len(c) for c in chunks],
    }
    with open(os.path.join(args.output_dir,'manifest.json'),'w',encoding='utf-8') as f:
        json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
