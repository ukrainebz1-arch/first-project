#!/usr/bin/env python3
import argparse,csv,json,os,re

KNOWN=['ARTUS','RTG','KPS','CONTAX','ECOVIS','Gneist','RSM','Steuer & Service','Schweitzer','Steuerviertel','Accurata','Geyer','HEW','FP Steuer','AWT','Gerstgrasser','GSV','Writzmann','EOS','KMB','zobl','Prodinger','APP','FUSSEIS','Grazer Treuhand','Schneider','LLP','Pfeiffer Hiebl','Gaun','MOORE','Raml','LBG','TPA','EY','Ernst & Young','KPMG','Fidas','COUNT IT','HGC','RKP','KRW','Klinger']
CONF={'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS'}
def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def n(v):
    try:return int(float(v))
    except:return 0
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();rows=read(a.input)
    c30=[r for r in rows if r.get('agent_verdict')=='CONFIRMED_30_PLUS'];c20=[r for r in rows if r.get('agent_verdict') in CONF]
    suspicious=[]
    for r in c30:
        lo=n(r.get('agent_employee_low'));name=r.get('group_name','')
        if lo>1200 and not any(x.lower() in name.lower() for x in ['kpmg','ernst','ey ','tpa','lbg']):suspicious.append({'group_key':r['group_key'],'name':name,'employee_low':lo,'reason':'very_high_count_non_big4_or_lbg'})
        if lo>5000:suspicious.append({'group_key':r['group_key'],'name':name,'employee_low':lo,'reason':'implausibly_high_count'})
    known=[]
    for term in KNOWN:
        matches=[r for r in rows if term.lower() in (' '.join([r.get('group_name',''),r.get('economic_component_names',''),r.get('member_entities','')])).lower()]
        known.append({'term':term,'matches':[{'name':r.get('group_name',''),'verdict':r.get('agent_verdict',''),'low':r.get('agent_employee_low','')} for r in matches[:6]]})
    report={'economic_groups':len(rows),'confirmed_30_plus':len(c30),'confirmed_20_plus_total':len(c20),'likely_20_plus':sum(r.get('agent_verdict')=='LIKELY_20_PLUS' for r in rows),'suspicious_high_counts':suspicious,'known_firm_checks':known,'gate_ok':len(c30)>=40 and not any(x['reason']=='implausibly_high_count' for x in suspicious)}
    os.makedirs(os.path.dirname(a.output) or '.',exist_ok=True);json.dump(report,open(a.output,'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['gate_ok']:raise SystemExit('Stage 2 sanity gate failed: market appears undercounted or contains implausible headcount evidence')
if __name__=='__main__':main()
