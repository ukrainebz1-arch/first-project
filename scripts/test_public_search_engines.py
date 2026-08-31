import requests,re,urllib.parse
from bs4 import BeautifulSoup
q='"Andreas Fluckinger" "Fluckinger Transport" Telefon'
ua={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/139 Safari/537.36','Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
urls=[
 ('ddg','https://html.duckduckgo.com/html/?q='+urllib.parse.quote(q)),
 ('bing','https://www.bing.com/search?q='+urllib.parse.quote(q)),
 ('google','https://www.google.com/search?q='+urllib.parse.quote(q)+'&num=10&hl=de'),
 ('brave','https://search.brave.com/search?q='+urllib.parse.quote(q)+'&source=web'),
 ('yahoo','https://search.yahoo.com/search?p='+urllib.parse.quote(q)),
 ('mojeek','https://www.mojeek.com/search?q='+urllib.parse.quote(q)),
 ('ecosia','https://www.ecosia.org/search?q='+urllib.parse.quote(q)),
 ('startpage','https://www.startpage.com/sp/search?query='+urllib.parse.quote(q)),
]
for name,u in urls:
  try:
    r=requests.get(u,headers=ua,timeout=25)
    print('\nENGINE',name,'STATUS',r.status_code,'LEN',len(r.text),'URL',r.url)
    s=BeautifulSoup(r.text,'html.parser')
    links=[]
    for a in s.find_all('a',href=True):
      h=a['href']; txt=' '.join(a.get_text(' ',strip=True).split())
      if txt and ('fluckinger' in h.lower() or 'fluckinger' in txt.lower()):
        links.append((txt[:140],h[:300]))
    print('HAS_DOMAIN','fluckinger.com' in r.text.lower(),'HAS_NAME','andreas fluckinger' in r.text.lower())
    print('MATCH_LINKS',links[:12])
    text=' '.join(s.get_text(' ',strip=True).split())
    m=re.search(r'.{0,250}Andreas Fluckinger.{0,500}',text,re.I)
    print('TEXT',(m.group(0) if m else text[:800]))
  except Exception as e: print(name,'ERR',repr(e))
