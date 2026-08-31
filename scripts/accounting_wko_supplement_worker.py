#!/usr/bin/env python3
import argparse,csv,os,re,time,random
from urllib.parse import urlparse,urljoin
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
SERVICE=('bilanzbuchhaltung','buchhaltung','personalverrechnung','lohnverrechnung','payroll','accounting','jahresabschluss','bibu','rechnungswesen','kostenrechnung')
UNRELATED=('pharma','werkzeug','agrar','forst','rehabilitation','bildung','apotheken','veterinär','veterinaer','softwarehaus','maschinenbau','holzindustrie')
BAD=('jahr','jahre','partner','standort','standorte','büro','buero','filiale','mandant','kunde','klient','umsatz','euro','eur','million','max.','maximal','bis zu','nicht mehr als','höchstens','hoechstens','arbeitgeber','arbeitnehmer','auva','zuschuss','entgeltfortzahlung','steuerfreiheit','zulage','grenzwert','schwellenwert','förderung','foerderung','gesetz','gesetzlich','kmu-definition')
EMP=r'(?:mitarbeiter(?:innen)?|mitarbeiter:innen|mitarbeitende|besch[aä]ftigte|kolleg(?:innen|en)|employees)'
PATS=[
 re.compile(r'(?i)(?:wir\s+)?(?:besch[aä]ftigen|z[aä]hlen|umfassen|haben|sind)\s+(?:derzeit\s+)?(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{1,4})\+?\s+'+EMP),
 re.compile(r'(?i)(?:team|kanzlei|unternehmen|gruppe)\s+(?:mit|von|umfasst|besteht\s+aus|z[aä]hlt)\s+(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)?\s*(\d{1,4})\+?\s+'+EMP),
 re.compile(r'(?i)(rund|ca\.?|circa|etwa|über|mehr\s+als|knapp)\s*(\d{2,4})\+?\s+'+EMP)]
WHOLE=re.compile(r'(?i)(?:unser\s+(?:gesamtes\s+)?team|team\s+besteht\s+aus|wir\s+sind\s+ein\s+team\s+von)')

def host(u):
    try:return re.sub(r'^www\.','',urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0])
    except:return ''
def get(u,timeout=9):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and 'text/html' in r.headers.get('content-type',''):
            r.encoding=r.apparent_encoding or r.encoding;return r.url,r.text[:1200000]
    except:pass
    return '',''
def text(h):return re.sub(r'\s+',' ',BeautifulSoup(h or '','html.parser').get_text(' ',strip=True))
def counts(t):
    out=[]
    for p in PATS:
        for m in p.finditer(t):
            n=int(m.group(2));ctx=t[max(0,m.start()-170):min(len(t),m.end()+230)];cl=ctx.lower()
            if 5<=n<=10000 and not 1900<=n<=2100 and not any(x in cl for x in BAD):out.append((n,bool(m.group(1)),ctx))
    return out
def service_score(t,name):
    low=(name+' '+t[:90000]).lower();hits=sum(1 for x in SERVICE if x in low);bad=sum(1 for x in UNRELATED if x in low)
    return hits,bad
