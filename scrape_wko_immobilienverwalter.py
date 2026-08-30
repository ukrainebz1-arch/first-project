# Triggered via GitHub Actions to collect the complete Austrian WKO Immobilienverwalter universe.
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
                await page.wait_for_timeout(300)
                return
        except Exception:
            pass


async def result_links(page):
    data = await page.locator('a[href*="firmaid="]').evaluate_all(
        """els => els.map(a => ({href: a.href, text: (a.innerText || a.textContent || '').trim()}))"""
    )
    out, seen = [], set()
    for item in data:
        href = item.get("href") or ""
        if not href or href in seen:
            continue
        seen.add(href)
        out.append({"href": href, "text": clean_text(item.get("text", ""))})
    return out


async def locate_more(page):
    # WKO has changed markup over time, so support buttons, anchors, inputs,
    # spans/divs containing the label, and accessible-text matching.
    selectors = [
        'button:has-text("Mehr laden")', 'a:has-text("Mehr laden")',
        'input[value*="Mehr laden" i]', '[role="button"]:has-text("Mehr laden")',
        'button:has-text("Mehr")', 'a:has-text("Mehr")',
        'input[value*="Mehr" i]', '[role="button"]:has-text("Mehr")',
        'text=/Mehr laden/i',
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            for i in range(count):
                el = loc.nth(i)
                if await el.is_visible():
                    return el
        except Exception:
            pass
    return None


async def dump_more_diagnostics(page, state):
    try:
        els = await page.locator('button,a,input,[role="button"],span,div').evaluate_all(
            """els => els.map(e => ({tag:e.tagName, text:(e.innerText||e.textContent||'').trim(), value:e.value||'', cls:e.className||'', id:e.id||'', html:e.outerHTML||''}))
                 .filter(x => /mehr|laden/i.test((x.text||'')+' '+(x.value||'')))
                 .slice(0,30)"""
        )
        print(f"  MORE_DIAG {state}: {json.dumps(els, ensure_ascii=False)[:12000]}", flush=True)
    except Exception as e:
        print(f"  MORE_DIAG failed: {e}", flush=True)


async def click_more_until_done(page, state, expected=None):
    stagnant = 0
    clicks = 0
    while True:
        n_before = len(await result_links(page))
        if expected and n_before >= expected:
            break

        btn = await locate_more(page)
        if btn is None:
            await dump_more_diagnostics(page, state)
            break

        try:
            await btn.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        clicked = False
        for method in ("normal", "force", "js"):
            try:
                if method == "normal":
                    await btn.click(timeout=8000)
                elif method == "force":
                    await btn.click(timeout=8000, force=True)
                else:
                    await btn.evaluate("el => el.click()")
                clicked = True
                break
            except Exception:
                pass
        if not clicked:
            await dump_more_diagnostics(page, state)
            break

        clicks += 1
        grew = False
        for _ in range(32):
            await page.wait_for_timeout(250)
            if len(await result_links(page)) > n_before:
                grew = True
                break
        if grew:
            stagnant = 0
        else:
            stagnant += 1
            if stagnant >= 2:
                await dump_more_diagnostics(page, state)
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
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
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

    clicks = await click_more_until_done(page, state, expected=expected)
    links = await result_links(page)
    print(f"  final loaded links={len(links)} after {clicks} clicks", flush=True)

    rows = []
    for item in links:
        href = item["href"]
        firmaid = qs_value(href, "firmaid")
        if not firmaid:
            continue
        rows.append({
            "bundesland": state,
            "company_name": item["text"],
            "firmaid": firmaid,
            "standortid": qs_value(href, "standortid"),
            "profile_url": href,
            "source_list_url": url,
        })
    rows = list({r["profile_url"]: r for r in rows}.values())
    diag = {
        "bundesland": state, "source_url": url, "expected_treffer": expected,
        "extracted_profile_urls": len(rows), "load_more_clicks": clicks,
        "count_match": (expected == len(rows)) if expected is not None else None,
    }
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
        w = csv.DictWriter(f, fieldnames=raw_fields); w.writeheader(); w.writerows(all_rows)

    grouped = {}
    for r in all_rows:
        key = r["firmaid"] or r["profile_url"]
        g = grouped.setdefault(key, {"company_name": r["company_name"], "firmaid": r["firmaid"], "bundeslaender": set(), "standort_count": 0, "profile_url": r["profile_url"]})
        g["bundeslaender"].add(r["bundesland"])
        g["standort_count"] += 1
        if len(r["company_name"]) > len(g["company_name"]): g["company_name"] = r["company_name"]

    unique = [{"company_name": g["company_name"], "firmaid": g["firmaid"], "bundeslaender": "; ".join(sorted(g["bundeslaender"])), "standort_count": g["standort_count"], "profile_url": g["profile_url"]} for g in grouped.values()]
    unique.sort(key=lambda x: x["company_name"].casefold())
    with (OUT / "immobilienverwalter_unique_companies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["company_name", "firmaid", "bundeslaender", "standort_count", "profile_url"]
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(unique)

    summary = {"raw_standort_rows": len(all_rows), "unique_firmaids": len(unique), "states": diagnostics}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    mismatches = [d for d in diagnostics if d["expected_treffer"] is not None and not d["count_match"]]
    if mismatches:
        raise SystemExit(f"Count mismatch in {len(mismatches)} state(s): {mismatches}")


if __name__ == "__main__":
    asyncio.run(main())
