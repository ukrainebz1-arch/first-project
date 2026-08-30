import csv
import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

PARTS_DIR = os.environ.get("PARTS_DIR", "parts")
OUT_DIR = os.environ.get("OUT_DIR", "final_immobilienverwalter")
os.makedirs(OUT_DIR, exist_ok=True)

STATES = [
    "burgenland", "kärnten", "niederösterreich", "oberösterreich",
    "salzburg", "steiermark", "tirol", "vorarlberg", "wien",
]
EXPECTED_KEYS = {("immobilienverwalter", state) for state in STATES}


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
            s = json.load(f)
        if s.get("query_term") == "immobilienverwalter":
            summaries.append(s)

    found_keys = {(s["query_term"], s["state"]) for s in summaries}
    missing = sorted(EXPECTED_KEYS - found_keys)
    extras = sorted(found_keys - EXPECTED_KEYS)
    invalid = [s for s in summaries if int(s.get("collected", -1)) != int(s.get("wko_live_total", -2))]
    if missing or extras or invalid or len(summaries) != 9:
        raise RuntimeError(
            f"validation failed: summaries={len(summaries)}, missing={missing}, extras={extras}, invalid={invalid}"
        )

    part_files = glob.glob(os.path.join(PARTS_DIR, "**", "immobilienverwalter_*_part.csv"), recursive=True)
    all_rows = []
    for p in part_files:
        all_rows.extend(read_csv(p))

    expected_raw = sum(int(s["wko_live_total"]) for s in summaries)
    if len(all_rows) != expected_raw:
        raise RuntimeError(f"raw row count mismatch: got={len(all_rows)} expected={expected_raw}")

    # Deduplicate by WKO firmaid. If one company is present in several states,
    # preserve all state provenance and fill missing contact fields from any row.
    merged = {}
    provenance = defaultdict(set)
    standort_counts = defaultdict(int)
    for row in all_rows:
        fid = row["firmaid"]
        provenance[fid].add(row["state"])
        standort_counts[fid] += 1
        if fid not in merged:
            merged[fid] = dict(row)
        else:
            for k in [
                "company_name", "business_label", "street", "postal_code", "city", "address",
                "phones", "email", "all_emails", "website", "all_websites", "profile_url",
            ]:
                if not merged[fid].get(k) and row.get(k):
                    merged[fid][k] = row[k]

    final = []
    for fid, row in merged.items():
        out = dict(row)
        out["states_seen"] = " | ".join(sorted(provenance[fid]))
        out["wko_state_record_count"] = standort_counts[fid]
        out.pop("query_term", None)
        out.pop("state", None)
        final.append(out)
    final.sort(key=lambda x: (x.get("company_name", "").lower(), x.get("postal_code", ""), x.get("firmaid", "")))

    final_fields = [
        "firmaid", "company_name", "business_label", "street", "postal_code", "city", "address",
        "phones", "email", "all_emails", "website", "all_websites", "states_seen",
        "wko_state_record_count", "profile_url",
    ]
    raw_fields = [
        "firmaid", "company_name", "business_label", "street", "postal_code", "city", "address",
        "phones", "email", "all_emails", "website", "all_websites", "state", "query_term", "profile_url",
    ]

    write_csv(os.path.join(OUT_DIR, "wko_immobilienverwalter_austria_unique.csv"), final, final_fields)
    write_csv(os.path.join(OUT_DIR, "wko_immobilienverwalter_austria_raw_by_state.csv"), all_rows, raw_fields)

    by_state = sorted([
        {
            "state": s["state"],
            "wko_live_total": s["wko_live_total"],
            "collected": s["collected"],
            "rounds": s.get("rounds"),
            "url": s.get("url"),
        }
        for s in summaries
    ], key=lambda x: x["state"])

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "validated_state_parts": len(summaries),
        "raw_state_rows": len(all_rows),
        "sum_wko_live_totals": expected_raw,
        "unique_wko_firmaids": len(final),
        "states": by_state,
    }
    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
