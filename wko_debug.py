import json, os, re
from playwright.sync_api import sync_playwright

URLS={"buchhalter":"https://firmen.wko.at/buchhalter/","bilanzbuchhalter":"https://firmen.wko.at/bilanzbuchhalter/"}
os.makedirs("output",exist_ok=True)
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    ctx=browser.new_context(user_agent=UA,locale="de-AT",viewport={"width":1440,"height":1200})
    for label,url in URLS.items():
        page=ctx.new_page()
        net=[]
        def on_req(req):
            if req.resource_type in ("xhr","fetch"):
                try: post=req.post_data or ""
                except: post=""
                net.append({"method":req.method,"type":req.resource_type,"url":req.url,"post":post[:4000]})
        page.on("request",on_req)
        page.goto(url,wait_until="networkidle",timeout=120000)
        page.wait_for_timeout(1500)
        html=page.content()
        open(f"output/debug_{label}.html","w",encoding="utf-8").write(html)
        page.screenshot(path=f"output/debug_{label}.png",full_page=True)
        body=page.locator("body").inner_text()
        print(f"=== {label} BODY TAIL ===\n{body[-5000:]}",flush=True)
        matches=page.evaluate("""() => [...document.querySelectorAll('*')].map((e,i)=>{
          const cs=getComputedStyle(e); const r=e.getBoundingClientRect();
          const visible=cs.display!=='none'&&cs.visibility!=='hidden'&&r.width>0&&r.height>0;
          const text=((e.innerText||'')+' '+(e.value||'')+' '+(e.getAttribute('aria-label')||'')+' '+(e.title||'')+' '+(e.id||'')+' '+(e.className||'')).replace(/\\s+/g,' ').trim();
          return {i,tag:e.tagName,text:text.slice(0,500),visible,html:e.outerHTML.slice(0,2500)};
        }).filter(x=>x.visible && /mehr|laden|weitere|treffer|result|paging|page|next/i.test(x.text)).slice(-80)""")
        print(f"=== {label} MATCH ELEMENTS ===\n{json.dumps(matches,ensure_ascii=False,indent=2)}",flush=True)
        clickables=page.evaluate("""() => [...document.querySelectorAll('button,input,a,[onclick],[role=button]')].map((e,i)=>{
          const cs=getComputedStyle(e),r=e.getBoundingClientRect();
          if(cs.display==='none'||cs.visibility==='hidden'||r.width<=0||r.height<=0)return null;
          return {tag:e.tagName,type:e.getAttribute('type'),name:e.getAttribute('name'),id:e.id,class:e.className,value:e.value||'',text:(e.innerText||'').replace(/\\s+/g,' ').trim(),aria:e.getAttribute('aria-label'),title:e.title,href:e.href||'',onclick:e.getAttribute('onclick'),y:r.y,html:e.outerHTML.slice(0,1800)}
        }).filter(Boolean).filter(x=>x.y>500).slice(-80)""")
        print(f"=== {label} BOTTOM CLICKABLES ===\n{json.dumps(clickables,ensure_ascii=False,indent=2)}",flush=True)
        print(f"=== {label} XHR/FETCH ===\n{json.dumps(net,ensure_ascii=False,indent=2)}",flush=True)
        page.close()
    browser.close()
