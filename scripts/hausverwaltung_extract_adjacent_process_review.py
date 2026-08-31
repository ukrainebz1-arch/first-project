import csv, json, os
src='data/hausverwaltung/size_agent_first/size_agent_first_final_2026-08-31.csv'
out='data/hausverwaltung/size_agent_first/adjacent_process_review_input.tsv'
rows=[]
with open(src,encoding='utf-8-sig',newline='') as f:
    for r in csv.DictReader(f):
        if r.get('agent_class')=='E_ADJACENT_30_PLUS': rows.append(r)
fields=['company_name','states_seen','wko_standort_count','website','size_class_strict_v2','decision_reason','agent_evidence_url','confidence']
os.makedirs(os.path.dirname(out),exist_ok=True)
with open(out,'w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,delimiter='\t'); w.writeheader(); w.writerows([{k:r.get(k,'') for k in fields} for r in rows])
with open('data/hausverwaltung/size_agent_first/adjacent_process_review_summary.json','w',encoding='utf-8') as f:
    json.dump({'adjacent_rows':len(rows)},f,indent=2)
print('adjacent',len(rows))