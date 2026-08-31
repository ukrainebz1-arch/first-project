import argparse,base64,csv,html,re,urllib.parse,unicodedata,xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
S=requests.Session();S.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'})
LEGAL=re.compile(r'\b(gesellschaft\s+mit\s+beschr[aä]nkter\s+haftung|gesellschaft\s+m\.?\s*b\.?\s*h\.?|ges\.?\s*m\.?\s*b\.?\s*h\.?|gmbh|mbh|ag|kg|og|se|e\.?u\.?|co\.?\s*kg)\b',re.I)
FIELDS=['no','company','linkedin_url','linkedin_title','match_score','employee_min','employee_max','employee_evidence','snippet','source_mode','error']

def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def fold(s):
    s=''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower();s=s.replace('&',' und ');s=LEGAL.sub(' ',s);s=re.sub(r'[^a-z0-9]+',' ',s);return clean(s)
def tokens(s):return {x for x in fold(s).split() if len(x)>=2}
def similarity(a,b):
    A=tokens(a);B=tokens(b)
    if not A or not B:return 0
    # Recall-friendly: all target core tokens in result title is strongest.
    cover=len(A&B)/len(A);j=len(A&B)/len(A|B)
    return round(100*(0.7*cover+0.3*j))
def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
    import os;os.makedirs(os.path.dirname(p),exist_ok=True)
    with open(p,'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(rows)
def decode(href):
    href=html.unescape(href or '')
    try:
        p=urllib.parse.urlparse(href)
        if 'bing.com' not in p.netloc.lower():return href
        q=urllib.parse.parse_qs(p.query);u=(q.get('u') or [''])[0]
        if u.startswith('a1'):
            s=u[2:]+'='*((4-len(u[2:])%4)%4)
            try:
                z=base64.urlsafe_b64decode(s.encode()).decode('utf-8','ignore')
                if z.startswith('http'):return z
            except:pass
    except:pass
    return href
def search(q):
    out=[];seen=set()
    try:r=S.get('https://www.bing.com/search',params={'format':'rss','q':q,'count':10},timeout=15)
    except:r=None
    if r is not None and r.status_code==200:
        try:
            root=ET.fromstring(r.text)
            for it in root.findall('.//item')[:10]:
                t=clean(it.findtext('title') or '');u=clean(it.findtext('link') or '');d=clean(BeautifulSoup(it.findtext('description') or '','html.parser').get_text(' ',strip=True))
                if 'linkedin.com/company/' in u and u not in seen:seen.add(u);out.append((t,u,d,'rss'))
        except:pass
    try:r=S.get('https://www.bing.com/search',params={'q':q,'count':10,'setlang':'de-at'},timeout=15)
    except:r=None
    if r is not None and r.status_code==200:
        s=BeautifulSoup(r.text,'html.parser')
        for li in s.select('li.b_algo')[:10]:
            a=li.select_one('h2 a');p=li.select_one('.b_caption p')
            if not a:continue
            u=decode(a.get('href',''));t=clean(a.get_text(' ',strip=True));d=clean(p.get_text(' ',strip=True) if p else '')
            if 'linkedin.com/company/' in u and u not in seen:seen.add(u);out.append((t,u,d,'html'))
    return out
def parse_size(text):
    text=clean(text).replace('–','-').replace('—','-')
    pats=[
      r'(?:Größe|Unternehmensgröße|Company\s+size|Tamanho\s+da\s+empresa|Taille\s+de\s+l’entreprise)[^0-9]{0,40}([0-9\.]+)\s*-\s*([0-9\.]+)\s*(?:Beschäftigte|Mitarbeiter|employees|funcionários|employés)?',
      r'([0-9\.]+)\s*-\s*([0-9\.]+)\s+(?:Beschäftigte|Mitarbeiter|employees|funcionários|employés)',
      r'(?:Größe|Company\s+size)[^0-9]{0,30}([0-9\.]+)\+',
    ]
    for i,p in enumerate(pats):
        m=re.search(p,text,re.I)
        if not m:continue
        lo=int(m.group(1).replace('.',''))
        if i<2:
            hi=int(m.group(2).replace('.',''));return lo,hi,clean(m.group(0))
        return lo,None,clean(m.group(0))
    return None,None,''
def fetch_linkedin(u):
    try:
        r=S.get(u,timeout=15,allow_redirects=True)
        if r.status_code!=200:return ''
        return clean(BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True))[:150000]
    except:return ''
def one(no,company):
    rec={'no':no,'company':company,'linkedin_url':'','linkedin_title':'','match_score':'','employee_min':'','employee_max':'','employee_evidence':'','snippet':'','source_mode':'','error':''}
    q=f'site:linkedin.com/company "{company}" Austria OR Österreich'
    results=search(q);cands=[]
    for title,u,snip,mode in results:
        title_name=re.sub(r'\s*[|•-]\s*LinkedIn.*$','',title,flags=re.I)
        sc=similarity(company,title_name)
        # Require strong name identity; generic one-token names need near exact title.
        if sc>=78:cands.append((sc,title,u,snip,mode))
    if not cands:rec['error']='NO_STRONG_LINKEDIN_MATCH';return rec
    cands.sort(reverse=True);sc,title,u,snip,mode=cands[0]
    rec.update({'linkedin_url':u,'linkedin_title':title,'match_score':sc,'snippet':snip,'source_mode':mode})
    lo,hi,ev=parse_size(title+' '+snip)
    if lo is None:
        text=fetch_linkedin(u)
        lo,hi,ev=parse_size(text)
        if lo is not None:rec['source_mode']=mode+'+linkedin_page'
    if lo is not None:rec.update({'employee_min':lo,'employee_max':'' if hi is None else hi,'employee_evidence':ev})
    else:rec['error']='MATCH_NO_SIZE'
    return rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,required=True);ap.add_argument('--end',type=int,required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    rows=sorted(read('data/hausverwaltung/size_strict_v2/size_screening_strict_v2.csv'),key=lambda r:r['company_name'].casefold());out=[]
    for i,r in enumerate(rows,1):
        if not args.start<=i<=args.end:continue
        x=one(i,r['company_name']);out.append(x);write(args.out,out);print(i,r['company_name'],x['linkedin_title'],x['employee_min'],x['employee_max'],x['error'],flush=True)
    write(args.out,out);print('DONE',len(out))
if __name__=='__main__':main()
