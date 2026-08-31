import csv,glob,json,os,re,unicodedata
from collections import Counter,defaultdict
BASE='data/spedition/contacts'; OUT=f'{BASE}/final'
def read(path):
    if not os.path.exists(path): return []
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(path,rows,fields=None):
    os.makedirs(os.path.dirname(path),exist_ok=True); fields=fields or (list(rows[0]) if rows else [])
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def fold(s):return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower().strip()
def clean_person(p):
    p=re.sub(r'\([^)]*\)',' ',p or ''); p=re.sub(r'\b(Mag\.?|DI|Ing\.?|MBA|MSc|MA|BSc|Dr\.?|FH|Dipl\.?-?Bw\.?|Dipl\.?\s*Kfm\.?)\b',' ',p,flags=re.I)
    return re.sub(r'\s+',' ',p).strip(' ,')
def person_key(no,person):return (str(no).strip(),fold(clean_person(person)))
def norm_phone(x):
    x=re.sub(r'[^0-9+]','',x or '')
    if x.startswith('00'):x='+'+x[2:]
    if x.startswith('0'):x='+43'+x[1:]
    if x.startswith('+430'):x='+43'+x[4:]
    return x
def is_centralish(phone):return bool(re.search(r'(?:[-/. ]0|\.0)$',(phone or '').strip()))
def status_rank(s):return {'A_PUBLIC_MOBILE':6,'B_DIRECT_PHONE':5,'C_DIRECT_EMAIL_ONLY':4,'D_NAMED_MANAGEMENT_LINE':3,'E_CENTRAL_FALLBACK':2,'F_NO_PUBLIC_DIRECT_CONTACT':1}.get(s,0)
def confidence_rank(c):return {'high':4,'medium-high':3,'medium':2,'low':1}.get((c or '').lower(),0)
def classify_web(r):
    if (r.get('validation_status') or '').upper().startswith('HISTORICAL'):return None
    cc=(r.get('contact_class') or '').lower(); mobile=(r.get('mobile') or '').strip(); phone=(r.get('direct_phone') or '').strip(); email=(r.get('direct_email') or '').strip()
    if mobile and cc=='mobile_public':return 'A_PUBLIC_MOBILE'
    if phone and cc in ('direct_extension','direct_named') and not is_centralish(phone):return 'B_DIRECT_PHONE'
    if email and cc in ('personal_email_verified','personal_email_public') and not phone:return 'C_DIRECT_EMAIL_ONLY'
    if cc in ('named_management_line','direct_named') and (phone or email):return 'D_NAMED_MANAGEMENT_LINE'
    if phone or email:return 'E_CENTRAL_FALLBACK'
def baseline_to_evidence(r):
    s=r.get('baseline_status') or 'UNRESOLVED'
    if s=='UNRESOLVED':return None
    cc={'A_PUBLIC_MOBILE':'mobile_public','B_DIRECT_PHONE':'direct_extension','C_DIRECT_EMAIL_ONLY':'personal_email_verified'}.get(s,'central_fallback')
    return {'no':r['no'],'company':r['company'],'person':r['person'],'role':'','direct_phone':r.get('best_phone',''),'mobile':'','direct_email':r.get('best_email',''),'contact_class':cc,'source_url':r.get('source_url',''),'source_type':'existing_validated_or_official','method':'M00_EXISTING_BASELINE','context':r.get('reason',''),'source_date':'','independent_source_count':'1' if r.get('source_url') else '0','confidence':r.get('confidence',''),'validation_status':'VALID' if s!='E_CENTRAL_FALLBACK' else 'FALLBACK_ONLY','notes':r.get('reason',''),'_candidate_status':s}
targets=read(f'{BASE}/targets.csv'); meta={r['no']:r for r in read(f'{BASE}/target_meta.csv')}; baseline=read(f'{BASE}/baseline/baseline_primary_dm.csv')
web=[]
for p in sorted(glob.glob(f'{BASE}/external_web_chunks/web_*.csv')):web.extend(read(p))
dms=[]
for t in targets:
    for p0 in (t.get('primary_dm') or '').split(';'):
        p=clean_person(p0)
        if len(p.split())>=2:dms.append({'no':t['no'],'company':t['company'],'person':p,'owners':t.get('owners',''),'websites':t.get('websites',''),'wko_url':t.get('wko_url','')})
evidence=[]
for r in baseline:
    e=baseline_to_evidence(r)
    if e:evidence.append(e)
for r in web:
    x=dict(r);x['_candidate_status']=classify_web(r) or '';evidence.append(x)
seen=set();ded=[]
for e in evidence:
    k=(e.get('no',''),fold(e.get('person','')),e.get('source_url',''),norm_phone(e.get('mobile') or e.get('direct_phone')),fold(e.get('direct_email','')),e.get('contact_class',''))
    if k not in seen:seen.add(k);ded.append(e)
