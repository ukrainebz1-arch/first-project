#!/usr/bin/env python3
import argparse,csv,json,re,time,urllib.parse
from pathlib import Path
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'

def clean(s): return re.sub(r'\s+',' ',s or '').strip()

def ddg(query):
    u='https://html.duckduckgo.com/html/?'+urllib.parse.urlencode({'q':query})
    r=requests.get(u,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.6'},timeout=25)
    if r.status_code!=200: return [],f'ddg_http_{r.status_code}'
    s=BeautifulSoup(r.text,'html.parser'); out=[]
    for x in s.select('.result')[:10]:
        a=x.select_one('.result__a'); sn=x.select_one('.result__snippet')
        if not a: continue
        href=a.get('href','')
        if href.startswith('//duckduckgo.com/l/?'):
            q=urllib.parse.parse_qs(urllib.parse.urlparse('https:'+href).query); href=(q.get('uddg') or [href])[0]
        out.append({'title':clean(a.get_text(' ',strip=True)),'url':href,'snippet':clean(sn.get_text(' ',strip=True)) if sn else ''})
    return out,''

def bing(query):
    u='https://www.bing.com/search?'+urllib.parse.urlencode({'q':query,'count':'10','setlang':'de-at'})
    r=requests.get(u,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.6'},timeout=25)
    if r.status_code!=200: return [],f'bing_http_{r.status_code}'
    s=BeautifulSoup(r.text,'html.parser'); out=[]
    for x in s.select('li.b_algo')[:10]:
        a=x.select_one('h2 a'); sn=x.select_one('.b_caption p')
        if not a: continue
        out.append({'title':clean(a.get_text(' ',strip=True)),'url':a.get('href',''),'snippet':clean(sn.get_text(' ',strip=True)) if sn else ''})
    return out,''

def search(row):
    name=row['company_name']; place=(row.get('places') or '').split('|')[0].strip()
    q=f'"{name}" Österreich Mitarbeiter Beschäftigte employees LinkedIn Karriere'
    hits,err=ddg(q); engine='duckduckgo'
    if len(hits)<2:
        h2,e2=bing(q)
        if len(h2)>len(hits): hits,err,engine=h2,e2,'bing'
    return q,engine,err,hits

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output',required=True); a=ap.parse_args()
    rows=list(csv.DictReader(open(a.input,encoding='utf-8-sig',newline='')))
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    counts={'input_rows':len(rows),'searched':0,'with_hits':0,'hits':0,'errors':0}
    with open(a.output,'w',encoding='utf-8',newline='') as f:
        for i,row in enumerate(rows,1):
            try:
                q,engine,err,hits=search(row)
            except Exception as e:
                q=f'"{row.get("company_name","")}" Österreich Mitarbeiter Beschäftigte employees LinkedIn Karriere'; engine=''; err=type(e).__name__+':'+str(e); hits=[]
            obj={'candidate_key':row.get('candidate_key',''),'company_name':row.get('company_name',''),'states':row.get('states',''),'places':row.get('places',''),'websites':row.get('websites',''),'wko_urls':row.get('wko_urls',''),'query':q,'engine':engine,'error':err,'results':hits}
            f.write(json.dumps(obj,ensure_ascii=False)+'\n'); f.flush()
            counts['searched']+=1; counts['hits']+=len(hits); counts['with_hits']+=bool(hits); counts['errors']+=bool(err and not hits)
            time.sleep(0.35)
    print(json.dumps(counts,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
