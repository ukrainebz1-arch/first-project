import csv,os,re,json,time,random,ssl
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

SHARD=int(os.environ.get('SHARD','0')); SHARDS=int(os.environ.get('SHARDS','20'))
SRC=os.environ.get('SRC','source/wko_bookkeeping_austria_combined.csv')
OUT=os.environ.get('OUT','site_out'); os.makedirs(OUT,exist_ok=True)
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.5'}
GENERIC={'info','office','kanzlei','kontakt','mail','buchhaltung','steuerberatung','sekretariat','team','bewerbung','karriere','jobs','datenschutz','rechnung','support','hello','willkommen','admin'}
TERMS=('team','mitarbeiter','mitarbeitende','ueber-uns','über-uns','about','kanzlei','unternehmen','karriere','career','jobs','standort','office','partner','people','personen')

with open(SRC,encoding='utf-8-sig',newline='') as f: allrows=list(csv.DictReader(f))
rows=[]
for i,r in enumerate(allrows):
    if i%SHARDS!=SHARD: continue
    u=(r.get('website') or '').split(' | ')[0].strip()
    if u: rows.append((i,r,u))
print('SHARD',SHARD,'WEBSITES',len(rows),flush=True)

def norm(s):return re.sub(r'\s+',' ',s or '').strip()
def host(u):return urlparse(u).netloc.lower().replace('www.','').split(':')[0]
def same_domain(a,b):
    ha,hb=host(a),host(b)
    return ha==hb or ha.endswith('.'+hb) or hb.endswith('.'+ha)

def get(url):
    try:
        r=requests.get(url,headers=H,timeout=14,allow_redirects=True,verify=True)
        if r.status_code<400 and 'text/html' in (r.headers.get('content-type') or 'text/html').lower(): return r
    except: pass
    return None

def extract_evidence(text):
    ev=[]
    patterns=[
      r'((?:über|ueber|mehr als|rund|circa|ca\.?|knapp)?\s*\d{1,4}\s+(?:Mitarbeiter(?:innen|:innen)?|Mitarbeitende|Beschäftigte|Kolleg(?:innen|:innen)?|Teammitglieder|Köpfe))',
      r'((?:Team|Kanzlei|Unternehmen|Gruppe)\s+(?:von|mit|aus|umfasst|besteht aus)?\s*(?:über|mehr als|rund|ca\.?)?\s*\d{1,4}\s+(?:Personen|Mitarbeiter(?:innen|:innen)?|Mitarbeitenden|Köpfen))',
      r'((?:über|mehr als|rund|ca\.?)\s*\d{1,4}\s+(?:Expert(?:innen|:innen)?|Steuerberater(?:innen|:innen)?|Berater(?:innen|:innen)?))',
    ]
    for p in patterns:
        for m in re.finditer(p,text,re.I):
            s=norm(m.group(1))
            if s not in ev: ev.append(s)
    return ev[:12]

def num_from_evidence(ev):
    vals=[]
    for s in ev:
        m=re.search(r'(\d{1,4})',s)
        if m: vals.append(int(m.group(1)))
    return max(vals) if vals else 0