evidence=ded;by=defaultdict(list)
for e in evidence:by[person_key(e.get('no',''),e.get('person',''))].append(e)
final=[]
for d in dms:
    ev=by.get(person_key(d['no'],d['person']),[]);ranked=[]
    for e in ev:
        s=e.get('_candidate_status') or classify_web(e)
        if s:ranked.append((status_rank(s),confidence_rank(e.get('confidence')),int(e.get('independent_source_count') or 0),e,s))
    ranked.sort(key=lambda z:(z[0],z[1],z[2]),reverse=True);best=ranked[0] if ranked else None
    if best:
        e,s=best[3],best[4];phone=(e.get('direct_phone') or '').strip();mobile=(e.get('mobile') or '').strip();email=(e.get('direct_email') or '').strip()
        if s=='A_PUBLIC_MOBILE' and not mobile:mobile=phone;phone=''
        source=e.get('source_url','');conf=e.get('confidence','') or 'medium';role=e.get('role','');validation=e.get('validation_status','') or 'VALID';notes=e.get('notes','') or e.get('context','')
    else:s='F_NO_PUBLIC_DIRECT_CONTACT';phone=mobile=email=source=role='';conf='';validation='NO_DIRECT_FOUND';notes='No validated public person-specific contact found in existing official/validated evidence or external web pass.'
    m=meta.get(d['no'],{});central_phone=(m.get('main_phones') or '').split(' | ')[0].strip();central_email=(m.get('main_emails') or '').split(' | ')[0].strip();distinct_sources=sorted(set(x.get('source_url','') for x in ev if x.get('source_url')))
    final.append({'no':d['no'],'company':d['company'],'person':d['person'],'role':role,'owners':d['owners'],'status':s,'public_mobile':mobile,'direct_phone':phone,'direct_email':email,'central_phone_fallback':central_phone,'central_email_fallback':central_email,'confidence':conf,'validation_status':validation,'independent_sources':len(distinct_sources),'best_source_url':source,'websites':d['websites'] or m.get('websites',''),'wko_url':d['wko_url'],'notes':notes})
company_rows=[]
for t in targets:
    rows=[r for r in final if r['no']==t['no']];rows.sort(key=lambda r:(status_rank(r['status']),confidence_rank(r['confidence']),r['independent_sources']),reverse=True);pref=rows[0] if rows else None;c=Counter(r['status'][0] for r in rows)
    company_rows.append({'no':t['no'],'company':t['company'],'owners':t.get('owners',''),'best_status':pref['status'] if pref else 'F_NO_PUBLIC_DIRECT_CONTACT','preferred_person':pref['person'] if pref else '','preferred_role':pref['role'] if pref else '','preferred_mobile':pref['public_mobile'] if pref else '','preferred_direct_phone':pref['direct_phone'] if pref else '','preferred_email':pref['direct_email'] if pref else '','preferred_source_url':pref['best_source_url'] if pref else '','decision_makers':len(rows),'A_mobile':c.get('A',0),'B_direct_phone':c.get('B',0),'C_email_only':c.get('C',0),'D_named_line':c.get('D',0),'E_fallback':c.get('E',0),'F_unresolved':c.get('F',0),'website':t.get('websites',''),'wko_url':t.get('wko_url','')})
all_ev=[]
for e in evidence:
    candidate=e.get('_candidate_status') or classify_web(e) or 'NON_PROMOTED_EVIDENCE';all_ev.append({'no':e.get('no',''),'company':e.get('company',''),'person':clean_person(e.get('person','')),'role':e.get('role',''),'candidate_status':candidate,'direct_phone':e.get('direct_phone',''),'mobile':e.get('mobile',''),'direct_email':e.get('direct_email',''),'contact_class':e.get('contact_class',''),'method':e.get('method',''),'source_type':e.get('source_type',''),'source_url':e.get('source_url',''),'source_date':e.get('source_date',''),'independent_source_count':e.get('independent_source_count',''),'confidence':e.get('confidence',''),'validation_status':e.get('validation_status',''),'context':e.get('context',''),'notes':e.get('notes','')})
all_ev.sort(key=lambda r:(int(r['no'] or 0),fold(r['person']),r['candidate_status'],r['source_url']))
mp=[];methods=defaultdict(list)
for e in all_ev:methods[e['method'] or 'UNKNOWN'].append(e)
for method,rows in sorted(methods.items()):
    people=set((r['no'],fold(r['person'])) for r in rows);companies=set(r['no'] for r in rows);ad=set((r['no'],fold(r['person'])) for r in rows if r['candidate_status'][:1] in 'ABCD');ac=set((r['no'],fold(r['person'])) for r in rows if r['candidate_status'][:1] in 'ABC')
    mp.append({'method':method,'evidence_rows':len(rows),'unique_people_with_evidence':len(people),'unique_companies':len(companies),'people_A_to_D':len(ad),'people_A_to_C_direct':len(ac)})
status_counts=Counter(r['status'] for r in final);company_best=Counter(r['best_status'] for r in company_rows);metrics={'companies':len(company_rows),'decision_makers':len(final),'evidence_rows':len(all_ev),'status_counts':dict(status_counts),'company_best_status_counts':dict(company_best),'direct_reachable_A_to_C':sum(v for k,v in status_counts.items() if k.startswith(('A_','B_','C_'))),'named_or_better_A_to_D':sum(v for k,v in status_counts.items() if k.startswith(('A_','B_','C_','D_'))),'unresolved_F':status_counts.get('F_NO_PUBLIC_DIRECT_CONTACT',0),'generated_utc':'2026-08-31'}
os.makedirs(OUT,exist_ok=True);write(f'{OUT}/final_contacts.csv',final);write(f'{OUT}/company_summary.csv',company_rows);write(f'{OUT}/all_evidence.csv',all_ev);write(f'{OUT}/method_performance.csv',mp);write(f'{OUT}/direct_contacts_A_C.csv',[r for r in final if r['status'][0] in 'ABC']);write(f'{OUT}/fallback_D_E.csv',[r for r in final if r['status'][0] in 'DE']);write(f'{OUT}/unresolved_F.csv',[r for r in final if r['status'].startswith('F_')]);open(f'{OUT}/summary.json','w',encoding='utf-8').write(json.dumps(metrics,ensure_ascii=False,indent=2));print(json.dumps(metrics,ensure_ascii=False,indent=2))