def crawl(row):
    pages=[];profiles=set();emails=set();jobs=set();seen=set();sites=[x.strip() for x in (row.get('websites') or '').split(' | ') if x.strip()]
    for site in sites[:2]:
        u=site if '://' in site else 'https://'+site;fu,hh=get(u)
        if not hh:continue
        bh=host(fu);queue=[(fu,hh)]
        while queue and len(pages)<10:
            uu,h=queue.pop(0)
            if uu in seen:continue
            seen.add(uu);t=text(h);pages.append((uu,t));b=BeautifulSoup(h,'html.parser');links=[]
            for a in b.find_all('a',href=True):
                href=urljoin(uu,a['href']).split('#')[0];lab=(a.get_text(' ',strip=True)+' '+href).lower()
                if host(href)!=bh:continue
                if any(k in lab for k in ['team','mitarbeiter','über-uns','ueber-uns','about','kanzlei','buchhaltung','personalverrechnung','karriere','jobs']):links.append(href)
                if any(k in lab for k in ['/team/','/mitarbeiter/','/person/','teammitglied']):profiles.add(href)
                if any(k in lab for k in ['karriere','jobs','stellen']):jobs.add(href)
            for e in re.findall(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',t):
                dom=e.lower().split('@')[-1]
                if bh and (dom==bh or dom.endswith('.'+bh)) and not any(e.lower().startswith(x) for x in ['office@','info@','kontakt@','mail@','bewerbung@']):emails.add(e.lower())
            for href in links[:10]:
                if href not in seen and len(queue)+len(pages)<10:
                    u2,h2=get(href)
                    if h2:queue.append((u2,h2))
    return pages,len(profiles),len(emails),len(jobs)
def make(row,verdict,lo,hi,scope,conf,summary,url='',fact='',relevance='RELEVANT_ACCOUNTING_FIRM'):
    r=dict(row);r.update({'agent_verdict':verdict,'agent_employee_low':'' if lo is None else lo,'agent_employee_high':'' if hi is None else hi,'agent_count_scope':scope,'agent_confidence':conf,'agent_research_summary':summary,'agent_source_urls':url,'agent_source_facts':fact,'agent_review_note':relevance,'agent_researcher_consensus':'SINGLE','accounting_relevance':relevance});return r
def main_one(row):
    pages,profiles,emails,jobs=crawl(row);combined=' '.join(t for _,t in pages);sh,bad=service_score(combined,row.get('group_name','')+' '+row.get('member_entities',''))
    if sh<2 or (bad>=2 and sh<4):
        return make(row,'UNRESOLVED',None,None,'UNKNOWN','HIGH',f'Excluded from the accounting supplement: official public site does not establish a primary bookkeeping/accounting/payroll business (service signals={sh}, unrelated-sector signals={bad}).',relevance='NOT_RELEVANT_ACCOUNTING_FIRM')
    vals=[]
    for u,t in pages:
        for n,approx,ctx in counts(t):vals.append((n,approx,u,ctx,bool(WHOLE.search(t))))
    if vals:
        n,approx,u,ctx,whole=max(vals,key=lambda x:x[0]);fact=f'Official accounting-firm page states {n} employees in context: {ctx[:420]}'
        if n>=30:return make(row,'CONFIRMED_30_PLUS',n,None,'AUSTRIA_GROUP' if int(float(row.get('legal_entities_count') or 1))>1 else 'AUSTRIA_LEGAL_ENTITY','HIGH',f'Fresh official-site evidence proves the relevant bookkeeping/accounting business has at least {n} employees.',u,fact)
        if n>=20:
            if whole and not approx:return make(row,'CONFIRMED_20_29',n,n,'AUSTRIA_LEGAL_ENTITY','HIGH',f'Fresh official whole-team statement gives {n} employees.',u,fact)
            return make(row,'CONFIRMED_20_PLUS',n,None,'AUSTRIA_LEGAL_ENTITY','HIGH',f'Fresh official-site evidence proves at least {n} employees.',u,fact)
        if n<20 and whole and not approx:return make(row,'BELOW_20',n,n,'AUSTRIA_LEGAL_ENTITY','HIGH',f'Fresh official whole-team statement gives {n} employees.',u,fact)
    lb=max(profiles,emails)
    u=pages[0][0] if pages else ''
    if lb>=30:return make(row,'CONFIRMED_30_PLUS',lb,None,'AUSTRIA_LEGAL_ENTITY','HIGH',f'Official accounting-firm site exposes at least {lb} distinct staff profiles/personal domain emails.',u,f'Official staff lower bound: {lb}.')
    if lb>=20:return make(row,'CONFIRMED_20_PLUS',lb,None,'AUSTRIA_LEGAL_ENTITY','HIGH',f'Official accounting-firm site exposes at least {lb} distinct staff profiles/personal domain emails.',u,f'Official staff lower bound: {lb}.')
    signals=sum([lb>=12,jobs>=2,int(float(row.get('legal_entities_count') or 1))>=2])
    if signals>=2 and u:return make(row,'LIKELY_20_PLUS',20,None,'AUSTRIA_GROUP','MEDIUM',f'Relevant accounting firm has multiple scale signals but no clean employee count: staff lower bound={lb}, jobs={jobs}, legal entities={row.get("legal_entities_count")}.',u,'Multiple fresh scale signals; no confirmation.')
    return make(row,'UNRESOLVED',None,None,'UNKNOWN','LOW','Relevant bookkeeping/accounting firm, but fresh public evidence does not safely prove 20 employees.',u,'No reliable 20+ headcount found.' if u else '')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-csv',required=True);a=ap.parse_args();rows=list(csv.DictReader(open(a.input_csv,encoding='utf-8-sig',newline='')));out=[]
    for i,r in enumerate(rows,1):
        try:o=main_one(r)
        except Exception as e:o=make(r,'UNRESOLVED',None,None,'UNKNOWN','LOW',f'WKO supplement audit error {type(e).__name__}; no promotion.',relevance='AUDIT_ERROR')
        out.append(o);print(f'{i}/{len(rows)} {r["group_name"]} -> {o["accounting_relevance"]} {o["agent_verdict"]} {o["agent_employee_low"]}',flush=True);time.sleep(random.uniform(.03,.10))
    fields=list(out[0].keys()) if out else []
    os.makedirs(os.path.dirname(a.output_csv) or '.',exist_ok=True)
    with open(a.output_csv,'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
if __name__=='__main__':main()
