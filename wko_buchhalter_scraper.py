import csv
import json
import os
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

SEARCHES = {
    "buchhalter": "https://firmen.wko.at/buchhalter/",
    "bilanzbuchhalter": "https://firmen.wko.at/bilanzbuchhalter/",
}

OUT_DIR = os.environ.get("OUT_DIR", "output")
os.makedirs(OUT_DIR, exist_ok=True)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)


def normalize_space(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def firmaid_from_url(url):
    try:
        return parse_qs(urlparse(url).query).get("firmaid", [""])[0]
    except Exception:
        return ""


def load_all_profile_links(page, label, url):
    print(f"\n=== Loading {label}: {url} ===", flush=True)
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(2500)

    # Dismiss common consent overlays if present.
    for txt in ["Alle akzeptieren", "Akzeptieren", "Zustimmen"]:
        try:
            loc = page.get_by_text(txt, exact=False)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=2000)
                page.wait_for_timeout(500)
                break
        except Exception:
            pass

    stable = 0
    previous = -1
    max_rounds = 600

    for round_no in range(1, max_rounds + 1):
        count = page.locator('a[href*="firmaid="]').count()
        if count != previous:
            print(f"[{label}] round {round_no}: {count} profile links currently in DOM", flush=True)
            previous = count

        clicked = False
        # WKO currently uses “Mehr laden”; keep fallbacks for wording changes.
        candidates = [
            "button:has-text('Mehr laden')",
            "a:has-text('Mehr laden')",
            "button:has-text('Weitere')",
            "a:has-text('Weitere')",
        ]
        for selector in candidates:
            try:
                loc = page.locator(selector)
                for i in range(loc.count()):
                    el = loc.nth(i)
                    if el.is_visible():
                        el.scroll_into_view_if_needed(timeout=3000)
                        el.click(timeout=5000, force=True)
                        clicked = True
                        page.wait_for_timeout(1200)
                        break
                if clicked:
                    break
            except Exception:
                pass

        if not clicked:
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            page.wait_for_timeout(1000)

        new_count = page.locator('a[href*="firmaid="]').count()
        if new_count <= count:
            stable += 1
        else:
            stable = 0

        # Give the page several chances to reveal the next load-more button.
        if stable >= 7:
            print(f"[{label}] stable after {round_no} rounds at {new_count} links", flush=True)
            break

    links = {}
    anchors = page.locator('a[href*="firmaid="]')
    for i in range(anchors.count()):
        try:
            a = anchors.nth(i)
            href = a.get_attribute("href") or ""
            if not href:
                continue
            absolute = urljoin(url, href)
            if "firmen.wko.at" not in absolute or not firmaid_from_url(absolute):
                continue
            fid = firmaid_from_url(absolute)
            name_hint = normalize_space(a.inner_text(timeout=1000))
            links[fid] = {"firmaid": fid, "profile_url": absolute, "name_hint": name_hint}
        except Exception:
            continue

    print(f"[{label}] extracted {len(links)} unique firmaids", flush=True)
    return links


def extract_address(text):
    # Extract the first public contact address from the contact section.
    m = re.search(
        r"Adresse:\s*(.*?)\s*(?:Öffnungszeiten:|Über uns|Produkte und Leistungen|Firmendaten|$)",
        text,
        flags=re.I | re.S,
    )
    if not m:
        return ""
    addr = normalize_space(m.group(1))
    # Drop map CTA if captured.
    addr = re.sub(r"\s*Route planen.*$", "", addr, flags=re.I)
    return addr[:500]


def split_address(address):
    # Best-effort Austrian postal-code split.
    postal_code = ""
    city = ""
    street = ""
    m = re.search(r"\b(\d{4})\s+([^,]+)$", address)
    if m:
        postal_code = m.group(1)
        city = normalize_space(m.group(2))
        street = normalize_space(address[: m.start()])
    return street, postal_code, city


