import csv,os,re,unicodedata
BASE='data/spedition/contacts/final'
def read(p):
 with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def fold(s):return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).lower()
rows=read(f'{BASE}/final_contacts.csv')
by={}
for r in rows:
 if not r['status'].startswith('F_'):continue
 by.setdefault(r['no'],[]).append(r)
queue=[]
for no,rs in sorted(by.items(),key=lambda kv:int(kv[0])):
 owners=fold(rs[0].get('owners',''))
 def score(r):
  p=fold(r['person']); toks=[x for x in re.split(r'\W+',p) if len(x)>3]
  owner_match=sum(1 for x in toks if x in owners)
  return (owner_match,len(toks))
 rs.sort(key=score,reverse=True)
 r=rs[0]
 queue.append({'no':r['no'],'company':r['company'],'person':r['person'],'owners':r.get('owners',''),'central_phone':r.get('central_phone_fallback',''),'central_email':r.get('central_email_fallback',''),'websites':r.get('websites',''),'wko_url':r.get('wko_url','')})
out='data/spedition/contacts/second_pass';os.makedirs(out,exist_ok=True)
fields=list(queue[0]) if queue else ['no','company','person']
with open(f'{out}/queue.csv','w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(queue)
for st in range(0,len(queue),10):
 part=queue[st:st+10]
 with open(f'{out}/queue_{st+1:03d}_{st+len(part):03d}.csv','w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(part)
print('unresolved_companies',len(queue))
