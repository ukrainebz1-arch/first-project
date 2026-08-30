import csv, glob, json, os
out=[]
for p in sorted(glob.glob('refined/refine_*.csv')):
 with open(p,encoding='utf-8-sig',newline='') as f: out += list(csv.DictReader(f))
if not out: raise SystemExit('no rows')
seen={}
for r in out: seen[r['group_key']]=r
rows=list(seen.values())
os.makedirs('final_refine',exist_ok=True)
fields=list(rows[0].keys())
with open('final_refine/all_possible_refined.csv','w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
conf30=[r for r in rows if r.get('refine_status')=='CONFIRMED_30_PLUS_LINKEDIN']
conf20=[r for r in rows if r.get('refine_status')=='CONFIRMED_20_PLUS_LINKEDIN']
for fn,data in [('new_30plus_linkedin.csv',conf30),('new_20plus_linkedin.csv',conf20)]:
 with open('final_refine/'+fn,'w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(data)
with open('final_refine/summary.json','w') as f: json.dump({'rows':len(rows),'new_30plus':len(conf30),'new_20plus':len(conf20)},f,indent=2)
print('refined',len(rows),'new30',len(conf30),'new20',len(conf20))
