#!/usr/bin/env python3
import argparse,csv,os,re,time,random
from urllib.parse import urlparse,urljoin,quote_plus,unquote
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
GENERIC={'office','info','kontakt','contact','service','support','kanzlei','sekretariat','secretary','verwaltung','karriere','jobs','hr','marketing','presse','press','bewerbung','mail','hello'}
MOBILE=('650','651','652','653','655','656','657','658','659','660','661','663','664','665','666','667','668','669','670','671','676','677','678','679','680','681','682','683','684','685','686','687','688','689','690','691','699')
EMAIL_RE=re.compile(r'(?<![\w.+-])([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})(?![\w.-])',re.I)
PHONE_RE=re.compile(r'(?:(?:\+|00)\s?43[\s()./-]*)?(?:\(?\d{1,5}\)?[\s./-]*){1,3}\d{2,6}(?:[\s./-]*(?:DW|Durchwahl|ext\.?|extension)?\s*\d{1,6})?',re.I)
PRIORITY=('kontakt','contact','impress','team','partner','management','geschäft','geschaeft','leitung','people','person','about','unternehmen','kanzlei','presse','press','news','karriere','career')
PATHS=['/kontakt','/contact','/impressum','/team','/partner','/management','/geschaeftsfuehrung','/geschäftsführung','/unternehmen','/ueber-uns','/über-uns','/about','/kanzlei','/presse','/news']

def host(u):
    try:return re.sub(r'^www\.','',urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0])
    except:return ''
def get(u,timeout=10):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and ('text/html' in r.headers.get('content-type','') or 'text/plain' in r.headers.get('content-type','')):
            r.encoding=r.apparent_encoding or r.encoding;return r.url,r.text[:1500000]
    except:pass
    return '',''
def text(h):
    b=BeautifulSoup(h or '','html.parser')
    for x in b(['script','style','noscript','svg']):x.decompose()
    return re.sub(r'\s+',' ',b.get_text(' ',strip=True))
def norm_phone(x):
    s=re.sub(r'[^0-9+]','',x or '')
    if s.startswith('00'):s='+'+s[2:]
    if s.startswith('0') and not s.startswith('00'):s='+43'+s[1:]
    if s.startswith('+430'):s='+43'+s[4:]
    return s
def valid_phone(x):
    n=norm_phone(x);d=re.sub(r'\D','',n)
    if len(d)<8 or len(d)>15:return False
    # avoid dates/years and VAT-like fragments
    return not (len(d)==8 and d.startswith('20'))
def name_parts(person):
    p=re.sub(r'\b(?:Mag\.?|Dr\.?|DI|Ing\.?|MBA|MSc|LL\.M\.|MMag\.?)\b',' ',person,flags=re.I)
    return [re.sub(r'[^A-Za-zÀ-ÖØ-öø-ÿ]','',x).lower() for x in p.split() if len(re.sub(r'\W','',x))>=2]
def email_class(e,person,ctx):
    e=e.lower().strip(' .;,');local=e.split('@')[0];parts=name_parts(person);cl=ctx.lower()
    if local in GENERIC or any(local.startswith(g+'.') or local.startswith(g+'-') for g in GENERIC):return 'generic_email',30
    last=parts[-1] if parts else '';first=parts[0] if parts else ''
    compact=re.sub(r'[^a-z]','',local)
    if last and last in compact and (not first or first[:1] in compact):return 'personal_verified_email',90
    if last and last in compact:return 'personal_candidate_email',82
    return 'named_context_email',70
def phone_class(p,ctx):
    n=norm_phone(p);d=re.sub(r'\D','',n);at=d[2:] if d.startswith('43') else d;cl=ctx.lower()
    if any(at.startswith(x) for x in MOBILE) or 'mobil' in cl or 'mobile' in cl:return 'mobile_public',100
    if any(k in cl for k in ['durchwahl',' dw ','dw:','direkt','direct','extension',' ext']):return 'direct_extension',95
    return 'named_fixed_candidate',75
def person_spans(t,person):
    last=(name_parts(person)[-1] if name_parts(person) else '')
    pats=[re.compile(re.escape(person),re.I)]
    if last:pats.append(re.compile(r'\b'+re.escape(last)+r'\b',re.I))
    for p in pats:
        s=[m.span() for m in p.finditer(t)]
        if s:return s[:8]
    return []
def extract(t,person,url,method):
    hits=[]
    for st,en in person_spans(t,person):
        ctx=t[max(0,st-650):min(len(t),en+1000)]
        for e in sorted(set(x.lower() for x in EMAIL_RE.findall(ctx))):
            cls,score=email_class(e,person,ctx);hits.append({'person':person,'contact_type':'email','contact':e,'contact_class':cls,'score':score,'source_url':url,'method':method,'context':ctx[:1000]})
        for raw in PHONE_RE.findall(ctx):
            p=re.sub(r'\s+',' ',raw).strip(' .;,')
            if not valid_phone(p):continue
            cls,score=phone_class(p,ctx);hits.append({'person':person,'contact_type':'phone','contact':norm_phone(p),'contact_class':cls,'score':score,'source_url':url,'method':method,'context':ctx[:1000]})
    return hits
