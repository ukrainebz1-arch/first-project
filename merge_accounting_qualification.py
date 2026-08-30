import csv, glob, json, os, re, unicodedata
from collections import defaultdict, Counter
from urllib.parse import urlparse

INDIR=os.environ.get('INDIR','chunks')
OUTDIR=os.environ.get('OUTDIR','final_qualification')
os.makedirs(OUTDIR,exist_ok=True)
SOCIAL={'facebook.com','instagram.com','linkedin.com','xing.com','youtube.com','tiktok.com'}
GENERIC_MAIL={'gmail.com','gmx.at','gmx.net','outlook.com','hotmail.com','aon.at','icloud.com','yahoo.com','yahoo.de'}
STATUS_RANK={'CONFIRMED_30_PLUS':6,'CONFIRMED_20_PLUS':5,'CONFIRMED_20_29':5,'LIKELY_20_PLUS':4,'UNRESOLVED':2,'BELOW_20_SIGNAL':1,'LOW_LIKELIHOOD_SOLO':0}

def norm(s):
    s=unicodedata.normalize('NFKD',s or ''); s=''.join(c for c in s if not unicodedata.combining(c)).lower(); s=re.sub(r'[^a-z0-9]+',' ',s); return re.sub(r'\s+',' ',s).strip()
def host(url):
    try:
        u=url if '://' in (url or '') else 'https://'+(url or ''); h=urlparse(u).netloc.lower().split(':')[0]; return re.sub(r'^www\.','',h)
    except:return ''
def emaildom(e):
    try:return e.lower().split('@',1)[1].strip()
    except:return ''
def phonekey(s):
    d=re.sub(r'\D','',s or ''); return d[-9:] if len(d)>=9 else ''
def namebase(s):
    t=norm(s)
    for x in ['gmbh','gesmbh','mbh','kg','og','ag','se','flexco','e u','steuerberatung','steuerberater','buchhaltung','bilanzbuchhaltung','wirtschaftstreuhand','wirtschaftsprufung','wirtschaftspruefung','kanzlei']:
        t=re.sub(r'\b'+re.escape(x)+r'\b',' ',t)
    return re.sub(r'\s+',' ',t).strip()
