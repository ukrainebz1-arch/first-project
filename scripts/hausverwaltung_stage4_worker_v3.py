#!/usr/bin/env python3
import argparse,csv,json,os,re,time
from urllib.parse import urljoin
import hausverwaltung_stage4_worker as base
import hausverwaltung_stage4_worker_v2 as strict
from bs4 import BeautifulSoup

PATHS=['/','/team','/ueber-uns','/über-uns','/management','/geschaeftsfuehrung','/geschäftsführung','/kontakt','/contact','/impressum','/presse','/downloads']

def quick_research(row):
    company=row['company_name']; ps=base.people(row); site=(row.get('website') or '').strip()
    evidence=[];checked=[];fp=[];fe=[];pdfs=[]
    if not site:return evidence,checked,fp,fe
    root=site if '://' in site else 'https://'+site
    fu,ct,b=base.get_url(root,8)
    if not b:return evidence,checked,fp,fe
    bh=base.host(fu)
    urls=[]
    for p in PATHS:
        u=fu if p=='/' else urljoin(fu,p)
        if u not in urls:urls.append(u)
    for u in urls:
        uu,ct,b=base.get_url(u,8)
        if not b or (base.host(uu) and base.host(uu)!=bh):continue
        checked.append(uu)
        sk='official_pdf' if 'pdf' in ct or uu.lower().endswith('.pdf') else 'official_html'
        t=base.decode_text(ct,b)
        if t:
            for p in ps:evidence+=strict.strict_extract(t,p,company,uu,sk)
            ph,em=base.extract_fallback(t,uu);fp+=ph;fe+=em
        if sk=='official_html':
            try:
                s=BeautifulSoup(b,'html.parser')
                for a in s.find_all('a',href=True):
                    href=urljoin(uu,a['href']).split('#')[0]
                    lab=(a.get_text(' ',strip=True)+' '+href).lower()
                    if base.host(href)==bh and href.lower().endswith('.pdf') and any(k in lab for k in ('presse','bericht','download','brosch','geschäft','management','team')) and href not in pdfs:
                        pdfs.append(href)
            except:pass
    for u in pdfs[:4]:
        uu,ct,b=base.get_url(u,10)
        if not b:continue
        checked.append(uu);t=base.pdf_text(b)
        for p in ps:evidence+=strict.strict_extract(t,p,company,uu,'official_pdf')
    evidence=base.dedupe(evidence)
    return evidence,list(dict.fromkeys(checked)),list(dict.fromkeys(fp)),list(dict.fromkeys(fe))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    with open(a.input_csv,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    allhits=[];coverage=[]
    for i,row in enumerate(rows,1):
        hits,checked,fp,fe=quick_research(row)
        for h in hits:
            h.update({'no':row['no'],'company_name':row['company_name'],'stage3_scope':row['stage3_scope'],'primary_dm':row['primary_dm'],'primary_dm_role':row['primary_dm_role']});allhits.append(h)
        coverage.append({'no':row['no'],'company_name':row['company_name'],'stage3_scope':row['stage3_scope'],'primary_dm':row['primary_dm'],'website':row.get('website',''),'checked_source_count':str(len(checked)),'checked_source_urls':' | '.join(checked),'fallback_phones':' | '.join(fp),'fallback_emails':' | '.join(fe),'machine_research_complete':'yes'})
        print(f'{i}/{len(rows)} #{row["no"]} {row["company_name"]}: hits={len(hits)} checked={len(checked)}',flush=True)
    hf=['no','company_name','stage3_scope','primary_dm','primary_dm_role','person','contact_type','contact','contact_class','score','source_count','source_url','all_source_urls','source_kind','query','context']
    with open(os.path.join(a.output_dir,'evidence.csv'),'w',encoding='utf-8-sig',newline='') as f:
        x=csv.DictWriter(f,fieldnames=hf);x.writeheader();x.writerows([{k:r.get(k,'') for k in hf} for r in allhits])
    cf=['no','company_name','stage3_scope','primary_dm','website','checked_source_count','checked_source_urls','fallback_phones','fallback_emails','machine_research_complete']
    with open(os.path.join(a.output_dir,'coverage.csv'),'w',encoding='utf-8-sig',newline='') as f:
        x=csv.DictWriter(f,fieldnames=cf);x.writeheader();x.writerows(coverage)
    with open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8') as f:json.dump({'rows':len(rows),'evidence_rows':len(allhits),'machine_research_complete':len(rows),'mode':'official_conservative_v3'},f,ensure_ascii=False,indent=2)
if __name__=='__main__':main()
