import argparse,csv,html,os,re,time,urllib.parse,requests
from bs4 import BeautifulSoup
from collections import defaultdict

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
S=requests.Session();S.headers.update({'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'})
EMAIL_RE=re.compile(r'(?<![\w.+-])([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})(?![\w.-])',re.I)
# Explicit international or local-phone starts only. Deliberately excludes bare IDs/dates.
PHONE_RE=re.compile(r'(?<!\w)(?:(?:\+|00)\s?\d{1,3}|0\d{1,4})[\s()./\-]*\d{2,5}(?:[\s()./\-]*\d{2,6}){1,3}(?:\s*(?:DW|Durchwahl|ext\.?|extension)\s*\d{1,6})?',re.I)
GENERIC={'office','info','kontakt','contact','service','support','sales','booking','reception','sekretariat','secretary','verwaltung','karriere','jobs','hr','marketing','presse','press','dispatch','dispo','logistik','spedition','transport'}
MOBILE_PREFIX=('650','651','652','653','655','656','657','658','659','660','661','663','664','665','666','667','668','669','670','671','676','677','678','679','680','681','682','683','684','685','686','687','688','689','690','691','699')
QUERY_FAMILIES=[
 ('Q01_DIRECT','"{person}" "{company}" Telefon E-Mail'),
 ('Q02_MOBILE_DW','"{person}" "{company}" Mobil Durchwahl'),
 ('Q03_PDF','"{person}" "{company}" filetype:pdf Telefon'),
 ('Q04_EVENT_ASSOC','"{person}" "{company}" Konferenz OR Vortrag OR Verband OR Club'),
 ('Q05_JOBS','"{person}" "{company}" Karriere OR Stellenanzeige OR Ansprechpartner'),
 ('Q06_PRESS_VCARD','"{person}" "{company}" Presse OR vCard OR Visitenkarte OR Präsentation'),
]

def read(path):
  with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def clean_person(p):
  p=re.sub(r'\([^)]*\)',' ',p or '')
  p=re.sub(r'\b(Mag\.?|DI|Ing\.?|MBA|MSc|MA|BSc|Dr\.?|FH)\b',' ',p,flags=re.I)
  return re.sub(r'\s+',' ',p).strip(' ,')

def people(row):
  out=[]
  # Primary DM is the outreach target. Add management only if not already represented.
  for field in ('primary_dm','management'):
    for p in (row.get(field) or '').split(';'):
      p=clean_person(p)
      if len(p.split())>=2 and p not in out:out.append(p)
  return out[:4]

def domain(u):
  try:
    d=urllib.parse.urlparse(u).netloc.lower().split(':')[0]
    return d[4:] if d.startswith('www.') else d
  except:return ''

def norm_phone(x):
  x=(x or '').strip()
  if not re.match(r'^(?:\+|00|0)',x):return ''
  if re.fullmatch(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}',x):return ''
  n=re.sub(r'[^0-9+]','',x)
  if n.startswith('00'):n='+'+n[2:]
  if n.startswith('0'):n='+43'+n[1:]
  if n.startswith('+430'):n='+43'+n[4:]
  digs=re.sub(r'\D','',n)
  return n if 8<=len(digs)<=15 else ''

def phone_class(raw):
  n=norm_phone(raw)
  if not n:return 'invalid'
  d=re.sub(r'\D','',n);at=d[2:] if d.startswith('43') else d
  if any(at.startswith(x) for x in MOBILE_PREFIX):return 'mobile_public'
  if re.search(r'\b(?:DW|Durchwahl|ext\.?|extension)\b',raw,re.I):return 'direct_extension'
  # Hyphenated final 2-5 digits frequently encode a published extension.
  if re.search(r'[-/]\s*\d{2,5}\s*$',raw):return 'direct_or_office'
  return 'named_fixed_candidate'

def email_class(e,person):
  e=e.lower().strip(' .;,')
  if '@' not in e:return 'invalid'
  local=e.split('@')[0]
  if local in GENERIC or any(local.startswith(g+'.') or local.startswith(g+'-') for g in GENERIC):return 'generic_fallback'
  toks=[re.sub(r'[^a-z0-9]','',x.lower()) for x in clean_person(person).split()]
  simple=re.sub(r'[^a-z0-9]','',local)
  if any(len(t)>=4 and t in simple for t in toks):return 'personal_verified'
  return 'personal_candidate'

def classify_source(url,title='',query_family=''):
  u=(url+' '+title).lower();d=domain(url)
  if url.lower().endswith('.pdf') or ' pdf' in u:return 'M13_INDEXED_PDF'
  if any(x in u for x in ['konferenz','conference','kongress','congress','speaker','tagung','forum','event','symposium']):return 'M14_EVENT_SPEAKER'
  if any(x in u for x in ['verband','association','verein','club','netzwerk','network','vnl.at','logistikclub','wirtschaftsbund']):return 'M15_ASSOCIATION_CLUB'
  if any(x in u for x in ['karriere','career','jobs','job','stellen','stepstone','indeed','hokify','jobs.at']):return 'M16_JOB_ARCHIVE'
  if any(x in u for x in ['presse','press','news','ots.at','leadersnet','medianet','wirtschaftszeit','logistik-express','dispo.cc']):return 'M17_MEDIA_PRESS'
  if any(x in u for x in ['partner','case-study','casestudy','referenz','reference','kunde','customer-story']):return 'M18_PARTNER_CASESTUDY'
  if any(x in u for x in ['presentation','präsentation','slideshare','slide','ppt','powerpoint']):return 'M19_PRESENTATION'
  if any(x in u for x in ['vcard','visitenkarte','business-card','contact-card']):return 'M20_VCARD'
  if any(x in d for x in ['firmenabc.','firmenatlas.','herold.','northdata.','kompany.','wirtschaft.at']):return 'M21_DIRECTORY'
  if any(x in d for x in ['linkedin.com','xing.com']):return 'M22_BUSINESS_SOCIAL'
  if any(x in u for x in ['ausschreibung','tender','vergabe','procurement','ted.europa','bbg.gv']):return 'M23_TENDER_DOC'
  return 'M24_GENERAL_WEB'

