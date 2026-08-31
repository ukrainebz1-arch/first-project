import argparse,base64,csv,datetime,html,io,os,re,time,urllib.parse,unicodedata,xml.etree.ElementTree as ET
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

PIPELINE_VERSION='v2.1'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
S=requests.Session()
S.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'})

EMAIL_RE=re.compile(r'(?<![\w.+-])([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})(?![\w.-])',re.I)
PHONE_RE=re.compile(r'(?<!\w)(?:(?:\+|00)\s?\d{1,3}|0\d{1,4})[\s()./\-]*\d{2,5}(?:[\s()./\-]*\d{2,6}){1,3}(?:\s*(?:DW|Durchwahl|ext\.?|extension)\s*\d{1,6})?',re.I)
GENERIC={'office','info','kontakt','contact','service','support','sales','booking','reception','sekretariat','secretary','verwaltung','karriere','jobs','hr','marketing','presse','press','dispatch','dispo','logistik','spedition','transport','mail'}
MOBILE_PREFIX=('650','651','652','653','655','656','657','658','659','660','661','663','664','665','666','667','668','669','670','671','676','677','678','679','680','681','682','683','684','685','686','687','688','689','690','691','699')
LEGAL_SUFFIX_RE=re.compile(r'\b(GmbH|Gesellschaft\s+m\.b\.H\.|m\.b\.H\.|AG|KG|OG|SE|Co\.?\s*KG|Ges\.m\.b\.H\.|Speditionsges\.m\.b\.H\.)\b',re.I)

BASE_QUERY_FAMILIES=[
    ('Q01_NAME_PHONE','"{person}" Telefon'),
    ('Q02_NAME_MOBILE','"{person}" Mobil OR Handy OR Durchwahl'),
    ('Q03_NAME_EMAIL','"{person}" E-Mail OR email'),
    ('Q04_COMPANY_PHONE','"{person}" "{company_core}" Telefon'),
    ('Q05_PDF','"{person}" filetype:pdf Telefon OR E-Mail'),
    ('Q06_ASSOCIATION','"{person}" Verband OR Verein OR Logistik OR Spedition'),
    ('Q07_EVENT','"{person}" Konferenz OR Kongress OR Vortrag OR Messe OR Speaker'),
    ('Q08_JOB','"{person}" Karriere OR Stellenanzeige OR Ansprechpartner OR jobs'),
    ('Q09_PRESS','"{person}" Presse OR News OR Interview OR Presseaussendung'),
    ('Q10_DIRECTORY','"{person}" FirmenABC OR WKO OR Herold OR Firmenatlas'),
    ('Q11_TENDER','"{person}" Ausschreibung OR Vergabe OR tender OR procurement'),
    ('Q12_PARTNER','"{person}" Partner OR Referenz OR case study OR Kunde'),
]

EVIDENCE_FIELDS=['no','company','person','contact_type','contact','contact_class','method','source_url','source_title','query_family','origin','context']
PROGRESS_FIELDS=['pipeline_version','no','company','person','query_family','query','search_result_count','pages_fetched','evidence_hits','status','checked_at']


def read_csv(path):
    if not path or not os.path.exists(path): return []
    with open(path,encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))


def write_csv(path,fields,rows):
    os.makedirs(os.path.dirname(path),exist_ok=True)
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)


def clean_person(p):
    p=re.sub(r'\([^)]*\)',' ',p or '')
    p=re.sub(r'\b(Mag\.?|DI|Ing\.?|MBA|MSc|MA|BSc|Dr\.?|FH|Dipl\.?\s*Kfm\.?)\b',' ',p,flags=re.I)
    p=re.sub(r'\b(jun\.?|sen\.?)\b',' ',p,flags=re.I)
    return re.sub(r'\s+',' ',p).strip(' ,')


def people(row):
    out=[]
    for field in ('primary_dm','management'):
        for p in (row.get(field) or '').split(';'):
            p=clean_person(p)
            if len(p.split())>=2 and p.lower() not in [x.lower() for x in out]: out.append(p)
    return out[:4]


def company_core(s):
    s=LEGAL_SUFFIX_RE.sub(' ',s or '')
    s=re.sub(r'[^\wÄÖÜäöüß&+.-]+',' ',s)
    return re.sub(r'\s+',' ',s).strip(' .,-')[:70]


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower()


def domain(u):
    try:
        d=urllib.parse.urlparse(u).netloc.lower().split(':')[0]
        return d[4:] if d.startswith('www.') else d
    except Exception:return ''


