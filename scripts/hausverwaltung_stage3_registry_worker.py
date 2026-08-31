#!/usr/bin/env python3
import argparse,csv,json,re,time,random,unicodedata
from urllib.parse import quote_plus,urlparse,unquote
import requests
from bs4 import BeautifulSoup

H={'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36','Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
LEGAL={'gmbh','gesmbh','m.b.h','ag','kg','og','holding','gesellschaft','privatstiftung','stiftung','se','bv','b.v','sarl','s.r.l','ltd','inc','aktiengesellschaft'}
HEADINGS=['Geschäftsführer','Geschaeftsfuehrer','Geschäftsführer/in','Gesellschafter','Gesellschafter/in','Aktionär','Aktionaer','Inhaber','persönlich haftender Gesellschafter','Komplementär','Komplementaer','Kommanditist','Aufsichtsrat','Prokurist','Finanzdaten','Beteiligungen','Firmenhistorie','Unternehmensdokumente','Alle Angaben']

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    s=s.replace('&',' und ')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()
def host(u):
    try:return urlparse(u).netloc.lower().removeprefix('www.')
    except:return ''
def get(u,timeout=15):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and 'text' in r.headers.get('content-type','text/html'):
            r.encoding=r.apparent_encoding or r.encoding
            return r.url,r.text[:2500000]
    except Exception: pass
    return '',''
def search(q):
    out=[]
    for base in ['https://www.bing.com/search?q=','https://html.duckduckgo.com/html/?q=']:
        try:
            r=requests.get(base+quote_plus(q),headers=H,timeout=15)
            if r.status_code!=200: continue
            b=BeautifulSoup(r.text,'html.parser')
            if 'bing.com' in base:
                for x in b.select('li.b_algo')[:10]:
                    a=x.select_one('h2 a'); p=x.select_one('.b_caption p')
                    if a: out.append((a.get('href',''),a.get_text(' ',strip=True),(p.get_text(' ',strip=True) if p else '')))
            else:
                for x in b.select('.result')[:10]:
                    a=x.select_one('.result__a'); p=x.select_one('.result__snippet')
                    if not a: continue
                    u=a.get('href',''); m=re.search(r'[?&]uddg=([^&]+)',u)
                    if m: u=unquote(m.group(1))
                    out.append((u,a.get_text(' ',strip=True),(p.get_text(' ',strip=True) if p else '')))
            if out: break
        except Exception: pass
    return out

def company_tokens(name):
    toks=[x for x in norm(name).split() if len(x)>=4 and x not in {'gmbh','gesmbh','gesellschaft','immobilien','immobilienverwaltung','hausverwaltung','management'}]
    return toks[:5]
def good_match(name,title,snip):
    hay=norm(title+' '+snip); toks=company_tokens(name)
    return not toks or sum(t in hay for t in toks)>=max(1,min(2,len(toks)))

def find_profile(name,domain):
    qs=[f'site:{domain} "{name}"',f'"{name}" {domain}']
    for q in qs:
        for u,t,s in search(q):
            if domain in host(u) and good_match(name,t,s):
                return u
        time.sleep(random.uniform(.05,.15))
    return ''

def lines(html):
    b=BeautifulSoup(html,'html.parser')
    return [re.sub(r'\s+',' ',x).strip() for x in b.get_text('\n',strip=True).splitlines() if re.sub(r'\s+',' ',x).strip()]
def section(ls, heading, maxn=60):
    inds=[i for i,x in enumerate(ls) if x.strip().lower()==heading.lower() or x.strip().lower().startswith(heading.lower())]
    if not inds:return []
    i=inds[0]+1; out=[]
    for x in ls[i:i+maxn]:
        if any(x.lower()==h.lower() or x.lower().startswith(h.lower()) for h in HEADINGS if h.lower()!=heading.lower()): break
        out.append(x)
    return out

def clean_person(s):
    s=re.sub(r'^(Herr|Frau/Herr|Frau)\s+','',s).strip()
    s=s.replace('Privatperson','').strip()
    s=re.sub(r'\s+',' ',s)
    if len(s)<4:return ''
    bad=['alleinvertretungsberechtigt','gemeinsam vertretungsberechtigt','vertritt seit','eingetragen am','anteil:']
    if any(b in s.lower() for b in bad):return ''
    if re.search(r'\b(GmbH|Ges\.m\.b\.H|AG|KG|OG|Holding|Stiftung|Gesellschaft)\b',s,re.I):return ''
    return s

def clean_company(s):
    s=re.sub(r'^Firma\s+','',s).strip()
    s=re.sub(r'\s+(Ges\.m\.b\.H\.|Ges\.m\.b\.H|Privatstiftung|Aktiengesellschaft)$','',s).strip()
    return re.sub(r'\s+',' ',s)

def parse_firmenabc(name,u,html):
    ls=lines(html); management=[]; owners=[]
    # GF sections
    for h in ['Geschäftsführer','Geschäftsführer/in']:
        sec=section(ls,h)
        for x in sec:
            if x.startswith(('Herr ','Frau ','Frau/Herr ')):
                p=clean_person(x)
                if p and p not in [m['name'] for m in management]: management.append({'name':p,'role':'Geschäftsführer','source_url':u})
    # owners / shareholders
    for h in ['Gesellschafter','Aktionär','Inhaber','persönlich haftender Gesellschafter','Komplementär']:
        sec=section(ls,h)
        cur=None
        for x in sec:
            if x.startswith('Firma '):
                cur={'name':clean_company(x),'owner_type':'entity','share_pct':None,'source_url':u}; owners.append(cur)
            elif x.startswith(('Herr ','Frau ','Frau/Herr ')):
                p=clean_person(x)
                if p:
                    cur={'name':p,'owner_type':'individual','share_pct':None,'source_url':u}; owners.append(cur)
            elif x.lower().startswith('anteil:') and cur:
                m=re.search(r'(\d{1,3}(?:[\.,]\d+)?)\s*%',x)
                if m:
                    try:cur['share_pct']=float(m.group(1).replace(',','.'))
                    except:pass
    # de-dupe
    ded=[];seen=set()
    for o in owners:
        k=norm(o['name'])
        if not k or k in seen:continue
        seen.add(k);ded.append(o)
    return management,ded

def parse_evi(name,u,html):
    ls=lines(html); management=[];owners=[]
    for h in ['Geschäftsführer/in','Geschäftsführer']:
        sec=section(ls,h)
        for x in sec:
            if x.startswith('• '): x=x[2:].strip()
            p=clean_person(x)
            if p and not re.search(r'\b(GmbH|AG|KG|Stiftung|Gesellschaft)\b',p,re.I): management.append({'name':p,'role':'Geschäftsführer','source_url':u})
    for h in ['Gesellschafter/in','Gesellschafter','Aktionär']:
        sec=section(ls,h)
        for x in sec:
            if x.startswith('• '): x=x[2:].strip()
            if not x or x.lower().startswith(('eingetragen','vertritt')):continue
            typ='entity' if re.search(r'\b(GmbH|AG|KG|OG|Stiftung|Gesellschaft|Holding|SE)\b',x,re.I) else 'individual'
            owners.append({'name':x,'owner_type':typ,'share_pct':None,'source_url':u})
    return management,owners

def official_management(name,site):
    if not site:return []
    u=site if '://' in site else 'https://'+site
    fu,h=get(u)
    if not h:return []
    b=BeautifulSoup(h,'html.parser'); cands=[fu]
    for a in b.find_all('a',href=True):
        href=requests.compat.urljoin(fu,a['href']).split('#')[0]; lab=(a.get_text(' ',strip=True)+' '+href).lower()
        if host(href)==host(fu) and any(k in lab for k in ['impressum','geschaeftsfuehr','geschäftsführ','management','team','unternehmen']):cands.append(href)
    out=[]
    for uu in list(dict.fromkeys(cands))[:5]:
        u2,h2=get(uu)
        if not h2:continue
        t=' '.join(lines(h2))
        pats=[r'(?:Geschäftsführer(?:in)?|Managing Director|Geschäftsleitung|Vorstand)\s*[:\-]?\s*((?:(?:Dr\.|Mag\.|DI|Ing\.|MBA|MSc|BSc)\s+)*[A-ZÄÖÜ][\wÄÖÜäöüß\-]+(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüß\-]+){1,3})']
        for p in pats:
            for m in re.finditer(p,t):
                n=m.group(1).strip()
                if n and n not in [x['name'] for x in out]:out.append({'name':n,'role':'Geschäftsführer/Management','source_url':u2})
    return out[:5]

def research_entity(name,site='',depth=0,seen=None):
    seen=seen or set(); k=norm(name)
    if not k or k in seen or depth>2:return None
    seen.add(k)
    fab=find_profile(name,'firmenabc.at'); evi=find_profile(name,'evi.gv.at')
    management=[];owners=[];sources=[]
    if fab:
        u,h=get(fab)
        if h:
            management,owners=parse_firmenabc(name,u,h);sources.append(u)
    if (not management or not owners) and evi:
        u,h=get(evi)
        if h:
            m2,o2=parse_evi(name,u,h);sources.append(u)
            if not management:management=m2
            if not owners:owners=o2
    if not management and site:management=official_management(name,site)
    # e.U./person target fallback
    if not owners and re.search(r'\be\.u\.?\b',name,re.I):
        p=re.sub(r'\be\.u\.?\b','',name,flags=re.I).strip(' ,')
        owners=[{'name':p,'owner_type':'individual','share_pct':100.0,'source_url':sources[0] if sources else site}]
    # build ultimate control conservatively
    ultimate=[]; chain=[]
    majors=[o for o in owners if o.get('share_pct') is not None and o['share_pct']>=25]
    indiv=[o for o in majors if o['owner_type']=='individual']
    if indiv:
        ultimate=[{'name':o['name'],'share_pct':o['share_pct'],'type':'individual'} for o in indiv]
    else:
        ents=[o for o in owners if o['owner_type']=='entity' and (o.get('share_pct') is None or o.get('share_pct',0)>=25)]
        for o in ents[:3]:
            on=o['name']; low=norm(on)
            if any(x in low for x in ['privatstiftung','stiftung','stadt wien','wien holding','oebb holding','obag','republik osterreich','uniCredit'.lower(),'zurich insurance','grawe','vonovia','cbre','strabag','apleona','mcarthurglen','unibail','porsche holding','raiffeisen']):
                ultimate.append({'name':on,'share_pct':o.get('share_pct'),'type':'entity_control'})
                continue
            sub=research_entity(on,'',depth+1,seen)
            if sub and sub.get('ultimate_control'):
                chain.append({'owner':on,'source_urls':sub.get('source_urls',[])})
                for z in sub['ultimate_control']:
                    if z['name'] not in [q['name'] for q in ultimate]:ultimate.append(z)
            else:
                ultimate.append({'name':on,'share_pct':o.get('share_pct'),'type':'direct_parent_control'})
    if not ultimate and owners:
        ultimate=[{'name':o['name'],'share_pct':o.get('share_pct'),'type':o['owner_type']} for o in owners[:4]]
    # primary DM
    pdm=[]
    major_ind=sorted([o for o in owners if o['owner_type']=='individual' and (o.get('share_pct') or 0)>=33],key=lambda x:-(x.get('share_pct') or 0))
    if major_ind:
        for o in major_ind[:2]:pdm.append({'name':o['name'],'role':'Owner/Gesellschafter','reason':'material direct ownership','source_url':o.get('source_url','')})
    elif management:
        for m in management[:2]:pdm.append({'name':m['name'],'role':m['role'],'reason':'Austrian operational leadership; ownership is corporate/public/fragmented or no controlling individual was verified','source_url':m.get('source_url','')})
    elif owners:
        for o in owners[:2]:pdm.append({'name':o['name'],'role':'Owner/Gesellschafter','reason':'best verified decision-maker evidence','source_url':o.get('source_url','')})
    typ='UNRESOLVED'
    if owners:
        if any(o['owner_type']=='individual' and (o.get('share_pct') or 0)>=50 for o in owners):typ='INDIVIDUAL_FAMILY_CONTROL'
        elif any(o['owner_type']=='individual' for o in owners):typ='PARTNER_OWNED'
        elif any('stiftung' in norm(o['name']) for o in owners):typ='FOUNDATION_CONTROL'
        else:typ='CORPORATE_GROUP'
    conf='HIGH' if management and owners and pdm and sources else ('MEDIUM_HIGH' if pdm and (management or owners) else 'LOW')
    return {'management':management,'owners':owners,'ultimate_control':ultimate,'ownership_type':typ,'primary_decision_makers':pdm,'source_urls':list(dict.fromkeys(sources+[x.get('source_url','') for x in management+owners if x.get('source_url')])),'ownership_chain':chain,'confidence':conf}

def read_targets(path):
    if path.endswith('.tsv'):
        return list(csv.DictReader(open(path,encoding='utf-8'),delimiter='\t'))
    return list(csv.DictReader(open(path,encoding='utf-8-sig')))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);ap.add_argument('--start',type=int,default=0);ap.add_argument('--end',type=int);a=ap.parse_args()
    rows=read_targets(a.input);end=a.end if a.end is not None else len(rows); out=[]
    for idx,r in enumerate(rows[a.start:end],a.start+1):
        name=r.get('company_name') or r.get('group_name') or r.get('name');site=r.get('website','')
        res=research_entity(name,site) or {}
        obj={'no':r.get('no',idx),'company_name':name,'group_name':r.get('group_name',name),'group_key':r.get('group_key',name),'stage3_scope':r.get('stage3_scope','MAIN'),'process_fit_class':r.get('process_fit_class',''),'size_class':r.get('size_class',''),'website':site}
        obj.update(res);out.append(obj)
        print(idx,name,res.get('confidence'),len(res.get('management',[])),len(res.get('owners',[])),flush=True)
    with open(a.output,'w',encoding='utf-8') as f:
        for o in out:f.write(json.dumps(o,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
