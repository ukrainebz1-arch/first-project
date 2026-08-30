import requests,re
from bs4 import BeautifulSoup
from urllib.parse import quote
from playwright.sync_api import sync_playwright

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
q='Schwarz Partner Wirtschaftsprüfung Steuerberatung GmbH Wien'

for name,url in [
 ('bing','https://www.bing.com/search?q='+quote(q)),
 ('google','https://www.google.com/search?q='+quote(q)),
 ('brave','https://search.brave.com/search?q='+quote(q)),
 ('ddg','https://html.duckduckgo.com/html/?q='+quote(q)),
]:
    try:
        r=requests.get(url,headers={'User-Agent':UA,'Accept-Language':'de-AT,de;q=0.9'},timeout=30,allow_redirects=True)
        print(name,'status',r.status_code,'len',len(r.text),'url',r.url)
        text=re.sub(r'\s+',' ',BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True))
        print(name,'mentions firmenabc', 'firmenabc' in text.lower(), 'linkedin' in text.lower(), text[:400])
    except Exception as e: print(name,'ERR',repr(e))

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--disable-blink-features=AutomationControlled'])
    ctx=browser.new_context(user_agent=UA,locale='de-AT',timezone_id='Europe/Vienna',viewport={'width':1440,'height':1000})
    page=ctx.new_page(); page.set_default_timeout(20000)
    r=page.goto('https://www.firmenabc.at/',wait_until='domcontentloaded',timeout=120000)
    print('firmenabc home',r.status if r else None,page.url)
    page.wait_for_timeout(1500)
    inputs=page.locator('input')
    print('inputs',inputs.count())
    for i in range(min(inputs.count(),12)):
        el=inputs.nth(i)
        try: print('INPUT',i,'type',el.get_attribute('type'),'name',el.get_attribute('name'),'ph',el.get_attribute('placeholder'))
        except: pass
    forms=page.locator('form')
    print('forms',forms.count())
    for i in range(forms.count()):
        f=forms.nth(i)
        try: print('FORM',i,'action',f.get_attribute('action'),'method',f.get_attribute('method'))
        except: pass
    # Try first visible text-like input and visible search button
    vis=[]
    for i in range(inputs.count()):
        el=inputs.nth(i)
        try:
            if el.is_visible() and (el.get_attribute('type') in (None,'text','search')): vis.append(i)
        except: pass
    print('visible text inputs',vis)
    if vis:
        inputs.nth(vis[0]).fill('Schwarz & Partner Wirtschaftsprüfung & Steuerberatung GmbH')
        if len(vis)>1: inputs.nth(vis[1]).fill('Wien')
        btn=page.get_by_role('button',name=re.compile('Suchen',re.I)).first
        print('search button count',page.get_by_role('button',name=re.compile('Suchen',re.I)).count())
        btn.click()
        page.wait_for_timeout(3000)
        print('after search url',page.url)
        links=page.locator('a[href]')
        out=[]
        for i in range(min(links.count(),300)):
            a=links.nth(i)
            try:
                href=a.get_attribute('href') or ''; txt=' '.join((a.inner_text() or '').split())
                if 'schwarz' in (txt+' '+href).lower(): out.append((txt,href))
            except: pass
        print('matching links',out[:20])
    browser.close()
