import csv, glob, os, re, unicodedata
from collections import defaultdict, Counter

BASE='data/spedition/contacts'

STATUS_ORDER=['A_PUBLIC_MOBILE','B_DIRECT_PHONE','C_DIRECT_EMAIL_ONLY','D_NAMED_MANAGEMENT_LINE','E_CENTRAL_FALLBACK','F_NO_PUBLIC_DIRECT_CONTACT_FOUND']
CLASS_RANK={'mobile_public':1,'direct_extension':2,'direct_named':2,'personal_email_verified':3,'named_management_line':4,'central_fallback':5,'guessed_email':6}
STATUS_BY_RANK={1:'A_PUBLIC_MOBILE',2:'B_DIRECT_PHONE',3:'C_DIRECT_EMAIL_ONLY',4:'D_NAMED_MANAGEMENT_LINE',5:'E_CENTRAL_FALLBACK',6:'F_NO_PUBLIC_DIRECT_CONTACT_FOUND'}
DIRECT_CLASSES={'mobile_public','direct_extension','direct_named','personal_email_verified','named_management_line'}
GENERIC_EMAIL_PREFIX=('office@','info@','kontakt@','contact@','sales@','service@','support@','presse@','press@','marketing@','jobs@','karriere@','bewerbung@','application@','dispatch@','dispo@')

METHOD_CATALOG=[
 ('01_OFFICIAL_CONTACT','Official Contact / official website'),
 ('02_TEAM_MANAGEMENT','Team / Management / Geschäftsführung'),
 ('03_IMPRESSUM','Impressum'),
 ('04_PRESS_NEWS','Presse / News / Media'),
 ('05_OFFICIAL_PDF','PDF on official website'),
 ('06_ANNUAL_CSR','Jahresbericht / CSR / Sustainability'),
 ('07_BROCHURE_PRESENTATION','Brochure / Presentation / Fact Sheet'),
 ('08_CAREER_CONTACT','Karriere / Ansprechpartner'),
 ('09_CURRENT_JOB','Current job ad'),
 ('10_ARCHIVED_JOB','Old / closed job ad'),
 ('11_WKO_PROFILE','WKO Firmen A-Z'),
 ('12_BUSINESS_DIRECTORY','FirmenABC / directory / vCard'),
 ('13_INDUSTRY_ASSOCIATION','Industry association / membership'),
 ('14_LOGISTICS_ASSOCIATION','Logistics / forwarding association'),
 ('15_CONFERENCE_EVENT','Conference / speaker / programme'),
 ('16_BUSINESS_CLUB','Wirtschaftsclub / entrepreneur community'),
 ('17_TRADE_FAIR','Messe / exhibitor / event profile'),
 ('18_PUBLIC_TENDER','Tender / procurement / project document'),
 ('19_INDUSTRY_REGISTER','Industry / transport / security register'),
 ('20_PARTNER_GROUP','Supplier / partner / group / case-study page'),
 ('21_PARTNER_PRESS','Press release on partner site'),
 ('22_BUSINESS_SOCIAL','Public LinkedIn / business-social snippet'),
 ('23_EXACT_NAME_SEARCH','Exact-name phone/mobile/DW/email search'),
 ('24_PDF_SPECIFIC_SEARCH','PDF-specific search'),
 ('25_EMAIL_PATTERN','E-mail pattern cross-check (guesses never verified)'),
]
METHOD_LABEL=dict(METHOD_CATALOG)


def read(path):
    try:
        with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    except (FileNotFoundError,UnicodeDecodeError):return []

def write(path,rows,fields):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def split_people(s):
    out=[]
    for x in (s or '').split(';'):
        x=re.sub(r'\([^)]*\)','',x).strip()
        x=re.sub(r'\b(Mag\.?|DI|Ing\.?|MBA|MSc|MA|BSc|Dr\.?|FH)\b',' ',x,flags=re.I)
        x=re.sub(r'\s+',' ',x).strip(' ,')
        if len(x.split())>=2 and x not in out:out.append(x)
    return out

