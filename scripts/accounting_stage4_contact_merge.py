#!/usr/bin/env python3
import argparse,csv,glob,json,os,re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
EMAIL=re.compile(r'(?<![\w.+-])([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})(?![\w.-])',re.I)
PHONE=re.compile(r'(?:(?:\+|00)\s?43[\s()./-]*)?(?:\(?\d{1,5}\)?[\s./-]*){1,3}\d{2,6}',re.I)
GENERIC=('info@','office@','kontakt@','kanzlei@','mail@','service@')

def rows(p):
    with open(p,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def normphone(x):
    s=re.sub(r'[^0-9+]','',x or '')
    if s.startswith('00'):s='+'+s[2:]
    if s.startswith('0') and not s.startswith('00'):s='+43'+s[1:]
    if s.startswith('+430'):s='+43'+s[4:]
    return s
def goodphone(x):
    d=re.sub(r'\D','',normphone(x));return 8<=len(d)<=15 and not (len(d)==8 and d.startswith('20'))
def fallback(row):
    sites=[x.strip() for x in (row.get('websites') or '').split(' | ') if x.strip()];emails=[];phones=[];src=''
    for site in sites[:1]:
        u=site if '://' in site else 'https://'+site
        for path in ['', '/kontakt','/contact','/impressum']:
            try:
                r=requests.get(urljoin(u,path),headers=H,timeout=8,allow_redirects=True)
                if r.status_code!=200:continue
                t=re.sub(r'\s+',' ',BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True));src=r.url
                for e in EMAIL.findall(t):
                    e=e.lower()
                    if e not in emails:emails.append(e)
                for p in PHONE.findall(t):
                    p=normphone(p)
                    if goodphone(p) and p not in phones:phones.append(p)
                if emails or phones:break
            except:pass
        if emails or phones:break
    ge=[e for e in emails if e.startswith(GENERIC)] or emails
    return (phones[0] if phones else ''),(ge[0] if ge else ''),src

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--targets',required=True);ap.add_argument('--hits-dir',required=True);ap.add_argument('--output-dir',required=True);a=ap.parse_args();os.makedirs(a.output_dir,exist_ok=True)
    targets=rows(a.targets);by={r['group_key']:r for r in targets};hits=[]
    for p in glob.glob(os.path.join(a.hits_dir,'**','*.csv'),recursive=True):
        try:hits+=rows(p)
        except:pass
    # Deduplicate same person/contact across chunks/sources.
    merged={}
    for h in hits:
        k=(h.get('group_key',''),h.get('person','').lower(),h.get('contact_type',''),h.get('contact','').lower())
        if not k[0] or not k[3]:continue
        try:score=int(float(h.get('score') or 0));sc=int(float(h.get('source_count') or 1))
        except:score=0;sc=1
        if k not in merged:merged[k]=dict(h);merged[k]['score']=score;merged[k]['source_count']=sc
        else:
            x=merged[k];x['score']=max(int(x.get('score') or 0),score);urls=set((x.get('all_source_urls') or '').split(' | '));urls.update((h.get('all_source_urls') or h.get('source_url','')).split(' | '));urls.discard('');x['all_source_urls']=' | '.join(sorted(urls));x['source_count']=len(urls)
    allhits=list(merged.values());allhits.sort(key=lambda h:(h.get('group_key',''),-int(h.get('score') or 0),h.get('person','')))
    fields=['group_key','group_name','size_gate','primary_dm','person','contact_type','contact','contact_class','score','source_count','method_count','source_url','all_source_urls','method','context']
    with open(os.path.join(a.output_dir,'validated_contacts.csv'),'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:h.get(k,'') for k in fields} for h in allhits])
    out=[];direct_phone=direct_email=any_phone=any_email=0
    for k,r in by.items():
        hs=[h for h in allhits if h.get('group_key')==k]
        ph=sorted([h for h in hs if h.get('contact_type')=='phone'],key=lambda h:-int(h.get('score') or 0))
        em=sorted([h for h in hs if h.get('contact_type')=='email'],key=lambda h:-int(h.get('score') or 0))
        bp=ph[0] if ph else None;be=em[0] if em else None;fbp=fbe=fbs=''
        if not bp or not be:fbp,fbe,fbs=fallback(r)
        rr=dict(r);rr.update({
          'best_direct_phone':bp.get('contact','') if bp and int(bp.get('score') or 0)>=75 else '',
          'best_phone_class':bp.get('contact_class','') if bp else ('central_fallback' if fbp else ''),
          'best_phone_score':bp.get('score','') if bp else ('20' if fbp else ''),
          'best_phone_person':bp.get('person','') if bp else '',
          'best_phone_sources':bp.get('all_source_urls','') if bp else (fbs if fbp else ''),
          'best_personal_email':be.get('contact','') if be and int(be.get('score') or 0)>=70 else '',
          'best_email_class':be.get('contact_class','') if be else ('generic_fallback' if fbe else ''),
          'best_email_score':be.get('score','') if be else ('30' if fbe else ''),
          'best_email_person':be.get('person','') if be else '',
          'best_email_sources':be.get('all_source_urls','') if be else (fbs if fbe else ''),
          'fallback_central_phone':fbp if not bp else '',
          'fallback_generic_email':fbe if not be else '',
        });out.append(rr)
        if rr['best_direct_phone']:direct_phone+=1
        if rr['best_personal_email']:direct_email+=1
        if rr['best_direct_phone'] or rr['fallback_central_phone']:any_phone+=1
        if rr['best_personal_email'] or rr['fallback_generic_email']:any_email+=1
    if out:
        with open(os.path.join(a.output_dir,'final_prospect_dataset.csv'),'w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(out[0].keys()));w.writeheader();w.writerows(out)
    summary={'targets':len(targets),'raw_hits':len(hits),'deduped_hits':len(allhits),'targets_with_direct_phone':direct_phone,'targets_with_personal_email':direct_email,'targets_with_any_phone_including_fallback':any_phone,'targets_with_any_email_including_fallback':any_email}
    json.dump(summary,open(os.path.join(a.output_dir,'summary.json'),'w',encoding='utf-8'),ensure_ascii=False,indent=2);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
