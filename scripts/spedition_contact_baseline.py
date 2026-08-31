import csv,os,re,unicodedata
from collections import defaultdict

def read(p):
  with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def fold(s):return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower().strip()
def clean_person(p):
  p=re.sub(r'\([^)]*\)',' ',p or '')
  p=re.sub(r'\b(Mag\.?|DI|Ing\.?|MBA|MSc|MA|BSc|Dr\.?|FH|Dipl\.?-?Bw\.?|Dipl\.?\s*Kfm\.?)\b',' ',p,flags=re.I)
  return re.sub(r'\s+',' ',p).strip(' ,')
def norm_phone(x):
  x=re.sub(r'[^0-9+]','',x or '')
  if x.startswith('00'):x='+'+x[2:]
  if x.startswith('0'):x='+43'+x[1:]
  if x.startswith('+430'):x='+43'+x[4:]
  return x

def v_status(r):
  level=(r.get('contact_level') or '').lower()
  if r.get('mobile'):return 'A_PUBLIC_MOBILE'
  if r.get('direct_phone') and level in ('direct_named','direct_extension'):return 'B_DIRECT_PHONE'
  if r.get('direct_email') and 'personal' in level:return 'C_DIRECT_EMAIL_ONLY'
  if r.get('direct_email') and r.get('direct_phone'):return 'B_DIRECT_PHONE'
  if 'management' in level:return 'D_NAMED_MANAGEMENT_LINE'
  return ''

targets=read('data/spedition/contacts/targets.csv')
val=read('data/spedition/contacts/validated_contacts.csv')
off=read('data/spedition/contacts/official_best_contacts.csv')
vm={(fold(r['company']),fold(clean_person(r['person']))):r for r in val}
# exact normalized phone reuse across people inside same company makes a phone non-personal unless validated
reuse=defaultdict(set)
for r in off:
  n=norm_phone(r.get('best_phone'))
  if n:reuse[(fold(r['company']),n)].add(fold(clean_person(r['person'])))
om={(fold(r['company']),fold(clean_person(r['person']))):r for r in off}
rows=[]
for t in targets:
  for p0 in (t.get('primary_dm') or '').split(';'):
    p=clean_person(p0)
    if len(p.split())<2:continue
    k=(fold(t['company']),fold(p));status='';source='';phone='';email='';confidence='';reason=''
    if k in vm:
      r=vm[k];status=v_status(r);phone=r.get('mobile') or r.get('direct_phone') or '';email=r.get('direct_email') or '';source=r.get('source_url') or '';confidence=r.get('confidence') or 'high';reason='validated_contacts'
    elif k in om:
      r=om[k];ph=r.get('best_phone') or '';pc=(r.get('phone_class') or '').lower();em=r.get('best_email') or '';ec=(r.get('email_class') or '').lower();ps=int(r.get('phone_sources') or 0);es=int(r.get('email_sources') or 0);n=norm_phone(ph);multi=len(reuse.get((fold(t['company']),n),set()))>1 if n else False
      centralish=bool(re.search(r'(?:[-/. ]0|\.0)$',ph.strip())) or pc in ('central_fallback','central_exact')
      if pc=='mobile_public' and not multi:
        status='A_PUBLIC_MOBILE';phone=ph;source=r.get('phone_source_url') or '';confidence='high' if ps>=2 else 'medium';reason=f'official_mobile_sources={ps}'
      elif ph and not centralish and not multi and (re.search(r'[-/ ]\d{2,5}\s*$',ph) or pc in ('direct_extension','direct_named')):
        status='B_DIRECT_PHONE';phone=ph;source=r.get('phone_source_url') or '';confidence='medium-high' if ps>=2 else 'medium';reason=f'official_named_phone_sources={ps}'
      elif ec in ('personal_verified','personal_email_verified') and em:
        status='C_DIRECT_EMAIL_ONLY';email=em;source=r.get('email_source_url') or '';confidence='high' if es>=2 else 'medium';reason=f'official_email_sources={es}'
      elif ph or em:
        status='E_CENTRAL_FALLBACK';phone=ph if centralish or multi else '';email=em if ec in ('generic_fallback','central_fallback') else '';source=r.get('phone_source_url') or r.get('email_source_url') or '';confidence='low';reason='official_candidate_needs_external_validation'
    rows.append({'no':t['no'],'company':t['company'],'person':p,'owners':t.get('owners',''),'websites':t.get('websites',''),'baseline_status':status or 'UNRESOLVED','best_phone':phone,'best_email':email,'confidence':confidence,'source_url':source,'reason':reason})
os.makedirs('data/spedition/contacts/baseline',exist_ok=True)
fields=list(rows[0])
with open('data/spedition/contacts/baseline/baseline_primary_dm.csv','w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
un=[r for r in rows if r['baseline_status'] in ('UNRESOLVED','E_CENTRAL_FALLBACK')]
for st in range(0,len(un),10):
  part=un[st:st+10];p=f'data/spedition/contacts/baseline/unresolved_{st+1:03d}_{st+len(part):03d}.csv'
  with open(p,'w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(part)
from collections import Counter
print('primary_dm',len(rows),'unresolved_or_fallback',len(un),'status_counts',dict(Counter(r['baseline_status'] for r in rows)))