def unionfind(n):
    p=list(range(n))
    def find(x):
        while p[x]!=x:
            p[x]=p[p[x]]; x=p[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:p[b]=a
    return p,find,union

def main():
    files=sorted(glob.glob(os.path.join(INDIR,'**','qualified_chunk_*.csv'),recursive=True))
    rows=[]
    for fp in files:
        with open(fp,encoding='utf-8-sig',newline='') as f: rows.extend(csv.DictReader(f))
    if len(rows)!=4331: raise RuntimeError(f'expected 4331 rows, got {len(rows)} from {len(files)} files')
    ids=[r['firmaid'] for r in rows]
    if len(set(ids))!=4331: raise RuntimeError('firmaid duplication after chunks')
    p,find,union=unionfind(len(rows))
    by_domain=defaultdict(list); by_phone=defaultdict(list); by_mail=defaultdict(list); by_name=defaultdict(list)
    for i,r in enumerate(rows):
        d=(r.get('discovered_domain') or r.get('original_domain') or '').lower().strip()
        if d and d not in SOCIAL and not d.endswith('wko.at'): by_domain[d].append(i)
        ph=phonekey(r.get('phones',''))
        if ph: by_phone[ph].append(i)
        md=emaildom(r.get('email',''))
        if md and md not in GENERIC_MAIL: by_mail[md].append(i)
        nb=namebase(r.get('company_name',''))
        if nb and len(nb)>=5: by_name[nb].append(i)
    # Strong group identifiers: same non-social domain or non-generic mail domain. Same phone also strong.
    for mp in [by_domain,by_mail,by_phone]:
        for k,inds in mp.items():
            if len(inds)>1:
                first=inds[0]
                for j in inds[1:]: union(first,j)
    # Exact normalized base name is only used when at least one other strong clue (same city/address prefix) exists.
    for nb,inds in by_name.items():
        if len(inds)>1:
            for a in range(len(inds)):
                for b in range(a+1,len(inds)):
                    i,j=inds[a],inds[b]; ri,rj=rows[i],rows[j]
                    if norm(ri.get('city'))==norm(rj.get('city')) or norm(ri.get('street'))==norm(rj.get('street')):
                        union(i,j)
    groups=defaultdict(list)
    for i,r in enumerate(rows): groups[find(i)].append(r)
    grows=[]
    for gid,members in groups.items():
        members=sorted(members,key=lambda r:(-STATUS_RANK.get(r['qualification_status'],0),-int(r.get('employee_estimate_min') or 0),r['company_name']))
        best=members[0]
        status=max((r['qualification_status'] for r in members),key=lambda s:STATUS_RANK.get(s,0))
        conf='HIGH' if any(r.get('confidence')=='HIGH' and STATUS_RANK.get(r['qualification_status'],0)>=4 for r in members) else ('MEDIUM' if any(r.get('confidence')=='MEDIUM' for r in members) else 'LOW')
        emin=max([int(r.get('employee_estimate_min') or 0) for r in members]+[0]); emax=max([int(r.get('employee_estimate_max') or 0) for r in members]+[0])
        domains=sorted({(r.get('discovered_domain') or r.get('original_domain') or '').strip() for r in members if (r.get('discovered_domain') or r.get('original_domain') or '').strip()})
        names=sorted({r['company_name'] for r in members}); cities=sorted({r.get('city','') for r in members if r.get('city')})
        urls=[]; reasons=[]; snippets=[]
        for r in members:
            for u in (r.get('source_urls') or '').split(' | '):
                if u and u not in urls: urls.append(u)
            if r.get('qualification_reason') and r['qualification_reason'] not in reasons: reasons.append(r['qualification_reason'])
            if r.get('evidence_snippet'): snippets.append(r['evidence_snippet'][:800])
        # Canonical display name: prefer business label if present on best member, otherwise company name.
        display=(best.get('business_label') or best['company_name']).strip()
        grows.append({
            'group_id':f'G{gid:04d}', 'company_or_group':display, 'qualification_status':status, 'confidence':conf,
            'employee_estimate_min':emin,'employee_estimate_max':emax,'wko_legal_entities':len(members),
            'cities':' | '.join(cities),'domains':' | '.join(domains),'member_companies':' | '.join(names),
            'phones':' | '.join(dict.fromkeys(x for r in members for x in (r.get('phones') or '').split(' | ') if x)),
            'emails':' | '.join(dict.fromkeys(x for r in members for x in (r.get('all_emails') or '').split(' | ') if x)),
            'websites':' | '.join(dict.fromkeys(x for r in members for x in (r.get('all_websites') or '').split(' | ') if x)),
            'qualification_reason':' || '.join(reasons)[:6000], 'source_urls':' | '.join(urls)[:12000],
            'wko_firmaids':' | '.join(r['firmaid'] for r in members), 'evidence_snippet':' || '.join(snippets)[:6000]
        })
    grows.sort(key=lambda r:(-STATUS_RANK.get(r['qualification_status'],0),-int(r['employee_estimate_min']),r['company_or_group'].lower()))
    shortlist=[r for r in grows if STATUS_RANK.get(r['qualification_status'],0)>=4]
    confirmed30=[r for r in grows if r['qualification_status']=='CONFIRMED_30_PLUS']
    confirmed20=[r for r in grows if r['qualification_status'] in ('CONFIRMED_20_PLUS','CONFIRMED_20_29','CONFIRMED_30_PLUS')]
    def write(path,data):
        if not data: return
        with open(path,'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
    write(os.path.join(OUTDIR,'all_4331_reviewed.csv'),rows)
    write(os.path.join(OUTDIR,'all_deduplicated_groups.csv'),grows)
    write(os.path.join(OUTDIR,'final_shortlist_20plus_confirmed_or_likely.csv'),shortlist)
    write(os.path.join(OUTDIR,'confirmed_30plus.csv'),confirmed30)
    write(os.path.join(OUTDIR,'confirmed_20plus.csv'),confirmed20)
    summary={'input_wko_companies':len(rows),'deduplicated_groups':len(grows),'shortlist_confirmed_or_likely_20plus':len(shortlist),'confirmed_20plus':len(confirmed20),'confirmed_30plus':len(confirmed30),'status_counts_groups':dict(Counter(r['qualification_status'] for r in grows)),'status_counts_rows':dict(Counter(r['qualification_status'] for r in rows)),'method':'WKO dedup + shared-domain/phone/email grouping + official website crawl + public search/LinkedIn snippets + employee/location/team/career signals'}
    with open(os.path.join(OUTDIR,'qualification_summary.json'),'w',encoding='utf-8') as f: json.dump(summary,f,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
