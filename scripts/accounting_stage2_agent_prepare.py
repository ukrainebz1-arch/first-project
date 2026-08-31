#!/usr/bin/env python3
import argparse, csv, json, os
from collections import Counter, defaultdict

CANDIDATE_STATUSES = {
    'CONFIRMED_30_PLUS',
    'CONFIRMED_20_29',
    'LIKELY_20_PLUS',
    'POSSIBLE_20_PLUS',
}

KEEP_FIELDS = [
    'group_key','group_name','domain','websites','cities','legal_entities_count',
    'ksw_listings_count','locations_count','member_entities','qualification_status',
    'confidence','employee_low','employee_high','reason','official_employee_evidence',
    'site_team_profiles','site_team_emails','site_job_links','search_employee_evidence',
    'search_size_ranges','linkedin_visible','evidence_urls'
]

def compact(value, limit=6000):
    value = (value or '').replace('\x00', '').strip()
    return value if len(value) <= limit else value[:limit] + ' …[truncated]'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--output-dir', required=True)
    ap.add_argument('--chunks', type=int, default=32)
    args = ap.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    with open(args.input, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))

    candidates = []
    for r in rows:
        if r.get('qualification_status') not in CANDIDATE_STATUSES:
            continue
        rr = {k: compact(r.get(k,'')) for k in KEEP_FIELDS}
        rr['prior_status'] = rr.pop('qualification_status')
        rr['prior_confidence'] = rr.pop('confidence')
        rr['prior_employee_low'] = rr.pop('employee_low')
        rr['prior_employee_high'] = rr.pop('employee_high')
        rr['prior_reason'] = rr.pop('reason')
        rr['research_mode'] = 'DEEP_RESEARCH' if rr['prior_status'] in {'POSSIBLE_20_PLUS','LIKELY_20_PLUS'} else 'VERIFY_PRIOR'
        candidates.append(rr)

    buckets = defaultdict(list)
    for r in candidates:
        buckets[r['prior_status']].append(r)
    for v in buckets.values():
        v.sort(key=lambda x: (x['group_name'].lower(), x['group_key']))
    ordered = []
    priority = ['POSSIBLE_20_PLUS','LIKELY_20_PLUS','CONFIRMED_30_PLUS','CONFIRMED_20_29']
    while any(buckets[s] for s in priority if s in buckets):
        for s in priority:
            if buckets[s]:
                ordered.append(buckets[s].pop(0))

    chunks = [[] for _ in range(args.chunks)]
    for i, r in enumerate(ordered):
        chunks[i % args.chunks].append(r)

    fieldnames = list(candidates[0].keys()) if candidates else []
    for i, chunk in enumerate(chunks):
        path = os.path.join(args.output_dir, f'chunk_{i:02d}.csv')
        with open(path, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader(); w.writerows(chunk)

    summary = {
        'source_rows': len(rows),
        'candidate_rows': len(candidates),
        'chunks': args.chunks,
        'status_counts': dict(Counter(r['prior_status'] for r in candidates)),
        'chunk_sizes': [len(c) for c in chunks],
    }
    with open(os.path.join(args.output_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
