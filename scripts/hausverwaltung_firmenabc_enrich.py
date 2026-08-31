import argparse,base64,csv,io,os,re,urllib.parse,xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
S=requests.Session();S.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'})
LEGAL=re.compile(r'\b(gesellschaft\s+mit\s+beschr[aä]nkter\s+haftung|gesellschaft\s+m\.?\s*b\.?\s*h\.?|ges\.?\s*m\.?\s*b\.?\s*h\.?|gmbh|mbh|ag|kg|og|se|e\.?\s*u\.?|co\.?\s*kg)\b',re.I)
FIELDS=['no','company','firmenabc_url','profile_title','match_class','match_score','owners','management','latest_report_date','employee_min','employee_max','employee_evidence','report_url','error']

def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def fold(s):
    import unicodedata
    s=''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower()
    s=s.replace('&',' und ');s=LEGAL.sub(' ',s);s=re.sub(r'[^a-z0-9]+',' ',s)
    return clean(s)
def toks(s):return set(fold(s).split())
def score(a,b):
    A=toks(a);B=toks(b)
    if not A or not B:return 0
    return round(100*len(A&B)/len(A|B))
def read_csv(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
    os.makedirs(os.path.dirname(p),exist_ok=True)
    with open(p,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore');w.writeheader();w.writerows(rows)
def bing(q):
    out=[]
    try:r=S.get('https://www.bing.com/search',params={'format':'rss','q':q,'count':8},timeout=15)
    except:return out
    if r.status_code==200:
        try:
            root=ET.fromstring(r.text)
            for item in root.findall('.//item')[:8]:
                u=clean(item.findtext('link') or '');t=clean(item.findtext('title') or '');d=clean(BeautifulSoup(item.findtext('description') or '','html.parser').get_text(' ',strip=True))
                if 'firmenabc.at/' in u:out.append((t,u,d))
        except:pass
    return out
def fetch(url):
    try:
        r=S.get(url,timeout=20,allow_redirects=True)
        return r if r.status_code==200 else None
    except:return None

def profile_match(company):
    results=bing(f'site:firmenabc.at "{company}"')
    cands=[]
    for title,url,desc in results:
        sc=max(score(company,title),score(company,desc[:250]))
        exact=fold(company) and fold(company) in fold(title+' '+desc)
        cands.append((1 if exact else 0,sc,title,url,desc))
    if not cands:return None
    cands.sort(reverse=True);ex,sc,title,url,desc=cands[0]
    if sc<45 and not ex:return None
    return {'url':url,'title':title,'match_class':'EXACT' if ex else 'STRONG','score':sc}

def extract_people(text):
    # Text blocks on FirmenABC use headings Geschäftsführer / Gesellschafter and Anteil percentages.
    mg=[];owners=[]
    for m in re.finditer(r'(?:Geschäftsführer|GESCHÄFTSFÜHRER/IN)[^\n]{0,80}\n?(.{0,140})',text,re.I):
        s=clean(m.group(1));
        if s and len(s)<140:mg.append(s)
    # More robust from lines: capture names preceding role labels.
    lines=[clean(x) for x in text.splitlines() if clean(x)]
    for i,l in enumerate(lines):
        if re.search(r'GESCHÄFTSFÜHRER/IN|Geschäftsführer$',l,re.I) and i>0:
            n=lines[i-1]
            if 2<=len(n.split())<=8 and n not in mg:mg.append(n)
        if re.search(r'Gesellschafter$',l,re.I):
            for j in range(i+1,min(len(lines),i+8)):
                if re.search(r'Anteil\s*:\s*[0-9,.]+%',lines[j],re.I):
                    n=lines[j-1] if j>i+1 else ''
                    if n:owners.append(n+' '+lines[j]);break
    return '; '.join(dict.fromkeys(owners)), '; '.join(dict.fromkeys(mg))
def report_links(soup,base):
    out=[]
    for a in soup.find_all('a',href=True):
        h=urllib.parse.urljoin(base,a['href'])
        label=clean(a.get_text(' ',strip=True))
        if 'singleDocument' in h or 'companydocument' in h:
            out.append((h,label))
    return list(dict.fromkeys(out))
def pdf_text(content):
    try:
        rd=PdfReader(io.BytesIO(content));parts=[]
        for p in rd.pages[:80]:
            try:parts.append(p.extract_text() or '')
            except:pass
        return clean(' '.join(parts))
    except:return ''
def employee_claim(text):
    pats=[
      r'(?:durchschnittliche\s+(?:Zahl|Anzahl)\s+der\s+(?:Arbeitnehmer|Beschäftigten)|durchschnittlich\s+beschäftigt(?:e|en)?|Arbeitnehmer\s+im\s+Jahresdurchschnitt)[^0-9]{0,100}([0-9]{1,5})',
      r'(?:Mitarbeiter(?:innen|:innen|\*innen)?|Beschäftigte)\s*(?:im\s+Jahresdurchschnitt)?\s*[:\-]?\s*([0-9]{1,5})',
      r'([0-9]{1,5})\s+(?:Mitarbeiter(?:innen|:innen|\*innen)?|Beschäftigte)\b'
    ]
    for p in pats:
        m=re.search(p,text,re.I)
        if m:
            v=int(m.group(1))
            if 2<=v<=100000 and not 1900<=v<=2035:
                ctx=clean(text[max(0,m.start()-250):min(len(text),m.end()+350)])
                return v,v,ctx
    # Employee split by Angestellte / Arbeiter often appears as a table.
    nums=[]
    for lab in ('Angestellte','Arbeiter'):
        m=re.search(lab+r'[^0-9]{0,80}([0-9]{1,5})',text,re.I)
        if m:
            v=int(m.group(1));
            if 0<=v<=100000:nums.append((lab,v,m.start()))
    if nums and sum(v for _,v,_ in nums)>=2:
        pos=min(x[2] for x in nums);return sum(v for _,v,_ in nums),sum(v for _,v,_ in nums),clean(text[max(0,pos-200):pos+500])
    return None,None,''
def parse_date(text):
    m=re.search(r'Stichtag\s*:\s*(\d{2}\.\d{2}\.\d{4})',text,re.I);return m.group(1) if m else ''

def enrich(no,company):
    rec={'no':no,'company':company,'firmenabc_url':'','profile_title':'','match_class':'','match_score':'','owners':'','management':'','latest_report_date':'','employee_min':'','employee_max':'','employee_evidence':'','report_url':'','error':''}
    pm=profile_match(company)
    if not pm:rec['error']='NO_PROFILE_MATCH';return rec
    rec.update({'firmenabc_url':pm['url'],'profile_title':pm['title'],'match_class':pm['match_class'],'match_score':pm['score']})
    r=fetch(pm['url'])
    if not r:rec['error']='PROFILE_FETCH_FAILED';return rec
    soup=BeautifulSoup(r.text,'html.parser');text=soup.get_text('\n',strip=True);owners,mg=extract_people(text);rec['owners']=owners;rec['management']=mg
    links=report_links(soup,r.url)
    # Newest reports appear first on the profile. Inspect up to 3 until employee evidence is found.
    for h,label in links[:3]:
        rr=fetch(h)
        if not rr:continue
        ct=rr.headers.get('content-type','').lower()
        if 'pdf' not in ct and not rr.content.startswith(b'%PDF'):continue
        txt=pdf_text(rr.content)
        if not txt:continue
        if not rec['latest_report_date']:rec['latest_report_date']=parse_date(text)
        lo,hi,ev=employee_claim(txt)
        if lo is not None:
            rec.update({'employee_min':lo,'employee_max':hi,'employee_evidence':ev,'report_url':rr.url});break
    return rec

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,required=True);ap.add_argument('--end',type=int,required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    rows=read_csv('data/hausverwaltung/size_strict_v2/size_screening_strict_v2.csv')
    rows=sorted(rows,key=lambda r:r['company_name'].casefold())
    out=[]
    for i,r in enumerate(rows,1):
        if not args.start<=i<=args.end:continue
        x=enrich(i,r['company_name']);out.append(x);write(args.out,out);print(i,r['company_name'],x['match_class'],x['employee_min'],x['error'],flush=True)
    write(args.out,out);print('DONE',len(out))
if __name__=='__main__':main()