def norm_contact(s):
    s=(s or '').strip()
    if '@' in s:return s.lower().strip(' .;,')
    d=re.sub(r'\D','',s)
    if s.startswith('00') and d.startswith('00'):d=d[2:]
    if s.startswith('0') and not s.startswith('00'):d='43'+d[1:]
    return d

def strict_phone_valid(s):
    s=(s or '').strip()
    if not re.match(r'^(?:\+|00|0)',s):return False
    d=re.sub(r'\D','',s)
    return 8<=len(d)<=15

def email_valid(s):
    return bool(re.fullmatch(r'[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}',(s or '').strip(),re.I))

def email_matches_person(email,person):
    if not email_valid(email):return False
    local=norm(email.split('@')[0]).replace(' ','')
    toks=[x for x in norm(person).split() if len(x)>=3]
    if not toks:return False
    surname=toks[-1]
    if surname in local:return True
    return sum(1 for t in toks if t in local)>=2

def year_from(*parts):
    txt=' '.join(x or '' for x in parts)
    ys=[int(y) for y in re.findall(r'\b(20\d{2})\b',txt)]
    return str(max(ys)) if ys else ''

def method_standard(method='',source_url='',source_title='',query_family='',origin=''):
    m=(method or '').lower(); u=(source_url or '').lower(); t=(source_title or '').lower(); q=(query_family or '').upper(); o=(origin or '').lower()
    # Explicit manual/source methods first.
    if 'wko' in m or 'firmen.wko.at' in u:return '11_WKO_PROFILE'
    if any(x in m for x in ['official_team','official_group_team','official_locations_management']):return '02_TEAM_MANAGEMENT'
    if 'impress' in m or 'impress' in u:return '03_IMPRESSUM'
    if any(x in m for x in ['historical_press','official_press','media_press']):return '04_PRESS_NEWS'
    if 'annual' in m or 'csr' in m or 'sustainab' in m:return '06_ANNUAL_CSR'
    if any(x in m for x in ['presentation','brochure','fact_sheet','company_presentation']):return '07_BROCHURE_PRESENTATION'
    if 'career' in m and 'job' not in m:return '08_CAREER_CONTACT'
    if 'current_job' in m:return '09_CURRENT_JOB'
    if any(x in m for x in ['archived_job','job_archive']):return '10_ARCHIVED_JOB'
    if any(x in m for x in ['business_council']):return '16_BUSINESS_CLUB'
    if any(x in m for x in ['conference','delegate','event_speaker']):return '15_CONFERENCE_EVENT'
    if any(x in m for x in ['forwarding_association','logistics_association']):return '14_LOGISTICS_ASSOCIATION'
    if any(x in m for x in ['industry_association','industry_brand','association_board']):return '13_INDUSTRY_ASSOCIATION'
    if any(x in m for x in ['industry_register','industry_security','ilu','transport_register']):return '19_INDUSTRY_REGISTER'
    if any(x in m for x in ['public_procurement','tender']):return '18_PUBLIC_TENDER'
    if any(x in m for x in ['related_group','partner_','group_company','partner_network','official_related']):return '20_PARTNER_GROUP'
    if any(x in m for x in ['business_social','linkedin']):return '22_BUSINESS_SOCIAL'
    if any(x in m for x in ['directory','vcard']) and 'industry' not in m:return '12_BUSINESS_DIRECTORY'
    if 'pdf_specific' in m:return '24_PDF_SPECIFIC_SEARCH'
    # Existing official crawler method IDs.
    if method=='M01_WKO_PROFILE':return '11_WKO_PROFILE'
    if method in ('M02_OFFICIAL_WEBSITE','M03_OFFICIAL_CONTACT'):return '01_OFFICIAL_CONTACT'
    if method=='M04_IMPRINT':return '03_IMPRESSUM'
    if method=='M05_TEAM_MANAGEMENT':return '02_TEAM_MANAGEMENT'
    if method=='M06_ABOUT_COMPANY':return '01_OFFICIAL_CONTACT'
    if method=='M08_OFFICIAL_PDF':return '05_OFFICIAL_PDF'
    if method=='M09_REPORT_PDF':return '06_ANNUAL_CSR'
    if method=='M10_PRESS_NEWS':return '04_PRESS_NEWS'
    if method=='M11_CAREER_JOBS':return '08_CAREER_CONTACT'
    # Existing external crawler method IDs/query families.
    if method=='M13_INDEXED_PDF' or q=='Q03_PDF':return '24_PDF_SPECIFIC_SEARCH'
    if method=='M14_EVENT_SPEAKER':return '15_CONFERENCE_EVENT'
    if method=='M15_ASSOCIATION_CLUB':return '13_INDUSTRY_ASSOCIATION'
    if method=='M16_JOB_ARCHIVE' or q=='Q05_JOBS':return '10_ARCHIVED_JOB'
    if method=='M17_MEDIA_PRESS':return '04_PRESS_NEWS'
    if method=='M18_PARTNER_CASESTUDY':return '20_PARTNER_GROUP'
    if method=='M19_PRESENTATION':return '07_BROCHURE_PRESENTATION'
    if method=='M20_VCARD':return '12_BUSINESS_DIRECTORY'
    if method=='M21_DIRECTORY':return '12_BUSINESS_DIRECTORY'
    if method=='M22_BUSINESS_SOCIAL':return '22_BUSINESS_SOCIAL'
    if method=='M23_TENDER_DOC':return '18_PUBLIC_TENDER'
    if q in ('Q01_DIRECT','Q02_MOBILE_DW') or method=='M24_GENERAL_WEB':return '23_EXACT_NAME_SEARCH'
    if 'official' in m:return '01_OFFICIAL_CONTACT'
    return '23_EXACT_NAME_SEARCH'

