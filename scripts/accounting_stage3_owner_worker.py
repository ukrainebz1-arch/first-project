#!/usr/bin/env python3
import argparse,csv,json,os,re,time,random
from urllib.parse import urlparse,urljoin,quote_plus,unquote
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
NETWORKS=('ey ','ernst & young','kpmg','tpa ','rsm ','ecovis','bdo ','deloitte','pwc ','moore ')
ROLE_WORDS=('geschäftsführer','geschaeftsfuehrer','geschäftsführung','geschaeftsfuehrung','managing partner','geschäftsleiter','geschaeftsleiter','vorstand','kanzleileitung','managing director')
OWNER_WORDS=('gesellschafter','gesellschafterin','eigentümer','eigentuemer','inhaber','inhaberin','anteilseigner')
PARTNER_WORDS=('partner','partnerin','managing partner')
STOP={'Steuerberatung','Wirtschaftsprüfung','Wirtschaftspruefung','Gesellschaft','Geschäftsführer','Geschaeftsfuehrer','Geschäftsführung','Geschaeftsfuehrung','Partner','Team','Kanzlei','Unternehmen','Impressum','Kontakt','Wien','Austria','Österreich','Oesterreich','GmbH','KG','AG','OG','Wirtschaftstreuhand'}
NAME_TOKEN=r"[A-ZÄÖÜ][A-Za-zÀ-ÖØ-öø-ÿ'’\-]+"
NAME_RE=re.compile(r'(?:(?:Dr\.?|Mag\.?|DI|Ing\.?|MMag\.?|MBA|LL\.M\.)\s+)*(%s(?:\s+%s){1,3})' % (NAME_TOKEN,NAME_TOKEN))
SHARE_AFTER=re.compile(r'(?i)(%s(?:\s+%s){1,3}).{0,70}?(\d{1,3}(?:[\.,]\d+)?)\s*%%' % (NAME_TOKEN,NAME_TOKEN))
SHARE_BEFORE=re.compile(r'(?i)(\d{1,3}(?:[\.,]\d+)?)\s*%%.{0,70}?(%s(?:\s+%s){1,3})' % (NAME_TOKEN,NAME_TOKEN))

def host(u):
    try:return re.sub(r'^www\.','',urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0])
    except:return ''
def get(u,timeout=10):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and ('text/html' in r.headers.get('content-type','') or 'text/plain' in r.headers.get('content-type','')):
            r.encoding=r.apparent_encoding or r.encoding;return r.url,r.text[:1600000]
    except:pass
    return '',''
def text(h):return re.sub(r'\s+',' ',BeautifulSoup(h or '','html.parser').get_text(' ',strip=True))
def search(q):
    for base in ['https://www.bing.com/search?q=','https://html.duckduckgo.com/html/?q=']:
        try:
            r=requests.get(base+quote_plus(q),headers=H,timeout=10)
            if r.status_code!=200:continue
            b=BeautifulSoup(r.text,'html.parser');res=[]
            if 'bing.com' in base:
                for x in b.select('li.b_algo')[:10]:
                    a=x.select_one('h2 a');p=x.select_one('.b_caption p')
                    if a:res.append({'url':a.get('href',''),'title':a.get_text(' ',strip=True),'snippet':p.get_text(' ',strip=True) if p else ''})
            else:
                for x in b.select('.result')[:10]:
                    a=x.select_one('.result__a');p=x.select_one('.result__snippet')
                    if a:
                        u=a.get('href','');m=re.search(r'[?&]uddg=([^&]+)',u)
                        if m:u=unquote(m.group(1))
                        res.append({'url':u,'title':a.get_text(' ',strip=True),'snippet':p.get_text(' ',strip=True) if p else ''})
            if res:return res
        except:pass
    return []
def company_tokens(name):
    return [x.lower() for x in re.findall(r'[A-Za-zÄÖÜäöüß0-9]+',name) if len(x)>=4 and x.lower() not in {'gmbh','steuerberatung','wirtschaftsprüfung','wirtschaftspruefung','gesellschaft','kanzlei'}][:5]
