import re
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
name='Schwarz & Partner Wirtschaftsprüfung & Steuerberatung GmbH'
city='Wien'

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,args=['--disable-blink-features=AutomationControlled'])
    ctx=browser.new_context(user_agent=UA,locale='de-AT',timezone_id='Europe/Vienna',viewport={'width':1440,'height':1000})
    page=ctx.new_page(); page.set_default_timeout(30000)
    r=page.goto('https://www.firmenabc.at/',wait_until='domcontentloaded',timeout=120000)
    print('HOME',r.status if r else None,page.url)
    # Bypass cookie overlay; submit the search form directly rather than clicking.
    form=page.locator('form').nth(0)
    texts=form.locator('input[type="text"]')
    print('TEXT INPUTS',texts.count())
    for i in range(texts.count()):
        el=texts.nth(i)
        print(i,el.get_attribute('name'),el.get_attribute('placeholder'))
    texts.nth(0).fill(name)
    if texts.count()>1:
        texts.nth(1).fill(city)
    print('FORM HTML',form.evaluate('(f)=>f.outerHTML')[:4000])
    # Native requestSubmit executes normal form semantics without pointer interception.
    form.evaluate('(f)=>f.requestSubmit()')
    page.wait_for_load_state('domcontentloaded',timeout=60000)
    page.wait_for_timeout(1500)
    print('SEARCH URL',page.url)
    print('SEARCH TITLE',page.title())
    print('STATUS TEXT',page.locator('body').inner_text()[:2000].replace('\n',' | '))
    links=page.locator('a[href]')
    matches=[]
    for i in range(min(links.count(),500)):
        a=links.nth(i)
        try:
            txt=' '.join((a.inner_text() or '').split()); href=a.get_attribute('href') or ''
            low=(txt+' '+href).lower()
            if 'schwarz' in low or 'steuerberatung' in low:
                matches.append((txt,urljoin(page.url,href)))
        except: pass
    print('MATCHES',matches[:50])
    # visit plausible company profile
    for txt,href in matches:
        if href.startswith('https://www.firmenabc.at/') and '/suche/' not in href and href.rstrip('/')!='https://www.firmenabc.at':
            rr=page.goto(href,wait_until='domcontentloaded',timeout=60000)
            page.wait_for_timeout(800)
            body=' '.join(page.locator('body').inner_text().split())
            print('PROFILE',rr.status if rr else None,page.url)
            for pat in [r'Mitarbeiterzahl\s*:?\s*([^|]{0,80})',r'Mitarbeiter(?:innen|:innen)?\s*:?\s*(\d+)',r'(\d+)\s+Mitarbeiter']:
                m=re.search(pat,body,re.I)
                if m: print('EMP MATCH',pat,m.group(0),m.groups())
            print('PROFILE TEXT',body[:2500])
            break
    browser.close()