def is_historical(method,context='',title=''):
    x=(method+' '+context+' '+title).lower()
    return any(k in x for k in ['historical','2003','2013','2016','old / closed','archived'])

targets=read(f'{BASE}/targets.csv')
meta={r['no']:r for r in read(f'{BASE}/target_meta.csv')}
target_by_no={r['no']:r for r in targets}
primary_by_no={r['no']:split_people(r.get('primary_dm')) for r in targets}
person_to_nos=defaultdict(set)
for t in targets:
    for p in primary_by_no[t['no']]:person_to_nos[norm(p)].add(t['no'])

# ---------- Raw evidence universe ----------
ALL_FIELDS=['no','company','person','role','ownership_context','contact_type','contact','raw_contact_class','effective_class','method_raw','method_standard','source_url','source_title','query_family','origin','context','source_date','validation_state','confidence']
all_rows=[]; all_seen=set()

def add_all(no,company,person,ctype,contact,rawcls='',effcls='',method='',url='',title='',qfam='',origin='',context='',state='raw_unvalidated',confidence=''):
    if not no or not person or not contact:return
    t=target_by_no.get(str(no),{})
    k=(str(no),norm(person),ctype,norm_contact(contact),url or '',method or '',state)
    if k in all_seen:return
    all_seen.add(k)
    all_rows.append({'no':str(no),'company':company or t.get('company',''),'person':person,
      'role':'Primary Decision Maker (Geschäftsführung/Vorstand target)' if norm(person) in {norm(x) for x in primary_by_no.get(str(no),[])} else 'Additional public business contact',
      'ownership_context':t.get('owners',''),'contact_type':ctype,'contact':contact,'raw_contact_class':rawcls,'effective_class':effcls,
      'method_raw':method,'method_standard':method_standard(method,url,title,qfam,origin),'source_url':url,'source_title':title,'query_family':qfam,
      'origin':origin,'context':context,'source_date':year_from(context,title,url),'validation_state':state,'confidence':confidence})

# Raw official crawl from persistent chunks (full raw evidence, including false positives).
for f in sorted(glob.glob(f'{BASE}/official_chunks/*.csv')):
    for r in read(f):
        add_all(r.get('no'),r.get('company'),r.get('person'),r.get('contact_type'),r.get('contact'),r.get('contact_class'),'',
                r.get('method'),r.get('source_url'),r.get('source_title'),'','official_crawl',r.get('context'),'raw_official','')

