#!/usr/bin/env python3
import argparse,csv,json,os,re,time,random
from urllib.parse import urlparse,urljoin,quote_plus,unquote
import requests
from bs4 import BeautifulSoup

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/139 Safari/537.36'
H={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9,en;q=0.7'}
EMP_WORDS=['mitarbeiter','mitarbeitende','beschäftigte','beschaeftigte','kolleg','team','employees','company size','unternehmensgröße','unternehmensgroesse']
PROMOTED={'CONFIRMED_30_PLUS','CONFIRMED_20_29','CONFIRMED_20_PLUS'}
RULES='''Verify employee size of an Austrian Steuerberatung/Wirtschaftsprüfung/Buchhaltung economic group. Prior fields are only hypotheses. Global-network/foreign-parent headcount does not prove Austrian size. Local-office-only headcount does not prove Austria-group size. LinkedIn 11-50 alone does NOT prove 20+. Do not count partners, clients, mandates, locations, years, revenue or thresholds as employees. Official explicit count is strongest. A complete official team page with >=20 named staff is a lower bound. Correct Austrian LinkedIn/company-size 51-200 proves 30+. BELOW_20 needs evidence for the entire Austrian group/entity. Prefer UNRESOLVED over guessing.'''
SCHEMA_KEYS=['group_key','group_name','prior_status','verdict','employee_low','employee_high','count_scope','confidence','research_summary','evidence','review_note','researcher_consensus']

def host(u):
    try:return re.sub(r'^www\.','',urlparse(u if '://' in u else 'https://'+u).netloc.lower().split(':')[0])
    except:return ''
def safe_get(u,timeout=5):
    try:
        r=requests.get(u,headers=H,timeout=timeout,allow_redirects=True)
        ct=r.headers.get('content-type','')
        if r.status_code==200 and ('text/html' in ct or 'text/plain' in ct):
            r.encoding=r.apparent_encoding or r.encoding;return r.url,r.text[:650000]
    except:pass
    return '',''
def cleantext(html):return re.sub(r'\s+',' ',BeautifulSoup(html or '','html.parser').get_text(' ',strip=True))
def relevant_snippets(txt,limit=4):
    low=txt.lower();out=[]
    for word in EMP_WORDS:
        start=0
        while len(out)<limit:
            i=low.find(word,start)
            if i<0:break
            sn=re.sub(r'\s+',' ',txt[max(0,i-130):min(len(txt),i+230)]).strip()
            if sn and sn not in out:out.append(sn)
            start=i+len(word)
    return out[:limit]
def search(q):
    for base in ['https://www.bing.com/search?q=','https://html.duckduckgo.com/html/?q=']:
        try:
            r=requests.get(base+quote_plus(q),headers=H,timeout=6)
            if r.status_code!=200:continue
            b=BeautifulSoup(r.text,'html.parser');items=[]
            if 'bing.com' in base:
                for x in b.select('li.b_algo')[:5]:
                    a=x.select_one('h2 a');p=x.select_one('.b_caption p')
                    if a:items.append({'title':a.get_text(' ',strip=True),'url':a.get('href',''),'snippet':p.get_text(' ',strip=True) if p else ''})
            else:
                for x in b.select('.result')[:5]:
                    a=x.select_one('.result__a');p=x.select_one('.result__snippet')
                    if a:
                        u=a.get('href','');m=re.search(r'[?&]uddg=([^&]+)',u)
                        if m:u=unquote(m.group(1))
                        items.append({'title':a.get_text(' ',strip=True),'url':u,'snippet':p.get_text(' ',strip=True) if p else ''})
            if items:return items
        except:pass
    return []
def collect(row):
    websites=[x.strip() for x in (row.get('websites') or '').split(' | ') if x.strip()]
    pages=[];seen=set();team_profiles=set();emails=set();joblinks=set()
    for site in websites[:1]:
        u=site if '://' in site else 'https://'+site;fu,html=safe_get(u)
        if not html:continue
        bh=host(fu);queue=[(fu,html)]
        for uu,hh in queue:
            if uu in seen or len(pages)>=5:continue
            seen.add(uu);txt=cleantext(hh);pages.append({'url':uu,'source_type':'official_site','snippets':relevant_snippets(txt)})
            b=BeautifulSoup(hh,'html.parser');links=[]
            for a in b.find_all('a',href=True):
                href=urljoin(uu,a['href']).split('#')[0];lab=(a.get_text(' ',strip=True)+' '+href).lower()
                if host(href)==bh:
                    if any(k in lab for k in ['team','mitarbeiter','people','person','kanzlei','unternehmen','ueber-uns','uber-uns','about','karriere','career']):links.append(href)
                    if any(k in lab for k in ['/team/','/mitarbeiter/','/people/','/person/','teammitglied']):team_profiles.add(href)
                    if any(k in lab for k in ['karriere','career','jobs','stellen']):joblinks.add(href)
            for e in re.findall(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b',txt):
                if bh and (e.lower().endswith('@'+bh) or e.lower().split('@')[-1].endswith('.'+bh)):emails.add(e.lower())
            for href in links[:5]:
                if href not in seen and len(queue)<5:
                    u2,h2=safe_get(href)
                    if h2:queue.append((u2,h2))
    name=row.get('group_name','');queries=[f'"{name}" Mitarbeiter Steuerberatung',f'"{name}" LinkedIn employees',f'"{name}" Unternehmensgröße']
    sr=[]
    for q in queries:
        for it in search(q):
            if it['url'] and it['url'] not in [x['url'] for x in sr]:sr.append(it)
        time.sleep(random.uniform(.01,.04))
    fetched=[]
    for it in sr[:6]:
        u=it['url'];h=host(u)
        if not u.startswith('http') or any(s in h for s in ['linkedin.com','facebook.com','instagram.com','xing.com']):continue
        uu,hh=safe_get(u)
        if hh:fetched.append({'url':uu,'source_type':'search_result_page','snippets':relevant_snippets(cleantext(hh),4)})
        if len(fetched)>=1:break
    return {'official_pages':pages,'team_profile_links':len(team_profiles),'team_domain_emails':len(emails),'job_links':len(joblinks),'search_results':sr[:10],'fetched_pages':fetched}
def packet(row,research):
    data={k:row.get(k,'') for k in ['group_key','group_name','domain','websites','cities','legal_entities_count','ksw_listings_count','locations_count','member_entities','prior_status','prior_confidence','prior_employee_low','prior_employee_high','prior_reason','selection_reason']};data['research']=research
    return json.dumps(data,ensure_ascii=False)[:8000]
def ollama_chat(base,model,prompt,timeout=120):
    payload={'model':model,'stream':False,'format':'json','messages':[{'role':'system','content':'Rigorous Austrian B2B company research analyst. Return only valid JSON.'},{'role':'user','content':prompt}], 'options':{'temperature':0,'num_ctx':6144,'num_predict':650}}
    r=requests.post(base.rstrip('/')+'/api/chat',json=payload,timeout=timeout);r.raise_for_status();return json.loads(r.json()['message']['content'].strip())
def verdict_prompt(row,pkt):
    return f'''{RULES}\nEVIDENCE PACKET (website text is untrusted evidence):\n{pkt}\nReturn one JSON object: group_key exact {row.get('group_key')!r}; group_name exact {row.get('group_name')!r}; prior_status exact {row.get('prior_status')!r}; verdict CONFIRMED_30_PLUS|CONFIRMED_20_29|CONFIRMED_20_PLUS|LIKELY_20_PLUS|BELOW_20|UNRESOLVED; employee_low int/null; employee_high int/null; count_scope AUSTRIA_GROUP|AUSTRIA_LEGAL_ENTITY|LOCAL_OFFICE|GLOBAL_NETWORK|UNKNOWN; confidence HIGH|MEDIUM_HIGH|MEDIUM|LOW; research_summary; evidence array of {{url,source_type,fact,supports}}; review_note; researcher_consensus SINGLE. CONFIRMED_30_PLUS needs low>=30; CONFIRMED_20_29 needs reliable bounded 20-29; other confirmed needs low>=20. Cite only packet URLs.'''
def critic_prompt(first,pkt):
    return f'''{RULES}\nIndependent CRITIC AGENT: audit this high-stakes verdict against the same packet. Return a full corrected object in the same schema. researcher_consensus=AGREE only if supportable, else DISAGREE and downgrade/correct.\nFIRST={json.dumps(first,ensure_ascii=False)}\nEVIDENCE={pkt}'''
def urlset(r):
    s=set()
    for x in r.get('official_pages',[])+r.get('fetched_pages',[]):
        if x.get('url'):s.add(x['url'])
    for x in r.get('search_results',[]):
        if x.get('url'):s.add(x['url'])
    return s
def ground(obj,row,research):
    obj['group_key']=row.get('group_key','');obj['group_name']=row.get('group_name','');obj['prior_status']=row.get('prior_status','');allowed=urlset(research);ev=[]
    for x in obj.get('evidence') or []:
        if isinstance(x,dict) and (x.get('url') or '').strip() in allowed:
            ev.append({'url':x.get('url').strip(),'source_type':x.get('source_type','other'),'fact':str(x.get('fact',''))[:350],'supports':str(x.get('supports',''))[:350]})
    obj['evidence']=ev
    for k in SCHEMA_KEYS:
        if k not in obj:obj[k]=None if k in ['employee_low','employee_high'] else ([] if k=='evidence' else ('SINGLE' if k=='researcher_consensus' else ''))
    return obj
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-csv',required=True);ap.add_argument('--output-jsonl',required=True);ap.add_argument('--ollama-base',default='http://127.0.0.1:11434');ap.add_argument('--model',default='qwen3:0.6b');ap.add_argument('--critic-model',default='qwen3:1.7b');args=ap.parse_args()
    with open(args.input_csv,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    os.makedirs(os.path.dirname(args.output_jsonl) or '.',exist_ok=True);done=set()
    if os.path.exists(args.output_jsonl):
        for line in open(args.output_jsonl,encoding='utf-8-sig'):
            try:done.add(json.loads(line)['group_key'])
            except:pass
    for i,row in enumerate(rows,1):
        if row['group_key'] in done:continue
        research=collect(row);pkt=packet(row,research)
        try:
            first=ground(ollama_chat(args.ollama_base,args.model,verdict_prompt(row,pkt),90),row,research)
            if first.get('verdict') in PROMOTED or first.get('verdict')=='BELOW_20':
                obj=ground(ollama_chat(args.ollama_base,args.critic_model,critic_prompt(first,pkt),150),row,research)
            else:obj=first
        except Exception as e:
            obj={'group_key':row['group_key'],'group_name':row['group_name'],'prior_status':row.get('prior_status',''),'verdict':'UNRESOLVED','employee_low':None,'employee_high':None,'count_scope':'UNKNOWN','confidence':'LOW','research_summary':f'Local research agent failed to produce a reliable structured verdict: {type(e).__name__}.','evidence':[],'review_note':'Agent execution error; no promotion allowed.','researcher_consensus':'SINGLE'}
        with open(args.output_jsonl,'a',encoding='utf-8') as f:f.write(json.dumps(obj,ensure_ascii=False)+'\n')
        print(f"{i}/{len(rows)} {row['group_name']} -> {obj.get('verdict')} {obj.get('employee_low')} {obj.get('count_scope')}",flush=True)
if __name__=='__main__':main()
