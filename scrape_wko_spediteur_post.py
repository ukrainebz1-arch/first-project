import csv
import json
import re
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = "https://firmen.wko.at"
OUT = Path("spedition_post_output")
OUT.mkdir(exist_ok=True)

STATES = OrderedDict([
    ("Burgenland", "burgenland"),
    ("Kärnten", "k%C3%A4rnten"),
    ("Niederösterreich", "nieder%C3%B6sterreich"),
    ("Oberösterreich", "ober%C3%B6sterreich"),
    ("Salzburg", "salzburg"),
    ("Steiermark", "steiermark"),
    ("Tirol", "tirol"),
    ("Vorarlberg", "vorarlberg"),
    ("Wien", "wien"),
])

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def q(url, key):
    try:
        return parse_qs(urlparse(url).query).get(key, [""])[0]
    except Exception:
        return ""


def first_text(node, selector):
    x = node.select_one(selector)
    return clean(x.get_text(" ", strip=True)) if x else ""


def parse_expected(soup):
    body = clean(soup.get_text(" ", strip=True))
    m = re.search(r"Ihre Suche erzielte\s+(?:über\s+)?([\d\.]+)\s+Treffer", body, re.I)
    return int(m.group(1).replace(".", "")) if m else None


def parse_rows(soup, state, source_url):
    rows = []
    articles = soup.select("article.search-result-article")
    if not articles:
        # Fallback: use title/profile links if WKO changes outer article class.
        articles = []
        for a in soup.select('a[href*="firmaid="]'):
            parent = a.find_parent("article") or a.parent
            if parent:
                articles.append(parent)

    seen = set()
    for art in articles:
        title = art.select_one('a.title-link[href*="firmaid="]') or art.select_one('a[href*="firmaid="]')
        if not title:
            continue
        href = urljoin(BASE, title.get("href", ""))
        fid = q(href, "firmaid")
        sid = q(href, "standortid")
        if not fid:
            continue
        key = (fid, sid, href.split("&page=", 1)[0])
        if key in seen:
            continue
        seen.add(key)

        h3 = title.select_one("h3")
        name = clean((h3 or title).get_text(" ", strip=True))
        street = first_text(art, ".address-container .street") or first_text(art, ".street")
        place = first_text(art, ".address-container .place") or first_text(art, ".place")

        phones = []
        for x in art.select('[itemprop="telephone"]'):
            v = clean(x.get_text(" ", strip=True))
            if v and v not in phones: phones.append(v)
        emails = []
        for x in art.select('[itemprop="email"]'):
            v = clean(x.get_text(" ", strip=True))
            if v and v not in emails: emails.append(v)
        websites = []
        for x in art.select('a[itemprop="url"]'):
            v = (x.get("href") or "").strip()
            if v and "firmen.wko.at" not in v and v not in websites: websites.append(v)

        rows.append({
            "bundesland": state,
            "company_name": name,
            "street": street,
            "place": place,
            "phone": " | ".join(phones),
            "email": " | ".join(emails),
            "website": " | ".join(websites),
            "firmaid": fid,
            "standortid": sid,
            "profile_url": href,
            "source_list_url": source_url,
        })
    return rows


def hidden_payload(soup):
    form = soup.find("form")
    payload = {}
    if not form:
        return payload
    for inp in form.find_all("input"):
        name = inp.get("name")
        typ = (inp.get("type") or "").lower()
        if name and typ == "hidden":
            payload[name] = inp.get("value", "")
    return payload


def has_more(soup):
    return bool(
        soup.select_one('#ctl00_ContentPlaceHolder1_nextPageButton')
        or soup.select_one('input[type="submit"][name="ctl00$ContentPlaceHolder1$nextPageButton"]')
    )