# Raw external automated chunks. Manual files are added separately as validated evidence.
for f in sorted(glob.glob(f'{BASE}/external_chunks/*.csv')):
    if os.path.basename(f).startswith('manual_web_'):continue
    for r in read(f):
        add_all(r.get('no'),r.get('company'),r.get('person'),r.get('contact_type'),r.get('contact'),r.get('contact_class'),'',
                r.get('method'),r.get('source_url'),r.get('source_title'),r.get('query_family'),r.get('origin','external_automated'),r.get('context'),'raw_external','')

# ---------- Curated evidence used for final selection ----------
curated=defaultdict(list)  # (no, norm person) -> evidence

def add_curated(no,person,ctype,contact,cls,url='',method='',context='',title='',confidence='',state='validated'):
    if not no or not person or not contact:return
    no=str(no); t=target_by_no.get(no,{})
    row={'no':no,'company':t.get('company',''),'person':person,'contact_type':ctype,'contact':contact,'class':cls,'source_url':url or '',
         'source_title':title or '','method_raw':method or '','method_standard':method_standard(method,url,title),'context':context or '',
         'confidence':confidence or '','historical':is_historical(method,context,title),'source_date':year_from(context,title,url),'validation_state':state}
    curated[(no,norm(person))].append(row)
    add_all(no,t.get('company',''),person,ctype,contact,cls,cls,method,url,title,'','curated',context,state,confidence)

# Strong pre-existing targeted validation.
for r in read(f'{BASE}/validated_contacts.csv'):
    p=r.get('person',''); nos=person_to_nos.get(norm(p),set())
    if len(nos)!=1:continue
    no=next(iter(nos)); lvl=r.get('contact_level','')
    if r.get('mobile'):add_curated(no,p,'phone',r['mobile'],'mobile_public',r.get('source_url'),r.get('source_type'),r.get('notes'),'',
                                   r.get('confidence'),'validated_targeted')
    if r.get('direct_phone'):
        cls='named_management_line' if lvl=='direct_management_line' else ('direct_extension' if re.search(r'(?:-|\s)\d{2,5}$',r['direct_phone']) else 'direct_named')
        add_curated(no,p,'phone',r['direct_phone'],cls,r.get('source_url'),r.get('source_type'),r.get('notes'),'',r.get('confidence'),'validated_targeted')
    if r.get('direct_email'):
        em=r['direct_email']; cls='personal_email_verified'
        if lvl=='direct_management_line' or em.lower().startswith(GENERIC_EMAIL_PREFIX):cls='named_management_line'
        add_curated(no,p,'email',em,cls,r.get('source_url'),r.get('source_type'),r.get('notes'),'',r.get('confidence'),'validated_targeted')

# Manually researched multi-source evidence.
for f in sorted(glob.glob(f'{BASE}/external_chunks/manual_web_*.csv')):
    for r in read(f):
        add_curated(r.get('no'),r.get('person'),r.get('contact_type'),r.get('contact'),r.get('contact_class'),r.get('source_url'),r.get('method'),
                    r.get('context'),r.get('source_title'),'', 'validated_manual')

# Conservative official-best layer: shared phones are never treated as direct.
official=read(f'{BASE}/official_best_contacts.csv')
shared=defaultdict(set)
for r in official:
    if r.get('best_phone'):shared[(r['no'],norm_contact(r['best_phone']))].add(norm(r.get('person')))
for r in official:
    no=r.get('no'); p=r.get('person','')
    ph=r.get('best_phone',''); pc=r.get('phone_class','')
    if ph:
        sh=len(shared[(no,norm_contact(ph))])>1
        cls='mobile_public' if pc=='mobile_public' and not sh else 'central_fallback'
        add_curated(no,p,'phone',ph,cls,r.get('phone_source_url'),'official_best_conservative',
                    f"official_best raw_class={pc}; reported_source_count={r.get('phone_sources','')}; shared_across_target_people={sh}",'','', 'official_best_conservative')
    em=r.get('best_email',''); ec=r.get('email_class','')
    if em:
        cls='personal_email_verified' if ec=='personal_verified' and email_matches_person(em,p) else 'central_fallback'
        add_curated(no,p,'email',em,cls,r.get('email_source_url'),'official_best_conservative',
                    f"official_best raw_class={ec}; reported_source_count={r.get('email_sources','')}",'','', 'official_best_conservative')

