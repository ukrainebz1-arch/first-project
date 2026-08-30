import csv
import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs, quote

import requests
from bs4 import BeautifulSoup

OUT_DIR = os.environ.get("OUT_DIR", "output_full")
os.makedirs(OUT_DIR, exist_ok=True)

SEARCH_TERMS = ["buchhalter", "bilanzbuchhalter"]
STATES = [
    "burgenland", "kärnten", "niederösterreich", "oberösterreich",
    "salzburg", "steiermark", "tirol", "vorarlberg", "wien",
]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def profile_id(url):
    try:
        return parse_qs(urlparse(url).query).get("firmaid", [""])[0]
    except Exception:
        return ""


def get_hidden(soup):
    out = {}
    form = soup.find("form")
    if not form:
        return out
    for inp in form.find_all("input"):
        n = inp.get("name")
        if n and inp.get("type", "").lower() == "hidden":
            out[n] = inp.get("value", "")
    return out


def extract_total(soup):
    text = norm(soup.get_text(" ", strip=True))
    m = re.search(r"Ihre Suche erzielte\s+([\d\.]+)\s+Treffer", text, re.I)
    if not m:
        m = re.search(r"([\d\.]+)\s+Unternehmen gefunden", text, re.I)
    return int(m.group(1).replace(".", "")) if m else None


def parse_cards(html, base_url, term, state):
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for article in soup.select("article.search-result-article"):
        title = article.select_one('a.title-link[href*="firmaid="]') or article.select_one('a[href*="firmaid="]')
        if not title:
            continue
        href = urljoin(base_url, title.get("href", ""))
        fid = profile_id(href)
        name = norm(title.get_text(" ", strip=True))
        if not fid:
            continue

        phones, emails, websites = [], [], []
        for a in article.find_all("a", href=True):
            h = (a.get("href") or "").strip()
            low = h.lower()
            if low.startswith("tel:"):
                p = norm(h.split(":", 1)[1])
                if p and p not in phones:
                    phones.append(p)
            elif low.startswith("mailto:"):
                e = h.split(":", 1)[1].split("?", 1)[0].strip()
                if e and e not in emails:
                    emails.append(e)
            elif low.startswith("http") or low.startswith("//"):
                absolute = urljoin(base_url, h)
                host = urlparse(absolute).netloc.lower().replace("www.", "")
                if "firmen.wko.at" in host or host.endswith("wko.at") or "google." in host or "maps." in host:
                    continue
                if absolute not in websites:
                    websites.append(absolute)

        strings = [norm(x) for x in article.stripped_strings if norm(x)]
        postal_code = city = street = ""
        pc_idx = None
        for i, s in enumerate(strings):
            m = re.match(r"^(\d{4})\s+(.+)$", s)
            if m:
                postal_code = m.group(1)
                city = norm(m.group(2))
                pc_idx = i
                break
        if pc_idx is not None and pc_idx > 0:
            candidate = strings[pc_idx - 1]
            if candidate.lower() != "route planen" and candidate != name:
                street = candidate
        address = norm(" ".join(x for x in [street, postal_code, city] if x))

        business_label = ""
        for s in strings[1:]:
            sl = s.lower()
            if s == name or sl == "route planen" or re.match(r"^\d{4}\s+", s):
                continue
            if any(e in s for e in emails) or any(p in s for p in phones):
                continue
            if any(urlparse(w).netloc.replace("www.", "") in s for w in websites if urlparse(w).netloc):
                continue
            if s == street:
                break
            # Skip obvious phone-only strings.
            if re.fullmatch(r"[+\d\s()/.-]{6,}", s):
                continue
            business_label = s
            break

        cards.append({
            "firmaid": fid,
            "company_name": name,
            "business_label": business_label,
            "street": street,
            "postal_code": postal_code,
            "city": city,
            "address": address,
            "phones": " | ".join(phones),
            "email": emails[0] if emails else "",
            "all_emails": " | ".join(emails),
            "website": websites[0] if websites else "",
            "all_websites": " | ".join(websites),
            "state": state,
            "query_term": term,
            "profile_url": href,
        })
    return cards, soup