def ddg(q):
  url='https://html.duckduckgo.com/html/?q='+urllib.parse.quote_plus(q)
  try:r=S.get(url,timeout=20);txt=r.text
  except:return []
  if r.status_code!=200:return []
  s=BeautifulSoup(txt,'html.parser');out=[]
  for res in s.select('.result')[:7]:
    a=res.select_one('a.result__a');sn=res.select_one('.result__snippet')
    if not a:continue
    href=a.get('href','')
    if 'uddg=' in href:
      try:href=urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get('uddg',[href])[0]
      except:pass
    out.append((html.unescape(a.get_text(' ',strip=True)),href,html.unescape(sn.get_text(' ',strip=True)) if sn else ''))
  return out

def bing(q):
  url='https://www.bing.com/search?q='+urllib.parse.quote_plus(q)+'&count=10'
  try:r=S.get(url,timeout=20)
  except:return []
  if r.status_code!=200:return []
  s=BeautifulSoup(r.text,'html.parser');out=[]
  for li in s.select('li.b_algo')[:7]:
    a=li.select_one('h2 a');sn=li.select_one('.b_caption p')
    if a:out.append((a.get_text(' ',strip=True),a.get('href',''),sn.get_text(' ',strip=True) if sn else ''))
  return out

def search(q):
  r=ddg(q)
  if not r:r=bing(q)
  return r

def visible(htmltxt):
  s=BeautifulSoup(htmltxt,'html.parser')
  for t in s(['script','style','noscript','svg']):t.decompose()
  return re.sub(r'\s+',' ',s.get_text(' ',strip=True))

def fetch_text(url):
  if domain(url) in ('linkedin.com','xing.com'):return ''
  try:
    r=S.get(url,timeout=18,allow_redirects=True)
    if r.status_code!=200:return ''
    ct=r.headers.get('content-type','').lower()
    if 'html' in ct:return visible(r.text)[:300000]
  except:pass
  return ''

def snippets_near(text,person):
  last=person.split()[-1];sp=[]
  for m in re.finditer(r'\b'+re.escape(last)+r'\b',text,re.I):sp.append(text[max(0,m.start()-700):min(len(text),m.end()+1000)])
  return sp[:5]

def extract(text,person,url,title,qfam,origin):
  out=[]
  for ctx in snippets_near(text,person):
    for e in sorted(set(EMAIL_RE.findall(ctx))):
      cls=email_class(e,person)
      if cls!='invalid':out.append((person,'email',e.lower(),cls,classify_source(url,title,qfam),url,title,qfam,origin,ctx[:1200]))
    for m in PHONE_RE.finditer(ctx):
      raw=re.sub(r'\s+',' ',m.group(0)).strip(' .;,');n=norm_phone(raw)
      if not n:continue
      cls=phone_class(raw)
      if cls!='invalid':out.append((person,'phone',raw,cls,classify_source(url,title,qfam),url,title,qfam,origin,ctx[:1200]))
  return out

def main():
  ap=argparse.ArgumentParser();ap.add_argument('--start',type=int,required=True);ap.add_argument('--end',type=int,required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
  targets=[r for r in read('data/spedition/contacts/targets.csv') if args.start<=int(r['no'])<=args.end]
  fields=['no','company','person','contact_type','contact','contact_class','method','source_url','source_title','query_family','origin','context']
  rows=[]
  for r in targets:
    ps=people(r);company=r['company']
    for person in ps:
      for qfam,tpl in QUERY_FAMILIES:
        q=tpl.format(person=person,company=company)
        results=search(q)
        for title,url,snip in results[:5]:
          if not url:continue
          # Search snippet itself can contain a direct published contact.
          rows += [dict(zip(fields[2:],x)) | {'no':r['no'],'company':company} for x in extract((title+' '+snip),person,url,title,qfam,'search_snippet')]
          txt=fetch_text(url)
          if txt:
            rows += [dict(zip(fields[2:],x)) | {'no':r['no'],'company':company} for x in extract(txt,person,url,title,qfam,'fetched_page')]
        time.sleep(.12)
    print(r['no'],company,'people',len(ps),'hits',sum(1 for x in rows if x['no']==r['no']),flush=True)
  # Dedupe evidence
  ded=[];seen=set()
  for x in rows:
    norm=norm_phone(x['contact']) if x['contact_type']=='phone' else x['contact'].lower()
    k=(x['no'],x['person'].lower(),x['contact_type'],norm,x['source_url'],x['method'])
    if k not in seen:seen.add(k);ded.append(x)
  os.makedirs(os.path.dirname(args.out),exist_ok=True)
  with open(args.out,'w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(ded)
  print('DONE companies',len(targets),'hits',len(ded),'out',args.out)
if __name__=='__main__':main()