# Company-level fallback for every target person, explicitly non-direct.
for t in targets:
    m=meta.get(t['no'],{})
    for p in primary_by_no[t['no']]:
        for ph in [x.strip() for x in (m.get('main_phones') or '').split('|') if x.strip()][:1]:
            add_curated(t['no'],p,'phone',ph,'central_fallback',t.get('wko_url'),'target_meta_fallback','Company main phone; not person-direct.','','','fallback')
        for em in [x.strip() for x in (m.get('main_emails') or '').split('|') if x.strip()][:1]:
            add_curated(t['no'],p,'email',em,'central_fallback',t.get('wko_url'),'target_meta_fallback','Company main e-mail; not person-direct.','','','fallback')

# Dedupe all raw/curated evidence after both layers were added.
all_rows.sort(key=lambda r:(int(r['no']) if r['no'].isdigit() else 9999,norm(r['person']),r['method_standard'],r['contact_type'],norm_contact(r['contact'])))
write(f'{BASE}/all_contact_evidence.csv',all_rows,ALL_FIELDS)

# ---------- Final one-row-per-primary-DM output ----------
FINAL_FIELDS=['no','company','person','role','ownership_context','management_context','status','best_contact','best_contact_class','mobile','direct_phone','direct_email','named_management_line','central_fallback','alternative_contacts','independent_source_count','confidence','evidence_urls','methods','notes','wko_url','websites']
final=[]
for t in targets:
    no=t['no']
    for p in primary_by_no[no]:
        ev=curated.get((no,norm(p)),[])
        byc={}
        for x in ev:
            k=(x['contact_type'],norm_contact(x['contact']))
            if not k[1]:continue
            if k not in byc:
                y=x.copy(); y['urls']=set([x['source_url']]) if x['source_url'] else set(); y['methods_set']=set([x['method_standard']]); y['contexts']=[x['context']] if x['context'] else []
                byc[k]=y
            else:
                y=byc[k]
                if CLASS_RANK.get(x['class'],99)<CLASS_RANK.get(y['class'],99):
                    keep_urls=y['urls'];keep_methods=y['methods_set'];keep_contexts=y['contexts'];y.update(x);y['urls']=keep_urls;y['methods_set']=keep_methods;y['contexts']=keep_contexts
                if x['source_url']:y['urls'].add(x['source_url'])
                y['methods_set'].add(x['method_standard'])
                if x['context'] and x['context'] not in y['contexts']:y['contexts'].append(x['context'])
                y['historical']=y.get('historical',False) and x.get('historical',False)
        vals=list(byc.values())
        # Current evidence beats historical within same class; then phone before email.
        vals.sort(key=lambda x:(CLASS_RANK.get(x['class'],99),1 if x.get('historical') else 0,0 if x['contact_type']=='phone' else 1,-len(x.get('urls',[]))))
        best=vals[0] if vals else None
        if best:
            rr=CLASS_RANK.get(best['class'],6);status=STATUS_BY_RANK.get(rr,'F_NO_PUBLIC_DIRECT_CONTACT_FOUND')
            nsrc=max(1,len(best.get('urls',set())))
            related=best.get('method_standard') in ('20_PARTNER_GROUP','12_BUSINESS_DIRECTORY','14_LOGISTICS_ASSOCIATION','15_CONFERENCE_EVENT','16_BUSINESS_CLUB','19_INDUSTRY_REGISTER')
            if best.get('historical'):conf='medium'
            elif rr<=2 and not related:conf='high'
            elif rr<=3:conf='medium-high' if related or nsrc==1 else 'high'
            elif rr<=4:conf='medium-high'
            else:conf='medium'
        else:
            status='F_NO_PUBLIC_DIRECT_CONTACT_FOUND';nsrc=0;conf='low'
        mobiles=[x['contact'] for x in vals if x['class']=='mobile_public']
        dphones=[x['contact'] for x in vals if x['class'] in ('direct_extension','direct_named')]
        emails=[x['contact'] for x in vals if x['class']=='personal_email_verified']
        named=[x['contact'] for x in vals if x['class']=='named_management_line']
        fallback=[x['contact'] for x in vals if x['class']=='central_fallback']
        alts=[x['contact'] for x in vals if not best or norm_contact(x['contact'])!=norm_contact(best['contact'])][:7]
        all_urls=[];all_methods=[]
        for x in vals:
            all_urls.extend(sorted(x.get('urls',set())));all_methods.extend(sorted(x.get('methods_set',set())))
        notes=''
        if best:
            notes=' | '.join(best.get('contexts',[])[:2])
            if best.get('historical'):notes=('Historical/age-adjusted evidence. '+notes).strip()
        final.append({'no':no,'company':t['company'],'person':p,'role':'Primary Decision Maker (Geschäftsführung/Vorstand target)',
          'ownership_context':t.get('owners',''),'management_context':t.get('management',''),'status':status,
          'best_contact':best['contact'] if best else '','best_contact_class':best['class'] if best else '',
          'mobile':' | '.join(dict.fromkeys(mobiles)),'direct_phone':' | '.join(dict.fromkeys(dphones)),'direct_email':' | '.join(dict.fromkeys(emails)),
          'named_management_line':' | '.join(dict.fromkeys(named)),'central_fallback':' | '.join(dict.fromkeys(fallback)),
          'alternative_contacts':' | '.join(dict.fromkeys(alts)),'independent_source_count':nsrc,'confidence':conf,
          'evidence_urls':' | '.join(dict.fromkeys([u for u in all_urls if u])),'methods':' | '.join(dict.fromkeys(all_methods)),
          'notes':notes,'wko_url':t.get('wko_url',''),'websites':t.get('websites','')})

