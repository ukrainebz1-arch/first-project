import argparse,csv,io,json,os,re,time,urllib.parse,requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'})
GENERIC_EMAIL={'office','info','kontakt','contact','service','support','sales','booking','reception','sekretariat','secretary','verwaltung','karriere','jobs','hr','marketing','presse','press','dispatch','dispo'}
MOBILE_PREFIX=('650','651','652','653','655','656','657','658','659','660','661','663','664','665','666','667','668','669','670','671','676','677','678','679','680','681','682','683','684','685','686','687','688','689','690','691','699')
PRIORITY_TOKENS=['kontakt','contact','impress','team','management','geschaeft','geschäft','leitung','about','unternehmen','ueber','über','company','people','karriere','career','jobs','presse','press','news','download','media','ansprech','staff','vorstand']
GENERATED_PATHS=['/kontakt','/contact','/impressum','/imprint','/team','/management','/geschaeftsfuehrung','/geschäftsführung','/unternehmen','/ueber-uns','/über-uns','/about-us','/company','/karriere','/career','/jobs','/presse','/press','/news','/downloads','/download','/media']
PHONE_RE=re.compile(r'(?:(?:\+|00)\s?\d{1,3}[\s()./-]*)?(?:\(?\d{2,5}\)?[\s./-]*){1,3}\d{2,5}(?:[\s./-]*(?:DW|Durchwahl|ext\.?|extension)?\s*\d{1,6})?',re.I)
EMAIL_RE=re.compile(r'(?<![\w.+-])([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})(?![\w.-])',re.I)

def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def clean_name(s):
    s=re.sub(r'\([^)]*\)',' ',s or '')
    s=re.sub(r'\b(Mag\.?|DI|Ing\.?|MBA|MSc|MA|BSc|Dr\.?|FH)\b',' ',s,flags=re.I)
    return re.sub(r'\s+',' ',s).strip(' ,')

def people(row):
    vals=[]
    for field in ('primary_dm','management'):
        for p in (row.get(field) or '').split(';'):
            p=clean_name(p)
            if len(p.split())>=2 and p not in vals: vals.append(p)
    return vals

def main_domain(url):
    try:
        h=urllib.parse.urlparse(url).netloc.lower().split(':')[0]
        return h[4:] if h.startswith('www.') else h
    except:return ''

def norm_phone(x):
    x=re.sub(r'[^0-9+]','',x or '')
    if x.startswith('00'):x='+'+x[2:]
    if x.startswith('0') and not x.startswith('00'):x='+43'+x[1:]
    if x.startswith('+430'):x='+43'+x[4:]
    return x

def phone_kind(p,main_phones):
    n=norm_phone(p); digs=re.sub(r'\D','',n)
    if not n or len(digs)<8:return 'invalid'
    mains={norm_phone(x) for x in re.split(r'\s*\|\s*',main_phones or '') if x}
    if n in mains:return 'central_exact'
    at=digs[2:] if digs.startswith('43') else digs
    if any(at.startswith(x) for x in MOBILE_PREFIX):return 'mobile'
    return 'direct_or_office'

def email_kind(e,main_emails):
    e=e.lower().strip('.;, ')
    mains={x.lower().strip() for x in re.split(r'\s*\|\s*',main_emails or '') if x}
    if e in mains:return 'central_exact'
    local=e.split('@')[0]
    if local in GENERIC_EMAIL or any(local.startswith(g+'.') or local.startswith(g+'-') for g in GENERIC_EMAIL):return 'generic'
    return 'personal_or_direct'

def get(url,timeout=18):
    try:
        r=S.get(url,timeout=timeout,allow_redirects=True)
        ct=r.headers.get('content-type','').lower()
        if r.status_code==200:return r,ct
    except Exception:pass
    return None,''

def visible_text(html):
    s=BeautifulSoup(html,'html.parser')
    for t in s(['script','style','noscript','svg']):t.decompose()
    return re.sub(r'\s+',' ',s.get_text(' ',strip=True))

