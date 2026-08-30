import csv,glob,os,re
from collections import defaultdict

TARGETS='data/spedition/contacts/targets.csv'
META='data/spedition/contacts/target_meta.csv'
CHUNKS='data/spedition/contacts/official_chunks/chunk_*.csv'
OUT_ALL='data/spedition/contacts/official_hits_validated.csv'
OUT_BEST='data/spedition/contacts/official_best_contacts.csv'

GENERIC_EMAIL={'office','info','kontakt','contact','service','support','sales','booking','reception','sekretariat','secretary','verwaltung','karriere','jobs','hr','marketing','presse','press','dispatch','dispo','logistik','spedition','transport'}
MOBILE_PREFIX=('650','651','652','653','655','656','657','658','659','660','661','663','664','665','666','667','668','669','670','671','676','677','678','679','680','681','682','683','684','685','686','687','688','689','690','691','699')

def read(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def norm_phone(x):
    x=(x or '').strip()
    # Keep only plausible public phone strings: must explicitly start with +, 00 or 0.
    if not re.match(r'^(?:\+|00|0)',x): return ''
    if re.fullmatch(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}',x): return ''
    n=re.sub(r'[^0-9+]','',x)
    if n.startswith('00'):n='+'+n[2:]
    if n.startswith('0') and not n.startswith('00'):n='+43'+n[1:]
    if n.startswith('+430'):n='+43'+n[4:]
    digs=re.sub(r'\D','',n)
    if not (8 <= len(digs) <= 15): return ''
    return n

def clean_person(p):
    p=re.sub(r'^\.\s*','',p or '').strip()
    p=re.sub(r'\b(Mag\.?|DI|Ing\.?|MBA|MSc|MA|BSc|Dr\.?|FH)\b',' ',p,flags=re.I)
    return re.sub(r'\s+',' ',p).strip(' ,')

def phone_class(raw, main_phones=''):
    n=norm_phone(raw)
    if not n:return 'invalid'
    digs=re.sub(r'\D','',n)
    at=digs[2:] if digs.startswith('43') else digs
    if any(at.startswith(x) for x in MOBILE_PREFIX):return 'mobile_public'
    mains=[]
    for m in re.split(r'\s*\|\s*',main_phones or ''):
        nm=norm_phone(m)
        if nm:mains.append(nm)
    if n in mains:return 'central_fallback'
    # A longer number extending a known switchboard stem is a strong Durchwahl signal.
    for m in mains:
        if len(n)>len(m) and n.startswith(m): return 'direct_extension'
        if len(m)>len(n) and m.startswith(n): return 'office_base'
    # Explicit DW/ext wording is a direct-extension signal.
    if re.search(r'\b(?:DW|Durchwahl|ext\.?|extension)\b',raw,re.I):return 'direct_extension'
    # Austrian fixed-line number in named-person context.
    return 'named_fixed_candidate'

def email_class(e,person,main_emails=''):
    e=(e or '').lower().strip(' .;,')
    if '@' not in e:return 'invalid'
    mains={x.lower().strip() for x in re.split(r'\s*\|\s*',main_emails or '') if x}
    local=e.split('@')[0]
    if e in mains:return 'central_fallback'
    if local in GENERIC_EMAIL or any(local.startswith(g+'.') or local.startswith(g+'-') for g in GENERIC_EMAIL):return 'generic_fallback'
    toks=[re.sub(r'[^a-z0-9]','',x.lower()) for x in clean_person(person).split()]
    simple=re.sub(r'[^a-z0-9]','',local)
    if toks and any(len(t)>=4 and t in simple for t in toks):return 'personal_verified'
    return 'personal_candidate'

def rank(cls):
    return {'mobile_public':100,'direct_extension':95,'personal_verified':90,'personal_candidate':80,'named_fixed_candidate':75,'office_base':55,'generic_fallback':30,'central_fallback':20}.get(cls,0)

def main():
    meta={r['no']:r for r in read(META)}
    target={r['no']:r for r in read(TARGETS)}
    rows=[]
    for f in glob.glob(CHUNKS):
        for r in read(f):
            no=r.get('no',''); person=clean_person(r.get('person',''))
            if no not in target or len(person.split())<2: continue
            m=meta.get(no,{})
            if r.get('contact_type')=='phone':
                normalized=norm_phone(r.get('contact',''))
                cls=phone_class(r.get('contact',''),m.get('main_phones',''))
            else:
                normalized=(r.get('contact') or '').lower().strip()
                cls=email_class(normalized,person,m.get('main_emails',''))
            if cls=='invalid':continue
            rr=dict(r);rr['person']=person;rr['normalized_contact']=normalized;rr['validated_class']=cls;rr['rank']=rank(cls)
            rows.append(rr)
    # dedupe exact evidence rows
    ded=[];seen=set()
    for r in rows:
        k=(r['no'],r['person'].lower(),r['contact_type'],r['normalized_contact'],r['source_url'])
        if k not in seen:seen.add(k);ded.append(r)
    # confirmation counts by independent source urls and methods
    grouped=defaultdict(list)
    for r in ded:grouped[(r['no'],r['person'].lower(),r['contact_type'],r['normalized_contact'])].append(r)
    for rs in grouped.values():
        urls=len(set(x['source_url'] for x in rs)); methods=len(set(x['method'] for x in rs))
        for x in rs:x['source_confirmations']=urls;x['method_confirmations']=methods
    fields=['no','company','person','contact_type','contact','normalized_contact','validated_class','rank','source_confirmations','method_confirmations','method','source_url','source_title','context']
    os.makedirs(os.path.dirname(OUT_ALL),exist_ok=True)
    with open(OUT_ALL,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(sorted(ded,key=lambda x:(int(x['no']),x['person'],-int(x['rank']))))
    # one best phone + email per person
    out=[]
    persons=defaultdict(list)
    for r in ded:persons[(r['no'],r['person'].lower())].append(r)
    for (no,_),rs in sorted(persons.items(),key=lambda kv:int(kv[0][0])):
        person=rs[0]['person']; company=rs[0]['company']
        ph=sorted([x for x in rs if x['contact_type']=='phone'],key=lambda x:(-int(x['rank']),-int(x['source_confirmations'])))
        em=sorted([x for x in rs if x['contact_type']=='email'],key=lambda x:(-int(x['rank']),-int(x['source_confirmations'])))
        bp=ph[0] if ph else {};be=em[0] if em else {}
        out.append({'no':no,'company':company,'person':person,'best_phone':bp.get('contact',''),'phone_class':bp.get('validated_class',''),'phone_sources':bp.get('source_confirmations',''),'phone_source_url':bp.get('source_url',''),'best_email':be.get('contact',''),'email_class':be.get('validated_class',''),'email_sources':be.get('source_confirmations',''),'email_source_url':be.get('source_url','')})
    bf=['no','company','person','best_phone','phone_class','phone_sources','phone_source_url','best_email','email_class','email_sources','email_source_url']
    with open(OUT_BEST,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=bf);w.writeheader();w.writerows(out)
    print('validated_evidence',len(ded),'companies',len(set(r['no'] for r in ded)),'people',len(out))
    from collections import Counter
    print('classes',Counter(r['validated_class'] for r in ded))
    print('best_direct_people',sum(1 for r in out if r['phone_class'] in ('mobile_public','direct_extension','named_fixed_candidate') or r['email_class'] in ('personal_verified','personal_candidate')))

if __name__=='__main__':main()