write(f'{BASE}/final_contacts.csv',final,FINAL_FIELDS)

# ---------- Status summary ----------
status_counts=Counter(r['status'] for r in final)
write(f'{BASE}/final_status_summary.csv',[{'status':s,'persons':status_counts[s]} for s in STATUS_ORDER],['status','persons'])

# ---------- Method performance ----------
# Raw hit counts from normalized evidence + validated direct/fallback counts.
raw_by=defaultdict(list); curated_by=defaultdict(list)
for r in all_rows:
    raw_by[r['method_standard']].append(r)
for evs in curated.values():
    for r in evs:curated_by[r['method_standard']].append(r)

# Automated external attempted coverage is derived from persisted resume chunk filenames, even when hit CSV is header-only.
auto_nos=set()
for f in glob.glob(f'{BASE}/external_chunks/resume_*.csv'):
    m=re.search(r'resume_(\d+)_(\d+)\.csv$',f)
    if m:
        a,b=map(int,m.groups());auto_nos.update(str(x) for x in range(a,b+1))
auto_people=sum(len(primary_by_no.get(no,[])) for no in auto_nos)

PERF_FIELDS=['method','description','companies_checked','persons_checked','denominator_basis','raw_hits','valid_direct_hits','unique_mobile_hits','unique_durchwahl_or_named_phone_hits','personal_email_hits','named_management_hits','fallback_hits','false_positives','hit_rate']
perf=[]
for mid,desc in METHOD_CATALOG:
    raw=raw_by.get(mid,[]); cur=curated_by.get(mid,[])
    # Unique curated contact-level counts.
    uniq={(r['no'],norm(r['person']),r['contact_type'],norm_contact(r['contact']),r['class']) for r in cur}
    direct=[x for x in uniq if x[4] in DIRECT_CLASSES]
    mobiles=[x for x in uniq if x[4]=='mobile_public']
    phones=[x for x in uniq if x[4] in ('direct_extension','direct_named')]
    emails=[x for x in uniq if x[4]=='personal_email_verified']
    named=[x for x in uniq if x[4]=='named_management_line']
    fall=[x for x in uniq if x[4]=='central_fallback']
    invalid=0
    for r in raw:
        if r['contact_type']=='phone' and not strict_phone_valid(r['contact']):invalid+=1
        elif r['contact_type']=='email' and not email_valid(r['contact']):invalid+=1
    if mid in {'01_OFFICIAL_CONTACT','02_TEAM_MANAGEMENT','03_IMPRESSUM','04_PRESS_NEWS','05_OFFICIAL_PDF','06_ANNUAL_CSR','08_CAREER_CONTACT','11_WKO_PROFILE'}:
        companies_checked=len(targets);persons_checked=sum(len(v) for v in primary_by_no.values());basis='Official crawler attempted the full 118-company target universe; some companies lack a usable page of this subtype.'
    elif mid in {'23_EXACT_NAME_SEARCH','24_PDF_SPECIFIC_SEARCH','10_ARCHIVED_JOB','15_CONFERENCE_EVENT','13_INDUSTRY_ASSOCIATION'} and auto_nos:
        companies_checked=len(auto_nos);persons_checked=auto_people;basis='Automated external resume: persisted completed/attempted chunk ranges; manual targeted searches add evidence but are not counted in denominator.'
    else:
        people={(r['no'],norm(r['person'])) for r in cur};companies={r['no'] for r in cur}
        companies_checked=len(companies);persons_checked=len(people);basis='Manual targeted channel: denominator instrumentation was not complete; checked count is evidence-confirmed minimum, so hit rate is left blank.'
    hit_rate=''
    if basis.startswith('Official crawler') or basis.startswith('Automated external'):
        hit_rate=f"{(len({(x[0],x[1]) for x in direct})/persons_checked):.3f}" if persons_checked else ''
    perf.append({'method':mid,'description':desc,'companies_checked':companies_checked,'persons_checked':persons_checked,'denominator_basis':basis,
      'raw_hits':len(raw),'valid_direct_hits':len(direct),'unique_mobile_hits':len(mobiles),'unique_durchwahl_or_named_phone_hits':len(phones),
      'personal_email_hits':len(emails),'named_management_hits':len(named),'fallback_hits':len(fall),'false_positives':invalid,'hit_rate':hit_rate})