def matches_company(name,hay):
    toks=company_tokens(name);h=hay.lower();return not toks or any(t in h for t in toks)
def clean_name(n):
    n=re.sub(r'\s+',' ',n).strip(' ,;:-')
    parts=n.split()
    if len(parts)<2 or len(parts)>4:return ''
    if any(p in STOP for p in parts):return ''
    if any(p.lower() in {'der','die','das','und','von','für','fuer','mit','unser','unsere'} for p in parts):return ''
    return n
def names_near(t,keywords,window=220):
    low=t.lower();out=[]
    for kw in keywords:
        start=0
        while True:
            i=low.find(kw,start)
            if i<0:break
            seg=t[max(0,i-80):min(len(t),i+window)]
            for m in NAME_RE.finditer(seg):
                n=clean_name(m.group(1))
                if n and n not in out:out.append(n)
            start=i+len(kw)
    return out[:12]
def role_for(name,t):
    low=t.lower();pos=low.find(name.lower())
    seg=low[max(0,pos-150):pos+180] if pos>=0 else low
    if 'managing partner' in seg:return 'Managing Partner'
    if 'geschäftsführer' in seg or 'geschaeftsfuehrer' in seg:return 'Geschäftsführer'
    if 'geschäftsführung' in seg or 'geschaeftsfuehrung' in seg:return 'Geschäftsführung'
    if 'vorstand' in seg:return 'Vorstand'
    if 'kanzleileitung' in seg:return 'Kanzleileitung'
    if 'partner' in seg:return 'Partner'
    if 'inhaber' in seg:return 'Inhaber'
    return 'Management'
def shares_near(t):
    if not any(k in t.lower() for k in OWNER_WORDS):return []
    out=[]
    for p in (SHARE_AFTER,SHARE_BEFORE):
        for m in p.finditer(t):
            if p is SHARE_AFTER:n=clean_name(m.group(1));raw=m.group(2)
            else:raw=m.group(1);n=clean_name(m.group(2))
            if not n:continue
            try:v=float(raw.replace(',','.'))
            except:continue
            if 0<v<=100 and (n,v) not in out:out.append((n,v))
    return out[:12]
def source_type(u):
    h=host(u)
    if 'firmenabc.' in h:return 'firmenabc'
    if 'firmenatlas.' in h:return 'firmenatlas'
    if 'wirtschaft.at' in h:return 'wirtschaft'
    if 'evi.gv.at' in h:return 'evi'
    if 'linkedin.com' in h:return 'linkedin'
    return 'other'

def collect(row):
    official=[];seen=set();sites=[x.strip() for x in (row.get('websites') or '').split(' | ') if x.strip()]
    for site in sites[:2]:
        u=site if '://' in site else 'https://'+site;fu,hh=get(u)
        if not hh:continue
        bh=host(fu);queue=[(fu,hh)]
        while queue and len(official)<12:
            uu,h=queue.pop(0)
            if uu in seen:continue
            seen.add(uu);t=text(h);official.append({'url':uu,'text':t[:350000]})
            b=BeautifulSoup(h,'html.parser');cand=[]
            for a in b.find_all('a',href=True):
                href=urljoin(uu,a['href']).split('#')[0];lab=(a.get_text(' ',strip=True)+' '+href).lower()
                if host(href)==bh and any(k in lab for k in ['impressum','team','partner','people','personen','geschäftsführung','geschaeftsfuehrung','unternehmen','ueber-uns','uber-uns','about','kanzlei']):cand.append(href)
            for href in cand[:14]:
                if href not in seen and len(queue)+len(official)<12:
                    u2,h2=get(href)
                    if h2:queue.append((u2,h2))
    name=row['group_name'];sr=[]
    qs=[f'"{name}" Geschäftsführer',f'"{name}" Gesellschafter',f'"{name}" Inhaber',f'"{name}" Partner Steuerberatung',f'"{name}" Firmenbuch']
    for q in qs:
        for x in search(q):
            if x['url'] and matches_company(name,x['title']+' '+x['snippet']) and x['url'] not in [y['url'] for y in sr]:sr.append(x)
        time.sleep(random.uniform(.03,.08))
    fetched=[]
    for x in sr[:18]:
        if 'linkedin.com' in host(x['url']):continue
        u,h=get(x['url'],8)
        if h:fetched.append({'url':u,'text':text(h)[:250000]})
        if len(fetched)>=7:break
    return official,sr[:25],fetched

