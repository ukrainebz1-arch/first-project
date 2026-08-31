import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone

MASTER = os.environ.get("MASTER_CSV", "work/input/company_master.csv")
KARRIERE = os.environ.get("KARRIERE_CSV", "work/karriere/karriere_matches.csv")
WEBSITE = os.environ.get("WEBSITE_CSV", "work/website/website_employee_mentions.csv")
WKO = os.environ.get("WKO_PROFILE_CSV", "work/wko/wko_profile_employee_mentions.csv")
OUTDIR = os.environ.get("OUTDIR", "data/hausverwaltung/size")
os.makedirs(OUTDIR, exist_ok=True)


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def as_int(v):
    try:
        if v is None or clean(str(v)) == "":
            return None
        return int(float(str(v).replace(".", "")))
    except Exception:
        return None


def as_float(v):
    try:
        if v is None or clean(str(v)) == "":
            return None
        return float(v)
    except Exception:
        return None


def truthy(v):
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def groupish(text):
    t = (text or "").casefold()
    markers = [
        "gruppe", "group", "konzern", "weltweit", "worldwide", "international",
        "länder", "laender", "standorte", "locations", "gesamt", "europaweit",
        "europa", "unternehmensgruppe", "holding",
    ]
    return any(x in t for x in markers)


def borderline_value(v):
    return v is not None and 20 <= v <= 30


master = read_csv(MASTER)
karriere_rows = read_csv(KARRIERE)
website_rows = read_csv(WEBSITE)
wko_rows = read_csv(WKO)

karriere = {clean(r.get("company_name", "")): r for r in karriere_rows}
wko = {clean(r.get("company_name", "")): r for r in wko_rows}
website = defaultdict(list)
for r in website_rows:
    website[clean(r.get("company_name", ""))].append(r)

out = []
for m in master:
    name = clean(m["company_name"])
    k = karriere.get(name, {})
    w = wko.get(name, {})
    wrs = website.get(name, [])

    kmin = as_int(k.get("karriere_emp_min"))
    kmax = as_int(k.get("karriere_emp_max"))
    kscore = as_float(k.get("karriere_match_score"))
    kloc = truthy(k.get("karriere_location_hit"))
    kstrong_name = kscore is not None and (kscore >= 82 or (kscore >= 72 and kloc))
    k_31 = bool(kstrong_name and kmin is not None and kmin >= 31)
    k_probable = bool(kstrong_name and kmin == 30 and (kmax is None or kmax >= 31))
    k_border = bool(kstrong_name and ((kmin is not None and 20 <= kmin <= 30) or (kmax is not None and 20 <= kmax <= 30)))

    web_best = None
    web_evidence = []
    web_urls = []
    for r in wrs:
        v = as_int(r.get("employee_best_numeric_mention"))
        if v is not None and (web_best is None or v > web_best):
            web_best = v
        ev = clean(r.get("employee_evidence_contexts", ""))
        if ev:
            web_evidence.append(ev)
        u = clean(r.get("website", ""))
        if u and u not in web_urls:
            web_urls.append(u)
    web_text = " || ".join(web_evidence)
    web_group = groupish(web_text)
    web_31_direct = bool(web_best is not None and web_best >= 31 and not web_group)
    web_31_group = bool(web_best is not None and web_best >= 31 and web_group)
    web_border = borderline_value(web_best)

    wbest = as_int(w.get("employee_best_numeric_mention"))
    wev = clean(w.get("employee_evidence_contexts", ""))
    w_group = groupish(wev)
    w_31_direct = bool(wbest is not None and wbest >= 31 and not w_group)
    w_31_group = bool(wbest is not None and wbest >= 31 and w_group)
    w_border = borderline_value(wbest)

    direct_sources = []
    group_sources = []
    if k_31:
        direct_sources.append("karriere.at")
    if web_31_direct:
        direct_sources.append("company website")
    if w_31_direct:
        direct_sources.append("WKO profile")
    if k_probable:
        group_sources.append("karriere.at 30+ band")
    if web_31_group:
        group_sources.append("company/group website")
    if w_31_group:
        group_sources.append("WKO group-context mention")

    if direct_sources:
        classification = "A_TARGET_30_PLUS"
        reason = "31+ direct/employer evidence: " + ", ".join(direct_sources)
    elif group_sources:
        classification = "B_LIKELY_30_PLUS_GROUP"
        reason = "30+/group-level evidence: " + ", ".join(group_sources)
    elif k_border or web_border or w_border:
        classification = "C_BORDERLINE_20_30"
        reason = "Public employee evidence is in the 20-30 range"
    else:
        classification = "U_NOT_PROVEN"
        reason = "No reliable 20+/31+ employee evidence found by automated sources"

    # This is only a screening layer. Final Spedition-style qualification still
    # requires manual checks for false matches, Austrian entity vs group claims,
    # and whether the company is a real external Hausverwaltung target.
    adjacent_tokens = [
        "holding", "projektentwicklung", "entwicklungsgesellschaft", "wohnbau",
        "baugesellschaft", "bundesimmobiliengesellschaft", "facility", "gebäudemanagement",
        "versicherung", "bank", "stiftung",
    ]
    adjacent_hint = any(x in name.casefold() for x in adjacent_tokens)

    out.append({
        **m,
        "size_class_preliminary": classification,
        "size_reason_preliminary": reason,
        "manual_review_required": "yes" if classification != "U_NOT_PROVEN" else "no",
        "adjacent_non_core_hint": "yes" if adjacent_hint else "no",
        "karriere_url": clean(k.get("karriere_url", "")),
        "karriere_name": clean(k.get("karriere_name", "")),
        "karriere_match_score": clean(k.get("karriere_match_score", "")),
        "karriere_location_hit": clean(k.get("karriere_location_hit", "")),
        "karriere_emp_min": clean(k.get("karriere_emp_min", "")),
        "karriere_emp_max": clean(k.get("karriere_emp_max", "")),
        "karriere_employee_evidence": clean(k.get("karriere_employee_evidence", "")),
        "karriere_jobs": clean(k.get("karriere_jobs", "")),
        "website_employee_best": "" if web_best is None else web_best,
        "website_group_context": "yes" if web_group else "no",
        "website_evidence": web_text,
        "website_evidence_urls": " | ".join(web_urls),
        "wko_employee_best": "" if wbest is None else wbest,
        "wko_group_context": "yes" if w_group else "no",
        "wko_employee_evidence": wev,
        "wko_employee_profile_url": clean(w.get("wko_profile_url", "")),
        "independent_direct_31plus_sources": len(direct_sources),
        "group_or_probable_30plus_sources": len(group_sources),
    })

