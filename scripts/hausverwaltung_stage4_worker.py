#!/usr/bin/env python3
import argparse,csv,io,json,os,random,re,time
from urllib.parse import urljoin,urlparse,quote_plus,unquote
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
EMAIL_RE=re.compile(r'(?<![\w.+-])([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})(?![\w.-])',re.I)
PHONE_RE=re.compile(r'(?:(?:\+|00)\s?43[\s()./-]*|\b0)(?:\(?\d{1,5}\)?[\s./-]*){1,3}\d{2,6}(?:[\s./-]*(?:DW|Durchwahl|ext\.?|extension)?\s*\d{1,6})?',re.I)
GENERIC_LOCAL={'info','office','kontakt','contact','service','support','verwaltung','hausverwaltung','sekretariat','rezeption','reception','mail','hello','presse','press','marketing','jobs','karriere','bewerbung','buchhaltung','rechnung','vermietung','verkauf'}
MANAGEMENT_LOCAL=('geschaeftsfuehr','geschäftsführ','management','vorstand','direktion','leitung','gf@')
MOBILE_PREFIX=('650','651','652','653','655','656','657','658','659','660','661','663','664','665','666','667','668','669','670','671','676','677','678','679','680','681','682','683','684','685','686','687','688','689','690','691','699')
PHONE_LABEL=('telefon','tel.','tel:','phone','mobil','mobile','durchwahl','direkt','direct','dw:',' dw ','extension','ext.')
CENTRAL_LABEL=('zentrale','sekretariat','rezeption','reception','allgemeine anfragen','office','vermittlung')
PRIORITY_WORDS=('kontakt','contact','impress','team','management','geschäft','geschaeft','leitung','people','about','unternehmen','presse','press','news','download','publikation','bericht','brosch','karriere','career')
COMMON_PATHS=['/kontakt','/contact','/impressum','/team','/management','/geschaeftsfuehrung','/geschäftsführung','/unternehmen','/ueber-uns','/über-uns','/about','/presse','/news','/downloads','/publikationen','/sitemap.xml']
BAD_SEARCH_HOSTS=('facebook.com','instagram.com','x.com','twitter.com','pinterest.','youtube.com')


def host(u):
    try:return re.sub(r'^www\.','',urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0])
    except:return ''
def clean_name(s):
    s=re.sub(r'\b(?:Mag\.?|Dr\.?|DI|Ing\.?|MBA|MSc|MA|BSc|LL\.M\.?|MMag\.?|FH|MRICS)\b',' ',s or '',flags=re.I)
    return re.sub(r'\s+',' ',s).strip(' ,;')
def name_parts(s):
    return [re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ-]','',x).lower() for x in clean_name(s).split() if len(re.sub(r'\W','',x))>=2]
def people(row):
    out=[]
    for x in (row.get('primary_dm') or '').split(';'):
        n=clean_name(x)
        if len(n.split())>=2 and n not in out:out.append(n)
    return out
def norm_phone(x):
    raw=(x or '').strip()
    ext=''
    m=re.search(r'(?:DW|Durchwahl|ext\.?|extension)\s*[:.-]?\s*(\d{1,6})',raw,re.I)
    if m:ext=m.group(1)
    s=re.sub(r'[^0-9+]','',raw)
    if s.startswith('00'):s='+'+s[2:]
    if s.startswith('0') and not s.startswith('00'):s='+43'+s[1:]
    if s.startswith('+430'):s='+43'+s[4:]
    if ext and not s.endswith(ext):s=s+'-'+ext
    return s
def valid_phone(x):
    d=re.sub(r'\D','',norm_phone(x))
    return 8<=len(d)<=15 and not (len(d)==8 and d.startswith('20'))
def is_mobile(x):
    d=re.sub(r'\D','',norm_phone(x)); at=d[2:] if d.startswith('43') else d.lstrip('0')
    return any(at.startswith(p) for p in MOBILE_PREFIX)
def generic_email(e):
    local=e.lower().split('@')[0]
    return local in GENERIC_LOCAL or any(local.startswith(x+'.') or local.startswith(x+'-') for x in GENERIC_LOCAL)
def management_email(e,ctx=''):
    low=(e+' '+ctx).lower()
    return any(x in low for x in MANAGEMENT_LOCAL)
