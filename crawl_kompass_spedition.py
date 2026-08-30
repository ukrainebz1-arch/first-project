import argparse, csv, re, time, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE='https://at.kompass.com'
CATEGORY='https://at.kompass.com/x/producer/a/verschiffungsagenten-und-spediteure/75780/'
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'})

def get(url, tries=3):
    err=''
    for i in range(tries):
        try:
            r=S.get(url,timeout=30)
            if r.status_code==200 and len(r.text)>1000: return r
            err=f'HTTP {r.status_code} len={len(r.text)}'
        except Exception as e: err=repr(e)
        time.sleep(1.5*(i+1))
    raise RuntimeError(f'{url}: {err}')

def page_url(n):
    return CATEGORY if n==1 else CATEGORY+f'page-{n}/'

def company_links(n):
    r=get(page_url(n)); s=BeautifulSoup(r.text,'html.parser')
    out=[]; seen=set()
    for a in s.find_all('a',href=True):
        h=urljoin(BASE,a['href'])
        if re.search(r'https://at\.kompass\.com/c/[^/]+/at\d+/?$',h):
            h=h.split('?')[0]
            if h not in seen:
                seen.add(h); out.append(h)
    return out

def clean(t): return re.sub(r'\s+',' ',t or '').strip()

def parse_emp(text):
    # Kompass German public profile: "Gesamtzahl Mitarbeiter | Von 20 bis 49 Mitarbeiter"
    snippets=[]
    for m in re.finditer(r'Gesamtzahl\s+Mitarbeiter.{0,220}',text,re.I|re.S): snippets.append(clean(m.group(0)))
    blob=' | '.join(snippets[:3]) or text
    pats=[
      (r'Von\s+([\d\.]+)\s+bis\s+([\d\.]+)\s*Mitarbeiter', 'range'),
      (r'([\d\.]+)\s*(?:-|bis)\s*([\d\.]+)\s*Mitarbeiter', 'range'),
      (r'(?:Mehr als|Über)\s+([\d\.]+)\s*Mitarbeiter', 'over'),
      (r'([\d\.]+)\s*Mitarbeiter', 'exact')]
    for p,k in pats:
        m=re.search(p,blob,re.I)
        if m:
            nums=[int(x.replace('.','')) for x in m.groups() if x]
            if k=='range': return nums[0],nums[1],clean(m.group(0)),k
            if k=='over': return nums[0]+1,None,clean(m.group(0)),k
            return nums[0],nums[0],clean(m.group(0)),k
    return None,None,'',''

def parse_profile(url):
    try:
        r=get(url); s=BeautifulSoup(r.text,'html.parser'); text=clean(s.get_text(' ',strip=True))
        h1=s.find('h1'); name=clean(h1.get_text(' ',strip=True)) if h1 else ''
        # strip bullet/subtitle from h1 if present
        name=re.sub(r'\s*[•|]\s*.*$','',name).strip()
        lo,hi,evidence,kind=parse_emp(text)
        # address line around Standort / postcode-city
        city=''
        m=re.search(r'\b(\d{4})\s+([A-ZÄÖÜa-zäöüß][A-Za-zÄÖÜäöüß .\-/]{2,60})\s*-\s*Österreich',text)
        if m: city=clean(m.group(1)+' '+m.group(2))
        return {'kompass_url':url,'kompass_name':name,'kompass_place':city,'employee_min':lo or '', 'employee_max':hi or '', 'employee_evidence':evidence,'employee_kind':kind,'http_status':r.status_code,'error':''}
    except Exception as e:
        return {'kompass_url':url,'kompass_name':'','kompass_place':'','employee_min':'','employee_max':'','employee_evidence':'','employee_kind':'','http_status':'','error':repr(e)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--page',type=int,required=True); ap.add_argument('--out',required=True); args=ap.parse_args()
    links=company_links(args.page)
    rows=[]
    for i,u in enumerate(links,1):
        rows.append(parse_profile(u))
        if i%10==0: print(f'page {args.page}: {i}/{len(links)}',flush=True)
        time.sleep(.08)
    fields=['kompass_url','kompass_name','kompass_place','employee_min','employee_max','employee_evidence','employee_kind','http_status','error']
    with open(args.out,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print(f'PAGE={args.page} LINKS={len(links)} EMPLOYEE_RANGES={sum(bool(r["employee_min"]) for r in rows)} OUT={args.out}')
if __name__=='__main__': main()
