# Hausverwaltung Stage 4 — machine discovery checkpoint

Source of truth input: `data/hausverwaltung/stage3_owners/stage3_master_99.csv`.

This checkpoint is **not** the final Stage 4. Automated discovery is conservative: search snippets are evidence only, central numbers are fallback only, and guessed e-mails are never verified. `manual_review_queue.csv` / `manual_overrides.csv` must be completed by agent/manual verification before `stage4_master_99.csv` can be emitted and the final quality gate can pass.

Files:
- `stage4_machine_master_99.csv` — 99-row machine checkpoint
- `machine_evidence.csv` — raw/candidate public evidence
- `manual_review_queue.csv` — ordered MAIN-first verification queue
- `manual_overrides.csv` — editable curated override layer
- `chunks/` — persisted worker checkpoints
- `summary.json` — machine-pass metrics and explicit non-final gate
