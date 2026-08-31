import csv, json, os, re, unicodedata
from collections import defaultdict
from datetime import datetime, timezone

MASTER=os.environ.get('MASTER_CSV','work/input/company_master.csv')
KARRIERE=os.environ.get('KARRIERE_CSV','work/karriere/karriere_matches.csv')
WEBSITE=os.environ.get('WEBSITE_CSV','work/website/website_employee_mentions.csv')
WKO=os.environ.get('WKO_PROFILE_CSV','work/wko/wko_profile_employee_mentions.csv')
OUTDIR=os.environ.get('OUTDIR','data/hausverwaltung/size_strict')
os.makedirs(OUTDIR,exist_ok=True)

LEGAL=re.compile(r'\b(gesellschaft\s+mit\s+beschr[aä]nkter\s+haftung|gesellschaft\s+m\.?\s*b\.?\s*h\.?|ges\.?\s*m\.?\s*b\.?\s*h\.?|gmbh|mbh|aktiengesellschaft|ag|kommanditgesellschaft|kg|offene\s+gesellschaft|og|se|e\.?\s*u\.?|co\.?\s*kg|gmbh\s*&\s*co\.?\s*kg)\b',re.I)
GROUP_MARKERS=['gruppe','group','konzern','weltweit','worldwide','international','länder','laender','standorte','locations','gesamt','europaweit','unternehmensgruppe','holding','group-wide','global']
ADJACENT=['facility','gebäudemanagement','gebaeudemanagement','projektentwicklung','entwicklungsgesellschaft','wohnbau','baugesellschaft','bundesimmobiliengesellschaft','versicherung','bank','stiftung','gemeinde','magistrat','wirtschaftsagentur','shopping','center management','parking','apcoa']

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def fold(s):
    s=''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower()
    s=s.replace('&',' und ')
    s=LEGAL.sub(' ',s)
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return clean(s)
def asint(v):
    try:
        s=clean(str(v))
        return int(float(s.replace('.',''))) if s else None
    except:return None
def asfloat(v):
    try:return float(v) if clean(str(v)) else None
    except:return None
def groupish(s):
    t=(s or '').casefold()
    return any(x in t for x in GROUP_MARKERS)

def parse_mentions(blob):
    # Existing crawlers emit: VALUE [kind] URL :: context || VALUE [kind] ...
    out=[]
    for part in (blob or '').split(' || '):
        part=clean(part)
        if not part:continue
        m=re.match(r'([0-9\.]{1,9})\s+\[([^\]]+)\]\s+(.*?)\s+::\s+(.*)$',part,re.S)
        if not m:continue
        try:v=int(m.group(1).replace('.',''))
        except:continue
        url=clean(m.group(3));ctx=clean(m.group(4))
        # Common regex false positive: a foundation/history year adjacent to Mitarbeiter.
        if 1900 <= v <= 2035:continue
        if v<2 or v>250000:continue
        out.append({'value':v,'kind':m.group(2),'url':url,'context':ctx,'groupish':groupish(ctx)})
    return out

def best_mentions(rows,field):
    ms=[]
    for r in rows:ms.extend(parse_mentions(r.get(field,'')))
    direct=[x for x in ms if not x['groupish']]
    group=[x for x in ms if x['groupish']]
    # Extremely large figures are kept as audit evidence but not automatic standalone proof.
    sane_direct=[x for x in direct if x['value']<=5000]
    suspicious=[x for x in direct if x['value']>5000]
    return ms,sane_direct,group,suspicious

def fmt_mentions(ms,limit=8):
    return ' || '.join(f"{x['value']} [{x['kind']}] {x['url']} :: {x['context']}" for x in ms[:limit])

master=read(MASTER);kr=read(KARRIERE);wr=read(WEBSITE);wkor=read(WKO)
# Exact normalized legal-name match is the only automatic karriere trust rule.
k_by=defaultdict(list)
for r in kr:k_by[fold(r.get('company_name',''))].append(r)
web_by=defaultdict(list)
for r in wr:web_by[clean(r.get('company_name',''))].append(r)
wko_by=defaultdict(list)
for r in wkor:wko_by[clean(r.get('company_name',''))].append(r)

