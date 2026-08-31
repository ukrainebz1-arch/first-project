#!/usr/bin/env python3
import argparse,csv,os,re,random,time
import hausverwaltung_stage4_worker as w

# Stage-3 lesson: discovery parsers must not promote adjacent-card contacts.
# This wrapper narrows evidence to the closest contact(s) around the exact person name.

def strict_phone_class(raw,ctx):
    low=ctx.lower(); n=w.norm_phone(raw)
    if w.is_mobile(n):
        return 'A_MOBILE_PUBLIC',100
    # Word-boundary labels only: "Immobilien" must never trigger "mobil".
    if re.search(r'\b(?:mobil|mobile)\b',low) and w.is_mobile(n):
        return 'A_MOBILE_PUBLIC',100
    if re.search(r'\b(?:durchwahl|dw|direkt|direct|extension|ext\.)\b',low):
        return 'B_DIRECT_DIAL',95
    if re.search(r'(?:[-/ ]0)\s*$',raw.strip()) or any(x in low for x in w.CENTRAL_LABEL):
        return 'E_CENTRAL_FALLBACK',20
    if re.search(r'\b(?:telefon|tel|phone)\b',low):
        return 'C_PERSON_BOUND_OFFICE',82
    return 'NONE',0


def exact_spans(text,person):
    full=w.clean_name(person)
    if not full:return []
    return [m.span() for m in re.finditer(re.escape(full),text,re.I)][:12]


def nearest_matches(regex,text,st,en,max_before=90,max_after=220):
    lo=max(0,st-max_before); hi=min(len(text),en+max_after)
    seg=text[lo:hi]; center=(st+en)/2-lo
    found=[]
    for m in regex.finditer(seg):
        mcenter=(m.start()+m.end())/2
        found.append((abs(mcenter-center),m.group(0),m.start(),m.end(),seg))
    found.sort(key=lambda x:x[0])
    return found


def strict_extract(text,person,company,url,source_kind,query=''):
    out=[]
    for st,en in exact_spans(text,person):
        lo=max(0,st-90);hi=min(len(text),en+220);ctx=text[lo:hi]
        if not w.company_match(ctx+' '+text[:500],company) and source_kind not in ('official_html','official_pdf'):
            continue
        # Personal e-mails: only a name-matching address is allowed to become person evidence.
        # Generic addresses remain company fallback and are collected elsewhere.
        emails=[]
        for dist,raw,_,_,seg in nearest_matches(w.EMAIL_RE,text,st,en):
            e=raw.lower().strip(' .;,')
            if w.person_email_match(e,person):
                emails.append((dist,e))
        for _,e in emails[:2]:
            out.append({'person':person,'contact_type':'email','contact':e,'contact_class':'A_PERSONAL_VERIFIED','score':96,'source_url':url,'source_kind':source_kind,'query':query,'context':ctx[:550]})
        # Keep only the nearest plausible phones to reduce spillover from the next team card.
        phones=[]
        for dist,raw,ms,me,seg in nearest_matches(w.PHONE_RE,text,st,en):
            raw=re.sub(r'\s+',' ',raw).strip(' .;,')
            if not w.valid_phone(raw):continue
            local=seg[max(0,ms-55):min(len(seg),me+55)]
            cls,score=strict_phone_class(raw,local)
            if score:phones.append((dist,raw,cls,score,local))
        for _,raw,cls,score,local in phones[:2]:
            out.append({'person':person,'contact_type':'phone','contact':w.norm_phone(raw),'contact_class':cls,'score':score,'source_url':url,'source_kind':source_kind,'query':query,'context':ctx[:550]})
    return out

w.context_spans=exact_spans
w.classify_phone=strict_phone_class
w.extract_person=strict_extract


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    with open(a.input_csv,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    allhits=[];coverage=[]
    for i,row in enumerate(rows,1):
        hits,checked,fp,fe=w.research(row)
        for h in hits:
            h.update({'no':row['no'],'company_name':row['company_name'],'stage3_scope':row['stage3_scope'],'primary_dm':row['primary_dm'],'primary_dm_role':row['primary_dm_role']});allhits.append(h)
        coverage.append({'no':row['no'],'company_name':row['company_name'],'stage3_scope':row['stage3_scope'],'primary_dm':row['primary_dm'],'website':row.get('website',''),'checked_source_count':str(len(checked)),'checked_source_urls':' | '.join(checked),'fallback_phones':' | '.join(fp),'fallback_emails':' | '.join(fe),'machine_research_complete':'yes'})
        print(f'{i}/{len(rows)} #{row["no"]} {row["company_name"]}: people={len(w.people(row))} hits={len(hits)} checked={len(checked)}',flush=True)
        time.sleep(random.uniform(.01,.04))
    hf=['no','company_name','stage3_scope','primary_dm','primary_dm_role','person','contact_type','contact','contact_class','score','source_count','source_url','all_source_urls','source_kind','query','context']
    with open(os.path.join(a.output_dir,'evidence.csv'),'w',encoding='utf-8-sig',newline='') as f:
        x=csv.DictWriter(f,fieldnames=hf);x.writeheader();x.writerows([{k:r.get(k,'') for k in hf} for r in allhits])
    cf=['no','company_name','stage3_scope','primary_dm','website','checked_source_count','checked_source_urls','fallback_phones','fallback_emails','machine_research_complete']
    with open(os.path.join(a.output_dir,'coverage.csv'),'w',encoding='utf-8-sig',newline='') as f:
        x=csv.DictWriter(f,fieldnames=cf);x.writeheader();x.writerows(coverage)

if __name__=='__main__':main()