def scrape_profile(item, timeout=40):
    url = item["profile_url"]
    headers = {"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.6"}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    flat = normalize_space(text)

    h1 = soup.find("h1")
    company_name = normalize_space(h1.get_text(" ", strip=True) if h1 else item.get("name_hint", ""))

    emails = []
    phones = []
    websites = []
    social = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        low = href.lower()
        if low.startswith("mailto:"):
            val = href.split(":", 1)[1].split("?", 1)[0].strip()
            if val and val not in emails:
                emails.append(val)
        elif low.startswith("tel:"):
            val = normalize_space(href.split(":", 1)[1])
            if val and val not in phones:
                phones.append(val)
        elif low.startswith("http"):
            host = urlparse(href).netloc.lower().replace("www.", "")
            if "firmen.wko.at" in host or host.endswith("wko.at") or "google." in host:
                continue
            if any(x in host for x in ["facebook.com", "instagram.com", "linkedin.com", "youtube.com", "x.com", "twitter.com"]):
                if href not in social:
                    social.append(href)
            elif href not in websites:
                websites.append(href)

    address = extract_address(flat)
    street, postal_code, city = split_address(address)

    gln = ""
    gln_m = re.search(r"GLN\s*\(der öffentlichen Verwaltung\)\s*:?\s*(\d{10,15})", flat, flags=re.I)
    if gln_m:
        gln = gln_m.group(1)

    business_label = ""
    # Usually the line/text immediately following the H1 is the business designation.
    if h1:
        nxt = h1.find_next()
        seen = 0
        while nxt is not None and seen < 8:
            if nxt.name not in ["h1", "script", "style"]:
                t = normalize_space(nxt.get_text(" ", strip=True))
                if t and t != company_name and len(t) < 220:
                    business_label = t
                    break
            nxt = nxt.find_next()
            seen += 1

    # Authorization/category clues useful for later filtering.
    authorizations = []
    for term in ["Bilanzbuchhalter", "Buchhalter", "Personalverrechner"]:
        if re.search(rf"\b{re.escape(term)}\b", flat, flags=re.I):
            authorizations.append(term)

    return {
        "firmaid": item["firmaid"],
        "company_name": company_name,
        "business_label": business_label,
        "address": address,
        "street": street,
        "postal_code": postal_code,
        "city": city,
        "phones": " | ".join(phones),
        "email": emails[0] if emails else "",
        "all_emails": " | ".join(emails),
        "website": websites[0] if websites else "",
        "all_websites": " | ".join(websites),
        "social_links": " | ".join(social),
        "gln": gln,
        "wko_authorization_terms": " | ".join(authorizations),
        "profile_url": url,
        "http_status": r.status_code,
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    by_firmaid = {}
    sources = defaultdict(set)
    counts = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, locale="de-AT", viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(10_000)

        for label, url in SEARCHES.items():
            found = load_all_profile_links(page, label, url)
            counts[label] = len(found)
            for fid, item in found.items():
                by_firmaid.setdefault(fid, item)
                sources[fid].add(label)

        browser.close()

    items = list(by_firmaid.values())
    print(f"\nCombined unique WKO firmaids: {len(items)}", flush=True)

    rows = []
    errors = []
    max_workers = int(os.environ.get("PROFILE_WORKERS", "5"))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(scrape_profile, item): item for item in items}
        total = len(futs)
        done = 0
        for fut in as_completed(futs):
            item = futs[fut]
            done += 1
            try:
                row = fut.result()
                row["query_sources"] = " | ".join(sorted(sources[item["firmaid"]]))
                rows.append(row)
            except Exception as e:
                errors.append({
                    "firmaid": item.get("firmaid", ""),
                    "profile_url": item.get("profile_url", ""),
                    "error": repr(e),
                })
            if done % 50 == 0 or done == total:
                print(f"Profiles processed: {done}/{total}; errors={len(errors)}", flush=True)

    rows.sort(key=lambda r: (r.get("company_name", "").lower(), r.get("postal_code", ""), r.get("firmaid", "")))

    fields = [
        "firmaid", "company_name", "business_label", "address", "street", "postal_code", "city",
        "phones", "email", "all_emails", "website", "all_websites", "social_links", "gln",
        "wko_authorization_terms", "query_sources", "profile_url", "http_status", "scraped_at_utc",
    ]
    write_csv(os.path.join(OUT_DIR, "wko_buchhalter_austria_combined.csv"), rows, fields)

    # Per-query CSVs from the combined enrichment.
    for label in SEARCHES:
        subset = [r for r in rows if label in (r.get("query_sources") or "").split(" | ")]
        write_csv(os.path.join(OUT_DIR, f"wko_{label}_austria.csv"), subset, fields)

    if errors:
        write_csv(os.path.join(OUT_DIR, "scrape_errors.csv"), errors, ["firmaid", "profile_url", "error"])

    summary = {
        "search_counts": counts,
        "combined_unique_firmaids": len(items),
        "successfully_enriched": len(rows),
        "profile_errors": len(errors),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "search_urls": SEARCHES,
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
