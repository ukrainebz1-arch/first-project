import argparse,base64,csv,datetime,html,io,os,re,time,urllib.parse,unicodedata,xml.etree.ElementTree as ET
from collections import defaultdict
import requests
from bs4 import BeautifulSoup
try:
    from pypdf import PdfReader
except Exception:
    PdfReader=None

PIPELINE_VERSION='size-v1.0'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
S=requests.Session();S.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'})
GROUP_MARKERS=['gruppe','group','konzern','weltweit','worldwide','international','länder','laender','standorte','locations','gesamt','europaweit','unternehmensgruppe','holding','global']
LEGAL=re.compile(r'\b(gmbh|mbh|gesellschaft\s+m\.?b\.?h\.?|gesellschaft\s+mit\s+beschr[aä]nkter\s+haftung|ag|kg|og|se|e\.?u\.?|co\.?\s*kg)\b',re.I)
QUERY_FAMILIES=[
 ('S01_EMPLOYEES','"{company}" Mitarbeiter'),
 ('S02_BESCHAEFTIGTE','"{company}" Beschäftigte OR Mitarbeiter:innen'),
 ('S03_HAUSVERWALTUNG','"{company}" Hausverwaltung Mitarbeiter'),
 ('S04_PDF','"{company}" filetype:pdf Mitarbeiter OR Beschäftigte'),
 ('S05_CAREER','"{company}" Karriere Mitarbeiter'),
 ('S06_LINKEDIN','"{company}" LinkedIn Mitarbeiter employees'),
]
EVIDENCE_FIELDS=['no','company','method','query_family','source_url','source_title','origin','employee_min','employee_max','employee_claim','claim_context','group_context','relevance_score']
PROGRESS_FIELDS=['pipeline_version','no','company','query_family','query','search_result_count','pages_fetched','evidence_hits','status','checked_at']

