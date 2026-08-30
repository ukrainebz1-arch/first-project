import csv, os, re, time, random
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

CHUNK=int(os.environ.get('CHUNK','0'))
CHUNKS=int(os.environ.get('CHUNKS','16'))
OUTDIR=os.environ.get('OUTDIR','out')
TOTAL_PAGES=int(os.environ.get('TOTAL_PAGES','536'))
os.makedirs(OUTDIR,exist_ok=True)

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
BASE='https://ksw.or.at/mitgliederverzeichnis/'
COMPANY_RE=re.compile(r'(?i)(gmbh|gesmbh|gesellschaft|gesellschaft m\.b\.h|kg\b|og\b|ag\b|se\b|flexco|steuerberatung|wirtschaftstreuhand|wirtschaftspr[uü]fung|tax|treuhand|consulting|beratungsgesellschaft)')
PERSON_HINT=re.compile(r'(?i)\b(mag\.|msc\b|bsc\b|ll\.?m\.?|dr\.|mba\b|ba\b|dipl\.|m\.a\.|phd\b)')
POSTAL_RE=re.compile(r'\b(\d{4})\s+([^\n|]{2,60})')
PHONE_RE=re.compile(r'\+43[\d\s/().-]{6,25}')

def norm(s):
    s=re.sub(r'\s+',' ',s or '').strip().lower()
    s=s.replace('ö','oe').replace('ä','ae').replace('ü','ue').replace('ß','ss')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def page_url(p):
    if p==1: return BASE
    return BASE+'?tx_kswmembers_membersdirectory%5Bcontroller%5D=MembersDirectory&tx_kswmembers_membersdirectory%5BcurrentPage%5D='+str(p)

def fetch(p):
    for attempt in range(4):
        try:
            r=requests.get(page_url(p),headers=H,timeout=25)
            if r.status_code==200 and 'Ergebnisse gefunden' in r.text:
                return r.text
        except Exception: pass
        time.sleep(1.5*(attempt+1))
    raise RuntimeError(f'failed page {p}')

def is_company_like(title):
    if not COMPANY_RE.search(title or ''): return False
    # Professional persons often include academic degrees and no legal/company keyword besides profession.
    legal=bool(re.search(r'(?i)(gmbh|gesmbh|gesellschaft|\bkg\b|\bog\b|\bag\b|\bse\b|flexco)',title or ''))
    if PERSON_HINT.search(title or '') and not legal: return False
    return True

def parse_page(html,p):
    soup=BeautifulSoup(html,'html.parser')
    hs=soup.find_all('h4')
    out=[]
    for h in hs:
        title=h.get_text(' ',strip=True)
        if not title or not is_company_like(title): continue
        # collect content until next h4 or pagination/footer boundary
        parts=[]; links=[]
        for el in h.next_elements:
            if el is h: continue
            if getattr(el,'name',None)=='h4': break
            if getattr(el,'name',None) in ('footer',): break
            if getattr(el,'name',None)=='a' and el.get('href'):
                links.append(el.get('href'))
            if isinstance(el,str):
                t=el.strip()
                if t: parts.append(t)
            if len(parts)>160: break
        text=' | '.join(parts)
        # stop before representation details can overrun too far
        text=re.sub(r'\s+',' ',text)[:5000]
        websites=[]; emails=[]
        for href in links:
            href=href.strip()
            if href.startswith('mailto:'):
                emails.append(href[7:].replace('(at)','@'))
            elif href.startswith('http'):
                host=urlparse(href).netloc.lower()
                if 'ksw.or.at' not in host and 'kwt.or.at' not in host:
                    websites.append(href)
        # KSW rendered email often isn't mailto; parse textual (at)
        emails += [m.replace('(at)','@') for m in re.findall(r'[A-Za-z0-9._%+-]+\(at\)[A-Za-z0-9.-]+\.[A-Za-z]{2,}',text)]
        pm=POSTAL_RE.search(text)
        postal=pm.group(1) if pm else ''
        city=pm.group(2).split('|')[0].strip() if pm else ''
        phones=PHONE_RE.findall(text)
        out.append({
            'page':p,'title':title,'title_norm':norm(title),'postal_code':postal,'city':city,
            'website':' | '.join(dict.fromkeys(websites[:5])),'email':' | '.join(dict.fromkeys(emails[:5])),
            'phones':' | '.join(dict.fromkeys(x.strip() for x in phones[:5])),
            'text':text,'source_url':page_url(p)
        })
    return out

def main():
    pages=[p for p in range(1,TOTAL_PAGES+1) if (p-1)%CHUNKS==CHUNK]
    rows=[]
    for i,p in enumerate(pages,1):
        html=fetch(p)
        parsed=parse_page(html,p)
        rows.extend(parsed)
        print(f'chunk={CHUNK} page={p} companies={len(parsed)} total={len(rows)}',flush=True)
        time.sleep(random.uniform(.08,.25))
    path=os.path.join(OUTDIR,f'ksw_chunk_{CHUNK:02d}.csv')
    fields=['page','title','title_norm','postal_code','city','website','email','phones','text','source_url']
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print(path,len(rows))
if __name__=='__main__': main()
