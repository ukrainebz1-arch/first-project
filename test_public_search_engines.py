import requests,re,urllib.parse
from bs4 import BeautifulSoup
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
q='"Spedition Lang GesmbH" Mitarbeiter Österreich LinkedIn'
for name,url,params in [
 ('google','https://www.google.com/search',{'q':q,'num':10,'hl':'de'}),
 ('brave','https://search.brave.com/search',{'q':q,'source':'web'}),
 ('mojeek','https://www.mojeek.com/search',{'q':q}),
 ('yahoo','https://search.yahoo.com/search',{'p':q}),
]:
 try:
  r=requests.get(url,params=params,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.6'},timeout=30)
  print('\nENGINE',name,'status',r.status_code,'bytes',len(r.text),'url',r.url)
  s=BeautifulSoup(r.text,'html.parser')
  # print first links/snippets broadly
  found=[]
  for a in s.find_all('a',href=True):
   text=' '.join(a.stripped_strings)
   href=a.get('href','')
   if len(text)>15 and not href.startswith('#'):
    found.append((text[:180],href[:300]))
  for x in found[:15]: print(' ',x)
 except Exception as e: print(name,'ERR',repr(e))
