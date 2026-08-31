import csv, glob, re, unicodedata
from collections import defaultdict

BASE='data/spedition/contacts'

def read(path):
    try:
        with open(path,encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
    except (FileNotFoundError,UnicodeDecodeError): return []

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def norm_contact(s):
    s=(s or '').strip()
    if '@' in s:return s.lower()
    d=re.sub(r'\D','',s)
    if d.startswith('00'):d=d[2:]
    if d.startswith('0') and not d.startswith('00'):d='43'+d[1:]
    return d

def email_matches_person(email,person):
    if not email or '@' not in email:return False
    local=norm(email.split('@')[0]).replace(' ','')
    toks=[x for x in norm(person).split() if len(x)>=3]
    if not toks:return False
    # Require surname match, or first+last initials/names. Avoid shared surname-only generic addresses when multiple DMs.
    surname=toks[-1]
    if surname in local:return True
    return sum(1 for t in toks if t in local)>=2

def split_people(s):
    return [re.sub(r'\([^)]*\)','',x).strip() for x in (s or '').split(';') if len(re.sub(r'\([^)]*\)','',x).strip().split())>=2]

targets=read(f'{BASE}/targets.csv')
meta={r['no']:r for r in read(f'{BASE}/target_meta.csv')}
validated=read(f'{BASE}/validated_contacts.csv')
official=read(f'{BASE}/official_best_contacts.csv')
manual=[]
for f in sorted(glob.glob(f'{BASE}/external_chunks/manual_web_*.csv')): manual += read(f)

# Map unique person names in target master to target numbers, useful for previously validated related/group companies.
person_to_nos=defaultdict(set)
for t in targets:
    for p in split_people(t.get('primary_dm')): person_to_nos[norm(p)].add(t['no'])

evidence=defaultdict(list)  # (no, normalized person) -> rows

def add(no,person,kind,contact,cls,source_url,method,context='',confidence=''):
    if not no or not person or not contact:return
    evidence[(str(no),norm(person))].append({
        'contact_type':kind,'contact':contact,'class':cls,'source_url':source_url or '',
        'method':method or '', 'context':context or '', 'confidence':confidence or ''
    })

# Strong manually/targeted validated layer.
for r in validated:
    key=norm(r.get('person'))
    nos=person_to_nos.get(key,set())
    # If the person occurs only once in current master, map related/group-company public contact to that target.
    if len(nos)!=1: continue
    no=next(iter(nos)); lvl=r.get('contact_level','')
    if r.get('mobile'): add(no,r['person'],'phone',r['mobile'],'mobile_public',r.get('source_url'),r.get('source_type'),r.get('notes'),r.get('confidence'))
    if r.get('direct_phone'):
        cls='direct_extension' if re.search(r'(?:-|\s)\d{2,5}$',r['direct_phone']) else ('named_management_line' if lvl=='direct_management_line' else 'direct_named')
        add(no,r['person'],'phone',r['direct_phone'],cls,r.get('source_url'),r.get('source_type'),r.get('notes'),r.get('confidence'))
    if r.get('direct_email'):
        cls='personal_email_verified' if lvl!='direct_management_line' and not r['direct_email'].lower().startswith(('office@','info@','sales@')) else 'named_management_line'
        add(no,r['person'],'email',r['direct_email'],cls,r.get('source_url'),r.get('source_type'),r.get('notes'),r.get('confidence'))

# Manually researched external evidence: classifications are explicit and source-contextual.
for r in manual:
    add(r.get('no'),r.get('person'),r.get('contact_type'),r.get('contact'),r.get('contact_class'),r.get('source_url'),r.get('method'),r.get('context'),'')

# Official crawler: use only conservative evidence. Shared crawler phone attached to >1 DM is not direct.
shared_phone_people=defaultdict(set)
for r in official:
    if r.get('best_phone'):
        shared_phone_people[(r['no'],norm_contact(r['best_phone']))].add(norm(r.get('person')))
for r in official:
    no=r.get('no'); person=r.get('person','')
    ph=r.get('best_phone',''); pc=r.get('phone_class','')
    if ph:
        shared=len(shared_phone_people[(no,norm_contact(ph))])>1
        if pc=='mobile_public' and not shared:
            cls='mobile_public'
        else:
            cls='central_fallback' if shared or pc=='named_fixed_candidate' else 'central_fallback'
        add(no,person,'phone',ph,cls,r.get('phone_source_url'),'official_crawl',f"official_best class={pc}; source_count={r.get('phone_sources','')}; shared_across_people={shared}",'')
    em=r.get('best_email',''); ec=r.get('email_class','')
    if em:
        if ec=='personal_verified' and email_matches_person(em,person): cls='personal_email_verified'
        elif ec=='generic_fallback' or not email_matches_person(em,person): cls='central_fallback'
        else: cls='central_fallback'
        add(no,person,'email',em,cls,r.get('email_source_url'),'official_crawl',f"official_best class={ec}; source_count={r.get('email_sources','')}",'')

rank={'mobile_public':1,'direct_extension':2,'direct_named':2,'personal_email_verified':3,'named_management_line':4,'central_fallback':5,'guessed_email':6}
status_by_rank={1:'A_PUBLIC_MOBILE',2:'B_DIRECT_PHONE',3:'C_DIRECT_EMAIL_ONLY',4:'D_NAMED_MANAGEMENT_LINE',5:'E_CENTRAL_FALLBACK',6:'F_NO_PUBLIC_DIRECT_CONTACT_FOUND'}
rows=[]
for t in targets:
    no=t['no']; m=meta.get(no,{})
    for person in split_people(t.get('primary_dm')):
        ev=evidence.get((no,norm(person)),[])
        # Add target_meta company central fallback only if no published person evidence exists at all or only weak central evidence.
        phones=[x.strip() for x in (m.get('main_phones') or '').split('|') if x.strip()]
        emails=[x.strip() for x in (m.get('main_emails') or '').split('|') if x.strip()]
        for ph in phones[:1]:
            if not any(x['class'] in ('mobile_public','direct_extension','direct_named','named_management_line') for x in ev):
                ev=ev+[{'contact_type':'phone','contact':ph,'class':'central_fallback','source_url':t.get('wko_url',''),'method':'target_meta_fallback','context':'Company main phone fallback; not person-direct.','confidence':''}]
        for em in emails[:1]:
            if not any(x['contact_type']=='email' and x['class']=='personal_email_verified' for x in ev):
                ev=ev+[{'contact_type':'email','contact':em,'class':'central_fallback','source_url':t.get('wko_url',''),'method':'target_meta_fallback','context':'Company main email fallback; not person-direct.','confidence':''}]
        # dedupe exact contacts while retaining best class and sources
        byc={}
        for x in ev:
            k=(x['contact_type'],norm_contact(x['contact']))
            if not k[1]: continue
            if k not in byc or rank.get(x['class'],99)<rank.get(byc[k]['class'],99): byc[k]=x.copy(); byc[k]['sources']={x.get('source_url','')}
            else: byc[k].setdefault('sources',set()).add(x.get('source_url',''))
        vals=list(byc.values())
        vals.sort(key=lambda x:(rank.get(x['class'],99), x['contact_type']!='phone'))
        best=vals[0] if vals else None
        if best:
            rr=rank.get(best['class'],6); status=status_by_rank.get(rr,'F_NO_PUBLIC_DIRECT_CONTACT_FOUND')
            source_count=max(1,len([s for s in best.get('sources',set()) if s]))
            conf='high' if rr<=2 and best.get('method') not in ('official_crawl','target_meta_fallback','official_pdf_historical','public_procurement_directory_historical','historical_press_release') else ('medium-high' if rr<=3 else ('medium' if rr<=5 else 'low'))
        else:
            status='F_NO_PUBLIC_DIRECT_CONTACT_FOUND'; source_count=0; conf='low'
        direct_phones=[x['contact'] for x in vals if x['class'] in ('mobile_public','direct_extension','direct_named')]
        personal_emails=[x['contact'] for x in vals if x['class']=='personal_email_verified']
        fallbacks=[x['contact'] for x in vals if x['class'] in ('named_management_line','central_fallback')]
        alts=[x['contact'] for x in vals[1:6]]
        rows.append({
            'no':no,'company':t['company'],'person':person,'role':'Primary Decision Maker (Geschäftsführung/Vorstand target)',
            'ownership_context':t.get('owners',''),'management_context':t.get('management',''),
            'status':status,'best_contact':best['contact'] if best else '','best_contact_class':best['class'] if best else '',
            'direct_phone':' | '.join(dict.fromkeys(direct_phones)),'direct_email':' | '.join(dict.fromkeys(personal_emails)),
            'alternative_contacts':' | '.join(dict.fromkeys(alts)),'fallback':' | '.join(dict.fromkeys(fallbacks)),
            'independent_source_count':source_count,'confidence':conf,
            'best_source_url':best.get('source_url','') if best else '','best_method':best.get('method','') if best else '',
            'best_context':best.get('context','') if best else '', 'wko_url':t.get('wko_url',''),'websites':t.get('websites','')
        })

fields=list(rows[0].keys())
with open(f'{BASE}/coverage_interim.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

# Compact status summary by target person.
counts=defaultdict(int)
for r in rows: counts[r['status']]+=1
with open(f'{BASE}/coverage_status_summary.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(['status','persons']);
    for s in ['A_PUBLIC_MOBILE','B_DIRECT_PHONE','C_DIRECT_EMAIL_ONLY','D_NAMED_MANAGEMENT_LINE','E_CENTRAL_FALLBACK','F_NO_PUBLIC_DIRECT_CONTACT_FOUND']:w.writerow([s,counts[s]])
print('target companies',len(targets),'target persons',len(rows),'status',dict(counts))
