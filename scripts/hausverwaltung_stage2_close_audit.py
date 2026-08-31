import csv
import json
import os
import re
import unicodedata

OUTDIR = 'data/hausverwaltung/size_agent_first'
FINAL = f'{OUTDIR}/size_agent_first_final_2026-08-31.csv'
CORE_OUT = f'{OUTDIR}/core_sales_targets_agent_first_2026-08-31.csv'
SUMMARY = f'{OUTDIR}/summary_agent_first_final_2026-08-31.json'
AUDIT = f'{OUTDIR}/final_audit_decisions_2026-08-31.tsv'

CORE = {
    'A_CORE_30_PLUS_DIRECT',
    'B_CORE_30_PLUS_GROUP',
    'C_CORE_20_PLUS_RANGE',
    'D_CORE_RECALL_11_30',
}


def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = s.replace('&', ' und ')
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


# Final seven audit cases. These overwrite any stale strict-baseline class.
DECISIONS = {
    norm('IMMOTOTAL Immobilientreuhand GmbH'): {
        'agent_class': 'EXCLUDE_SMALL',
        'scope': 'exclude',
        'decision_reason': 'final agent audit: LinkedIn employer size is 2-10; multi-office footprint was a false size signal',
        'agent_evidence_url': 'https://at.linkedin.com/company/immototal',
        'confidence': 'high',
    },
    norm('International Campus Austria GmbH'): {
        'agent_class': 'E_ADJACENT_30_PLUS',
        'scope': 'adjacent',
        'decision_reason': 'final agent audit: 101-500 employer, but student-housing development/operator platform rather than classic external Hausverwaltung',
        'agent_evidence_url': 'https://www.karriere.at/f/international-campus-austria',
        'confidence': 'high',
    },
    norm('Salinen Immobilien Gesellschaft m.b.H.'): {
        'agent_class': 'E_ADJACENT_30_PLUS',
        'scope': 'adjacent',
        'decision_reason': 'final agent audit: property entity inside the 580-employee Salinen group; internal/group real-estate operation rather than classic external Hausverwaltung',
        'agent_evidence_url': 'https://www.salinen.com/de/unternehmen/salinen-gruppe/salinen-austria-ag/',
        'confidence': 'high',
    },
    norm('Verein zur Förderung der Expertis Gruppe - BBRZ BFI FAB'): {
        'agent_class': 'EXCLUDE_NON_CORE',
        'scope': 'exclude',
        'decision_reason': 'final agent audit: social/employment/education organisation; not a Hausverwaltung sales target',
        'agent_evidence_url': 'https://www.fab.at/de/',
        'confidence': 'high',
    },
    norm('GOLDBECK Parking GmbH'): {
        'agent_class': 'EXCLUDE_NON_CORE',
        'scope': 'exclude',
        'decision_reason': 'final agent audit: operating business is parking/garage and mobility services; Immobilienverwaltung licence is ancillary, not the target Hausverwaltung model',
        'agent_evidence_url': 'https://www.goldbeck-parking.at/',
        'confidence': 'high',
    },
    norm('IBT Verwaltung GmbH'): {
        'agent_class': 'EXCLUDE_NON_CORE',
        'scope': 'exclude',
        'decision_reason': 'final agent audit: official company purpose is Verwaltung eigenen Vermögens; internal asset-holding/administration rather than external Hausverwaltung',
        'agent_evidence_url': 'https://www.evi.gv.at/f/210191f',
        'confidence': 'high',
    },
    norm('IVB-Immobilienvermarktung und Bauträger Ges.m.b.H.'): {
        'agent_class': 'D_CORE_RECALL_11_30',
        'scope': 'core',
        'decision_reason': 'final agent audit: 11-30 employees, 15-company real-estate group, ~50 properties, and explicit WKO Immobilienverwalter licence; retain for sales recall despite owner/operator profile',
        'agent_evidence_url': 'https://www.karriere.at/f/ivb-immobilienvermarktung-bautr%C3%A4ger',
        'confidence': 'high',
    },
}

rows = list(csv.DictReader(open(FINAL, encoding='utf-8-sig', newline='')))
assert len(rows) == 1780, f'Expected 1780 canonical companies, got {len(rows)}'

seen = set()
audit_rows = []
for r in rows:
    k = norm(r.get('company_name', ''))
    d = DECISIONS.get(k)
    if not d:
        continue
    seen.add(k)
    before = r.get('agent_class', '')
    r.update(d)
    r['sales_include'] = 'yes' if r['agent_class'] in CORE else 'no'
    audit_rows.append({
        'company_name': r.get('company_name', ''),
        'before_class': before,
        'after_class': r['agent_class'],
        'sales_include': r['sales_include'],
        'decision_reason': r['decision_reason'],
        'agent_evidence_url': r['agent_evidence_url'],
    })

missing = [k for k in DECISIONS if k not in seen]
assert not missing, f'Audit decisions did not match dataset rows: {missing}'

# Refresh sales flag globally in case any previous row was stale.
for r in rows:
    r['sales_include'] = 'yes' if r.get('agent_class') in CORE else 'no'

fields = list(rows[0].keys())
with open(FINAL, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

core = [r for r in rows if r['sales_include'] == 'yes']
adj = [r for r in rows if r.get('agent_class') == 'E_ADJACENT_30_PLUS']

core_fields = [
    'company_name', 'agent_class', 'group_key', 'states_seen', 'wko_standort_count',
    'website', 'size_class_strict_v2', 'decision_reason', 'agent_evidence_url', 'confidence'
]
with open(CORE_OUT, 'w', encoding='utf-8-sig', newline='') as f:
    w = csv.DictWriter(f, fieldnames=core_fields)
    w.writeheader()
    w.writerows([{k: r.get(k, '') for k in core_fields} for r in core])

with open(AUDIT, 'w', encoding='utf-8', newline='') as f:
    af = ['company_name', 'before_class', 'after_class', 'sales_include', 'decision_reason', 'agent_evidence_url']
    w = csv.DictWriter(f, fieldnames=af, delimiter='\t')
    w.writeheader()
    w.writerows(audit_rows)

counts = {}
for r in rows:
    counts[r.get('agent_class', '')] = counts.get(r.get('agent_class', ''), 0) + 1

core_groups = {norm(r.get('group_key') or r.get('company_name', '')) for r in core}
adj_groups = {norm(r.get('group_key') or r.get('company_name', '')) for r in adj}
baseline_core = [
    r for r in core
    if (r.get('decision_reason') or '').startswith('baseline strict signal retained')
]

summary = {
    'total_canonical_companies': len(rows),
    'class_counts': dict(sorted(counts.items())),
    'core_sales_target_legal_entities': len(core),
    'core_sales_target_outreach_groups': len(core_groups),
    'adjacent_30plus_legal_entities': len(adj),
    'adjacent_30plus_groups': len(adj_groups),
    'core_definition': 'A direct 30+ OR B group 30+ OR C direct 20+ range OR D agent-first recall 11-30/credible operational team; optimized for sales recall, not statistical purity',
    'final_audit_cases_closed': len(audit_rows),
    'unresolved_core_baseline_rows': len(baseline_core),
    'stage2_status': 'FINAL' if not baseline_core else 'NEEDS_REVIEW',
    'stage3_started': False,
}

assert len(core) == 62, f'Expected 62 final core legal entities, got {len(core)}'
assert len(baseline_core) == 0, f'Core still contains stale baseline-only rows: {[r.get("company_name") for r in baseline_core]}'

with open(SUMMARY, 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print(json.dumps(summary, ensure_ascii=False, indent=2))