def website_domain(row,meta_by_no):
    raw=(row.get('websites') or '')
    if not raw and row.get('no') in meta_by_no: raw=meta_by_no[row['no']].get('websites') or ''
    for u in raw.split('|'):
        d=domain(u.strip())
        if d and not any(x in d for x in ['facebook.','linkedin.','instagram.']): return d
    return ''


def norm_phone(x):
    x=(x or '').strip()
    if not re.match(r'^(?:\+|00|0)',x): return ''
    if re.fullmatch(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}',x): return ''
    n=re.sub(r'[^0-9+]','',x)
    if n.startswith('00'): n='+'+n[2:]
    if n.startswith('0'): n='+43'+n[1:]
    if n.startswith('+430'): n='+43'+n[4:]
    digs=re.sub(r'\D','',n)
    return n if 8<=len(digs)<=15 else ''


def phone_class(raw):
    n=norm_phone(raw)
    if not n:return 'invalid'
    d=re.sub(r'\D','',n);at=d[2:] if d.startswith('43') else d
    if any(at.startswith(x) for x in MOBILE_PREFIX):return 'mobile_public'
    if re.search(r'\b(?:DW|Durchwahl|ext\.?|extension)\b',raw,re.I):return 'direct_extension'
    if re.search(r'[-/]\s*\d{2,5}\s*$',raw):return 'direct_extension_candidate'
    return 'direct_named_candidate'


def email_class(e,person):
    e=e.lower().strip(' .;,')
    if '@' not in e:return 'invalid'
    local=e.split('@')[0]
    if local in GENERIC or any(local.startswith(g+'.') or local.startswith(g+'-') for g in GENERIC):return 'generic_fallback'
    toks=[re.sub(r'[^a-z0-9]','',fold(x)) for x in clean_person(person).split()]
    simple=re.sub(r'[^a-z0-9]','',fold(local))
    if any(len(t)>=4 and t in simple for t in toks):return 'personal_email_verified'
    return 'personal_email_candidate'


def classify_source(url,title='',qfam=''):
    u=fold(url+' '+title);d=domain(url)
    if url.lower().endswith('.pdf') or ' pdf' in u:return 'M13_INDEXED_PDF'
    if any(x in u for x in ['konferenz','conference','kongress','congress','speaker','tagung','forum','event','symposium','messe']):return 'M14_EVENT_SPEAKER'
    if any(x in u for x in ['verband','association','verein','club','netzwerk','network','vnl.at','logistikclub','wirtschaftsbund','ilu-code']):return 'M15_ASSOCIATION_CLUB'
    if any(x in u for x in ['karriere','career','jobs','job','stellen','stepstone','indeed','hokify','jobs.at','karriere.at']):return 'M16_JOB_ARCHIVE'
    if any(x in u for x in ['presse','press','news','ots.at','leadersnet','medianet','wirtschaftszeit','logistik-express','dispo.cc']):return 'M17_MEDIA_PRESS'
    if any(x in u for x in ['partner','case-study','casestudy','referenz','reference','kunde','customer-story']):return 'M18_PARTNER_CASESTUDY'
    if any(x in u for x in ['presentation','prasentation','slideshare','slide','ppt','powerpoint','broschure','brochure']):return 'M19_PRESENTATION'
    if any(x in u for x in ['vcard','visitenkarte','business-card','contact-card']):return 'M20_VCARD'
    if any(x in d for x in ['firmenabc.','firmenatlas.','herold.','northdata.','kompany.','wirtschaft.at','firmen.wko.at']):return 'M21_DIRECTORY'
    if any(x in d for x in ['linkedin.com','xing.com']):return 'M22_BUSINESS_SOCIAL'
    if any(x in u for x in ['ausschreibung','tender','vergabe','procurement','ted.europa','bbg.gv']):return 'M23_TENDER_DOC'
    return 'M24_GENERAL_WEB'


def decode_bing_redirect(href):
    if not href:return ''
    href=html.unescape(href)
    try:
        p=urllib.parse.urlparse(href)
        if 'bing.com' not in p.netloc.lower():return href
        qs=urllib.parse.parse_qs(p.query)
        u=(qs.get('u') or [''])[0]
        if u.startswith('a1'):
            enc=u[2:];enc += '='*((4-len(enc)%4)%4)
            try:
                dec=base64.urlsafe_b64decode(enc.encode()).decode('utf-8','ignore')
                if dec.startswith('http'):return dec
            except Exception:pass
        for key in ('url','r'):
            v=(qs.get(key) or [''])[0]
            if v.startswith('http'):return v
    except Exception:pass
    return href


