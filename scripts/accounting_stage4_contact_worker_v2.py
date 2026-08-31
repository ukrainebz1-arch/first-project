#!/usr/bin/env python3
import argparse,csv,os,re,time,random
import accounting_stage4_contact_worker as w

PHONE_SIGNAL=('telefon','tel.','tel:','phone','mobil','mobile','durchwahl','direkt','direct','dw:',' dw ','extension','ext.')
CENTRAL_SIGNAL=('zentrale','sekretariat','office','kanzlei allgemein','allgemeine anfragen','rezeption','reception')

def safe_phone_class(raw,ctx):
    low=ctx.lower();n=w.norm_phone(raw);d=re.sub(r'\D','',n);at=d[2:] if d.startswith('43') else d
    if any(at.startswith(x) for x in w.MOBILE) or 'mobil' in low or 'mobile' in low:return 'mobile_public',100
    if any(k in low for k in ['durchwahl',' dw ','dw:','direkt','direct','extension',' ext.']):return 'direct_extension',95
    # Common Austrian switchboard presentation ending in -0 is never direct by default.
    if re.search(r'(?:[-/ ]0)\s*$',raw.strip()) or any(k in low for k in CENTRAL_SIGNAL):return 'central_context',20
    # Fixed number is accepted only when a phone label is in the same compact person card/context.
    if any(k in low for k in PHONE_SIGNAL):return 'named_fixed_candidate',75
    return 'unqualified_number',0

def safe_extract(t,person,url,method):
    hits=[]
    for st,en in w.person_spans(t,person):
        # Deliberately compact window: contacts must be in the same person card/paragraph,
        # not merely somewhere in a long Team/Impressum page.
        ctx=t[max(0,st-260):min(len(t),en+420)]
        for e in sorted(set(x.lower() for x in w.EMAIL_RE.findall(ctx))):
            cls,score=w.email_class(e,person,ctx)
            hits.append({'person':person,'contact_type':'email','contact':e,'contact_class':cls,'score':score,'source_url':url,'method':method,'context':ctx[:850]})
        for raw in w.PHONE_RE.findall(ctx):
            p=re.sub(r'\s+',' ',raw).strip(' .;,')
            # Must look like an Austrian phone itself, or have a local phone label.
            if not w.valid_phone(p):continue
            rawcompact=p.replace(' ','')
            low=ctx.lower()
            if not (rawcompact.startswith(('+43','0043','0')) or any(k in low for k in PHONE_SIGNAL)):continue
            cls,score=safe_phone_class(p,ctx)
            if score<=0:continue
            hits.append({'person':person,'contact_type':'phone','contact':w.norm_phone(p),'contact_class':cls,'score':score,'source_url':url,'method':method,'context':ctx[:850]})
    return hits

w.extract=safe_extract

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-csv',required=True);a=ap.parse_args()
    rows=list(csv.DictReader(open(a.input_csv,encoding='utf-8-sig',newline='')));allhits=[]
    for i,row in enumerate(rows,1):
        ps=w.people(row);sites=[x.strip() for x in (row.get('websites') or '').split(' | ') if x.strip()];hits=[]
        for u,t in w.crawl(sites):
            for p in ps:hits+=safe_extract(t,p,u,'official_site')
        for p in ps:
            qs=[f'"{p}" "{row["group_name"]}" Telefon',f'"{p}" "{row["group_name"]}" E-Mail',f'"{p}" Mobil',f'"{p}" Durchwahl',f'"{p}" filetype:pdf']
            seenurls=set()
            for q in qs:
                for x in w.search(q):
                    u=x['url'];blob=x['title']+' '+x['snippet']
                    if not u or u in seenurls:continue
                    seenurls.add(u);hits+=safe_extract(blob,p,u,'external_search_snippet')
                    if 'linkedin.com' not in w.host(u):
                        uu,hh=w.get(u,8)
                        if hh:hits+=safe_extract(w.text(hh),p,uu,'external_page')
                time.sleep(random.uniform(.02,.06))
        hits=w.dedupe(hits)
        for h in hits:
            h['group_key']=row['group_key'];h['group_name']=row['group_name'];h['size_gate']=row.get('size_gate','');h['primary_dm']=row.get('primary_dm','')
            h['score']=int(h['score'])+min(8,max(0,(int(h['source_count'])-1)*4));allhits.append(h)
        print(f'{i}/{len(rows)} {row["group_name"]}: people={len(ps)} hits={len(hits)}',flush=True);time.sleep(random.uniform(.03,.10))
    fields=['group_key','group_name','size_gate','primary_dm','person','contact_type','contact','contact_class','score','source_count','method_count','source_url','all_source_urls','method','context']
    os.makedirs(os.path.dirname(a.output_csv) or '.',exist_ok=True)
    with open(a.output_csv,'w',encoding='utf-8-sig',newline='') as f:
        x=csv.DictWriter(f,fieldnames=fields);x.writeheader();x.writerows(allhits)
if __name__=='__main__':main()
