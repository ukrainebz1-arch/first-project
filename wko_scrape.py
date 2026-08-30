import csv
import json
import re
import sys
import time
from collections import OrderedDict
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

BASE = "https://firmen.wko.at"
LIST_URL = BASE + "/-/?branche=47627&branchenname=spedition+und+logistik+%28gesamt%29&categoryid=0&firma=&standortid=0&page={page}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36"

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9,en;q=0.7"})


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def firma_id(url):
    q = parse_qs(urlparse(url).query)
    return (q.get("firmaid") or q.get("FirmaID") or [""])[0]


def parse_listing(html, page):
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.search-result-article")
    out = []
    for a in articles:
        title = a.select_one("a.title-link")
        if not title:
            continue
        href = urljoin(BASE, title.get("href", ""))
        name_node = title.select_one("h3") or title
        name = clean(name_node.get_text(" ", strip=True))
        street = clean((a.select_one(".address-container .street") or BeautifulSoup("", "html.parser")).get_text(" ", strip=True))
        place = clean((a.select_one(".address-container .place") or BeautifulSoup("", "html.parser")).get_text(" ", strip=True))
        phone_node = a.select_one('[itemprop="telephone"]')
        email_node = a.select_one('[itemprop="email"]')
        web_node = a.select_one('[itemprop="url"]')
        out.append({
            "listing_page": page,
            "company_name_listing": name,
            "listing_street": street,
            "listing_place": place,
            "listing_phone": clean(phone_node.get_text(" ", strip=True)) if phone_node else "",
            "listing_email": clean(email_node.get_text(" ", strip=True)) if email_node else "",
            "listing_website": web_node.get("href", "") if web_node else "",
            "source_url": href,
            "firma_id": firma_id(href),
        })
    # fallback for changed markup
    if not out:
        for title in soup.select("a.title-link"):
            href = urljoin(BASE, title.get("href", ""))
            name = clean(title.get_text(" ", strip=True))
            if name:
                out.append({"listing_page": page, "company_name_listing": name, "listing_street": "", "listing_place": "", "listing_phone": "", "listing_email": "", "listing_website": "", "source_url": href, "firma_id": firma_id(href)})
    return out


def extract_field(text, label):
    m = re.search(rf"{re.escape(label)}\s*:?\s*(.+?)(?=\n(?:[A-ZÄÖÜ][^\n]{{0,60}}:?\s*)\n|\Z)", text, flags=re.I|re.S)
    return clean(m.group(1)) if m else ""


