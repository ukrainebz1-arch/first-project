import csv, os, re, json, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

INFILE=os.environ.get('WKO_CSV','wko_input/wko_spediteur_standorte.csv')
OUTDIR=os.environ.get('OUTDIR','wko_profile_size_out')
os.makedirs(OUTDIR,exist_ok=True)
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'

def clean(s): return re.sub(r'\s+',' ',s or '').strip()

def employee_mentions(text):
    text=clean(text)
    out=[]
    pats=[
      (r'\b(?:über|mehr als|mehr als rund)\s+([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?)\b','over'),
      (r'\b(?:rund|ca\.?|circa|etwa|knapp)\s+([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?)\b','approx'),
      (r'\b([0-9\.]{1,7})\s+(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?)\b','exact'),
      (r'\b(?:Mitarbeiter(?:innen|Innen|:innen|\*innen)?|Beschäftigte(?:n)?)\s*[:\-]?\s*(?:rund|ca\.?|circa|etwa)?\s*([0-9\.]{1,7})\b','exact'),
    ]
    seen=set()
    for pat,kind in pats:
        for m in re.finditer(pat,text,re.I):
            try: v=int(m.group(1).replace('.',''))
            except: continue
            if v<2 or v>200000: continue
            # context to help audit local vs group claim
            a=max(0,m.start()-180); b=min(len(text),m.end()+180)
            ctx=clean(text[a:b])
            key=(v,ctx)
            if key not in seen:
                seen.add(key); out.append({'value':v,'kind':kind,'context':ctx})
    return out

def fetch_one(item):
    name,url=item
    sess=requests.Session(); sess.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.6'})
    try:
        r=sess.get(url,timeout=45,allow_redirects=True)
        if r.status_code!=200: return {'company_name':name,'profile_url':url,'http':r.status_code,'mentions':[],'text_len':0}
        soup=BeautifulSoup(r.text,'html.parser')
        # Remove navigation/footer noise moderately
        for t in soup(['script','style','noscript']): t.decompose()
        text=clean(soup.get_text(' ',strip=True))
        mentions=employee_mentions(text)
        return {'company_name':name,'profile_url':url,'http':200,'mentions':mentions,'text_len':len(text)}
    except Exception as e:
        return {'company_name':name,'profile_url':url,'http':'ERR','mentions':[],'text_len':0,'error':repr(e)}

with open(INFILE,encoding='utf-8-sig',newline='') as f: raw=list(csv.DictReader(f))
# one representative WKO profile per exact company name, but keep count of WKO rows
by={}
for r in raw:
    n=clean(r['company_name'])
    g=by.setdefault(n,{'count':0,'urls':[]})
    g['count']+=1
    u=r.get('profile_url','')
    if u and u not in g['urls']: g['urls'].append(u)
items=[(n,g['urls'][0]) for n,g in by.items() if g['urls']]
print('unique names',len(by),'profiles to fetch',len(items),flush=True)

results=[]
with ThreadPoolExecutor(max_workers=16) as ex:
    futs={ex.submit(fetch_one,it):it for it in items}
    for i,fut in enumerate(as_completed(futs),1):
        res=fut.result(); results.append(res)
        if i%100==0: print('fetched',i,'with mentions',sum(bool(x['mentions']) for x in results),flush=True)

rows=[]
for res in results:
    mentions=res.get('mentions',[])
    vals=[m['value'] for m in mentions]
    # choose max mention as screening signal, but retain all contexts for audit
    best=max(vals) if vals else ''
    kinds=' | '.join(sorted({m['kind'] for m in mentions}))
    ev=' || '.join(f"{m['value']} [{m['kind']}] {m['context']}" for m in mentions[:8])
    rows.append({
      'company_name':res['company_name'],
      'wko_rows':by[res['company_name']]['count'],
      'wko_profile_url':res['profile_url'],
      'http_status':res.get('http',''),
      'employee_best_numeric_mention':best,
      'employee_mention_kinds':kinds,
      'employee_evidence_contexts':ev,
      'mentions_count':len(mentions),
      'profile_text_len':res.get('text_len',0),
      'error':res.get('error',''),
    })
rows.sort(key=lambda x:x['company_name'].casefold())
fields=list(rows[0].keys())
with open(os.path.join(OUTDIR,'wko_profile_employee_mentions.csv'),'w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
summary={'unique_company_names':len(by),'profiles_fetched':len(results),'http_200':sum(x.get('http')==200 for x in results),'profiles_with_employee_mentions':sum(bool(x.get('mentions')) for x in results),'numeric_mentions_20plus':sum(any(m['value']>=20 for m in x.get('mentions',[])) for x in results),'numeric_mentions_30plus':sum(any(m['value']>=30 for m in x.get('mentions',[])) for x in results)}
with open(os.path.join(OUTDIR,'summary.json'),'w',encoding='utf-8') as f: json.dump(summary,f,ensure_ascii=False,indent=2)
print('SUMMARY',json.dumps(summary,ensure_ascii=False),flush=True)