def person_email_match(e,p):
    local=re.sub(r'[^a-z]','',e.lower().split('@')[0]); parts=[re.sub(r'[^a-z]','',x) for x in name_parts(p)]
    if not parts:return False
    last=parts[-1]; first=parts[0]
    return (last and last in local) or (first and last and first[:1]+last in local) or (first and last and first+last[:1] in local)
def company_tokens(s):
    stop={'gmbh','mbh','kg','ag','co','und','immobilien','hausverwaltung','immobilienverwaltung','liegenschaftsmanagement','verwaltung','gesellschaft'}
    return [x for x in re.findall(r'[a-z0-9äöüß]{3,}',(s or '').lower()) if x not in stop]
def company_match(text,company):
    toks=company_tokens(company)[:5]
    low=(text or '').lower()
    return not toks or any(t in low for t in toks)


def get_url(u,timeout=12):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        ct=r.headers.get('content-type','').lower()
        if r.status_code==200:return r.url,ct,r.content[:5000000]
    except Exception:pass
    return '','',b''
def html_text(b):
    try:
        s=BeautifulSoup(b,'html.parser')
        for x in s(['script','style','noscript','svg']):x.decompose()
        return re.sub(r'\s+',' ',s.get_text(' ',strip=True))
    except:return ''
def pdf_text(b):
    try:
        reader=PdfReader(io.BytesIO(b)); out=[]
        for p in reader.pages[:80]:
            try:out.append(p.extract_text() or '')
            except:pass
        return re.sub(r'\s+',' ',' '.join(out))[:3000000]
    except:return ''
def decode_text(ct,b):
    if 'pdf' in ct:return pdf_text(b)
    return html_text(b)


def search(q):
    results=[]
    for base,kind in [('https://www.bing.com/search?q=','bing'),('https://html.duckduckgo.com/html/?q=','ddg')]:
        try:
            r=requests.get(base+quote_plus(q),headers=H,timeout=12)
            if r.status_code!=200:continue
            s=BeautifulSoup(r.text,'html.parser')
            if kind=='bing':
                for x in s.select('li.b_algo')[:10]:
                    a=x.select_one('h2 a'); p=x.select_one('.b_caption p')
                    if a:results.append({'url':a.get('href',''),'title':a.get_text(' ',strip=True),'snippet':p.get_text(' ',strip=True) if p else ''})
            else:
                for x in s.select('.result')[:10]:
                    a=x.select_one('.result__a'); p=x.select_one('.result__snippet')
                    if not a:continue
                    u=a.get('href',''); m=re.search(r'[?&]uddg=([^&]+)',u)
                    if m:u=unquote(m.group(1))
                    results.append({'url':u,'title':a.get_text(' ',strip=True),'snippet':p.get_text(' ',strip=True) if p else ''})
            if results:break
        except Exception:pass
    out=[]; seen=set()
    for x in results:
        u=x['url']
        if not u or u in seen or any(h in host(u) for h in BAD_SEARCH_HOSTS):continue
        seen.add(u);out.append(x)
    return out


def context_spans(text,person):
    parts=name_parts(person); pats=[]
    full=clean_name(person)
    if full:pats.append(re.compile(re.escape(full),re.I))
    if parts:pats.append(re.compile(r'\b'+re.escape(parts[-1])+r'\b',re.I))
    spans=[]
    for p in pats:
        spans=[m.span() for m in p.finditer(text)]
        if spans:break
    return spans[:12]
def classify_phone(raw,ctx):
    low=ctx.lower(); n=norm_phone(raw)
    if is_mobile(n) or 'mobil' in low or 'mobile' in low:return 'A_MOBILE_PUBLIC',100
    if any(x in low for x in ('durchwahl',' dw ','dw:','direkt','direct','extension',' ext.')):return 'B_DIRECT_DIAL',95
    if re.search(r'(?:[-/ ]0)\s*$',raw.strip()) or any(x in low for x in CENTRAL_LABEL):return 'E_CENTRAL_FALLBACK',20
    if any(x in low for x in PHONE_LABEL):return 'C_PERSON_BOUND_OFFICE',82
    return 'NONE',0