def fetch_query(term, state):
    state_path = quote(state, safe="")
    url = f"https://firmen.wko.at/{term}/{state_path}/"
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.6"})

    r = s.get(url, timeout=60)
    r.raise_for_status()
    rows, soup = parse_cards(r.text, url, term, state)
    expected = extract_total(soup)
    seen = {x["firmaid"]: x for x in rows}
    print(f"START {term}/{state}: expected={expected} loaded={len(rows)}", flush=True)

    rounds = 0
    max_rounds = 120
    while expected is None or len(seen) < expected:
        rounds += 1
        if rounds > max_rounds:
            raise RuntimeError(f"Exceeded {max_rounds} load-more rounds for {term}/{state}; {len(seen)}/{expected}")
        payload = get_hidden(soup)
        payload["ctl00$ContentPlaceHolder1$nextPageButton"] = "Mehr laden"
        payload.setdefault("__EVENTTARGET", "")
        payload.setdefault("__EVENTARGUMENT", "")

        rr = None
        last_exc = None
        for attempt in range(1, 4):
            try:
                rr = s.post(url, data=payload, timeout=90, allow_redirects=True)
                if rr.status_code == 200 and "Error.aspx" not in rr.url:
                    break
                last_exc = RuntimeError(f"status={rr.status_code} url={rr.url}")
            except Exception as e:
                last_exc = e
            time.sleep(attempt * 1.2)
        if rr is None or rr.status_code != 200 or "Error.aspx" in rr.url:
            raise RuntimeError(f"POST failed {term}/{state} round={rounds}: {last_exc}")

        current, soup = parse_cards(rr.text, url, term, state)
        before = len(seen)
        for row in current:
            seen[row["firmaid"]] = row
        added = len(seen) - before
        if rounds % 10 == 0 or added != 10 or (expected and len(seen) >= expected):
            print(f"LOAD {term}/{state}: round={rounds} unique={len(seen)}/{expected} added={added}", flush=True)
        if added == 0:
            if expected is not None and len(seen) >= expected:
                break
            raise RuntimeError(f"No new rows before expected total for {term}/{state}: {len(seen)}/{expected}")
        time.sleep(0.08)

    rows = list(seen.values())
    print(f"DONE {term}/{state}: {len(rows)} expected={expected} rounds={rounds}", flush=True)
    return {"term": term, "state": state, "url": url, "expected": expected, "rows": rows, "rounds": rounds}


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    tasks = [(term, state) for term in SEARCH_TERMS for state in STATES]
    results, errors = [], []
    workers = int(os.environ.get("STATE_WORKERS", "4"))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_query, term, state): (term, state) for term, state in tasks}
        for fut in as_completed(futs):
            term, state = futs[fut]
            try:
                results.append(fut.result())
            except Exception as e:
                print(f"ERROR {term}/{state}: {e!r}", flush=True)
                errors.append({"query_term": term, "state": state, "error": repr(e)})

    all_rows = []
    for res in results:
        all_rows.extend(res["rows"])

    # Merge same WKO firmaid across the two search terms/states, retaining provenance.
    merged = {}
    provenance = defaultdict(lambda: {"terms": set(), "states": set()})
    for row in all_rows:
        fid = row["firmaid"]
        provenance[fid]["terms"].add(row["query_term"])
        provenance[fid]["states"].add(row["state"])
        if fid not in merged:
            merged[fid] = dict(row)
        else:
            # Fill missing contact fields from another appearance of the same profile.
            for k in ["company_name", "business_label", "street", "postal_code", "city", "address", "phones", "email", "all_emails", "website", "all_websites", "profile_url"]:
                if not merged[fid].get(k) and row.get(k):
                    merged[fid][k] = row[k]

    final = []
    for fid, row in merged.items():
        row["query_terms"] = " | ".join(sorted(provenance[fid]["terms"]))
        row["states_seen"] = " | ".join(sorted(provenance[fid]["states"]))
        row.pop("query_term", None)
        row.pop("state", None)
        final.append(row)
    final.sort(key=lambda x: (x.get("company_name", "").lower(), x.get("postal_code", ""), x.get("firmaid", "")))

    fields = [
        "firmaid", "company_name", "business_label", "street", "postal_code", "city", "address",
        "phones", "email", "all_emails", "website", "all_websites", "query_terms", "states_seen", "profile_url",
    ]
    write_csv(os.path.join(OUT_DIR, "wko_bookkeeping_austria_combined.csv"), final, fields)

    raw_fields = [
        "firmaid", "company_name", "business_label", "street", "postal_code", "city", "address",
        "phones", "email", "all_emails", "website", "all_websites", "state", "query_term", "profile_url",
    ]
    write_csv(os.path.join(OUT_DIR, "wko_bookkeeping_austria_raw_by_query_state.csv"), all_rows, raw_fields)

    for term in SEARCH_TERMS:
        subset_ids = {r["firmaid"] for r in all_rows if r["query_term"] == term}
        subset = [r for r in final if r["firmaid"] in subset_ids]
        write_csv(os.path.join(OUT_DIR, f"wko_{term}_austria.csv"), subset, fields)

    if errors:
        write_csv(os.path.join(OUT_DIR, "scrape_errors.csv"), errors, ["query_term", "state", "error"])

    query_summary = sorted([
        {"query_term": r["term"], "state": r["state"], "expected": r["expected"], "collected": len(r["rows"]), "rounds": r["rounds"], "url": r["url"]}
        for r in results
    ], key=lambda x: (x["query_term"], x["state"]))

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "queries_completed": len(results),
        "queries_expected": len(tasks),
        "query_errors": len(errors),
        "raw_query_state_rows": len(all_rows),
        "unique_wko_firmaids_combined": len(final),
        "queries": query_summary,
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("FINAL SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)

    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
