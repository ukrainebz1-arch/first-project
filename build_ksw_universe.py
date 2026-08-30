import csv, os, re, unicodedata
from collections import defaultdict
from urllib.parse import urlparse

INPUT=os.environ.get('INPUT','input/ksw_legal_entities_unique.csv')
OUTPUT=os.environ.get('OUTPUT','input/ksw_target_universe.csv')
GENERIC={'gmail.com','gmx.at','gmx.net','outlook.com','hotmail.com','aon.at','icloud.com','yahoo.com','yahoo.de','liwest.at','chello.at','magenta.at'}
SOCIAL={'facebook.com','instagram.com','linkedin.com','xing.com','youtube.com','tiktok.com'}

def norm(s):
    s=unicodedata.normalize('NFKD',s or '')
    s=''.join(c for c in s if not unicodedata.combining(c)).lower()
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def host(url):
    try:
        u=url if '://' in url else 'https://'+url
        h=urlparse(u).netloc.lower().split(':')[0]
        return re.sub(r'^www\.','',h)
    except: return ''

def official_domain(r):
    webs=[x.strip() for x in (r.get('website') or '').split('|') if x.strip()]
    for w in webs:
        h=host(w)
        if h and h not in SOCIAL and h not in GENERIC and 'ksw.or.at' not in h:
            return h
    return ''

rows=list(csv.DictReader(open(INPUT,encoding='utf-8-sig',newline='')))
groups=defaultdict(list)
for r in rows:
    d=official_domain(r)
    key=('domain:'+d) if d else ('entity:'+r['entity_key'])
    groups[key].append(r)

out=[]
for key, members in groups.items():
    domain=key.split(':',1)[1] if key.startswith('domain:') else ''
    members=sorted(members,key=lambda r:(-int(r.get('listing_count') or 0),len(r.get('title') or ''),r.get('title') or ''))
    rep=members[0]
    def join(field):
        vals=[]
        for r in members:
            for x in (r.get(field) or '').split('|'):
                x=x.strip()
                if x and x not in vals: vals.append(x)
        return ' | '.join(vals)
    out.append({
        'group_key':key,
        'group_name':rep.get('title',''),
        'domain':domain,
        'websites':join('website'),
        'emails':join('email'),
        'phones':join('phones'),
        'cities':join('cities'),
        'legal_entities_count':len(members),
        'ksw_listings_count':sum(int(r.get('listing_count') or 0) for r in members),
        'locations_count':sum(int(r.get('locations_count') or 0) for r in members),
        'member_entities':' | '.join(r.get('title','') for r in members),
        'ksw_pages':join('ksw_pages'),
        'has_official_domain':1 if domain else 0,
    })

out.sort(key=lambda r:(-r['has_official_domain'],-int(r['legal_entities_count']),norm(r['group_name'])))
os.makedirs(os.path.dirname(OUTPUT) or '.',exist_ok=True)
fields=list(out[0].keys()) if out else []
with open(OUTPUT,'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(out)
print({'input_unique_legal_entities':len(rows),'target_groups':len(out),'official_domain_groups':sum(x['has_official_domain'] for x in out),'no_domain_groups':sum(not x['has_official_domain'] for x in out)})

QUALIFIER_OUTPUT=os.environ.get('QUALIFIER_OUTPUT','input/ksw_for_qualifier.csv')
qfields=['firmaid','company_name','business_label','street','postal_code','city','address','phones','email','all_emails','website','all_websites','query_terms','states_seen','profile_url']
qrows=[]
for r in out:
    webs=[x.strip() for x in r['websites'].split('|') if x.strip()]
    official=next((x for x in webs if r['domain'] and host(x)==r['domain']),'')
    emails=[x.strip() for x in r['emails'].split('|') if x.strip()]
    qrows.append({
        'firmaid':r['group_key'], 'company_name':r['group_name'], 'business_label':r['member_entities'],
        'street':'','postal_code':'','city':(r['cities'].split('|')[0].strip() if r['cities'] else ''),'address':'',
        'phones':r['phones'],'email':(emails[0] if emails else ''),'all_emails':r['emails'],
        'website':official,'all_websites':r['websites'],'query_terms':'KSW Steuerberatung Wirtschaftsprüfung',
        'states_seen':'Austria','profile_url':r['ksw_pages']
    })
with open(QUALIFIER_OUTPUT,'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=qfields); w.writeheader(); w.writerows(qrows)
print({'qualifier_rows':len(qrows),'qualifier_output':QUALIFIER_OUTPUT})