def method_for(url,kind='html'):
    u=url.lower()
    if 'firmen.wko.at' in u:return 'M01_WKO_PROFILE'
    if kind=='pdf':
        if any(x in u for x in ['annual','jahr','report','csr','nachhalt','geschaeft','geschäft']):return 'M09_REPORT_PDF'
        return 'M08_OFFICIAL_PDF'
    if any(x in u for x in ['kontakt','contact']):return 'M03_OFFICIAL_CONTACT'
    if any(x in u for x in ['impress','imprint']):return 'M04_IMPRINT'
    if any(x in u for x in ['team','management','geschaeftsf','geschäftsf','vorstand','leitung','people']):return 'M05_TEAM_MANAGEMENT'
    if any(x in u for x in ['ueber','über','about','unternehmen','company']):return 'M06_ABOUT_COMPANY'
    if any(x in u for x in ['karriere','career','jobs','stellen']):return 'M11_CAREER_JOBS'
    if any(x in u for x in ['presse','press','news','media']):return 'M10_PRESS_NEWS'
    return 'M02_OFFICIAL_WEBSITE'

def person_hits(text,person):
    toks=person.split(); last=toks[-1] if toks else ''
    full=re.compile(re.escape(person),re.I)
    last_re=re.compile(r'\b'+re.escape(last)+r'\b',re.I) if last else None
    spans=[m.span() for m in full.finditer(text)]
    if not spans and last_re:spans=[m.span() for m in last_re.finditer(text)]
    return spans[:8]

def extract_near(text,person,url,method,main_phones,main_emails,source_title=''):
    out=[]; spans=person_hits(text,person)
    for st,en in spans:
        ctx=text[max(0,st-650):min(len(text),en+900)]
        emails=sorted(set(x.lower() for x in EMAIL_RE.findall(ctx)))
        phones=[]
        for m in PHONE_RE.findall(ctx):
            p=re.sub(r'\s+',' ',m).strip(' .;,')
            n=norm_phone(p)
            if len(re.sub(r'\D','',n))>=8: phones.append(p)
        phones=list(dict.fromkeys(phones))[:12]
        for e in emails[:10]:
            out.append({'person':person,'contact_type':'email','contact':e,'contact_class':email_kind(e,main_emails),'method':method,'source_url':url,'source_title':source_title,'context':ctx[:1000]})
        for p in phones:
            out.append({'person':person,'contact_type':'phone','contact':p,'contact_class':phone_kind(p,main_phones),'method':method,'source_url':url,'source_title':source_title,'context':ctx[:1000]})
    return out

def external_sites_from_wko(url):
    out=[]
    r,ct=get(url)
    if not r:return out
    try:
        s=BeautifulSoup(r.text,'html.parser')
        for a in s.find_all('a',href=True):
            h=urllib.parse.urljoin(r.url,a['href'])
            d=main_domain(h)
            if d and 'wko.at' not in d and not any(x in d for x in ['facebook.com','instagram.com','linkedin.com','youtube.com','google.com','maps.']):out.append(h)
    except:pass
    return list(dict.fromkeys(out))[:10]

def domain_seeds(row,meta):
    urls=[]
    for u in re.split(r'\s*\|\s*',row.get('websites') or ''):
        if u:urls.append(u)
    for u in re.split(r'\s*\|\s*',meta.get('websites') or ''):
        if u:urls.append(u)
    for e in re.split(r'\s*\|\s*',meta.get('main_emails') or ''):
        if '@' in e:
            d=e.split('@')[-1].strip().lower()
            if d and d not in ['gmail.com','outlook.com','hotmail.com','gmx.at','aon.at']:urls.append('https://'+d+'/')
    urls.extend(external_sites_from_wko(row.get('wko_url') or ''))
    final=[]
    for u in urls:
        if not re.match(r'https?://',u,re.I):u='https://'+u.lstrip('/')
        d=main_domain(u)
        if d and u not in final:final.append(u)
    return final[:8]

