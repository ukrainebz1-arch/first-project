import asyncio
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE = "https://firmen.wko.at"
OUT = Path("spedition_output")
OUT.mkdir(exist_ok=True)

STATES = {
    "Burgenland": "burgenland",
    "Kärnten": "k%C3%A4rnten",
    "Niederösterreich": "nieder%C3%B6sterreich",
    "Oberösterreich": "ober%C3%B6sterreich",
    "Salzburg": "salzburg",
    "Steiermark": "steiermark",
    "Tirol": "tirol",
    "Vorarlberg": "vorarlberg",
    "Wien": "wien",
}


def qs_value(url, key):
    try:
        return parse_qs(urlparse(url).query).get(key, [""])[0]
    except Exception:
        return ""


def clean_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


async def dismiss_cookie(page):
    for text in ["Alle akzeptieren", "Akzeptieren", "Zustimmen", "Einverstanden", "Accept all", "Accept", "OK"]:
        try:
            loc = page.get_by_role("button", name=re.compile(f"^{re.escape(text)}$", re.I))
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=2000, force=True)
                await page.wait_for_timeout(250)
                return
        except Exception:
            pass


async def current_batch(page, state, source_url):
    data = await page.locator("article.search-result-article").evaluate_all(
        """(arts) => arts.map(a => {
          const allProfile = Array.from(a.querySelectorAll('a[href*="firmaid="]'));
          let title = a.querySelector('a.title-link[href*="firmaid="]') || allProfile[0] || null;
          if (!title) return null;
          const href = title.href || '';
          const h3 = title.querySelector('h3');
          const name = ((h3 && h3.innerText) || title.innerText || title.textContent || '').trim();
          const street = (a.querySelector('.address-container .street') || a.querySelector('.street'));
          const place = (a.querySelector('.address-container .place') || a.querySelector('.place'));
          const tels = Array.from(a.querySelectorAll('[itemprop="telephone"]')).map(x => (x.innerText || x.textContent || '').trim()).filter(Boolean);
          const emails = Array.from(a.querySelectorAll('[itemprop="email"]')).map(x => (x.innerText || x.textContent || '').trim()).filter(Boolean);
          const urls = Array.from(a.querySelectorAll('a[itemprop="url"]')).map(x => x.href || '').filter(u => u && !u.includes('firmen.wko.at'));
          return {
            href,
            company_name: name,
            street: street ? (street.innerText || street.textContent || '').trim() : '',
            place: place ? (place.innerText || place.textContent || '').trim() : '',
            phone: [...new Set(tels)].join(' | '),
            email: [...new Set(emails)].join(' | '),
            website: [...new Set(urls)].join(' | ')
          };
        }).filter(Boolean)"""
    )
    # Fallback if WKO changed the article class.
    if not data:
        data = await page.locator('a[href*="firmaid="]').evaluate_all(
            """els => els.map(a => ({href:a.href, company_name:(a.innerText || a.textContent || '').trim(), street:'', place:'', phone:'', email:'', website:''}))"""
        )

    best = {}
    for item in data:
        href = item.get("href") or ""
        fid = qs_value(href, "firmaid")
        if not href or not fid:
            continue
        sid = qs_value(href, "standortid")
        key = (fid, sid, href.split("&page=", 1)[0])
        row = {
            "bundesland": state,
            "company_name": clean_text(item.get("company_name", "")),
            "street": clean_text(item.get("street", "")),
            "place": clean_text(item.get("place", "")),
            "phone": clean_text(item.get("phone", "")),
            "email": clean_text(item.get("email", "")),
            "website": clean_text(item.get("website", "")),
            "firmaid": fid,
            "standortid": sid,
            "profile_url": href,
            "source_list_url": source_url,
        }
        old = best.get(key)
        if old is None or sum(bool(row[x]) for x in ["street","place","phone","email","website"]) > sum(bool(old[x]) for x in ["street","place","phone","email","website"]):
            best[key] = row
    return list(best.values())


async def batch_signature(page, state, source_url):
    rows = await current_batch(page, state, source_url)
    return rows, tuple(sorted((r["firmaid"], r["standortid"], r["profile_url"]) for r in rows))


async def wait_for_batch_change(page, state, source_url, before_sig, timeout_ms=30000):
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    last_rows, last_sig = [], ()
    while asyncio.get_running_loop().time() < deadline:
        await page.wait_for_timeout(250)
        last_rows, last_sig = await batch_signature(page, state, source_url)
        if last_sig and last_sig != before_sig:
            return last_rows, last_sig
    return last_rows, last_sig


