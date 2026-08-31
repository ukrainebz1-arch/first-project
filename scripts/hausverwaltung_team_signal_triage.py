import csv,re,sys,html,concurrent.futures
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

SRC='data/hausverwaltung/size_strict_v2/size_screening_strict_v2.csv'
UA={'User-Agent':'Mozilla/5.0 (compatible; Stage2Recall/1.0)'}
GENERIC={'office','info','kontakt','contact','hausverwaltung','verwaltung','immo','immobilien','buchhaltung','rechnung','service','support','mail','datenschutz','karriere','jobs','bewerbung','marketing','vermietung','verkauf','team'}
TOK=('team','mitarbeiter','mitarbeitende','uber-uns','ueber-uns','über-uns','kontakt','ansprech','unternehmen','kanzlei')

def fetch(u):
    try:
        r=requests.get(u,headers=UA,timeout=12,allow_redirects=True)
        if r.status_code==200 and 'text/html' in r.headers.get('content-type','').lower(): return r.url,r.text[:2000000]
    except Exception: pass
    return u,''

def personal_emails(s):
    out=set()
    for e in re.findall(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}',s,re.I):
        e=e.lower().strip('.;,')
        local=e.split('@')[0]
        if local not in GENERIC and not any(local.startswith(x+'+') for x in GENERIC): out.add(e)
    return out

def likely_names(soup):
    names=set()
    bad=('team','kontakt','unternehmen','verwaltung','immobilien','buchhaltung','technik','assistenz','geschäftsführung','geschaftsfuhrung','leitung','sekretariat','service','karriere','über uns','ueber uns')
    for tag in soup.find_all(['h2','h3','h4','h5','strong']):
        t=' '.join(tag.get_text(' ',strip=True).split())
        if not (5<=len(t)<=60) or any(x in t.lower() for x in bad): continue
        ws=t.split()
        if 2<=len(ws)<=5 and sum(1 for w in ws if w[:1].isupper())>=2 and not re.search(r'\d',t): names.add(t)
    return names

def one(r):
    base=(r.get('website') or '').strip()
    if not base: return None
    u,body=fetch(base)
    if not body: return {'company_name':r['company_name'],'website':base,'pages':0,'personal_emails':0,'name_headings':0,'signal':0,'urls':'','emails':''}
    p=urlparse(u); host=p.netloc
    soup=BeautifulSoup(body,'html.parser')
    links=[]
    for a in soup.find_all('a',href=True):
        href=urljoin(u,a['href']); text=(' '.join(a.get_text(' ',strip=True).split())+' '+href).lower()
        if urlparse(href).netloc==host and any(t in text for t in TOK):
            href=href.split('#')[0]
            if href not in links: links.append(href)
    # common routes even when not linked clearly
    for path in ['/team/','/team','/ueber-uns/','/ueber-uns','/uber-uns/','/kontakt/','/kontakt','/unternehmen/']:
        x=urljoin(u,path)
        if x not in links: links.append(x)
    pages=[(u,body)]
    for x in links[:8]:
        ux,b=fetch(x)
        if b: pages.append((ux,b))
    em=set(); names=set(); used=[]
    for ux,b in pages:
        em|=personal_emails(b)
        names|=likely_names(BeautifulSoup(b,'html.parser'))
        used.append(ux)
    # personal e-mails are strongest; headings are only a weak escalation signal.
    signal=len(em)*3 + min(len(names),30)
    return {'company_name':r['company_name'],'website':base,'pages':len(pages),'personal_emails':len(em),'name_headings':len(names),'signal':signal,'urls':' | '.join(dict.fromkeys(used)),'emails':' | '.join(sorted(em))}

def main():
    rows=list(csv.DictReader(open(SRC,encoding='utf-8-sig',newline='')))
    todo=[r for r in rows if r.get('size_class_strict_v2')=='U_NOT_PROVEN' and r.get('website')]
    print('TODO',len(todo),flush=True)
    out=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        for i,x in enumerate(ex.map(one,todo),1):
            if x: out.append(x)
            if i%50==0: print('DONE',i,flush=True)
    out.sort(key=lambda x:(-x['signal'],-x['personal_emails'],-x['name_headings'],x['company_name']))
    fields=['company_name','website','pages','personal_emails','name_headings','signal','urls','emails']
    with open('data/hausverwaltung/size_agent_first/team_signal_all.csv','w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
    with open('data/hausverwaltung/size_agent_first/team_signal_candidates.tsv','w',encoding='utf-8') as f:
        f.write('\t'.join(fields)+'\n')
        for x in out:
            if x['personal_emails']>=5 or x['name_headings']>=10 or x['signal']>=18:
                f.write('\t'.join(str(x[k]).replace('\t',' ').replace('\n',' ') for k in fields)+'\n')
    print('ALL',len(out),'ESCALATED',sum(x['personal_emails']>=5 or x['name_headings']>=10 or x['signal']>=18 for x in out),flush=True)
if __name__=='__main__': main()
