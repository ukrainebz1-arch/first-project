import csv
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, quote, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

TERM = os.environ["TERM_NAME"]
STATE = os.environ["STATE_NAME"]
STATE_SLUG = os.environ.get("STATE_SLUG", STATE)
OUT_DIR = os.environ.get("OUT_DIR", "part")
os.makedirs(OUT_DIR, exist_ok=True)

EXPECTED_REFERENCE = {
    ("buchhalter", "burgenland"): 119,
    ("buchhalter", "kärnten"): 252,
    ("buchhalter", "niederösterreich"): 865,
    ("buchhalter", "oberösterreich"): 622,
    ("buchhalter", "salzburg"): 310,
    ("buchhalter", "steiermark"): 581,
    ("buchhalter", "tirol"): 482,
    ("buchhalter", "vorarlberg"): 240,
    ("buchhalter", "wien"): 828,
    ("bilanzbuchhalter", "burgenland"): 85,
    ("bilanzbuchhalter", "kärnten"): 169,
    ("bilanzbuchhalter", "niederösterreich"): 625,
    ("bilanzbuchhalter", "oberösterreich"): 457,
    ("bilanzbuchhalter", "salzburg"): 229,
    ("bilanzbuchhalter", "steiermark"): 387,
    ("bilanzbuchhalter", "tirol"): 335,
    ("bilanzbuchhalter", "vorarlberg"): 175,
    ("bilanzbuchhalter", "wien"): 621,
}


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def firmaid(url):
    try:
        return parse_qs(urlparse(url).query).get("firmaid", [""])[0]
    except Exception:
        return ""


def extract_total(html):
    soup = BeautifulSoup(html, "html.parser")
    text = norm(soup.get_text(" ", strip=True))
    for pat in [r"Ihre Suche erzielte\s+([\d\.]+)\s+Treffer", r"([\d\.]+)\s+Unternehmen gefunden"]:
        m = re.search(pat, text, re.I)
        if m:
            return int(m.group(1).replace(".", ""))
    return None