out=[]
for m in master:
    name=clean(m.get('company_name','')); nfold=fold(name)
    kcands=[]
    for r in k_by.get(nfold,[]):
        if fold(r.get('karriere_name',''))==nfold:kcands.append(r)
    # choose exact profile with strongest employee evidence / score
    kcands.sort(key=lambda r:(asint(r.get('karriere_emp_min')) is not None,asfloat(r.get('karriere_match_score')) or 0),reverse=True)
    k=kcands[0] if kcands else {}
    kmin=asint(k.get('karriere_emp_min'));kmax=asint(k.get('karriere_emp_max'))

    wms,wdirect,wgroup,wsusp=best_mentions(web_by.get(name,[]),'employee_evidence_contexts')
    kms,kdirect,kgroup,ksusp=best_mentions(wko_by.get(name,[]),'employee_evidence_contexts')

    direct=[];groups=[];border=[]
    if kmin is not None:
        if kmin>=31:direct.append(('karriere.at exact employer',kmin,kmax,clean(k.get('karriere_url','')),'exact normalized legal-name match'))
        elif 20<=kmin<=30 or (kmax is not None and 20<=kmax<=30):border.append(('karriere.at exact employer',kmin,kmax,clean(k.get('karriere_url','')),'exact normalized legal-name match'))
    for source,arr in [('official website',wdirect),('WKO profile',kdirect)]:
        vals=[x for x in arr if x['value']>=31]
        if vals:
            x=max(vals,key=lambda z:z['value']);direct.append((source,x['value'],x['value'],x['url'],x['context']))
        vals20=[x for x in arr if 20<=x['value']<=30]
        if vals20:
            x=max(vals20,key=lambda z:z['value']);border.append((source,x['value'],x['value'],x['url'],x['context']))
    for source,arr in [('official/group website',wgroup),('WKO group context',kgroup),('official website suspicious large',wsusp),('WKO suspicious large',ksusp)]:
        vals=[x for x in arr if x['value']>=31]
        if vals:
            x=max(vals,key=lambda z:z['value']);groups.append((source,x['value'],x['value'],x['url'],x['context']))

    if direct:
        cls='A_TARGET_30_PLUS';reason='Strict 31+ standalone/employer evidence'
    elif groups:
        cls='B_LIKELY_30_PLUS_GROUP';reason='30+ evidence exists only in group/global/suspicious-large context'
    elif border:
        cls='C_BORDERLINE_20_30';reason='Strict standalone evidence in 20-30 range'
    else:
        cls='U_NOT_PROVEN';reason='No strict 20+/31+ evidence from exact karriere, official website or WKO profile'

    adjacent=any(x in name.casefold() for x in ADJACENT)
    evidence=[]
    for kind,items in [('DIRECT',direct),('GROUP',groups),('BORDER',border)]:
        for src,lo,hi,url,ctx in items:
            evidence.append(f'{kind}|{src}|{lo}|{hi or ""}|{url}|{clean(ctx)[:700]}')
    out.append({**m,
      'size_class_strict':cls,'size_reason_strict':reason,
      'adjacent_non_core_hint':'yes' if adjacent else 'no',
      'karriere_exact_match':'yes' if k else 'no','karriere_url':clean(k.get('karriere_url','')),
      'karriere_emp_min':'' if kmin is None else kmin,'karriere_emp_max':'' if kmax is None else kmax,
      'website_valid_mentions':fmt_mentions(wms),'wko_valid_mentions':fmt_mentions(kms),
      'direct_31plus_sources':len(direct),'group_31plus_sources':len(groups),'borderline_sources':len(border),
      'strict_evidence':' || '.join(evidence),
      'manual_review_required':'yes' if cls!='U_NOT_PROVEN' or adjacent else 'no'})

order={'A_TARGET_30_PLUS':0,'B_LIKELY_30_PLUS_GROUP':1,'C_BORDERLINE_20_30':2,'U_NOT_PROVEN':3}
out.sort(key=lambda r:(order.get(r['size_class_strict'],9),r['company_name'].casefold()))
fields=list(out[0]) if out else []
with open(os.path.join(OUTDIR,'size_screening_strict.csv'),'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
queue=[r for r in out if r['size_class_strict']!='U_NOT_PROVEN' or r['adjacent_non_core_hint']=='yes']
with open(os.path.join(OUTDIR,'manual_review_queue.csv'),'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(queue)
counts=defaultdict(int)
for r in out:counts[r['size_class_strict']]+=1
summary={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'companies':len(out),'counts':dict(counts),
 'exact_karriere_matches':sum(r['karriere_exact_match']=='yes' for r in out),
 'strict_20plus_queue':sum(r['size_class_strict']!='U_NOT_PROVEN' for r in out),
 'manual_review_queue':len(queue),
 'rules':['karriere automatic evidence only for exact normalized legal-name match','website/WKO years 1900-2035 rejected','group/global context separated from standalone evidence','standalone numeric mentions above 5000 treated as suspicious/group until manual verification','U_NOT_PROVEN does not mean small']}
with open(os.path.join(OUTDIR,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False,indent=2))
