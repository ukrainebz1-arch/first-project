import asyncio
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

BASE = "https://firmen.wko.at"
OUT = Path("output")
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


async def result_links(page):
    data = await page.locator('a[href*="firmaid="]').evaluate_all(
        """els => els.map(a => ({href: a.href, text: (a.innerText || a.textContent || '').trim()}))"""
    )
    # WKO can render more than one anchor for the same profile. Keep the most
    # informative label rather than whichever duplicate happens to appear first.
    best = {}
    for item in data:
        href = item.get("href") or ""
        if not href or not qs_value(href, "firmaid"):
            continue
        text = clean_text(item.get("text", ""))
        old = best.get(href)
        if old is None or len(text) > len(old["text"]):
            best[href] = {"href": href, "text": text}
    return list(best.values())


async def wait_for_batch_change(page, before_hrefs, timeout_ms=30000):
    deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        await page.wait_for_timeout(200)
        current = {x["href"] for x in await result_links(page)}
        if current and current != before_hrefs:
            return current
    return {x["href"] for x in await result_links(page)}


async def collect_all_batches(page, state, expected):
    accumulated = {}
    batches = 0
    seen_batch_signatures = set()

    while True:
        current = await result_links(page)
        hrefs = {x["href"] for x in current}
        signature = tuple(sorted(hrefs))
        if signature in seen_batch_signatures:
            print(f"  repeated batch detected at batch={batches+1}", flush=True)
            break
        seen_batch_signatures.add(signature)
        batches += 1
        for item in current:
            old = accumulated.get(item["href"])
            if old is None or len(item["text"]) > len(old["text"]):
                accumulated[item["href"]] = item

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

        before = hrefs
        try:
            # This is an ASP.NET form postback to the same URL. Depending on the
            # WKO response it may register as navigation or only as a document
            # replacement, so tolerate expect_navigation timeout and verify the
            # actual result set afterwards.
            try:
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                    await more.first.click(timeout=8000)
            except PlaywrightTimeoutError:
                try:
                    await more.first.click(timeout=3000, force=True)
                except Exception:
                    pass
            after = await wait_for_batch_change(page, before, timeout_ms=20000)
            if not after or after == before:
                print(f"  next-page submit did not change result batch", flush=True)
                break
        except Exception as e:
            print(f"  pagination error: {type(e).__name__}: {e}", flush=True)
            break

        await page.wait_for_timeout(100)

    return list(accumulated.values()), batches


async def scrape_state(browser, state, slug):
    url = f"{BASE}/immobilienverwalter/{slug}/"
    context = await browser.new_context(
        locale="de-AT",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 1200},
    )
    page = await context.new_page()
    print(f"STATE {state}: {url}", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await dismiss_cookie(page)
    await page.wait_for_timeout(400)

    body = clean_text(await page.locator("body").inner_text())
    m = re.search(r"Ihre Suche erzielte\s+(?:über\s+)?([\d\.]+)\s+Treffer", body, re.I)
    expected = int(m.group(1).replace(".", "")) if m else None
    print(f"  expected={expected}", flush=True)

    links, batches = await collect_all_batches(page, state, expected)
    rows = []
    for item in links:
        href = item["href"]
        rows.append({
            "bundesland": state,
            "company_name": item["text"],
            "firmaid": qs_value(href, "firmaid"),
            "standortid": qs_value(href, "standortid"),
            "profile_url": href,
            "source_list_url": url,
        })

    diag = {
        "bundesland": state,
        "source_url": url,
        "expected_treffer": expected,
        "extracted_profile_urls": len(rows),
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

    raw_fields = ["bundesland", "company_name", "firmaid", "standortid", "profile_url", "source_list_url"]
    with (OUT / "immobilienverwalter_standorte.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=raw_fields)
        w.writeheader(); w.writerows(all_rows)

    grouped = {}
    for r in all_rows:
        key = r["firmaid"] or r["profile_url"]
        g = grouped.setdefault(key, {
            "company_name": r["company_name"], "firmaid": r["firmaid"],
            "bundeslaender": set(), "standort_count": 0, "profile_url": r["profile_url"]
        })
        g["bundeslaender"].add(r["bundesland"])
        g["standort_count"] += 1
        if len(r["company_name"]) > len(g["company_name"]):
            g["company_name"] = r["company_name"]

    unique = [{
        "company_name": g["company_name"], "firmaid": g["firmaid"],
        "bundeslaender": "; ".join(sorted(g["bundeslaender"])),
        "standort_count": g["standort_count"], "profile_url": g["profile_url"]
    } for g in grouped.values()]
    unique.sort(key=lambda x: x["company_name"].casefold())

    with (OUT / "immobilienverwalter_unique_companies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["company_name", "firmaid", "bundeslaender", "standort_count", "profile_url"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(unique)

    summary = {"raw_standort_rows": len(all_rows), "unique_firmaids": len(unique), "states": diagnostics}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    mismatches = [d for d in diagnostics if d["expected_treffer"] is not None and not d["count_match"]]
    if mismatches:
        raise SystemExit(f"Count mismatch in {len(mismatches)} state(s): {mismatches}")


if __name__ == "__main__":
    asyncio.run(main())
