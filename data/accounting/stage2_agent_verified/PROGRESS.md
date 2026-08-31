# Accounting / Steuerberatung — Stage 2.5 agent verification

Source Stage 2 artifact: `9731550965`
Agent workflow run: `33387687688`

This checkpoint re-researched every prior size candidate with Copilot lead research agents and web-research subagents. Deterministic code is used only to batch inputs, validate the JSON schema, reject impossible scope/count combinations, and merge outputs.

## Result

- Candidates expected: 823
- Valid agent results: 823
- Stage 3 confirmed targets: 192
- Still likely 20+: 281
- Below 20: 4
- Unresolved: 346

Verdict counts: `{"LIKELY_20_PLUS": 281, "UNRESOLVED": 346, "CONFIRMED_30_PLUS": 118, "BELOW_20": 4, "CONFIRMED_20_PLUS": 72, "CONFIRMED_20_29": 2}`

Raw per-company agent evidence is preserved under `raw/`. `stage3_size_verified_targets.csv` is the size-verified hand-off into owner / decision-maker research.