def crawl_domain(seed,max_pages=38,max_pdfs=12):
    d=main_domain(seed); parsed=urllib.parse.urlparse(seed); base=f'{parsed.scheme or "https"}://{parsed.netloc}'
    queue=[seed]+[urllib.parse.urljoin(base,p) for p in GENERATED_PATHS]
    # sitemap discovery
    for sm in ['/sitemap.xml','/sitemap_index.xml']:
        r,ct=get(urllib.parse.urljoin(base,sm))
        if r and ('xml' in ct or '<loc>' in r.text):
            locs=re.findall(r'<loc>(.*?)</loc>',r.text,re.I|re.S)
            for u in locs[:1200]:
                u=u.replace('&amp;','&').strip()
                if main_domain(u)==d and (any(t in u.lower() for t in PRIORITY_TOKENS) or u.lower().endswith('.pdf')):queue.append(u)
    seen=set(); html=[]; pdfs=[]
    while queue and len(html)<max_pages:
        u=queue.pop(0).split('#')[0]
        if u in seen or main_domain(u)!=d:continue
        seen.add(u)
        if u.lower().endswith('.pdf'):
            if len(pdfs)<max_pdfs:pdfs.append(u)
            continue
        r,ct=get(u)
        if not r or 'html' not in ct:continue
        html.append((r.url,r.text))
        s=BeautifulSoup(r.text,'html.parser')
        for a in s.find_all('a',href=True):
            h=urllib.parse.urljoin(r.url,a['href']).split('#')[0]
            if main_domain(h)!=d:continue
            low=h.lower()
            if low.endswith('.pdf'):
                if len(pdfs)<max_pdfs:pdfs.append(h)
            elif any(t in low for t in PRIORITY_TOKENS) and h not in seen and h not in queue:queue.append(h)
    return html,list(dict.fromkeys(pdfs))[:max_pdfs]

def pdf_text(url):
    r,ct=get(url,25)
    if not r or not (url.lower().endswith('.pdf') or 'pdf' in ct):return ''
    try:
        rd=PdfReader(io.BytesIO(r.content)); parts=[]
        for p in rd.pages[:60]:
            try:parts.append(p.extract_text() or '')
            except:pass
        return re.sub(r'\s+',' ',' '.join(parts))
    except:return ''

def dedupe_hits(hits):
    seen=set(); out=[]
    for h in hits:
        key=(h['person'].lower(),h['contact_type'],norm_phone(h['contact']) if h['contact_type']=='phone' else h['contact'].lower(),h['source_url'])
        if key not in seen:
            seen.add(key);out.append(h)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,required=True);ap.add_argument('--end',type=int,required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    targets=read_csv('data/spedition/contacts/targets.csv'); meta={r['no']:r for r in read_csv('data/spedition/contacts/target_meta.csv')}
    targets=[r for r in targets if args.start<=int(r['no'])<=args.end]
    fields=['no','company','person','contact_type','contact','contact_class','method','source_url','source_title','context']
    allhits=[]
    for ix,row in enumerate(targets,1):
        m=meta.get(row['no'],{}); ps=people(row); hits=[]
        # WKO profile itself
        wu=row.get('wko_url') or ''
        if wu:
            r,ct=get(wu)
            if r:
                txt=visible_text(r.text)
                for p in ps:hits += extract_near(txt,p,r.url,'M01_WKO_PROFILE',m.get('main_phones',''),m.get('main_emails',''),'WKO')
        seeds=domain_seeds(row,m)
        for seed in seeds[:4]:
            html,pdfs=crawl_domain(seed)
            for u,h in html:
                s=BeautifulSoup(h,'html.parser'); title=s.title.get_text(' ',strip=True)[:200] if s.title else ''
                txt=visible_text(h); meth=method_for(u)
                for p in ps:hits += extract_near(txt,p,u,meth,m.get('main_phones',''),m.get('main_emails',''),title)
            for u in pdfs:
                txt=pdf_text(u)
                if not txt:continue
                meth=method_for(u,'pdf')
                for p in ps:hits += extract_near(txt,p,u,meth,m.get('main_phones',''),m.get('main_emails',''),'PDF')
        hits=dedupe_hits(hits)
        for h in hits:h.update({'no':row['no'],'company':row['company']})
        allhits.extend(hits)
        print(f"{row['no']} {row['company']}: people={len(ps)} seeds={len(seeds)} hits={len(hits)}",flush=True)
    os.makedirs(os.path.dirname(args.out),exist_ok=True)
    with open(args.out,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(allhits)
    print('DONE targets',len(targets),'hits',len(allhits),'out',args.out)
if __name__=='__main__':main()