def profile_details(html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    name = ""
    h1 = soup.find("h1")
    if h1:
        name = clean(h1.get_text(" ", strip=True))
    # company-level identifiers
    fn = ""
    m = re.search(r"Firmenbuchnummer:\s*([^\n]+)", text, re.I)
    if m: fn = clean(m.group(1))
    gln = ""
    m = re.search(r"GLN(?: \(der öffentlichen Verwaltung\))?:\s*([0-9]{8,})", text, re.I)
    if m: gln = m.group(1)
    # contacts: prefer explicit page contact blocks / mailto/tel links
    emails = []
    phones = []
    websites = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith("mailto:"):
            emails.append(href.split(":",1)[1].split("?",1)[0])
        elif href.lower().startswith("tel:"):
            phones.append(href.split(":",1)[1])
        elif href.startswith("http") and "firmen.wko.at" not in href and "wko.at" not in href and "google." not in href:
            websites.append(href)
    emails = list(OrderedDict.fromkeys(filter(None, emails)))
    phones = list(OrderedDict.fromkeys(filter(None, phones)))
    websites = list(OrderedDict.fromkeys(filter(None, websites)))

    # Split permission blocks. We only keep blocks explicitly saying Berufszweig = Spedition.
    memberships = []
    parts = re.split(r"(?=FG\s+Spedition\s+und\s+Logistik)", text, flags=re.I)
    for part in parts:
        if not re.search(r"FG\s+Spedition\s+und\s+Logistik", part, re.I):
            continue
        # Bound the block at the next organization heading if possible
        block = re.split(r"\n(?:FG|FV|LG|BG|LI|BI)\s+", part[len("FG Spedition und Logistik"):], maxsplit=1, flags=re.I)[0]
        if not re.search(r"Berufszweig\s*\n?\s*Spedition(?:\s|$)", block, re.I):
            continue
        gisa = ""
        mm = re.search(r"GISA-Zahl:?\s*\n?\s*([^\n]*)", block, re.I)
        if mm: gisa = clean(mm.group(1))
        manager = ""
        mm = re.search(r"Gewerberechtliche Geschäftsführung:?\s*\n?\s*([^\n]+)", block, re.I)
        if mm: manager = clean(mm.group(1))
        address = ""
        # take Address after Berufszweig label, which belongs to this permission
        mm = re.search(r"Berufszweig\s*\n?\s*Spedition.*?Adresse\s*\n?\s*([^\n]+)", block, re.I|re.S)
        if mm: address = clean(mm.group(1))
        since = ""
        mm = re.search(r"Datum\s*\n?\s*Seit\s+([^\n]+)", block, re.I)
        if mm: since = clean(mm.group(1))
        wording = ""
        mm = re.search(r"Gewerbewortlaut\s*\n?\s*(.+?)(?=\nGewerberechtliche Geschäftsführung|\nGISA-Zahl|\nBerufszweig)", block, re.I|re.S)
        if mm: wording = clean(mm.group(1))
        memberships.append({"gisa": gisa, "manager": manager, "address": address, "since": since, "wording": wording})

    # simpler fallback if heading parsing changed but exact signal exists
    has_spedition = bool(memberships) or bool(re.search(r"Berufszweig\s*\n?\s*Spedition(?:\s|$)", text, re.I))
    return {
        "company_name": name,
        "firmenbuchnummer": fn,
        "gln": gln,
        "phones": phones,
        "emails": emails,
        "websites": websites,
        "memberships": memberships,
        "has_spedition": has_spedition,
        "profile_text_sample": text[:1500],
        "source_url": source_url,
    }


def fetch(url, tries=4):
    last = None
    for i in range(tries):
        try:
            r = session.get(url, timeout=35)
            if r.status_code == 200 and len(r.text) > 500:
                return r
            last = RuntimeError(f"HTTP {r.status_code}, len={len(r.text)}")
        except Exception as e:
            last = e
        time.sleep(1.5 * (i+1))
    raise last


def main():
    max_pages = int(sys.argv[1]) if len(sys.argv) > 1 else 260
    listing_rows = []
    seen_page_signatures = set()
    consecutive_empty = 0
    for page in range(1, max_pages+1):
        url = LIST_URL.format(page=page)
        try:
            r = fetch(url)
            rows = parse_listing(r.text, page)
        except Exception as e:
            print(f"LIST ERROR page={page}: {e}", flush=True)
            consecutive_empty += 1
            if consecutive_empty >= 3:
                break
            continue
        sig = tuple(x["source_url"] for x in rows)
        print(f"LIST page={page} rows={len(rows)} sig={sig[:2]}", flush=True)
        if not rows:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
            continue
        consecutive_empty = 0
        if sig in seen_page_signatures:
            print(f"STOP repeated page signature at page {page}", flush=True)
            break
        seen_page_signatures.add(sig)
        listing_rows.extend(rows)
        time.sleep(0.25)

    # Unique profiles by firma_id/url
    profiles = OrderedDict()
    for row in listing_rows:
        key = row["firma_id"] or row["source_url"].split("&page=",1)[0]
        profiles.setdefault(key, row)
    print(f"LIST TOTAL rows={len(listing_rows)} unique_profiles={len(profiles)}", flush=True)

    company_rows = []
    membership_rows = []
    for idx, (key, listing) in enumerate(profiles.items(), 1):
        url = listing["source_url"]
        try:
            r = fetch(url)
            d = profile_details(r.text, url)
        except Exception as e:
            print(f"PROFILE ERROR {idx}/{len(profiles)} {url}: {e}", flush=True)
            continue
        if not d["has_spedition"]:
            if idx % 50 == 0:
                print(f"PROFILE {idx}/{len(profiles)} not Spedition", flush=True)
            time.sleep(0.15)
            continue
        cname = d["company_name"] or listing["company_name_listing"]
        company_rows.append({
            "firma_id": listing["firma_id"],
            "company_name": cname,
            "firmenbuchnummer": d["firmenbuchnummer"],
            "gln": d["gln"],
            "phone": " | ".join(d["phones"]) or listing["listing_phone"],
            "email": " | ".join(d["emails"]) or listing["listing_email"],
            "website": " | ".join(d["websites"]) or listing["listing_website"],
            "listing_street": listing["listing_street"],
            "listing_place": listing["listing_place"],
            "source_url": url,
            "listing_page_first_seen": listing["listing_page"],
            "spedition_memberships_parsed": len(d["memberships"]),
        })
        for m in d["memberships"]:
            membership_rows.append({
                "firma_id": listing["firma_id"],
                "company_name": cname,
                "gisa": m["gisa"],
                "manager": m["manager"],
                "address": m["address"],
                "since": m["since"],
                "wording": m["wording"],
                "source_url": url,
            })
        if idx % 25 == 0:
            print(f"PROFILE {idx}/{len(profiles)} kept_companies={len(company_rows)} memberships={len(membership_rows)}", flush=True)
        time.sleep(0.15)

    # Deduplicate parsed memberships
    dedup_memberships = OrderedDict()
    for m in membership_rows:
        mk = (m["firma_id"], m["gisa"], m["address"], m["wording"])
        dedup_memberships.setdefault(mk, m)
    membership_rows = list(dedup_memberships.values())

    # Write output
    with open("wko_spedition_companies.csv", "w", newline="", encoding="utf-8-sig") as f:
        fields = list(company_rows[0].keys()) if company_rows else ["firma_id","company_name","firmenbuchnummer","gln","phone","email","website","listing_street","listing_place","source_url","listing_page_first_seen","spedition_memberships_parsed"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(company_rows)
    with open("wko_spedition_memberships.csv", "w", newline="", encoding="utf-8-sig") as f:
        fields = list(membership_rows[0].keys()) if membership_rows else ["firma_id","company_name","gisa","manager","address","since","wording","source_url"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(membership_rows)
    with open("wko_listing_raw.csv", "w", newline="", encoding="utf-8-sig") as f:
        fields = list(listing_rows[0].keys()) if listing_rows else ["listing_page","company_name_listing","listing_street","listing_place","listing_phone","listing_email","listing_website","source_url","firma_id"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(listing_rows)
    summary = {
        "parent_listing_rows": len(listing_rows),
        "unique_parent_profiles": len(profiles),
        "unique_companies_with_spedition": len(company_rows),
        "parsed_spedition_memberships": len(membership_rows),
        "parent_branch_id": 47627,
        "filter": "profile contains Berufszweig Spedition",
    }
    with open("summary.json", "w", encoding="utf-8") as f: json.dump(summary, f, ensure_ascii=False, indent=2)
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