async def collect_all_batches(page, state, source_url, expected):
    accumulated = {}
    batches = 0
    seen_signatures = set()

    while True:
        current, signature = await batch_signature(page, state, source_url)
        if signature in seen_signatures:
            print(f"  repeated batch detected at batch={batches+1}", flush=True)
            break
        seen_signatures.add(signature)
        batches += 1
        for r in current:
            key = (r["firmaid"], r["standortid"], r["profile_url"].split("&page=",1)[0])
            accumulated[key] = r

        n = len(accumulated)
        if batches == 1 or batches % 10 == 0 or (expected and n >= expected):
            print(f"  {state}: batches={batches}, collected={n}/{expected}", flush=True)
        if expected and n >= expected:
            break

        more = page.locator('#ctl00_ContentPlaceHolder1_nextPageButton')
        if not await more.count() or not await more.first.is_visible():
            more = page.locator('input[type="submit"][value="Mehr laden"]')
        if not await more.count() or not await more.first.is_visible():
            print(f"  no next-page submit after {n} records", flush=True)
            break

        before_sig = signature
        try:
            try:
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                    await more.first.click(timeout=8000)
            except PlaywrightTimeoutError:
                try:
                    await more.first.click(timeout=3000, force=True)
                except Exception:
                    pass
            _, after_sig = await wait_for_batch_change(page, state, source_url, before_sig, timeout_ms=20000)
            if not after_sig or after_sig == before_sig:
                print("  next-page submit did not change result batch", flush=True)
                break
        except Exception as e:
            print(f"  pagination error: {type(e).__name__}: {e}", flush=True)
            break
        await page.wait_for_timeout(120)

    return list(accumulated.values()), batches


async def scrape_state(browser, state, slug):
    url = f"{BASE}/spediteur/{slug}/"
    context = await browser.new_context(
        locale="de-AT",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 1200},
    )
    page = await context.new_page()
    print(f"STATE {state}: {url}", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await dismiss_cookie(page)
    await page.wait_for_timeout(450)

    body = clean_text(await page.locator("body").inner_text())
    m = re.search(r"Ihre Suche erzielte\s+(?:über\s+)?([\d\.]+)\s+Treffer", body, re.I)
    expected = int(m.group(1).replace(".", "")) if m else None
    print(f"  expected={expected}", flush=True)

    rows, batches = await collect_all_batches(page, state, url, expected)
    diag = {
        "bundesland": state,
        "source_url": url,
        "expected_treffer": expected,
        "extracted_rows": len(rows),
        "batches": batches,
        "count_match": (expected == len(rows)) if expected is not None else None,
    }
    print(f"  DONE {state}: {len(rows)}/{expected}, batches={batches}", flush=True)
    await context.close()
    return rows, diag


async def main():
    all_rows, diagnostics = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for state, slug in STATES.items():
            rows, diag = await scrape_state(browser, state, slug)
            all_rows.extend(rows)
            diagnostics.append(diag)
        await browser.close()

    # Exact location rows from the WKO result sets, deduplicated only within identical WKO location references.
    loc = {}
    for r in all_rows:
        key = (r["firmaid"], r["standortid"], r["profile_url"].split("&page=",1)[0], r["bundesland"])
        old = loc.get(key)
        if old is None or sum(bool(r[x]) for x in ["street","place","phone","email","website"]) > sum(bool(old[x]) for x in ["street","place","phone","email","website"]):
            loc[key] = r
    all_rows = list(loc.values())
    all_rows.sort(key=lambda x: (x["bundesland"], x["company_name"].casefold(), x["place"].casefold()))

    raw_fields = ["bundesland","company_name","street","place","phone","email","website","firmaid","standortid","profile_url","source_list_url"]
    with (OUT / "spediteur_standorte.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=raw_fields); w.writeheader(); w.writerows(all_rows)

    grouped = {}
    for r in all_rows:
        key = r["firmaid"] or r["profile_url"]
        g = grouped.setdefault(key, {
            "company_name": r["company_name"], "firmaid": r["firmaid"],
            "bundeslaender": set(), "standort_count": 0,
            "street": r["street"], "place": r["place"], "phone": r["phone"],
            "email": r["email"], "website": r["website"], "profile_url": r["profile_url"]
        })
        g["bundeslaender"].add(r["bundesland"])
        g["standort_count"] += 1
        if len(r["company_name"]) > len(g["company_name"]): g["company_name"] = r["company_name"]
        for field in ["street","place","phone","email","website"]:
            if not g[field] and r[field]: g[field] = r[field]

    unique = [{
        "company_name": g["company_name"], "firmaid": g["firmaid"],
        "bundeslaender": "; ".join(sorted(g["bundeslaender"])),
        "standort_count": g["standort_count"], "street": g["street"], "place": g["place"],
        "phone": g["phone"], "email": g["email"], "website": g["website"], "profile_url": g["profile_url"]
    } for g in grouped.values()]
    unique.sort(key=lambda x: x["company_name"].casefold())

    unique_fields = ["company_name","firmaid","bundeslaender","standort_count","street","place","phone","email","website","profile_url"]
    with (OUT / "spediteur_unique_companies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=unique_fields); w.writeheader(); w.writerows(unique)

    summary = {
        "wko_query": "Spediteur",
        "raw_standort_rows": len(all_rows),
        "unique_firmaids": len(unique),
        "expected_total_from_wko_pages": sum(d["expected_treffer"] or 0 for d in diagnostics),
        "all_state_counts_match": all(d["count_match"] for d in diagnostics if d["expected_treffer"] is not None),
        "states": diagnostics,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    mismatches = [d for d in diagnostics if d["expected_treffer"] is None or not d["count_match"]]
    if mismatches:
        raise SystemExit(f"WKO count mismatch in {len(mismatches)} state(s): {mismatches}")


if __name__ == "__main__":
    asyncio.run(main())
