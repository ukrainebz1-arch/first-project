#!/usr/bin/env python3
import argparse,csv,os,re,json
from urllib.parse import urlparse

def read(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def doms(s):
    out=set()
    for x in re.split(r'\s*\|\s*|[,;]\s*',s or ''):
        x=x.strip()
        if not x:continue
        if '://' not in x:x='https://'+x
        try:
            h=urlparse(x).netloc.lower().split(':')[0]
            if h.startswith('www.'):h=h[4:]
            if h:out.add(h)
        except:pass
    return out
def display(r):
    x=(r.get('company_or_group') or '').strip()
    bad=('http://','https://')
    if x.startswith(bad) or len(x)<4 or x in {'1 Zertifikat'}:
        m=(r.get('member_companies') or '').split(' | ')[0].strip()
        if m:return m
    return x
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--wko',required=True);ap.add_argument('--ksw',required=True);ap.add_argument('--output-dir',required=True);ap.add_argument('--chunks',type=int,default=4);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    wr=read(a.wko);kr=read(a.ksw);kd=set()
    for r in kr:
        kd|=doms(r.get('websites'));d=(r.get('domain') or '').strip().lower()
        if d:kd.add(d)
    out=[];duplicates=[]
    for r in wr:
        ds=doms(r.get('domains'))|doms(r.get('websites'))
        overlap=sorted(ds & kd)
        if overlap:
            duplicates.append({'group_id':r.get('group_id'),'company':display(r),'domains':' | '.join(sorted(ds)),'ksw_overlap':' | '.join(overlap)});continue
        rr={
          'group_key':'wko:'+r.get('group_id',''),'group_name':display(r),'domain':' | '.join(sorted(ds)),
          'websites':r.get('websites',''),'cities':r.get('cities',''),'legal_entities_count':r.get('wko_legal_entities','1'),
          'locations_count':'','member_entities':r.get('member_companies',''),'prior_status':r.get('qualification_status',''),
          'prior_confidence':r.get('confidence',''),'prior_employee_low':r.get('employee_estimate_min',''),'prior_employee_high':r.get('employee_estimate_max',''),
          'prior_reason':r.get('qualification_reason',''),'prior_source_urls':r.get('source_urls',''),'wko_firmaids':r.get('wko_firmaids',''),
          'wko_phones':r.get('phones',''),'wko_emails':r.get('emails',''),'old_evidence_snippet':r.get('evidence_snippet','')[:2500]
        };out.append(rr)
    fields=list(out[0].keys()) if out else []
    with open(os.path.join(a.output_dir,'wko_only_candidates.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
    chunks=[[] for _ in range(a.chunks)]
    for i,r in enumerate(out):chunks[i%a.chunks].append(r)
    for i,c in enumerate(chunks):
        with open(os.path.join(a.output_dir,f'chunk_{i:02d}.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(c)
    if duplicates:
        with open(os.path.join(a.output_dir,'excluded_ksw_duplicates.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(duplicates[0].keys()));w.writeheader();w.writerows(duplicates)
    m={'wko_shortlist_rows':len(wr),'wko_only_candidates':len(out),'excluded_as_ksw_domain_duplicates':len(duplicates),'chunks':a.chunks,'chunk_sizes':[len(c) for c in chunks]}
    json.dump(m,open(os.path.join(a.output_dir,'manifest.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(m,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