def bing_rss(q):
    url='https://www.bing.com/search?format=rss&q='+urllib.parse.quote_plus(q)+'&count=10'
    try:r=S.get(url,timeout=12)
    except Exception:return []
    if r.status_code!=200:return []
    out=[]
    try:
        root=ET.fromstring(r.text)
        for item in root.findall('.//item')[:8]:
            title=(item.findtext('title') or '').strip();href=(item.findtext('link') or '').strip();desc=(item.findtext('description') or '').strip()
            if href and domain(href)!='bing.com':out.append((html.unescape(title),href,BeautifulSoup(desc,'html.parser').get_text(' ',strip=True)))
    except Exception:return []
    return out


def bing_html(q):
    url='https://www.bing.com/search?q='+urllib.parse.quote_plus(q)+'&count=10&setlang=de-at'
    try:r=S.get(url,timeout=12)
    except Exception:return []
    if r.status_code!=200:return []
    s=BeautifulSoup(r.text,'html.parser');out=[]
    for li in s.select('li.b_algo')[:8]:
        a=li.select_one('h2 a');sn=li.select_one('.b_caption p')
        if not a:continue
        href=decode_bing_redirect(a.get('href',''))
        if not href or domain(href) in ('bing.com','www.bing.com'):continue
        out.append((a.get_text(' ',strip=True),href,sn.get_text(' ',strip=True) if sn else ''))
    return out


def search(q):
    rss=bing_rss(q)
    htmlr=bing_html(q)
    out=[];seen=set()
    for row in rss+htmlr:
        k=row[1].split('#')[0]
        if k not in seen:seen.add(k);out.append(row)
    return out[:8]


def visible(htmltxt):
    s=BeautifulSoup(htmltxt,'html.parser')
    for t in s(['script','style','noscript','svg']):t.decompose()
    return re.sub(r'\s+',' ',s.get_text(' ',strip=True))


def pdf_text(content):
    if not PdfReader:return ''
    try:
        reader=PdfReader(io.BytesIO(content));parts=[]
        for page in reader.pages[:50]:
            try:parts.append(page.extract_text() or '')
            except Exception:pass
        return re.sub(r'\s+',' ',' '.join(parts))[:500000]
    except Exception:return ''


def fetch_text(url,cache):
    key=url.split('#')[0]
    if key in cache:return cache[key]
    d=domain(url)
    if not d or any(x in d for x in ['linkedin.com','xing.com','facebook.com','instagram.com','bing.com']):cache[key]=('',url);return cache[key]
    try:
        r=S.get(url,timeout=10,allow_redirects=True)
        if r.status_code!=200:cache[key]=('',r.url);return cache[key]
        ct=r.headers.get('content-type','').lower()
        if 'pdf' in ct or r.url.lower().endswith('.pdf'):
            txt=pdf_text(r.content[:15_000_000])
        elif 'html' in ct or 'text/' in ct:
            txt=visible(r.text)[:500000]
        else:txt=''
        cache[key]=(txt,r.url);return cache[key]
    except Exception:
        cache[key]=('',url);return cache[key]


def snippets_near(text,person):
    if not text:return []
    names=clean_person(person).split();last=names[-1] if names else ''
    if len(last)<3:return []
    ft=fold(text);fl=fold(last);sp=[]
    for m in re.finditer(r'(?<!\w)'+re.escape(fl)+r'(?!\w)',ft):
        sp.append(text[max(0,m.start()-900):min(len(text),m.end()+1500)])
        if len(sp)>=8:break
    return sp


def extract(text,person,url,title,qfam,origin):
    out=[]
    for ctx in snippets_near(text,person):
        for e in sorted(set(EMAIL_RE.findall(ctx))):
            cls=email_class(e,person)
            if cls!='invalid':out.append({'person':person,'contact_type':'email','contact':e.lower(),'contact_class':cls,'method':classify_source(url,title,qfam),'source_url':url,'source_title':title,'query_family':qfam,'origin':origin,'context':ctx[:1600]})
        for m in PHONE_RE.finditer(ctx):
            raw=re.sub(r'\s+',' ',m.group(0)).strip(' .;,');n=norm_phone(raw)
            if not n:continue
            cls=phone_class(raw)
            if cls!='invalid':out.append({'person':person,'contact_type':'phone','contact':raw,'contact_class':cls,'method':classify_source(url,title,qfam),'source_url':url,'source_title':title,'query_family':qfam,'origin':origin,'context':ctx[:1600]})
    return out


