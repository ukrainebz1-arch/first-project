import requests,re,urllib.parse
from bs4 import BeautifulSoup
q='"Erwin Rossik" Rossik Telefon'
ua={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/139 Safari/537.36'}
urls=[
 ('ddg','https://html.duckduckgo.com/html/?q='+urllib.parse.quote(q)),
 ('bing','https://www.bing.com/search?q='+urllib.parse.quote(q)),
 ('google','https://www.google.com/search?q='+urllib.parse.quote(q)+'&num=10&hl=de'),
]
for name,u in urls:
  try:
    r=requests.get(u,headers=ua,timeout=25)
    print('\nENGINE',name,'STATUS',r.status_code,'LEN',len(r.text),'URL',r.url)
    s=BeautifulSoup(r.text,'html.parser')
    links=[]
    for a in s.find_all('a',href=True):
      h=a['href']; txt=' '.join(a.get_text(' ',strip=True).split())
      if h.startswith('http') and txt:
        links.append((txt[:120],h[:240]))
    print('LINKS',links[:8])
    text=' '.join(s.get_text(' ',strip=True).split())
    print('TEXT',text[:1200])
  except Exception as e: print(name,'ERR',repr(e))