def search(q):
    for base in ['https://www.bing.com/search?q=','https://html.duckduckgo.com/html/?q=']:
        try:
            r=requests.get(base+quote_plus(q),headers=H,timeout=10)
            if r.status_code!=200:continue
            b=BeautifulSoup(r.text,'html.parser');res=[]
            if 'bing.com' in base:
                for x in b.select('li.b_algo')[:10]:
                    a=x.select_one('h2 a');p=x.select_one('.b_caption p')
                    if a:res.append({'url':a.get('href',''),'title':a.get_text(' ',strip=True),'snippet':p.get_text(' ',strip=True) if p else ''})
            else:
                for x in b.select('.result')[:10]:
                    a=x.select_one('.result__a');p=x.select_one('.result__snippet')
                    if a:
                        u=a.get('href','');m=re.search(r'[?&]uddg=([^&]+)',u)
                        if m:u=unquote(m.group(1))
                        res.append({'url':u,'title':a.get_text(' ',strip=True),'snippet':p.get_text(' ',strip=True) if p else ''})
            if res:return res
        except:pass
    return []
def crawl(sites):
    pages=[];seen=set()
    for site in sites[:2]:
        u=site if '://' in site else 'https://'+site;fu,hh=get(u)
        if not hh:continue
        bh=host(fu);queue=[(fu,hh)]+[(urljoin(fu,p),None) for p in PATHS]
        while queue and len(pages)<22:
            uu,h=queue.pop(0);uu=uu.split('#')[0]
            if uu in seen or host(uu)!=bh:continue
            seen.add(uu)
            if h is None:uu,h=get(uu)
            if not h:continue
            pages.append((uu,text(h)))
            b=BeautifulSoup(h,'html.parser')
            for a in b.find_all('a',href=True):
                href=urljoin(uu,a['href']).split('#')[0];lab=(a.get_text(' ',strip=True)+' '+href).lower()
                if host(href)==bh and any(k in lab for k in PRIORITY) and href not in seen:queue.append((href,None))
    return pages
def people(row):
    out=[]
    for raw in (row.get('primary_dm') or '').split(';'):
        n=raw.strip()
        if len(n.split())>=2 and n not in out:out.append(n)
    return out[:4]
def dedupe(hits):
    d={}
    for h in hits:
        key=(h['person'].lower(),h['contact_type'],h['contact'].lower())
        if key not in d:d[key]=dict(h,source_count=1,method_count=1,all_source_urls=h['source_url'])
        else:
            x=d[key];urls=set(x['all_source_urls'].split(' | '));urls.add(h['source_url']);x['all_source_urls']=' | '.join(sorted(urls));x['source_count']=len(urls);x['score']=max(int(x['score']),int(h['score']))
    return list(d.values())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-csv',required=True);a=ap.parse_args();rows=list(csv.DictReader(open(a.input_csv,encoding='utf-8-sig',newline='')));allhits=[]
    for i,row in enumerate(rows,1):
        ps=people(row);sites=[x.strip() for x in (row.get('websites') or '').split(' | ') if x.strip()];hits=[]
        for u,t in crawl(sites):
            for p in ps:hits+=extract(t,p,u,'official_site')
        for p in ps:
            qs=[f'"{p}" "{row["group_name"]}" Telefon',f'"{p}" "{row["group_name"]}" E-Mail',f'"{p}" Mobil',f'"{p}" Durchwahl',f'"{p}" filetype:pdf']
            seenurls=set()
            for q in qs:
                for x in search(q):
                    u=x['url'];blob=x['title']+' '+x['snippet']
                    if not u or u in seenurls:continue
                    seenurls.add(u);hits+=extract(blob,p,u,'external_search_snippet')
                    if 'linkedin.com' not in host(u):
                        uu,hh=get(u,8)
                        if hh:hits+=extract(text(hh),p,uu,'external_page')
                time.sleep(random.uniform(.02,.06))
        hits=dedupe(hits)
        for h in hits:
            h['group_key']=row['group_key'];h['group_name']=row['group_name'];h['size_gate']=row.get('size_gate','');h['primary_dm']=row.get('primary_dm','')
            h['score']=int(h['score'])+min(8,max(0,(int(h['source_count'])-1)*4));allhits.append(h)
        print(f'{i}/{len(rows)} {row["group_name"]}: people={len(ps)} hits={len(hits)}',flush=True);time.sleep(random.uniform(.03,.10))
    fields=['group_key','group_name','size_gate','primary_dm','person','contact_type','contact','contact_class','score','source_count','method_count','source_url','all_source_urls','method','context']
    os.makedirs(os.path.dirname(a.output_csv) or '.',exist_ok=True)
    with open(a.output_csv,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(allhits)
if __name__=='__main__':main()
