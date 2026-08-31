# One-time repair of malformed Condor CSV row 62.
import csv,os,tempfile
p='data/spedition/contacts/targets.csv'
rows=[]
with open(p,encoding='utf-8-sig',newline='') as f:
    rd=csv.reader(f)
    header=next(rd); rows=list(rd)
assert header==['no','company','primary_dm','management','owners','websites','wko_url'],header
out=[];fixed=False
for r in rows:
    if r and r[0]=='62':
        assert len(r)==8, f'expected malformed 8-column row, got {len(r)}: {r}'
        r=['62',r[1]+','+r[2],r[3],r[4],r[5],'',r[7]]
        fixed=True
    assert len(r)==7,(r[0] if r else '?',len(r),r)
    out.append(r)
assert fixed,'Condor row 62 not found'
with open(p,'w',encoding='utf-8-sig',newline='') as f:
    w=csv.writer(f);w.writerow(header);w.writerows(out)
print('fixed row 62; rows',len(out))
