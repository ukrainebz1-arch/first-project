import csv,glob,os,re,json
from collections import defaultdict
from urllib.parse import urlparse

INDIR=os.environ.get('INDIR','chunks')
OUTDIR=os.environ.get('OUTDIR','ksw_final')
TOTAL_PAGES=int(os.environ.get('TOTAL_PAGES','536'))
EXPECTED_CHUNKS=int(os.environ.get('EXPECTED_CHUNKS','32'))
os.makedirs(OUTDIR,exist_ok=True)
GENERIC_MAIL={'gmail.com','gmx.at','gmx.net','outlook.com','hotmail.com','aon.at','icloud.com','yahoo.com','yahoo.de'}

def host(u):
    u=(u or '').split(' | ')[0].strip()
    if not u:return ''
    try:
        h=urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0]
        return re.sub(r'^www\.','',h)
    except:return ''

def maildomain(e):
    e=(e or '').split(' | ')[0].strip().lower()
    return e.split('@',1)[1] if '@' in e else ''

def brand_norm(title):
    s=(title or '').lower().replace('ö','oe').replace('ä','ae').replace('ü','ue').replace('ß','ss')
    s=re.sub(r'\b(gmbh|gesmbh|gesellschaft|m\.?b\.?h\.?|kg|og|ag|se|flexco|steuerberatungsgesellschaft|wirtschaftspruefungsgesellschaft|wirtschaftstreuhandgesellschaft|steuerberatung|wirtschaftspruefung|wirtschaftstreuhand)\b',' ',s)
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def joinuniq(vals):
    seen=[]
    for v in vals:
        for x in (v or '').split(' | '):
            x=x.strip()
            if x and x not in seen:seen.append(x)
    return ' | '.join(seen)

files=sorted(glob.glob(os.path.join(INDIR,'ksw_legal_chunk_*.csv')))
metafiles=sorted(glob.glob(os.path.join(INDIR,'ksw_legal_chunk_*.json')))
if len(files)!=EXPECTED_CHUNKS:raise SystemExit(f'expected {EXPECTED_CHUNKS} CSV chunks, got {len(files)}')
if len(metafiles)!=EXPECTED_CHUNKS:raise SystemExit(f'expected {EXPECTED_CHUNKS} metadata chunks, got {len(metafiles)}')
completed=[];failed=[];meta_rows=0
for p in metafiles:
    with open(p,encoding='utf-8') as f:m=json.load(f)
    completed += [int(x) for x in m.get('completed_pages',[])]
    failed += [int(x['page']) for x in m.get('failed_pages',[])]
    meta_rows += int(m.get('rows',0))
expected=set(range(1,TOTAL_PAGES+1));done=set(completed)
missing=sorted(expected-done)
duplicated=sorted(p for p in done if completed.count(p)>1)
if failed or missing or duplicated:
    raise SystemExit(f'KSW completeness failure: failed={failed[:30]}, missing={missing[:30]}, duplicates={duplicated[:30]}, completed={len(done)}/{TOTAL_PAGES}')

raw=[]
for p in files:
    with open(p,encoding='utf-8-sig',newline='') as f:raw.extend(csv.DictReader(f))
if len(raw)!=meta_rows:raise SystemExit(f'row count mismatch csv={len(raw)} meta={meta_rows}')

by_entity=defaultdict(list)
for r in raw:by_entity[r['title_norm']].append(r)
entities=[]
for k,rs in by_entity.items():
    rep=max(rs,key=lambda r:sum(bool(r.get(x)) for x in ['website','email','phones']))
    d=host(joinuniq([r['website'] for r in rs]));md=maildomain(joinuniq([r['email'] for r in rs]))
    entities.append({
        'entity_key':k,'title':rep['title'],'listing_count':len(rs),'locations_count':len(set((r['postal_code'],r['city']) for r in rs if r['postal_code'] or r['city'])),
        'postal_codes':joinuniq([r['postal_code'] for r in rs]),'cities':joinuniq([r['city'] for r in rs]),
        'website':joinuniq([r['website'] for r in rs]),'domain':d,'email':joinuniq([r['email'] for r in rs]),'email_domain':md,
        'phones':joinuniq([r['phones'] for r in rs]),'ksw_pages':joinuniq([r['source_url'] for r in rs]),
        'brand_norm':brand_norm(rep['title'])
    })

by_group=defaultdict(list)
for e in entities:
    d=e['domain'];md=e['email_domain']
    if d and d not in {'ksw.or.at','kwt.or.at'}:g='domain:'+d
    elif md and md not in GENERIC_MAIL:g='mail:'+md
    else:g='entity:'+e['entity_key']
    by_group[g].append(e)

groups=[]
for g,es in by_group.items():
    rep=max(es,key=lambda e:(e['locations_count'],len(e['website'])))
    groups.append({
        'group_key':g,'group_name':rep['title'],'legal_entities_count':len(es),'ksw_listings_count':sum(int(e['listing_count']) for e in es),
        'locations_count':sum(int(e['locations_count']) for e in es),'domain':rep['domain'] or rep['email_domain'],
        'websites':joinuniq([e['website'] for e in es]),'emails':joinuniq([e['email'] for e in es]),'phones':joinuniq([e['phones'] for e in es]),
        'cities':joinuniq([e['cities'] for e in es]),'member_entities':' | '.join(e['title'] for e in es),'ksw_pages':joinuniq([e['ksw_pages'] for e in es])
    })

def write(path,rows):
    if not rows:return
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)

write(os.path.join(OUTDIR,'ksw_legal_entities_raw.csv'),raw)
write(os.path.join(OUTDIR,'ksw_legal_entities_unique.csv'),entities)
write(os.path.join(OUTDIR,'ksw_legal_entity_groups.csv'),groups)
summary={'pages_verified':len(done),'raw_legal_listings':len(raw),'unique_legal_entities':len(entities),'grouped_targets_before_size_filter':len(groups),'chunks':len(files),'failed_pages':[]}
with open(os.path.join(OUTDIR,'summary.json'),'w') as f:json.dump(summary,f,indent=2)
print(json.dumps(summary,indent=2))