def parse_page(url,html):
    soup=BeautifulSoup(html,'html.parser')
    text=norm(soup.get_text(' ',strip=True))
    ev=extract_evidence(text)
    emails=[]; profile_links=[]; relevant=[]; linkedin=[]; jobs=[]
    basehost=host(url)
    for a in soup.find_all('a',href=True):
        h=(a.get('href') or '').strip(); label=norm(a.get_text(' ',strip=True)).lower()
        low=h.lower()
        if low.startswith('mailto:'):
            e=h.split(':',1)[1].split('?',1)[0].strip().lower()
            if '@' in e and e not in emails: emails.append(e)
        elif low.startswith('http') or low.startswith('/') or not re.match(r'^[a-z]+:',low):
            u=urljoin(url,h).split('#')[0]
            if 'linkedin.com/company/' in u.lower() and u not in linkedin: linkedin.append(u)
            if same_domain(url,u):
                token=(label+' '+urlparse(u).path.lower())
                if any(t in token for t in TERMS) and u.rstrip('/')!=url.rstrip('/') and u not in relevant:
                    relevant.append(u)
                if re.search(r'/(team|mitarbeiter|mitarbeitende|people|personen|partner)/[^/?#]{2,}',urlparse(u).path,re.I):
                    if u not in profile_links: profile_links.append(u)
                if any(t in token for t in ('karriere','career','jobs','stellen','bewerb')) and u not in jobs: jobs.append(u)
    personal=[]
    for e in emails:
        local=e.split('@',1)[0]
        if local not in GENERIC and not any(local.startswith(g+'.') or local.startswith(g+'-') for g in GENERIC): personal.append(e)
    return text,ev,personal,profile_links,relevant,linkedin,jobs

fields=['source_index','firmaid','company_name','city','website_input','website_final','http_status','pages_crawled','explicit_employee_evidence','explicit_employee_max','personal_emails_count','team_profile_links_count','team_lower_bound','locations_signal','career_signal','linkedin_url','relevant_pages','crawl_notes']
path=os.path.join(OUT,f'sites_{SHARD:02d}.csv')
with open(path,'w',encoding='utf-8-sig',newline='') as out:
  w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
  for k,(idx,row,start) in enumerate(rows):
    r=get(start)
    if not r:
      w.writerow({'source_index':idx,'firmaid':row['firmaid'],'company_name':row['company_name'],'city':row['city'],'website_input':start,'crawl_notes':'homepage_fetch_failed'}); continue
    pages=[r.url]; all_ev=[]; all_personal=set(); all_profiles=set(); all_linkedin=[]; all_jobs=set(); all_relevant=[]; loc_count=0
    text,ev,personal,profiles,relevant,linkedin,jobs=parse_page(r.url,r.text)
    all_ev+=ev; all_personal.update(personal); all_profiles.update(profiles); all_linkedin+=linkedin; all_jobs.update(jobs); all_relevant+=relevant
    queue=[]
    # prioritize team/about; then career/location; max 8 additional pages
    for u in relevant:
      if u not in queue: queue.append(u)
    queue=queue[:8]
    for u in queue:
      rr=get(u)
      if not rr: continue
      pages.append(rr.url)
      tx,ev2,pe2,pr2,rel2,li2,j2=parse_page(rr.url,rr.text)
      all_ev += [x for x in ev2 if x not in all_ev]
      all_personal.update(pe2); all_profiles.update(pr2); all_linkedin += [x for x in li2 if x not in all_linkedin]; all_jobs.update(j2)
      if any(t in (urlparse(rr.url).path.lower()) for t in ('standort','office','locations')):
        # count address-ish postal codes as a rough locations signal
        loc_count=max(loc_count,len(set(re.findall(r'\b[1-9]\d{3}\b',tx))))
    emp=max(num_from_evidence(all_ev),len(all_personal),len(all_profiles))
    w.writerow({
      'source_index':idx,'firmaid':row['firmaid'],'company_name':row['company_name'],'city':row['city'],'website_input':start,'website_final':r.url,'http_status':r.status_code,
      'pages_crawled':len(pages),'explicit_employee_evidence':' | '.join(all_ev),'explicit_employee_max':num_from_evidence(all_ev),'personal_emails_count':len(all_personal),
      'team_profile_links_count':len(all_profiles),'team_lower_bound':emp,'locations_signal':loc_count,'career_signal':1 if all_jobs else 0,'linkedin_url':all_linkedin[0] if all_linkedin else '',
      'relevant_pages':' | '.join(pages[1:]),'crawl_notes':''})
    if (k+1)%15==0: print('PROGRESS',SHARD,k+1,'/',len(rows),flush=True)
print('DONE',path,flush=True)