def read_csv(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_csv(p,fields,rows):
    os.makedirs(os.path.dirname(p),exist_ok=True)
    with open(p,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def fold(s):return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower()
def core_tokens(s):
    s=LEGAL.sub(' ',fold(s));s=re.sub(r'[^a-z0-9]+',' ',s)
    stop={'immobilien','immobilienverwaltung','hausverwaltung','verwaltung','real','estate','management','und','co','austria','osterreich','österreich'}
    return {t for t in s.split() if len(t)>=4 and t not in stop}
def domain(u):
    try:
        d=urllib.parse.urlparse(u).netloc.lower().split(':')[0]
        return d[4:] if d.startswith('www.') else d
    except:return ''
def groupish(s):
    t=fold(s);return any(x in t for x in GROUP_MARKERS)
def relevance(company,text):
    ct=core_tokens(company);ft=fold(text)
    if not ct:return 0
    hits=sum(1 for t in ct if t in ft)
    return round(100*hits/len(ct))

def employee_claims(text):
    text=clean(text);out=[];seen=set()
    pats=[
      (r'\b(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\s*[:\-]?\s*([0-9\.]{1,7})\s*[-–]\s*([0-9\.]{1,7})\b','range'),
      (r'\b([0-9\.]{1,7})\s*[-–]\s*([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\b','range'),
      (r'\b(?:über|mehr als|rund|ca\.?|circa|etwa|knapp|approximately|around|more than|over)\s*([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\b','single'),
      (r'\b([0-9\.]{1,7})\s*\+?\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\b','single'),
      (r'\b(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?|employees?)\s*[:\-]?\s*(?:rund|ca\.?|circa|etwa|über|mehr als)?\s*([0-9\.]{1,7})\b','single'),
    ]
    for pat,kind in pats:
        for m in re.finditer(pat,text,re.I):
            try:
                lo=int(m.group(1).replace('.',''));hi=int(m.group(2).replace('.','')) if kind=='range' else lo
            except:continue
            if 1900<=lo<=2035 or 1900<=hi<=2035:continue
            if lo<2 or hi>250000 or hi<lo:continue
            a=max(0,m.start()-350);b=min(len(text),m.end()+500);ctx=clean(text[a:b])
            key=(lo,hi,ctx)
            if key in seen:continue
            seen.add(key);out.append((lo,hi,m.group(0),ctx))
    return out

def decode_bing_redirect(href):
    if not href:return ''
    href=html.unescape(href)
    try:
        p=urllib.parse.urlparse(href)
        if 'bing.com' not in p.netloc.lower():return href
        qs=urllib.parse.parse_qs(p.query);u=(qs.get('u') or [''])[0]
        if u.startswith('a1'):
            enc=u[2:]+'='*((4-len(u[2:])%4)%4)
            try:
                dec=base64.urlsafe_b64decode(enc.encode()).decode('utf-8','ignore')
                if dec.startswith('http'):return dec
            except:pass
        for k in ('url','r'):
            v=(qs.get(k) or [''])[0]
            if v.startswith('http'):return v
    except:pass
    return href

def bing_rss(q):
    try:r=S.get('https://www.bing.com/search',params={'format':'rss','q':q,'count':10},timeout=15)
    except:return []
    if r.status_code!=200:return []
    out=[]
    try:
        root=ET.fromstring(r.text)
        for item in root.findall('.//item')[:8]:
            title=clean(item.findtext('title') or '');url=clean(item.findtext('link') or '');desc=BeautifulSoup(item.findtext('description') or '','html.parser').get_text(' ',strip=True)
            if url and domain(url)!='bing.com':out.append((title,url,desc))
    except:pass
    return out
def bing_html(q):
    try:r=S.get('https://www.bing.com/search',params={'q':q,'count':10,'setlang':'de-at'},timeout=15)
    except:return []
    if r.status_code!=200:return []
    s=BeautifulSoup(r.text,'html.parser');out=[]
    for li in s.select('li.b_algo')[:8]:
        a=li.select_one('h2 a');sn=li.select_one('.b_caption p')
        if not a:continue
        u=decode_bing_redirect(a.get('href',''))
        if u and domain(u) not in ('bing.com','www.bing.com'):out.append((clean(a.get_text(' ',strip=True)),u,clean(sn.get_text(' ',strip=True) if sn else '')))
    return out
def search(q):
    out=[];seen=set()
    for x in bing_rss(q)+bing_html(q):
        k=x[1].split('#')[0]
        if k not in seen:seen.add(k);out.append(x)
    return out[:8]
def visible(txt):
    s=BeautifulSoup(txt,'html.parser')
    for t in s(['script','style','noscript','svg']):t.decompose()
    return clean(s.get_text(' ',strip=True))
def pdf_text(content):
    if not PdfReader:return ''
    try:
        rd=PdfReader(io.BytesIO(content));parts=[]
        for p in rd.pages[:50]:
            try:parts.append(p.extract_text() or '')
            except:pass
        return clean(' '.join(parts))[:500000]
    except:return ''
def fetch_text(url,cache):
    key=url.split('#')[0]
    if key in cache:return cache[key]
    d=domain(url)
    if not d or any(x in d for x in ['linkedin.com','facebook.com','instagram.com','xing.com','bing.com']):cache[key]=('',url);return cache[key]
    try:
        r=S.get(url,timeout=12,allow_redirects=True)
        if r.status_code!=200:cache[key]=('',r.url);return cache[key]
        ct=r.headers.get('content-type','').lower()
        if 'pdf' in ct or r.url.lower().endswith('.pdf'):txt=pdf_text(r.content[:15_000_000])
        elif 'html' in ct or 'text/' in ct:txt=visible(r.text)[:500000]
        else:txt=''
        cache[key]=(txt,r.url);return cache[key]
    except:cache[key]=('',url);return cache[key]
def method(url,title=''):
    u=fold(url+' '+title);d=domain(url)
    if url.lower().endswith('.pdf') or ' pdf' in u:return 'SIZE_INDEXED_PDF'
    if 'karriere.at' in d or any(x in u for x in ['karriere','career','jobs','stellen']):return 'SIZE_CAREER'
    if any(x in d for x in ['linkedin.com','xing.com']):return 'SIZE_BUSINESS_SOCIAL_SNIPPET'
    if any(x in d for x in ['firmen.wko.at','firmenabc.','firmenatlas.','herold.','wirtschaft.at']):return 'SIZE_DIRECTORY'
    if any(x in u for x in ['jahresbericht','annual report','geschäftsbericht','geschaeftsbericht','csr','nachhaltigkeitsbericht']):return 'SIZE_REPORT'
    return 'SIZE_GENERAL_WEB'
def add_claims(store,company,no,qfam,url,title,origin,text):
    rel=relevance(company,title+' '+text[:5000]);hits=[]
    # Search snippets can be short; fetched pages require at least one meaningful company token.
    if origin=='fetched_page' and rel<34:return []
    for lo,hi,claim,ctx in employee_claims(text):
        hits.append({'no':no,'company':company,'method':method(url,title),'query_family':qfam,'source_url':url,'source_title':title,'origin':origin,'employee_min':lo,'employee_max':hi,'employee_claim':claim,'claim_context':ctx,'group_context':'yes' if groupish(ctx) else 'no','relevance_score':rel})
    store.extend(hits);return hits
def dedupe(rows):
    out=[];seen=set()
    for r in rows:
        k=(r['no'],r['source_url'].split('#')[0],r['employee_min'],r['employee_max'],r['claim_context'])
        if k not in seen:seen.add(k);out.append(r)
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,required=True);ap.add_argument('--end',type=int,required=True);ap.add_argument('--out',required=True);ap.add_argument('--progress-out',required=True);args=ap.parse_args()
    rows=read_csv('data/wko-immobilienverwalter/wko_immobilienverwalter_austria_unique.csv')
    rows=sorted(rows,key=lambda r:(clean(r.get('company_name','')).casefold(),r.get('firmaid','')))
    targets=[]
    for i,r in enumerate(rows,1):
        if args.start<=i<=args.end:targets.append((i,r))
    evidence=read_csv(args.out) if os.path.exists(args.out) else [];progress=read_csv(args.progress_out) if os.path.exists(args.progress_out) else []
    done={(r.get('no'),r.get('query_family')) for r in progress if r.get('status')=='DONE'};cache={}
    for no,r in targets:
        company=clean(r.get('company_name',''));before=len(evidence)
        for qfam,tpl in QUERY_FAMILIES:
            key=(str(no),qfam)
            if key in done:continue
            q=tpl.format(company=company);results=search(q);pages=0;new=[]
            for title,url,snip in results[:6]:
                new+=add_claims(evidence,company,str(no),qfam,url,title,'search_snippet',title+' '+snip)
                txt,final=fetch_text(url,cache)
                if txt:
                    pages+=1;new+=add_claims(evidence,company,str(no),qfam,final or url,title,'fetched_page',txt)
                if pages>=4:break
            progress.append({'pipeline_version':PIPELINE_VERSION,'no':no,'company':company,'query_family':qfam,'query':q,'search_result_count':len(results),'pages_fetched':pages,'evidence_hits':len(new),'status':'DONE','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()})
            done.add(key);evidence=dedupe(evidence);write_csv(args.out,EVIDENCE_FIELDS,evidence);write_csv(args.progress_out,PROGRESS_FIELDS,progress);time.sleep(.06)
        print(no,company,'new_evidence',len(evidence)-before,flush=True)
    evidence=dedupe(evidence);write_csv(args.out,EVIDENCE_FIELDS,evidence);write_csv(args.progress_out,PROGRESS_FIELDS,progress)
    print('DONE targets',len(targets),'evidence',len(evidence),'progress',len(progress),flush=True)
if __name__=='__main__':main()
