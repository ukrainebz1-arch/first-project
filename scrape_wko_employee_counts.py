import csv, os, re, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from bs4 import BeautifulSoup

INPUT = os.environ.get('INPUT', 'input/wko_bookkeeping_austria_combined.csv')
OUTDIR = Path(os.environ.get('OUTDIR', 'out_wko_counts'))
CHUNK = int(os.environ.get('CHUNK', '0'))
CHUNKS = int(os.environ.get('CHUNKS', '16'))
WORKERS = int(os.environ.get('WORKERS', '8'))
OUTDIR.mkdir(parents=True, exist_ok=True)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
HEADERS = {
    'User-Agent': UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'de-AT,de;q=0.9,en;q=0.7',
    'Cache-Control': 'no-cache',
}

COUNT_PATTERNS = [
    re.compile(r'(?<![\d.])(\d{1,5})\s+Mitarbeiter(?:innen|Innen|:innen|\b)', re.I),
    re.compile(r'(?<![\d.])(\d{1,5})\s+Beschäftigte(?:n|\b)', re.I),
]

session = requests.Session()
session.headers.update(HEADERS)

with open(INPUT, encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))
selected = [r for i, r in enumerate(rows) if i % CHUNKS == CHUNK]

def fetch_one(r):
    url = (r.get('profile_url') or '').strip()
    out = dict(r)
    out.update({
        'wko_http_status': '', 'wko_employee_count': '', 'wko_employee_all_signals': '',
        'wko_employee_context': '', 'wko_profile_fetch_ok': '0'
    })
    if not url:
        return out
    try:
        resp = session.get(url, timeout=25, allow_redirects=True)
        out['wko_http_status'] = str(resp.status_code)
        if resp.status_code != 200:
            return out
        soup = BeautifulSoup(resp.text, 'html.parser')
        text = ' '.join(soup.stripped_strings)
        # Only trust explicit numeric strings immediately attached to Mitarbeiter/Beschäftigte.
        hits = []
        for pat in COUNT_PATTERNS:
            for m in pat.finditer(text):
                n = int(m.group(1))
                if 0 <= n <= 50000:
                    lo = max(0, m.start()-100); hi = min(len(text), m.end()+100)
                    hits.append((m.start(), n, text[lo:hi]))
        hits.sort(key=lambda x: x[0])
        # WKO's own company facts block normally contains the first explicit employee count.
        if hits:
            out['wko_employee_count'] = str(hits[0][1])
            out['wko_employee_all_signals'] = ' | '.join(str(x[1]) for x in hits)
            out['wko_employee_context'] = hits[0][2][:500]
        out['wko_profile_fetch_ok'] = '1'
    except Exception as e:
        out['wko_http_status'] = 'ERR:' + type(e).__name__
    return out

results = []
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = [ex.submit(fetch_one, r) for r in selected]
    for j, fut in enumerate(as_completed(futs), 1):
        results.append(fut.result())
        if j % 50 == 0:
            print(f'chunk {CHUNK}: {j}/{len(selected)}')

# stable order by original firmaid is enough; merge will sort against source order if needed
fields = list(rows[0].keys()) + ['wko_http_status','wko_employee_count','wko_employee_all_signals','wko_employee_context','wko_profile_fetch_ok']
out = OUTDIR / f'wko_employee_counts_chunk_{CHUNK:02d}.csv'
with open(out, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader(); w.writerows(results)
print({'chunk': CHUNK, 'selected': len(selected), 'fetched_ok': sum(r['wko_profile_fetch_ok']=='1' for r in results), 'counts_found': sum(bool(r['wko_employee_count']) for r in results)})