def parse_cards(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for article in soup.select("article.search-result-article"):
        title = article.select_one('a.title-link[href*="firmaid="]') or article.select_one('a[href*="firmaid="]')
        if not title:
            continue
        href = urljoin(base_url, title.get("href", ""))
        fid = firmaid(href)
        if not fid:
            continue
        name = norm(title.get_text(" ", strip=True))

        phones, emails, websites = [], [], []
        for a in article.find_all("a", href=True):
            h = (a.get("href") or "").strip()
            low = h.lower()
            if low.startswith("tel:"):
                v = norm(h.split(":", 1)[1])
                if v and v not in phones:
                    phones.append(v)
            elif low.startswith("mailto:"):
                v = h.split(":", 1)[1].split("?", 1)[0].strip()
                if v and v not in emails:
                    emails.append(v)
            elif low.startswith("http") or low.startswith("//"):
                absolute = urljoin(base_url, h)
                host = urlparse(absolute).netloc.lower().replace("www.", "")
                if "firmen.wko.at" in host or host.endswith("wko.at") or "google." in host or "maps." in host:
                    continue
                if absolute not in websites:
                    websites.append(absolute)

        strings = [norm(x) for x in article.stripped_strings if norm(x)]
        street = postal_code = city = ""
        pc_idx = None
        for i, s in enumerate(strings):
            m = re.match(r"^(\d{4})\s+(.+)$", s)
            if m:
                postal_code, city, pc_idx = m.group(1), norm(m.group(2)), i
                break
        if pc_idx is not None and pc_idx > 0:
            candidate = strings[pc_idx - 1]
            if candidate.lower() != "route planen" and candidate != name:
                street = candidate
        address = norm(" ".join(x for x in [street, postal_code, city] if x))

        business_label = ""
        for s in strings[1:]:
            if s == name or s == street or s.lower() == "route planen" or re.match(r"^\d{4}\s+", s):
                continue
            if s in emails or s in phones or re.fullmatch(r"[+\d\s()/.-]{6,}", s):
                continue
            business_label = s
            break

        rows.append({
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
            "state": STATE,
            "query_term": TERM,
            "profile_url": href,
        })
    return rows


SUBMIT_JS = """
() => {
  const f = document.querySelector('form');
  if (!f) throw new Error('form not found');
  const prev = f.querySelector('input[data-oai-next="1"]');
  if (prev) prev.remove();
  const x = document.createElement('input');
  x.type = 'hidden';
  x.name = 'ctl00$ContentPlaceHolder1$nextPageButton';
  x.value = 'Mehr laden';
  x.setAttribute('data-oai-next', '1');
  f.appendChild(x);
  f.submit();
}
"""


def collect_once(attempt_no):
    url = f"https://firmen.wko.at/{TERM}/{quote(STATE, safe='')}/"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            locale="de-AT",
            timezone_id="Europe/Vienna",
            viewport={"width": 1440, "height": 1000},
            extra_http_headers={"Accept-Language": "de-AT,de;q=0.9,en;q=0.6"},
        )
        page = context.new_page()
        page.set_default_timeout(20_000)
        print(f"OPEN {TERM}/{STATE} attempt={attempt_no} {url}", flush=True)
        response = page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        if response is None or response.status >= 400:
            raise RuntimeError(f"initial status={None if response is None else response.status}")
        page.wait_for_timeout(1200)

        first_html = page.content()
        expected = extract_total(first_html)
        reference = EXPECTED_REFERENCE.get((TERM, STATE))
        if expected is None:
            raise RuntimeError("could not parse WKO total")
        print(f"TOTAL {TERM}/{STATE}: live={expected} reference={reference}", flush=True)

        seen = {}
        rounds = 0
        no_growth = 0
        while len(seen) < expected:
            html = page.content()
            if "Error.aspx" in page.url:
                raise RuntimeError(f"WKO Error.aspx at round {rounds}")
            current = parse_cards(html, url)
            before = len(seen)
            for row in current:
                seen[row["firmaid"]] = row
            added = len(seen) - before
            if rounds == 0 or rounds % 10 == 0 or added != 10 or len(seen) >= expected:
                print(f"PAGE {TERM}/{STATE}: round={rounds} dom_cards={len(current)} unique={len(seen)}/{expected} added={added}", flush=True)

            if len(seen) >= expected:
                break
            if added == 0:
                no_growth += 1
            else:
                no_growth = 0
            if no_growth >= 2:
                raise RuntimeError(f"no growth at {len(seen)}/{expected}")

            rounds += 1
            if rounds > 120:
                raise RuntimeError(f"too many rounds {rounds}")

            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=90_000):
                    page.evaluate(SUBMIT_JS)
            except PlaywrightTimeoutError:
                if "Error.aspx" in page.url:
                    raise RuntimeError(f"navigation to Error.aspx after round {rounds}")
                page.wait_for_load_state("domcontentloaded", timeout=30_000)
            page.wait_for_timeout(random.randint(650, 1100))

        browser.close()
        rows = list(seen.values())
        if len(rows) != expected:
            raise RuntimeError(f"collected {len(rows)} but WKO says {expected}")
        return rows, expected, rounds, reference, url


def main():
    last_error = None
    for attempt in range(1, 4):
        try:
            rows, expected, rounds, reference, url = collect_once(attempt)
            break
        except Exception as e:
            last_error = repr(e)
            print(f"ATTEMPT FAILED {TERM}/{STATE}: {last_error}", flush=True)
            time.sleep(attempt * 3)
    else:
        raise RuntimeError(f"all attempts failed for {TERM}/{STATE}: {last_error}")

    fields = [
        "firmaid", "company_name", "business_label", "street", "postal_code", "city", "address",
        "phones", "email", "all_emails", "website", "all_websites", "state", "query_term", "profile_url",
    ]
    csv_path = os.path.join(OUT_DIR, f"{TERM}_{STATE_SLUG}_part.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda x: (x["company_name"].lower(), x["firmaid"])))

    summary = {
        "query_term": TERM,
        "state": STATE,
        "state_slug": STATE_SLUG,
        "url": url,
        "wko_live_total": expected,
        "reference_total_2026_08_30": reference,
        "collected": len(rows),
        "rounds": rounds,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with open(os.path.join(OUT_DIR, f"{TERM}_{STATE_SLUG}_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("SUCCESS", json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