def classify_email(e,person,ctx):
    if management_email(e,ctx) and generic_email(e):return 'C_MANAGEMENT_NAMED',72
    if generic_email(e):return 'D_GENERAL_FALLBACK',20
    # It is public on a page/snippet explicitly containing the exact person. Name match is strongest,
    # but a non-generic address in the same compact person card remains a candidate for manual validation.
    if person_email_match(e,person):return 'A_PERSONAL_VERIFIED',96
    return 'A_PERSONAL_VERIFIED',80


def extract_person(text,person,company,url,source_kind,query=''):
    out=[]
    for st,en in context_spans(text,person):
        ctx=text[max(0,st-220):min(len(text),en+420)]
        if not company_match(ctx+' '+text[:500],company) and source_kind not in ('official_html','official_pdf'):continue
        for e in sorted(set(x.lower().strip(' .;,') for x in EMAIL_RE.findall(ctx))):
            cls,score=classify_email(e,person,ctx)
            out.append({'person':person,'contact_type':'email','contact':e,'contact_class':cls,'score':score,'source_url':url,'source_kind':source_kind,'query':query,'context':ctx[:800]})
        for raw in PHONE_RE.findall(ctx):
            raw=re.sub(r'\s+',' ',raw).strip(' .;,')
            if not valid_phone(raw):continue
            cls,score=classify_phone(raw,ctx)
            if score:
                out.append({'person':person,'contact_type':'phone','contact':norm_phone(raw),'contact_class':cls,'score':score,'source_url':url,'source_kind':source_kind,'query':query,'context':ctx[:800]})
    return out

def extract_fallback(text,url):
    emails=[];phones=[]
    for e in EMAIL_RE.findall(text):
        e=e.lower().strip(' .;,')
        if generic_email(e) or management_email(e,text[max(0,text.lower().find(e)-100):text.lower().find(e)+150]):emails.append(e)
    for raw in PHONE_RE.findall(text):
        if valid_phone(raw):phones.append(norm_phone(raw))
    return list(dict.fromkeys(phones))[:5],list(dict.fromkeys(emails))[:5]


def crawl_official(site,people_list,company):
    evidence=[];checked=[];fallback_p=[];fallback_e=[]
    if not site:return evidence,checked,fallback_p,fallback_e
    root=site if '://' in site else 'https://'+site
    fu,ct,b=get_url(root)
    if not b:return evidence,checked,fallback_p,fallback_e
    bh=host(fu);queue=[fu]+[urljoin(fu,p) for p in COMMON_PATHS];seen=set();pdfs=[]
    while queue and len(seen)<35:
        u=queue.pop(0).split('#')[0]
        if u in seen or (host(u) and host(u)!=bh):continue
        seen.add(u);uu,ct,b=get_url(u)
        if not b:continue
        t=decode_text(ct,b);checked.append(uu)
        sk='official_pdf' if 'pdf' in ct or uu.lower().endswith('.pdf') else 'official_html'
        if t:
            for p in people_list:evidence+=extract_person(t,p,company,uu,sk)
            if any(k in uu.lower() for k in ('kontakt','contact','impress','management','geschaeft','geschäft')) or uu==fu:
                ph,em=extract_fallback(t,uu);fallback_p+=ph;fallback_e+=em
        if sk=='official_html':
            try:
                s=BeautifulSoup(b,'html.parser')
                for a in s.find_all('a',href=True):
                    href=urljoin(uu,a['href']).split('#')[0]; lab=(a.get_text(' ',strip=True)+' '+href).lower()
                    if host(href)!=bh:continue
                    if href.lower().endswith('.pdf') and len(pdfs)<18:pdfs.append(href)
                    elif any(k in lab for k in PRIORITY_WORDS) and href not in seen and len(queue)<50:queue.append(href)
                if 'xml' in ct or uu.endswith('sitemap.xml'):
                    for loc in re.findall(r'<loc>(.*?)</loc>',b.decode('utf-8','ignore'),re.I):
                        if host(loc)==bh and any(k in loc.lower() for k in PRIORITY_WORDS):queue.append(loc)
            except:pass
    for u in list(dict.fromkeys(pdfs))[:18]:
        uu,ct,b=get_url(u,15)
        if not b:continue
        t=pdf_text(b);checked.append(uu)
        for p in people_list:evidence+=extract_person(t,p,company,uu,'official_pdf')
    return evidence,list(dict.fromkeys(checked)),list(dict.fromkeys(fallback_p)),list(dict.fromkeys(fallback_e))


