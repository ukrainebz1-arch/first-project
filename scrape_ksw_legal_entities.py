import csv, os, re, time, random, json
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
LEGAL_RE=re.compile(r'(?i)(gmbh|gesmbh|gmbh\s*&\s*co\.?\s*kg|gesellschaft\s+m\.?b\.?h\.?|gesellschaft\s+mit\s+beschr[aä]nkter\s+haftung|\bm\.?b\.?h\.?\b|\bkg\b|\bog\b|\bag\b|\bse\b|flexco|flexible\s+kapitalgesellschaft|genossenschaft|partnerschaftsgesellschaft)')
POSTAL_RE=re.compile(r'\b(\d{4})\s+([^|]{2,60})')
PHONE_RE=re.compile(r'\+43[\d\s/().-]{6,25}')

def norm(s):
    s=re.sub(r'\s+',' ',s or '').strip().lower()
    s=s.replace('ö','oe').replace('ä','ae').replace('ü','ue').replace('ß','ss')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def page_url(p):
    if p==1:return BASE
    return BASE+'?tx_kswmembers_membersdirectory%5Bcontroller%5D=MembersDirectory&tx_kswmembers_membersdirectory%5BcurrentPage%5D='+str(p)

def fetch(p,session):
    # KSW occasionally rate-limits individual requests; spread retries over a longer window.
    last=''
    for attempt in range(10):
        try:
            r=session.get(page_url(p),headers=H,timeout=35)
            last=f'status={r.status_code} len={len(r.text)}'
            if r.status_code==200 and 'Ergebnisse gefunden' in r.text:
                return r.text,''
        except Exception as e:
            last=repr(e)
        time.sleep(min(18, 1.2*(attempt+1)) + random.uniform(.4,1.8))
    return '',last

def parse_page(html,p):
    soup=BeautifulSoup(html,'html.parser')
    h4s=soup.find_all('h4')
    out=[]
    for h in h4s:
        title=h.get_text(' ',strip=True)
        if not title or not LEGAL_RE.search(title):continue
        parts=[];links=[]
        cur=h.next_sibling;steps=0
        while cur is not None and steps<80:
            if getattr(cur,'name',None)=='h4':break
            if hasattr(cur,'find_all'):
                for a in cur.find_all('a',href=True):links.append(a.get('href',''))
            txt=cur.get_text(' ',strip=True) if hasattr(cur,'get_text') else str(cur).strip()
            if txt:parts.append(txt)
            cur=cur.next_sibling;steps+=1
        if not parts:
            for el in h.next_elements:
                if el is h:continue
                if getattr(el,'name',None)=='h4':break
                if getattr(el,'name',None)=='a' and el.get('href'):links.append(el.get('href'))
                if isinstance(el,str) and el.strip():parts.append(el.strip())
                if len(parts)>140:break
        text=re.sub(r'\s+',' ',' | '.join(parts))[:5000]
        websites=[];emails=[]
        for href in links:
            href=(href or '').strip()
            if href.startswith('mailto:'):emails.append(href[7:].replace('(at)','@'))
            elif href.startswith('http'):
                host=urlparse(href).netloc.lower()
                if 'ksw.or.at' not in host and 'kwt.or.at' not in host:websites.append(href)
        emails += [m.replace('(at)','@') for m in re.findall(r'[A-Za-z0-9._%+-]+\(at\)[A-Za-z0-9.-]+\.[A-Za-z]{2,}',text)]
        pm=POSTAL_RE.search(text);postal=pm.group(1) if pm else '';city=pm.group(2).split('|')[0].strip() if pm else ''
        phones=PHONE_RE.findall(text)
        out.append({'page':p,'title':title,'title_norm':norm(title),'postal_code':postal,'city':city,
                    'website':' | '.join(dict.fromkeys(websites[:5])),'email':' | '.join(dict.fromkeys(emails[:5])),
                    'phones':' | '.join(dict.fromkeys(x.strip() for x in phones[:5])),'text':text,'source_url':page_url(p)})
    return out

def main():
    pages=[p for p in range(1,TOTAL_PAGES+1) if (p-1)%CHUNKS==CHUNK]
    rows=[];failed=[];done=[];session=requests.Session()
    for p in pages:
        html,err=fetch(p,session)
        if not html:
            failed.append({'page':p,'error':err});print(f'chunk={CHUNK} page={p} FAILED {err}',flush=True);continue
        parsed=parse_page(html,p);rows.extend(parsed);done.append(p)
        print(f'chunk={CHUNK} page={p} legal={len(parsed)} cumulative={len(rows)}',flush=True)
        time.sleep(random.uniform(.3,.9))
    fields=['page','title','title_norm','postal_code','city','website','email','phones','text','source_url']
    path=os.path.join(OUTDIR,f'ksw_legal_chunk_{CHUNK:02d}.csv')
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    meta={'chunk':CHUNK,'chunks':CHUNKS,'expected_pages':pages,'completed_pages':done,'failed_pages':failed,'rows':len(rows)}
    with open(os.path.join(OUTDIR,f'ksw_legal_chunk_{CHUNK:02d}.json'),'w') as f:json.dump(meta,f,indent=2)
    print(json.dumps({'chunk':CHUNK,'pages':len(pages),'completed':len(done),'failed':[x['page'] for x in failed],'rows':len(rows)}),flush=True)
    # Fail only after preserving partial data, so a retry can target incompleteness explicitly.
    if failed:raise SystemExit(2)
if __name__=='__main__':main()
