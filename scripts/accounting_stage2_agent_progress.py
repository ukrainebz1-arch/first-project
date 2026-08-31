#!/usr/bin/env python3
import argparse, json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--summary', required=True)
ap.add_argument('--output', required=True)
ap.add_argument('--run-id', required=True)
args = ap.parse_args()

s = json.loads(Path(args.summary).read_text(encoding='utf-8'))
text = f"""# Accounting / Steuerberatung — Stage 2.5 agent verification

Source Stage 2 artifact: `9731550965`
Agent workflow run: `{args.run_id}`

This checkpoint re-researched every prior size candidate with Copilot lead research agents and web-research subagents. Deterministic code is used only to batch inputs, validate the JSON schema, reject impossible scope/count combinations, and merge outputs.

## Result

- Candidates expected: {s['candidate_expected']}
- Valid agent results: {s['agent_results_valid']}
- Stage 3 confirmed targets: {s['stage3_confirmed_targets']}
- Still likely 20+: {s['still_likely_20plus']}
- Below 20: {s['below_20']}
- Unresolved: {s['unresolved']}

Verdict counts: `{json.dumps(s['verdict_counts'], ensure_ascii=False)}`

Raw per-company agent evidence is preserved under `raw/`. `stage3_size_verified_targets.csv` is the size-verified hand-off into owner / decision-maker research.
"""
Path(args.output).write_text(text, encoding='utf-8')
print(text)