write(f'{BASE}/method_performance.csv',perf,PERF_FIELDS)

# ---------- README ----------
ranked=sorted(perf,key=lambda r:(r['valid_direct_hits'],r['unique_mobile_hits'],r['personal_email_hits']),reverse=True)
lines=[
 '# Spedition Decision-Maker Contact Enrichment — Final', '',
 f'- Target companies: {len(targets)}',
 f'- Primary decision makers: {len(final)}',
 '- Final statuses: '+', '.join(f"{s}={status_counts[s]}" for s in STATUS_ORDER),
 '- Priority: public personal mobile > direct extension/named direct > verified personal business e-mail > named management line > central fallback.',
 '- Shared phone numbers attached to multiple decision makers are downgraded and are not treated as direct.',
 '- Guessed e-mail patterns are never marked verified without an independent public source.',
 '- Historical public contacts are retained with age-adjusted confidence only when the person is independently confirmed as still relevant.',
 '- Raw official crawl is preserved in official_hits.csv / official_chunks. all_contact_evidence.csv adds normalized provenance and validation state.',
 '', '## Method performance (top by valid direct evidence)', ''
]
for r in ranked[:10]:lines.append(f"- {r['method']} {r['description']}: valid_direct_hits={r['valid_direct_hits']}, mobiles={r['unique_mobile_hits']}, direct_phones={r['unique_durchwahl_or_named_phone_hits']}, personal_emails={r['personal_email_hits']}")
lines += ['', '## Files', '', '- final_contacts.csv — one row per primary decision maker; no blank status.', '- all_contact_evidence.csv — normalized raw + curated evidence with provenance.', '- method_performance.csv — channel effectiveness statistics and denominator notes.', '- final_status_summary.csv — A–F status counts.', '', 'Generated from persistent GitHub checkpoints; no private/leaked/home contact data is used.']
with open(f'{BASE}/README_final.md','w',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')

print('companies',len(targets),'primary_people',len(final),'status',dict(status_counts),'all_evidence_rows',len(all_rows))
print('top_methods',[(r['method'],r['valid_direct_hits']) for r in ranked[:8]])
