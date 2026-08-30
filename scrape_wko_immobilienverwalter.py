import asyncio
import csv
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

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
    candidates = [
        "Alle akzeptieren", "Akzeptieren", "Zustimmen", "Einverstanden",
        "Accept all", "Accept", "OK"
    ]
    for text in candidates:
        try:
            loc = page.get_by_role("button", name=re.compile(f"^{re.escape(text)}$", re.I))
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=2000, force=True)
                await page.wait_for_timeout(300)
                return
        except Exception:
            pass


async def result_links(page):
    # Company detail links in WKO Firmen A-Z include firmaid=. A result may expose
    # the same URL more than once (e.g. image/title), so dedupe by absolute href.
    data = await page.locator('a[href*="firmaid="]').evaluate_all(
        """els => els.map(a => ({href: a.href, text: (a.innerText || a.textContent || '').trim()}))"""
    )
    out = []
    seen = set()
    for item in data:
        href = item.get("href") or ""
        if not href or href in seen:
            continue
        seen.add(href)
        out.append({"href": href, "text": clean_text(item.get("text", ""))})
    return out


async def click_more_until_done(page, expected=None):
    stagnant = 0
    clicks = 0
    while True:
        links = await result_links(page)
        n_before = len(links)
        if expected and n_before >= expected:
            break

        # WKO help documents the control as "Mehr laden". Keep fallbacks in
        # case the accessible name changes slightly.
        selectors = [
            'button:has-text("Mehr laden")',
            'a:has-text("Mehr laden")',
            'button:has-text("Mehr anzeigen")',
            'a:has-text("Mehr anzeigen")',
        ]
        btn = None
        for sel in selectors:
            loc = page.locator(sel)
            if await loc.count():
                for i in range(await loc.count()):
                    try:
                        if await loc.nth(i).is_visible():
                            btn = loc.nth(i)
                            break
                    except Exception:
                        pass
            if btn:
                break
        if not btn:
            break

        try:
            await btn.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        try:
            await btn.click(timeout=10000, force=True)
        except Exception:
            try:
                await btn.evaluate("el => el.click()")
            except Exception:
                break

        clicks += 1
        grew = False
        for _ in range(24):
            await page.wait_for_timeout(250)
            n_after = len(await result_links(page))
            if n_after > n_before:
                grew = True
                break
        if grew:
            stagnant = 0
        else:
            stagnant += 1
            if stagnant >= 3:
                break

        if clicks % 10 == 0:
            print(f"  clicks={clicks}, loaded={len(await result_links(page))}, expected={expected}", flush=True)
        if clicks > 250:
            raise RuntimeError("Safety stop: more than 250 load-more clicks")

    return clicks


async def scrape_state(browser, state, slug):
    url = f"{BASE}/immobilienverwalter/{slug}/"
    context = await browser.new_context(
        locale="de-AT",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1440, "height": 1200},
    )
    page = await context.new_page()
    print(f"STATE {state}: {url}", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass
    await dismiss_cookie(page)
    await page.wait_for_timeout(700)

    body = clean_text(await page.locator("body").inner_text())
    m = re.search(r"Ihre Suche erzielte\s+(?:über\s+)?([\d\.]+)\s+Treffer", body, re.I)
    expected = int(m.group(1).replace(".", "")) if m else None
    print(f"  expected={expected}", flush=True)

    clicks = await click_more_until_done(page, expected=expected)
    links = await result_links(page)
    print(f"  final loaded links={len(links)} after {clicks} clicks", flush=True)

    rows = []
    for item in links:
        href = item["href"]
        name = item["text"]
        # Keep only WKO profile URLs with an actual firmaid.
        firmaid = qs_value(href, "firmaid")
        if not firmaid:
            continue
        rows.append({
            "bundesland": state,
            "company_name": name,
            "firmaid": firmaid,
            "standortid": qs_value(href, "standortid"),
            "profile_url": href,
            "source_list_url": url,
        })

    # Deduplicate exact profile hrefs only; same firmaid at multiple locations is
    # intentionally retained in the raw Standort export.
    dedup = {}
    for r in rows:
        dedup[r["profile_url"]] = r
    rows = list(dedup.values())

    # Write diagnostics even if counts differ; overall workflow will fail after
    # all states so partial data remains available in logs.
    diag = {
        "bundesland": state,
        "source_url": url,
        "expected_treffer": expected,
        "extracted_profile_urls": len(rows),
        "load_more_clicks": clicks,
        "count_match": (expected == len(rows)) if expected is not None else None,
    }
    await context.close()
    return rows, diag


async def main():
    all_rows = []
    diagnostics = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        for state, slug in STATES.items():
            rows, diag = await scrape_state(browser, state, slug)
            all_rows.extend(rows)
            diagnostics.append(diag)
        await browser.close()

    # Raw location-level export.
    fields = ["bundesland", "company_name", "firmaid", "standortid", "profile_url", "source_list_url"]
    with (OUT / "immobilienverwalter_standorte.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(all_rows)

    # Unique company export: WKO firmaid is the primary stable key. If the same
    # company appears in several states/locations, combine the state/location data.
    grouped = {}
    for r in all_rows:
        key = r["firmaid"] or r["profile_url"]
        g = grouped.setdefault(key, {
            "company_name": r["company_name"],
            "firmaid": r["firmaid"],
            "bundeslaender": set(),
            "standort_count": 0,
            "profile_url": r["profile_url"],
        })
        if r["bundesland"]:
            g["bundeslaender"].add(r["bundesland"])
        g["standort_count"] += 1
        if len(r["company_name"]) > len(g["company_name"]):
            g["company_name"] = r["company_name"]

    unique = []
    for g in grouped.values():
        unique.append({
            "company_name": g["company_name"],
            "firmaid": g["firmaid"],
            "bundeslaender": "; ".join(sorted(g["bundeslaender"])),
            "standort_count": g["standort_count"],
            "profile_url": g["profile_url"],
        })
    unique.sort(key=lambda x: x["company_name"].casefold())

    with (OUT / "immobilienverwalter_unique_companies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields2 = ["company_name", "firmaid", "bundeslaender", "standort_count", "profile_url"]
        w = csv.DictWriter(f, fieldnames=fields2)
        w.writeheader()
        w.writerows(unique)

    summary = {
        "raw_standort_rows": len(all_rows),
        "unique_firmaids": len(unique),
        "states": diagnostics,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    mismatches = [d for d in diagnostics if d["expected_treffer"] is not None and not d["count_match"]]
    if mismatches:
        raise SystemExit(f"Count mismatch in {len(mismatches)} state(s): {mismatches}")


if __name__ == "__main__":
    asyncio.run(main())