order = {
    "A_TARGET_30_PLUS": 0,
    "B_LIKELY_30_PLUS_GROUP": 1,
    "C_BORDERLINE_20_30": 2,
    "U_NOT_PROVEN": 3,
}
out.sort(key=lambda r: (order.get(r["size_class_preliminary"], 9), r["company_name"].casefold()))

fields = list(out[0].keys()) if out else []
with open(os.path.join(OUTDIR, "size_screening.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(out)

# Copy the canonical master into the persistent checkpoint folder.
with open(os.path.join(OUTDIR, "company_master.csv"), "w", newline="", encoding="utf-8-sig") as f:
    mf = list(master[0].keys()) if master else []
    w = csv.DictWriter(f, fieldnames=mf)
    w.writeheader()
    w.writerows(master)

counts = defaultdict(int)
for r in out:
    counts[r["size_class_preliminary"]] += 1
summary = {
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "pipeline_stage": "Stage 2 automated size screening",
    "companies_screened": len(out),
    "class_counts_preliminary": dict(counts),
    "karriere_profiles_matched": sum(bool(clean(r.get("karriere_url", ""))) for r in out),
    "karriere_employee_ranges": sum(bool(clean(r.get("karriere_emp_min", ""))) for r in out),
    "companies_with_website_employee_mentions": sum(bool(clean(r.get("website_evidence", ""))) for r in out),
    "companies_with_wko_employee_mentions": sum(bool(clean(r.get("wko_employee_evidence", ""))) for r in out),
    "manual_review_queue": sum(r["size_class_preliminary"] != "U_NOT_PROVEN" for r in out),
    "note": "Preliminary only. Final A/B/C classification requires Spedition-style manual verification of entity-vs-group evidence and non-core/adjacent status.",
}
with open(os.path.join(OUTDIR, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

progress = f"""# Hausverwaltung Austria qualification checkpoint — 2026-08-31

## Stage 1 — WKO market universe
- WKO query: `immobilienverwalter`
- Validated Standort rows: 1,948
- Canonical companies after conservative punctuation/spacing deduplication: {len(master):,}
- All 9 Bundesland counts matched WKO live totals in the completed matrix scrape.

## Stage 2 — automated size screening
The same source layers used for Spedition were run against the canonical Hausverwaltung universe:
1. karriere.at employer profiles
2. official company websites
3. WKO company profiles

Preliminary counts (NOT final qualification):
- A_TARGET_30_PLUS: {counts['A_TARGET_30_PLUS']}
- B_LIKELY_30_PLUS_GROUP: {counts['B_LIKELY_30_PLUS_GROUP']}
- C_BORDERLINE_20_30: {counts['C_BORDERLINE_20_30']}
- U_NOT_PROVEN: {counts['U_NOT_PROVEN']}

## Next required work
Review every A/B/C candidate against public sources, reject false karriere matches, distinguish Austrian legal-entity headcount from group headcount, and separate adjacent/non-core license holders. `U_NOT_PROVEN` means size was not proven, not that the company is small. After final size qualification, proceed to owner / decision-maker research.

## Persistence
Stage-2 files are committed under `data/hausverwaltung/size/` so the work can resume without depending on temporary Actions artifacts.
"""
with open(os.path.join(OUTDIR, "PROGRESS_2026-08-31.md"), "w", encoding="utf-8") as f:
    f.write(progress)

print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
