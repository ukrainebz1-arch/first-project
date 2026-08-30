import csv
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

PARTS_DIR = os.environ.get("PARTS_DIR", "parts")
OUT_DIR = os.environ.get("OUT_DIR", "final")
os.makedirs(OUT_DIR, exist_ok=True)

EXPECTED_KEYS = {
    (term, state)
    for term in ["buchhalter", "bilanzbuchhalter"]
    for state in ["burgenland", "kärnten", "niederösterreich", "oberösterreich", "salzburg", "steiermark", "tirol", "vorarlberg", "wien"]
}


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    summary_files = glob.glob(os.path.join(PARTS_DIR, "**", "*_summary.json"), recursive=True)
    summaries = []
    for p in summary_files:
        with open(p, encoding="utf-8") as f:
            summaries.append(json.load(f))

    found_keys = {(s["query_term"], s["state"]) for s in summaries}
    missing = sorted(EXPECTED_KEYS - found_keys)
    extras = sorted(found_keys - EXPECTED_KEYS)
    invalid = [s for s in summaries if int(s.get("collected", -1)) != int(s.get("wko_live_total", -2))]
    if missing or extras or invalid or len(summaries) != 18:
        raise RuntimeError(f"validation failed: summaries={len(summaries)}, missing={missing}, extras={extras}, invalid={invalid}")

    part_files = glob.glob(os.path.join(PARTS_DIR, "**", "*_part.csv"), recursive=True)
    all_rows = []
    for p in part_files:
        all_rows.extend(read_csv(p))

    expected_raw = sum(int(s["wko_live_total"]) for s in summaries)
    if len(all_rows) != expected_raw:
        raise RuntimeError(f"raw row count mismatch: got={len(all_rows)} expected={expected_raw}")

    merged = {}
    provenance = defaultdict(lambda: {"terms": set(), "states": set()})
    for row in all_rows:
        fid = row["firmaid"]
        provenance[fid]["terms"].add(row["query_term"])
        provenance[fid]["states"].add(row["state"])
        if fid not in merged:
            merged[fid] = dict(row)
        else:
            for k in ["company_name", "business_label", "street", "postal_code", "city", "address", "phones", "email", "all_emails", "website", "all_websites", "profile_url"]:
                if not merged[fid].get(k) and row.get(k):
                    merged[fid][k] = row[k]

    final = []
    for fid, row in merged.items():
        out = dict(row)
        out["query_terms"] = " | ".join(sorted(provenance[fid]["terms"]))
        out["states_seen"] = " | ".join(sorted(provenance[fid]["states"]))
        out.pop("query_term", None)
        out.pop("state", None)
        final.append(out)
    final.sort(key=lambda x: (x.get("company_name", "").lower(), x.get("postal_code", ""), x.get("firmaid", "")))

    final_fields = [
        "firmaid", "company_name", "business_label", "street", "postal_code", "city", "address",
        "phones", "email", "all_emails", "website", "all_websites", "query_terms", "states_seen", "profile_url",
    ]
    raw_fields = [
        "firmaid", "company_name", "business_label", "street", "postal_code", "city", "address",
        "phones", "email", "all_emails", "website", "all_websites", "state", "query_term", "profile_url",
    ]
    write_csv(os.path.join(OUT_DIR, "wko_bookkeeping_austria_combined.csv"), final, final_fields)
    write_csv(os.path.join(OUT_DIR, "wko_bookkeeping_austria_raw_by_query_state.csv"), all_rows, raw_fields)

    for term in ["buchhalter", "bilanzbuchhalter"]:
        ids = {r["firmaid"] for r in all_rows if r["query_term"] == term}
        subset = [r for r in final if r["firmaid"] in ids]
        write_csv(os.path.join(OUT_DIR, f"wko_{term}_austria.csv"), subset, final_fields)

    by_query = sorted([
        {
            "query_term": s["query_term"],
            "state": s["state"],
            "wko_live_total": s["wko_live_total"],
            "collected": s["collected"],
            "reference_total_2026_08_30": s.get("reference_total_2026_08_30"),
            "rounds": s.get("rounds"),
            "url": s.get("url"),
        }
        for s in summaries
    ], key=lambda x: (x["query_term"], x["state"]))

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "validated_query_state_parts": len(summaries),
        "raw_query_state_rows": len(all_rows),
        "sum_wko_live_totals": expected_raw,
        "unique_wko_firmaids_combined": len(final),
        "unique_buchhalter_firmaids": len({r["firmaid"] for r in all_rows if r["query_term"] == "buchhalter"}),
        "unique_bilanzbuchhalter_firmaids": len({r["firmaid"] for r in all_rows if r["query_term"] == "bilanzbuchhalter"}),
        "queries": by_query,
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