def scrape_state(state, slug):
    url = f"{BASE}/spediteur/{slug}/"
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.7"})
    print(f"STATE {state}: {url}", flush=True)
    r = sess.get(url, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    expected = parse_expected(soup)
    rows = parse_rows(soup, state, url)
    posts = 0
    print(f"  expected={expected}, initial={len(rows)}", flush=True)

    if expected is None:
        raise RuntimeError(f"Could not parse WKO Treffer count for {state}")

    last_count = -1
    while len(rows) < expected:
        if len(rows) == last_count:
            raise RuntimeError(f"No pagination progress in {state}: {len(rows)}/{expected}")
        last_count = len(rows)
        if not has_more(soup):
            raise RuntimeError(f"WKO has no Mehr laden button in {state} at {len(rows)}/{expected}")

        payload = hidden_payload(soup)
        payload["ctl00$ContentPlaceHolder1$nextPageButton"] = "Mehr laden"
        payload.setdefault("__EVENTTARGET", "")
        payload.setdefault("__EVENTARGUMENT", "")
        rr = sess.post(url, data=payload, timeout=90, allow_redirects=True)
        posts += 1
        if rr.status_code != 200:
            raise RuntimeError(f"WKO POST {state} #{posts}: HTTP {rr.status_code}, final URL={rr.url}")
        soup = BeautifulSoup(rr.text, "html.parser")
        new_expected = parse_expected(soup)
        if new_expected is not None:
            expected = new_expected
        rows = parse_rows(soup, state, url)
        if posts == 1 or posts % 5 == 0 or len(rows) >= expected:
            print(f"  {state}: posts={posts}, rows={len(rows)}/{expected}", flush=True)
        time.sleep(0.08)
        if posts > 150:
            raise RuntimeError(f"Safety stop in {state}: too many posts")

    # WKO can occasionally render one duplicate anchor/card; location-key dedupe above should remove it.
    if len(rows) != expected:
        raise RuntimeError(f"Count mismatch in {state}: extracted={len(rows)}, expected={expected}")

    print(f"  DONE {state}: {len(rows)}/{expected}, posts={posts}", flush=True)
    return rows, {
        "bundesland": state,
        "source_url": url,
        "expected_treffer": expected,
        "extracted_rows": len(rows),
        "postbacks": posts,
        "count_match": len(rows) == expected,
    }


def main():
    all_rows = []
    diagnostics = []
    for state, slug in STATES.items():
        rows, diag = scrape_state(state, slug)
        all_rows.extend(rows)
        diagnostics.append(diag)

    # State lists are disjoint geographically. Keep exact WKO location hits.
    all_rows.sort(key=lambda x: (x["bundesland"], x["company_name"].casefold(), x["place"].casefold()))
    raw_fields = ["bundesland","company_name","street","place","phone","email","website","firmaid","standortid","profile_url","source_list_url"]
    with (OUT / "wko_spediteur_standorte.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=raw_fields); w.writeheader(); w.writerows(all_rows)

    grouped = OrderedDict()
    for r in all_rows:
        key = r["firmaid"] or r["profile_url"]
        g = grouped.setdefault(key, {
            "company_name": r["company_name"],
            "firmaid": r["firmaid"],
            "bundeslaender": set(),
            "standort_count": 0,
            "street": r["street"],
            "place": r["place"],
            "phone": r["phone"],
            "email": r["email"],
            "website": r["website"],
            "profile_url": r["profile_url"],
        })
        g["bundeslaender"].add(r["bundesland"])
        g["standort_count"] += 1
        if len(r["company_name"]) > len(g["company_name"]):
            g["company_name"] = r["company_name"]
        for fld in ["street","place","phone","email","website"]:
            if not g[fld] and r[fld]: g[fld] = r[fld]

    unique = []
    for g in grouped.values():
        unique.append({
            "company_name": g["company_name"],
            "firmaid": g["firmaid"],
            "bundeslaender": "; ".join(sorted(g["bundeslaender"])),
            "standort_count": g["standort_count"],
            "street": g["street"],
            "place": g["place"],
            "phone": g["phone"],
            "email": g["email"],
            "website": g["website"],
            "profile_url": g["profile_url"],
        })
    unique.sort(key=lambda x: x["company_name"].casefold())
    unique_fields = ["company_name","firmaid","bundeslaender","standort_count","street","place","phone","email","website","profile_url"]
    with (OUT / "wko_spediteur_unique_companies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=unique_fields); w.writeheader(); w.writerows(unique)

    summary = {
        "data_source": "WKO Firmen A-Z",
        "wko_query": "Spediteur",
        "raw_standort_rows": len(all_rows),
        "unique_firmaids": len(unique),
        "expected_total_from_live_wko_pages": sum(d["expected_treffer"] for d in diagnostics),
        "all_state_counts_match": all(d["count_match"] for d in diagnostics),
        "states": diagnostics,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    if not summary["all_state_counts_match"] or summary["raw_standort_rows"] != summary["expected_total_from_live_wko_pages"]:
        raise SystemExit("Validation failed")


if __name__ == "__main__":
    main()
