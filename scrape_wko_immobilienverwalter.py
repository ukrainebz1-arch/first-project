import asyncio
import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright

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
                return
        except Exception:
            pass


async def result_links(page):
    data = await page.locator('a[href*="firmaid="]').evaluate_all(
        """els => els.map(a => ({href:a.href, text:(a.innerText||a.textContent||'').trim()}))"""
    )
    best = {}
    for item in data:
        href = item.get("href") or ""
        if not href or not qs_value(href, "firmaid"):
            continue
        text = clean_text(item.get("text", ""))
        if href not in best or len(text) > len(best[href]["text"]):
            best[href] = {"href": href, "text": text}
    return list(best.values())


async def wait_for_changed_batch(page, before, timeout_s=20):
    end = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < end:
        current = await result_links(page)
        sig = {x["href"] for x in current}
        if sig and sig != before:
            return current
        await page.wait_for_timeout(150)
    return await result_links(page)


async def collect_all_batches(page, state, expected):
    accumulated = {}
    seen_signatures = set()
    batch_no = 0
    while True:
        current = await result_links(page)
        sig = {x["href"] for x in current}
        signature = tuple(sorted(sig))
        if not sig or signature in seen_signatures:
            print(f"  {state}: empty/repeated batch, stopping", flush=True)
            break
        seen_signatures.add(signature)
        batch_no += 1
        for item in current:
            old = accumulated.get(item["href"])
            if old is None or len(item["text"]) > len(old["text"]):
                accumulated[item["href"]] = item

        n = len(accumulated)
        if batch_no == 1 or batch_no % 10 == 0 or (expected and n >= expected):
            print(f"  {state}: batch={batch_no}, collected={n}/{expected}", flush=True)
        if expected and n >= expected:
            break

        more = page.locator('#ctl00_ContentPlaceHolder1_nextPageButton')
        if not await more.count() or not await more.first.is_visible():
            print(f"  {state}: no Mehr laden after {n}", flush=True)
            break

        try:
            # input[type=submit] causes an ASP.NET postback. Playwright click waits
            # for the navigation it starts; afterwards verify the 10-result batch changed.
            await more.first.click(timeout=20000)
            nxt = await wait_for_changed_batch(page, sig, timeout_s=20)
            nxt_sig = {x["href"] for x in nxt}
            if not nxt_sig or nxt_sig == sig:
                print(f"  {state}: postback did not change batch", flush=True)
                break
        except Exception as e:
            print(f"  {state}: pagination error {type(e).__name__}: {e}", flush=True)
            break

    return list(accumulated.values()), batch_no


async def scrape_state(browser, state, slug):
    url = f"{BASE}/immobilienverwalter/{slug}/"
    ctx = await browser.new_context(
        locale="de-AT",
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 1200},
    )
    page = await ctx.new_page()
    print(f"STATE {state}: {url}", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await dismiss_cookie(page)
    await page.wait_for_timeout(300)
    body = clean_text(await page.locator("body").inner_text())
    m = re.search(r"Ihre Suche erzielte\s+(?:über\s+)?([\d\.]+)\s+Treffer", body, re.I)
    expected = int(m.group(1).replace(".", "")) if m else None
    print(f"  expected={expected}", flush=True)
    links, batches = await collect_all_batches(page, state, expected)
    rows = [{
        "bundesland": state,
        "company_name": x["text"],
        "firmaid": qs_value(x["href"], "firmaid"),
        "standortid": qs_value(x["href"], "standortid"),
        "profile_url": x["href"],
        "source_list_url": url,
    } for x in links]
    diag = {
        "bundesland": state, "source_url": url, "expected_treffer": expected,
        "extracted_profile_urls": len(rows), "batches": batches,
        "count_match": (len(rows) == expected) if expected is not None else None,
    }
    print(f"  DONE {state}: {len(rows)}/{expected}, batches={batches}", flush=True)
    await ctx.close()
    return rows, diag


async def main():
    all_rows, diagnostics = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for state, slug in STATES.items():
            rows, diag = await scrape_state(browser, state, slug)
            all_rows += rows
            diagnostics.append(diag)
        await browser.close()

    raw_fields = ["bundesland", "company_name", "firmaid", "standortid", "profile_url", "source_list_url"]
    with (OUT / "immobilienverwalter_standorte.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=raw_fields); w.writeheader(); w.writerows(all_rows)

    grouped = {}
    for r in all_rows:
        key = r["firmaid"] or r["profile_url"]
        g = grouped.setdefault(key, {"company_name": r["company_name"], "firmaid": r["firmaid"], "bundeslaender": set(), "standort_count": 0, "profile_url": r["profile_url"]})
        g["bundeslaender"].add(r["bundesland"])
        g["standort_count"] += 1
        if len(r["company_name"]) > len(g["company_name"]): g["company_name"] = r["company_name"]

    unique = [{
        "company_name": g["company_name"], "firmaid": g["firmaid"],
        "bundeslaender": "; ".join(sorted(g["bundeslaender"])),
        "standort_count": g["standort_count"], "profile_url": g["profile_url"]
    } for g in grouped.values()]
    unique.sort(key=lambda x: x["company_name"].casefold())
    with (OUT / "immobilienverwalter_unique_companies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["company_name", "firmaid", "bundeslaender", "standort_count", "profile_url"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(unique)

    summary = {"raw_standort_rows": len(all_rows), "unique_firmaids": len(unique), "states": diagnostics}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    bad = [d for d in diagnostics if d["expected_treffer"] is not None and not d["count_match"]]
    if bad:
        raise SystemExit(f"Count mismatch in {len(bad)} state(s): {bad}")


if __name__ == "__main__":
    asyncio.run(main())
