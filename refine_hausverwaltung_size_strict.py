import csv,json,os,re,unicodedata
from collections import defaultdict
from datetime import datetime,timezone

IN=os.environ.get('INPUT_CSV','data/hausverwaltung/size_strict/size_screening_strict.csv')
OUTDIR=os.environ.get('OUTDIR','data/hausverwaltung/size_strict_v2')
os.makedirs(OUTDIR,exist_ok=True)
MARKER_RE=re.compile(r'\b(gruppe|group|konzern|weltweit|worldwide|international|länder|laender|standorte|locations|gesamt|europaweit|unternehmensgruppe|holding|global)\b',re.I)
COUNTRIES=['österreich','osterreich','deutschland','germany','serbien','serbia','ungarn','hungary','rumänien','rumanien','romania','ukraine','schweiz','switzerland','italien','italy','slowakei','slovakia','slowenien','slovenia','tschechien','czech','kroatien','croatia','polen','poland','frankreich','france']

def clean(s):return re.sub(r'\s+',' ',s or '').strip()
def fold(s):return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower()
def groupish(s):
    t=fold(s)
    if MARKER_RE.search(t):return True
    if re.search(r'\b(?:in|an)\s+\d+\s+(?:europaischen\s+)?landern\b',t):return True
    countries={c for c in COUNTRIES if re.search(r'(?<![a-z])'+re.escape(fold(c))+r'(?![a-z])',t)}
    return len(countries)>=2

def parse(blob):
    out=[]
    for part in (blob or '').split(' || '):
        part=clean(part)
        m=re.match(r'([0-9\.]{1,9})\s+\[([^\]]+)\]\s+(.*?)\s+::\s+(.*)$',part,re.S)
        if not m:continue
        try:v=int(m.group(1).replace('.',''))
        except:continue
        if 1900<=v<=2035 or v<2 or v>250000:continue
        out.append({'value':v,'kind':m.group(2),'url':clean(m.group(3)),'context':clean(m.group(4)),'group':groupish(m.group(4))})
    return out

def emit(kind,src,x):return f"{kind}|{src}|{x['value']}|{x['value']}|{x['url']}|{x['context'][:700]}"
with open(IN,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
out=[]
for r in rows:
    direct=[];group=[];border=[]
    kmin=None
    try:kmin=int(float(r.get('karriere_emp_min') or 0)) or None
    except:kmin=None
    kmax=None
    try:kmax=int(float(r.get('karriere_emp_max') or 0)) or None
    except:kmax=None
    if r.get('karriere_exact_match')=='yes' and kmin is not None:
        if kmin>=31:direct.append(f"DIRECT|karriere.at exact employer|{kmin}|{kmax or ''}|{r.get('karriere_url','')}|exact normalized legal-name match")
        elif 20<=kmin<=30 or (kmax is not None and 20<=kmax<=30):border.append(f"BORDER|karriere.at exact employer|{kmin}|{kmax or ''}|{r.get('karriere_url','')}|exact normalized legal-name match")
    for label,blob in [('official website',r.get('website_valid_mentions','')),('WKO profile',r.get('wko_valid_mentions',''))]:
        ms=parse(blob)
        ds=[x for x in ms if not x['group'] and x['value']<=5000]
        gs=[x for x in ms if x['group'] or x['value']>5000]
        d31=[x for x in ds if x['value']>=31];d20=[x for x in ds if 20<=x['value']<=30];g31=[x for x in gs if x['value']>=31]
        if d31:direct.append(emit('DIRECT',label,max(d31,key=lambda x:x['value'])))
        if d20:border.append(emit('BORDER',label,max(d20,key=lambda x:x['value'])))
        if g31:group.append(emit('GROUP',label,max(g31,key=lambda x:x['value'])))
    if direct:cls='A_TARGET_30_PLUS';reason='Strict 31+ standalone/employer evidence'
    elif group:cls='B_LIKELY_30_PLUS_GROUP';reason='30+ evidence only in group/global/suspicious-large context'
    elif border:cls='C_BORDERLINE_20_30';reason='Strict standalone evidence in 20-30 range'
    else:cls='U_NOT_PROVEN';reason='No strict 20+/31+ evidence from exact karriere, official website or WKO profile'
    rr=dict(r);rr['size_class_strict_v2']=cls;rr['size_reason_strict_v2']=reason;rr['direct_31plus_sources_v2']=len(direct);rr['group_31plus_sources_v2']=len(group);rr['borderline_sources_v2']=len(border);rr['strict_evidence_v2']=' || '.join(direct+group+border);out.append(rr)
order={'A_TARGET_30_PLUS':0,'B_LIKELY_30_PLUS_GROUP':1,'C_BORDERLINE_20_30':2,'U_NOT_PROVEN':3}
out.sort(key=lambda r:(order.get(r['size_class_strict_v2'],9),r['company_name'].casefold()))
fields=list(out[0]) if out else []
with open(os.path.join(OUTDIR,'size_screening_strict_v2.csv'),'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
queue=[r for r in out if r['size_class_strict_v2']!='U_NOT_PROVEN' or r.get('adjacent_non_core_hint')=='yes']
with open(os.path.join(OUTDIR,'manual_review_queue_v2.csv'),'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(queue)
counts=defaultdict(int)
for r in out:counts[r['size_class_strict_v2']]+=1
changes=sum(r.get('size_class_strict')!=r.get('size_class_strict_v2') for r in out)
summary={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'companies':len(out),'counts':dict(counts),'classification_changes_vs_v1':changes,'manual_review_queue':len(queue),'group_rule':'word-boundary group markers plus multi-country detection; avoids matching gesamt inside insgesamt'}
with open(os.path.join(OUTDIR,'summary.json'),'w',encoding='utf-8') as f:json.dump(summary,f,ensure_ascii=False,indent=2)
print(json.dumps(summary,ensure_ascii=False,indent=2))