def main_result(row):
    official,sr,fetched=collect(row);management={};owners={};evidence=[]
    # Official pages are the strongest role source.
    for p in official:
        t=p['text'];url=p['url']
        for n in names_near(t,ROLE_WORDS+PARTNER_WORDS):
            management.setdefault(n,{'name':n,'title':role_for(n,t),'legal_entity':row['group_name'],'url':url})
        for n in names_near(t,OWNER_WORDS):
            owners.setdefault(n,{'name':n,'owner_type':'individual','share_pct':None,'legal_entity':row['group_name'],'url':url})
        for n,v in shares_near(t):
            owners[n]={'name':n,'owner_type':'individual','share_pct':v,'legal_entity':row['group_name'],'url':url}
    # Fetched business pages may corroborate or recover names.
    external_hits={}
    for p in fetched:
        t=p['text'];url=p['url']
        for n in names_near(t,ROLE_WORDS):external_hits.setdefault(n,[]).append((url,role_for(n,t),'management'))
        for n in names_near(t,OWNER_WORDS):external_hits.setdefault(n,[]).append((url,'Owner','owner'))
        for n,v in shares_near(t):
            owners[n]={'name':n,'owner_type':'individual','share_pct':v,'legal_entity':row['group_name'],'url':url};external_hits.setdefault(n,[]).append((url,'Owner','owner'))
    # Search snippets: accept management only if corroborated across two URLs, or if exact role appears and source is a business directory.
    for x in sr:
        blob=x['title']+' '+x['snippet'];url=x['url'];st=source_type(url)
        for n in names_near(blob,ROLE_WORDS):external_hits.setdefault(n,[]).append((url,role_for(n,blob),'management'))
        for n in names_near(blob,OWNER_WORDS):external_hits.setdefault(n,[]).append((url,'Owner','owner'))
    for n,hits in external_hits.items():
        urls=list(dict.fromkeys(h[0] for h in hits));kinds={h[2] for h in hits}
        trusted=any(source_type(u) in {'firmenabc','firmenatlas','wirtschaft','evi'} for u in urls)
        if 'management' in kinds and n not in management and (len(urls)>=2 or trusted):
            h=next(h for h in hits if h[2]=='management');management[n]={'name':n,'title':h[1],'legal_entity':row['group_name'],'url':h[0]}
        if 'owner' in kinds and n not in owners and (len(urls)>=2 or trusted):
            h=next(h for h in hits if h[2]=='owner');owners[n]={'name':n,'owner_type':'individual','share_pct':None,'legal_entity':row['group_name'],'url':h[0]}
    # Cull obvious company-name fragments and duplicates.
    ct=set(company_tokens(row['group_name']))
    def ok(n):
        toks=[x.lower() for x in n.split()];return not any(x in ct for x in toks) and len(n)>=5
    management={n:x for n,x in management.items() if ok(n)};owners={n:x for n,x in owners.items() if ok(n)}
    # Evidence is generated from accepted claims only.
    for x in list(management.values())[:8]:evidence.append({'url':x['url'],'source_type':'official_site' if any(x['url']==p['url'] for p in official) else source_type(x['url']),'fact':f"Public source identifies {x['name']} as {x['title']} for the matching Austrian firm/group."})
    for x in list(owners.values())[:8]:
        detail=f" with {x['share_pct']}%" if x['share_pct'] is not None else ''
        evidence.append({'url':x['url'],'source_type':'official_site' if any(x['url']==p['url'] for p in official) else source_type(x['url']),'fact':f"Public source identifies {x['name']} as owner/shareholder{detail} of the matching firm/entity."})
    # Primary-DM selection mirrors the Spedition policy.
    p=[];major=[x for x in owners.values() if x.get('share_pct') is not None and x['share_pct']>=33]
    if major:
        for x in sorted(major,key=lambda z:-(z.get('share_pct') or 0))[:3]:p.append({'name':x['name'],'role':'Owner/Gesellschafter','reason':'Material publicly documented ownership makes this person a principal decision maker.','url':x['url']})
    elif owners and not any(k in (' '+row['group_name'].lower()+' ') for k in NETWORKS):
        for x in list(owners.values())[:2]:p.append({'name':x['name'],'role':'Owner/Gesellschafter','reason':'Public source identifies ownership; share percentage is not safely available.','url':x['url']})
    if not p:
        ranked=sorted(management.values(),key=lambda x:(0 if x['title'] in {'Geschäftsführer','Managing Partner','Vorstand','Geschäftsführung'} else 1,x['name']))
        for x in ranked[:3]:p.append({'name':x['name'],'role':x['title'],'reason':'Confirmed Austrian operational leadership is the best supported first-outreach target where ownership control is unavailable or inappropriate.','url':x['url']})
    if major:
        ownership_type='INDIVIDUAL_FAMILY_CONTROL' if any((x.get('share_pct') or 0)>=50 for x in major) else 'PARTNER_OWNED'
        ultimate='; '.join(x['name'] for x in major)
        structure='Public sources identify material individual shareholders: '+', '.join(f"{x['name']} {x['share_pct']}%" for x in major)+'.'
    elif owners:
        ownership_type='PARTNER_OWNED';ultimate='; '.join(x['name'] for x in list(owners.values())[:4]);structure='Public sources identify owner/shareholder names, but complete share percentages were not safely established.'
    else:
        ownership_type='CORPORATE_GROUP' if any(k in (' '+row['group_name'].lower()+' ') for k in NETWORKS) else 'UNRESOLVED';ultimate='unresolved';structure='Ownership/control layer was not safely established from public evidence; operational management is retained where verified.'
    conf='HIGH' if major and management else ('MEDIUM_HIGH' if p and evidence else ('MEDIUM' if p else 'LOW'))
    note='No ownership was inferred from surname. Unknown share percentages remain null. For international/network firms the Austrian operational leadership is preferred over a global parent.'
    return {'group_key':row['group_key'],'group_name':row['group_name'],'management':list(management.values())[:10],'owners':list(owners.values())[:10],'ultimate_owner':ultimate,'ownership_structure':structure,'ownership_type':ownership_type,'primary_decision_makers':p,'confidence':conf,'evidence':evidence[:16],'review_note':note}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-jsonl',required=True);a=ap.parse_args();rows=list(csv.DictReader(open(a.input_csv,encoding='utf-8-sig',newline='')));os.makedirs(os.path.dirname(a.output_jsonl) or '.',exist_ok=True)
    with open(a.output_jsonl,'w',encoding='utf-8') as out:
        for i,row in enumerate(rows,1):
            try:o=main_result(row)
            except Exception as e:o={'group_key':row['group_key'],'group_name':row['group_name'],'management':[],'owners':[],'ultimate_owner':'unresolved','ownership_structure':'Public ownership research failed to establish a reliable structure.','ownership_type':'UNRESOLVED','primary_decision_makers':[],'confidence':'LOW','evidence':[],'review_note':f'Worker error {type(e).__name__}; no unsupported claim emitted.'}
            out.write(json.dumps(o,ensure_ascii=False)+'\n');out.flush();print(f'{i}/{len(rows)} {row["group_name"]} -> DM={len(o["primary_decision_makers"])} owners={len(o["owners"])}',flush=True);time.sleep(random.uniform(.03,.10))
if __name__=='__main__':main()
