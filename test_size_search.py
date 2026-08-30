import requests, re, urllib.parse, time
from bs4 import BeautifulSoup

NAMES=[
 '3LOG premium logistics GmbH','Spedition Lang GesmbH','BTG Spedition und Logistik GmbH',
 'ACL Schwerlast & Sondertransport GmbH','Quehenberger Logistics GmbH'
]
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'

def ddg(q):
    r=requests.get('https://html.duckduckgo.com/html/',params={'q':q},headers={'User-Agent':UA},timeout=30)
    print('DDG',r.status_code,len(r.text),r.url)
    s=BeautifulSoup(r.text,'html.parser')
    out=[]
    for res in s.select('.result')[:8]:
        a=res.select_one('.result__a')
        sn=res.select_one('.result__snippet')
        if a:
            href=a.get('href','')
            qs=urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            if 'uddg' in qs: href=urllib.parse.unquote(qs['uddg'][0])
            out.append((a.get_text(' ',strip=True),href,sn.get_text(' ',strip=True) if sn else ''))
    return out

def bing(q):
    r=requests.get('https://www.bing.com/search',params={'q':q,'count':10},headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9'},timeout=30)
    print('BING',r.status_code,len(r.text),r.url)
    s=BeautifulSoup(r.text,'html.parser')
    out=[]
    for li in s.select('li.b_algo')[:8]:
        a=li.select_one('h2 a'); p=li.select_one('.b_caption p') or li.select_one('p')
        if a: out.append((a.get_text(' ',strip=True),a.get('href',''),p.get_text(' ',strip=True) if p else ''))
    return out

for name in NAMES:
    q=f'"{name}" Mitarbeiter Österreich'
    print('\n###',name)
    for engine,fn in [('DDG',ddg),('BING',bing)]:
        try:
            rr=fn(q)
            print(engine,'results',len(rr))
            for x in rr[:5]: print(' -',x)
        except Exception as e: print(engine,'ERR',repr(e))
    time.sleep(.5)