def dedupe(rows):
    d={}
    for r in rows:
        k=(r['person'].lower(),r['contact_type'],r['contact'].lower())
        if k not in d:d[k]=dict(r,source_count=1,all_source_urls=r['source_url'])
        else:
            x=d[k];urls=set((x.get('all_source_urls') or '').split(' | '));urls.add(r['source_url']);urls.discard('');x['all_source_urls']=' | '.join(sorted(urls));x['source_count']=len(urls);x['score']=max(int(x['score']),int(r['score']))
            # Prefer a fetched page over a search snippet as representative source.
            if x.get('source_kind')=='search_snippet' and r.get('source_kind')!='search_snippet':
                for f in ('source_url','source_kind','query','context','contact_class'):x[f]=r.get(f,'')
    return list(d.values())


def research(row):
    company=row['company_name']; ps=people(row); evidence=[]; checked=[]; fp=[];fe=[]
    site=(row.get('website') or '').strip()
    ev,ch,p,e=crawl_official(site,ps,company);evidence+=ev;checked+=ch;fp+=p;fe+=e
    for p in ps:
        queries=[f'"{p}" "{company}" Telefon',f'"{p}" "{company}" E-Mail',f'"{p}" Mobil',f'"{p}" Durchwahl',f'"{p}" "{company}" filetype:pdf',f'"{p}" Hausverwaltung Kontakt']
        seen=set()
        for q in queries:
            for x in search(q):
                u=x['url'];blob=(x['title']+' '+x['snippet']).strip()
                if not u or u in seen:continue
                seen.add(u)
                evidence+=extract_person(blob,p,company,u,'search_snippet',q)
                # Search snippet is discovery only. Fetch public pages/PDFs for verification when possible.
                if 'linkedin.com' not in host(u):
                    uu,ct,b=get_url(u,10)
                    if b:
                        t=decode_text(ct,b);checked.append(uu);evidence+=extract_person(t,p,company,uu,'external_pdf' if 'pdf' in ct else 'external_page',q)
            time.sleep(random.uniform(.03,.08))
    evidence=dedupe(evidence)
    # Snippet-only evidence stays discoverable but is downgraded and cannot be auto-verified later.
    for h in evidence:
        if h.get('source_kind')=='search_snippet':h['score']=min(int(h['score']),65)
        h['score']=int(h['score'])+min(6,max(0,(int(h.get('source_count') or 1)-1)*3))
    return evidence,list(dict.fromkeys(checked)),list(dict.fromkeys(fp)),list(dict.fromkeys(fe))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    with open(a.input_csv,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    allhits=[];coverage=[]
    for i,row in enumerate(rows,1):
        hits,checked,fp,fe=research(row)
        for h in hits:
            h.update({'no':row['no'],'company_name':row['company_name'],'stage3_scope':row['stage3_scope'],'primary_dm':row['primary_dm'],'primary_dm_role':row['primary_dm_role']});allhits.append(h)
        coverage.append({'no':row['no'],'company_name':row['company_name'],'stage3_scope':row['stage3_scope'],'primary_dm':row['primary_dm'],'website':row.get('website',''),'checked_source_count':str(len(checked)),'checked_source_urls':' | '.join(checked),'fallback_phones':' | '.join(fp),'fallback_emails':' | '.join(fe),'machine_research_complete':'yes'})
        print(f'{i}/{len(rows)} #{row["no"]} {row["company_name"]}: people={len(people(row))} hits={len(hits)} checked={len(checked)}',flush=True)
    hf=['no','company_name','stage3_scope','primary_dm','primary_dm_role','person','contact_type','contact','contact_class','score','source_count','source_url','all_source_urls','source_kind','query','context']
    with open(os.path.join(a.output_dir,'evidence.csv'),'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=hf);w.writeheader();w.writerows([{k:r.get(k,'') for k in hf} for r in allhits])
    cf=['no','company_name','stage3_scope','primary_dm','website','checked_source_count','checked_source_urls','fallback_phones','fallback_emails','machine_research_complete']
    with open(os.path.join(a.output_dir,'coverage.csv'),'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=cf);w.writeheader();w.writerows(coverage)
    json.dump({'rows':len(rows),'evidence_rows':len(allhits),'machine_research_complete':sum(r['machine_research_complete']=='yes' for r in coverage)},open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2)

if __name__=='__main__':main()
