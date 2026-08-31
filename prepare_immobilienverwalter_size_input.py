import csv
import json
import os
import re
import unicodedata
from collections import defaultdict

INFILE = os.environ.get(
    "WKO_RAW_CSV",
    "data/wko-immobilienverwalter/wko_immobilienverwalter_austria_raw_by_state.csv",
)
OUTDIR = os.environ.get("OUTDIR", "iv_size_input")
os.makedirs(OUTDIR, exist_ok=True)


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def canonical_key(name):
    # Intentionally conservative: punctuation/spacing/case only.
    # Legal-form words are retained, so AG/GmbH/KG entities are not merged.
    s = unicodedata.normalize("NFKC", clean(name)).casefold()
    s = s.replace("&", " und ")
    s = re.sub(r"[^\w]+", " ", s, flags=re.UNICODE)
    return clean(s)


def first_nonempty(rows, key):
    for r in rows:
        v = clean(r.get(key, ""))
        if v:
            return v
    return ""


def joined_unique(rows, key):
    vals = []
    seen = set()
    for r in rows:
        v = clean(r.get(key, ""))
        if v and v not in seen:
            seen.add(v)
            vals.append(v)
    return " | ".join(vals)


with open(INFILE, encoding="utf-8-sig", newline="") as f:
    raw = list(csv.DictReader(f))

if not raw:
    raise RuntimeError("WKO raw input is empty")

by_key = defaultdict(list)
for r in raw:
    name = clean(r.get("company_name", ""))
    if not name:
        continue
    by_key[canonical_key(name)].append(r)

master = []
adapted_rows = []
for ck, rows in by_key.items():
    # Prefer the most common spelling; break ties by fewer quote characters,
    # then a readable shorter form.
    counts = defaultdict(int)
    for r in rows:
        counts[clean(r["company_name"])] += 1
    display = sorted(
        counts,
        key=lambda n: (-counts[n], n.count('"'), len(n), n.casefold()),
    )[0]

    states = sorted({clean(r.get("state", "")) for r in rows if clean(r.get("state", ""))})
    aliases = sorted({clean(r.get("company_name", "")) for r in rows if clean(r.get("company_name", ""))})
    firmaids = [clean(r.get("firmaid", "")) for r in rows if clean(r.get("firmaid", ""))]
    addresses = []
    for r in rows:
        a = clean(r.get("address", ""))
        if a and a not in addresses:
            addresses.append(a)

    websites = []
    for r in rows:
        for field in ("website", "all_websites"):
            for v in (r.get(field, "") or "").split("|"):
                v = clean(v)
                if v and v not in websites:
                    websites.append(v)

    master.append({
        "canonical_key": ck,
        "company_name": display,
        "aliases": " | ".join(aliases),
        "wko_standort_count": len(rows),
        "states_seen": " | ".join(states),
        "firmaids": " | ".join(firmaids),
        "addresses": " | ".join(addresses),
        "website": websites[0] if websites else "",
        "all_websites": " | ".join(websites),
        "email": first_nonempty(rows, "email"),
        "phones": first_nonempty(rows, "phones"),
        "profile_url": first_nonempty(rows, "profile_url"),
    })

    # Feed the existing Spedition enrichment scripts without changing their
    # research logic. All Standort rows use the canonical display name.
    for r in rows:
        out = dict(r)
        out["company_name"] = display
        out["bundesland"] = clean(r.get("state", ""))
        pc = clean(r.get("postal_code", ""))
        city = clean(r.get("city", ""))
        out["place"] = clean(f"{pc} {city}")
        if not clean(out.get("website", "")):
            out["website"] = clean(r.get("all_websites", "")).split(" | ")[0]
        adapted_rows.append(out)

master.sort(key=lambda x: (x["company_name"].casefold(), x["canonical_key"]))

master_fields = [
    "canonical_key", "company_name", "aliases", "wko_standort_count",
    "states_seen", "firmaids", "addresses", "website", "all_websites",
    "email", "phones", "profile_url",
]
with open(os.path.join(OUTDIR, "company_master.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=master_fields)
    w.writeheader()
    w.writerows(master)

adapt_fields = list(raw[0].keys()) + ["bundesland", "place"]
with open(os.path.join(OUTDIR, "iv_size_input.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=adapt_fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(adapted_rows)

summary = {
    "raw_wko_rows": len(raw),
    "canonical_companies": len(master),
    "rows_with_known_website": sum(bool(x["website"]) for x in master),
    "multi_standort_companies": sum(int(x["wko_standort_count"]) > 1 for x in master),
}
with open(os.path.join(OUTDIR, "prepare_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
if len(raw) != 1948:
    print(f"NOTE live/persisted raw WKO count is {len(raw)}, not historical 1948", flush=True)
