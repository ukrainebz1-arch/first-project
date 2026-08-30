import requests,re
from bs4 import BeautifulSoup
from urllib.parse import quote,urlparse

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.5'}
name='Schwarz & Partner Wirtschaftsprüfung & Steuerberatung GmbH'
city='Wien'
queries=[
 f'site:firmenabc.at "{name}" {city}',
 f'site:linkedin.com/company "{name}" {city}',
 f'(site:karriere.at OR site:kununu.com/at OR site:jobs.at) "{name}" {city}',
 f'"{name}" {city} Mitarbeiter Steuerberatung',
]
for q in queries:
    url='https://www.bing.com/search?q='+quote(q)+'&setlang=de-AT&cc=AT'
    r=requests.get(url,headers=H,timeout=30)
    print('\nQUERY',q,'STATUS',r.status_code,'LEN',len(r.text))
    soup=BeautifulSoup(r.text,'html.parser')
    for li in soup.select('li.b_algo')[:8]:
        a=li.select_one('h2 a')
        if not a: continue
        href=a.get('href',''); title=' '.join(a.get_text(' ',strip=True).split())
        sn=li.select_one('.b_caption p') or li.select_one('p')
        snippet=' '.join(sn.get_text(' ',strip=True).split()) if sn else ''
        print('RESULT',title,'|',href,'|',snippet[:300])
        host=urlparse(href).netloc.lower()
        if any(x in host for x in ['firmenabc.at','linkedin.com','karriere.at','kununu.com','jobs.at']):
            try:
                rr=requests.get(href,headers=H,timeout=30,allow_redirects=True)
                text=' '.join(BeautifulSoup(rr.text,'html.parser').get_text(' ',strip=True).split())
                print('FETCH',host,rr.status_code,len(rr.text),'Mitarbeiterzahl' in text,'Größe' in text, text[:500])
            except Exception as e: print('FETCHERR',host,repr(e))