def validated_people():
    out=set()
    for r in read_csv('data/spedition/contacts/validated_contacts.csv'):
        if (r.get('direct_phone') or r.get('mobile') or r.get('direct_email')):
            out.add((fold(r.get('company')),fold(clean_person(r.get('person')))))
    return out


def make_queries(person,row,meta_by_no):
    core=company_core(row.get('company'))
    d=website_domain(row,meta_by_no)
    qs=[(qf,tpl.format(person=person,company_core=core)) for qf,tpl in BASE_QUERY_FAMILIES]
    if d:qs.append(('Q13_OFFICIAL_DOMAIN',f'"{person}" site:{d} Telefon OR E-Mail OR Mobil'))
    return qs


def dedupe_evidence(rows):
    out=[];seen=set()
    for x in rows:
        norm=norm_phone(x.get('contact')) if x.get('contact_type')=='phone' else (x.get('contact') or '').lower()
        k=(x.get('no'),fold(x.get('person')),x.get('contact_type'),norm,(x.get('source_url') or '').split('#')[0],x.get('method'))
        if k not in seen:seen.add(k);out.append(x)
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--start',type=int,required=True);ap.add_argument('--end',type=int,required=True)
    ap.add_argument('--out',required=True);ap.add_argument('--progress-out',required=True)
    ap.add_argument('--include-validated',action='store_true')
    args=ap.parse_args()

    targets=[r for r in read_csv('data/spedition/contacts/targets.csv') if args.start<=int(r['no'])<=args.end]
    meta_by_no={r['no']:r for r in read_csv('data/spedition/contacts/target_meta.csv')}
    val=validated_people()
    evidence=read_csv(args.out)
    progress=read_csv(args.progress_out)
    done={(r.get('pipeline_version'),r.get('no'),fold(r.get('person')),r.get('query_family')) for r in progress if r.get('status') in ('DONE','SKIP_ALREADY_VALIDATED')}
    fetch_cache={}

    for row in targets:
        company=row['company'];no=row['no'];company_hits_before=len(evidence)
        for person in people(row):
            if not args.include_validated and (fold(company),fold(person)) in val:
                k=(PIPELINE_VERSION,no,fold(person),'VALIDATED_SKIP')
                if k not in done:
                    progress.append({'pipeline_version':PIPELINE_VERSION,'no':no,'company':company,'person':person,'query_family':'VALIDATED_SKIP','query':'','search_result_count':'0','pages_fetched':'0','evidence_hits':'0','status':'SKIP_ALREADY_VALIDATED','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
                    done.add(k)
                continue
            for qfam,q in make_queries(person,row,meta_by_no):
                key=(PIPELINE_VERSION,no,fold(person),qfam)
                if key in done:continue
                results=search(q);hits=[];pages=0
                for title,url,snip in results[:5]:
                    if not url:continue
                    # Snippets are evidence when the person and contact appear together.
                    hits.extend(extract(title+' '+snip,person,url,title,qfam,'search_snippet'))
                    txt,final_url=fetch_text(url,fetch_cache)
                    if txt:
                        pages+=1;hits.extend(extract(txt,person,final_url or url,title,qfam,'fetched_page'))
                for h in hits:
                    h['no']=no;h['company']=company;evidence.append(h)
                progress.append({'pipeline_version':PIPELINE_VERSION,'no':no,'company':company,'person':person,'query_family':qfam,'query':q,'search_result_count':str(len(results)),'pages_fetched':str(pages),'evidence_hits':str(len(hits)),'status':'DONE','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
                done.add(key)
                # Persist after every method so a cancelled job can resume exactly.
                evidence=dedupe_evidence(evidence);write_csv(args.out,EVIDENCE_FIELDS,evidence);write_csv(args.progress_out,PROGRESS_FIELDS,progress)
                time.sleep(.08)
        print(no,company,'people',len(people(row)),'new_hits',len(evidence)-company_hits_before,flush=True)

    evidence=dedupe_evidence(evidence);write_csv(args.out,EVIDENCE_FIELDS,evidence);write_csv(args.progress_out,PROGRESS_FIELDS,progress)
    print('DONE companies',len(targets),'evidence',len(evidence),'progress',len(progress),'out',args.out,flush=True)

if __name__=='__main__':main()
