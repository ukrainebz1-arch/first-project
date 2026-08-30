import requests, re
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs

URL='https://firmen.wko.at/spediteur/burgenland/'
s=requests.Session()
s.headers.update({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36','Accept-Language':'de-AT,de;q=0.9'})

def parse(html):
    soup=BeautifulSoup(html,'html.parser')
    rows=[]
    for a in soup.select('article.search-result-article'):
        t=a.select_one('a.title-link[href*="firmaid="]') or a.select_one('a[href*="firmaid="]')
        if t:
            href=urljoin(URL,t.get('href',''))
            rows.append((re.sub(r'\s+',' ',t.get_text(' ',strip=True)),href))
    return rows,soup

def hidden(soup):
    d={}
    form=soup.find('form')
    if not form: return d
    for inp in form.find_all('input'):
        n=inp.get('name')
        if n and inp.get('type','').lower()=='hidden': d[n]=inp.get('value','')
    return d

r=s.get(URL,timeout=60); r.raise_for_status()
rows,soup=parse(r.text)
print('GET',len(rows),[x[0] for x in rows[:2]], flush=True)
seen=set(x[1] for x in rows)
for i in range(1,6):
    payload=hidden(soup)
    payload['ctl00$ContentPlaceHolder1$nextPageButton']='Mehr laden'
    # Standard ASP.NET submit fields; keep empty unless WKO supplied otherwise.
    payload.setdefault('__EVENTTARGET','')
    payload.setdefault('__EVENTARGUMENT','')
    rr=s.post(URL,data=payload,timeout=60,allow_redirects=True)
    print('POST status',i,rr.status_code,'url',rr.url,'bytes',len(rr.text),flush=True)
    rr.raise_for_status()
    rows,soup=parse(rr.text)
    hrefs=[x[1] for x in rows]
    new=[h for h in hrefs if h not in seen]
    print('BATCH',i,'rows',len(rows),'new',len(new),'first',rows[0][0] if rows else '',flush=True)
    seen.update(hrefs)
    if not rows or not new: break
print('TOTAL UNIQUE',len(seen),flush=True)
