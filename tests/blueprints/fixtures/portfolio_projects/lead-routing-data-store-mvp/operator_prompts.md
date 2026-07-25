# Lead-Routing Operator Prompts

## 1) Build or edit project JSON from requirements

- Use `project.create` only for new IDs.
- Work directly on `projects/lead-routing-data-store-mvp/scenario.json` via
  `project.read_json` and `project.write_json`.
- Never treat `catalog.search` as the source of truth. It is advisory-only and only for ideas.
- Never inject `catalog.search` output into the local LLM operating context as a mandatory signal.
- If an exact module is needed, run:
  - `scenario.modules.search`
  - `scenario.modules.expand` on the chosen result.
- Do not invent Make modules or fake module IDs.

## 2) Read current project JSON and propose a minimal patch

- Load current state with `project.read_json`.
- Make the smallest patch needed for a single finding:
  - one required field
  - one missing mapping
  - or one route filter adjustment.
- Apply via JSON merge patch first; keep unrelated fields unchanged.
- Keep fake placeholders where runtime values are required.

## 3) Fix `project.validate_offline` findings

- Run `project.validate_offline`.
- Use `validation_summary.next_actions` as your action list.
- Prioritize:
  1. missing module replacements
  2. required-parameter mappings
  3. runtime configuration blockers.
- Keep changes minimal and re-run offline validation after each patch.

## 4) Replace unresolved module tokens

- For each unresolved token in `missing_module_blockers`, replace with an exact catalog-backed
  module ID or token pair from `scenario.modules.search/expand`.
- Confirm that replacements produce `module_id` matches in `catalog_backed_module_status`.
- Keep `module` fields realistic; do not create or invent module IDs.
- Do not use `catalog.search` output as the replacement source unless the missing module is
  backed by explicit catalog resolution.

## 5) Keep runtime placeholders, avoid fake credentials

- Use placeholders like `{{runtime.webhook.*}}` and `{{runtime.datastore.*}}`.
- Do not insert API keys, webhooks, bearer tokens, account IDs, or session values in this draft.
- Do not call live Make here.

## 6) Prepare portfolio screenshot notes

- After offline-valid result, capture:
  - `make-demo-canvas.png` (topology and routing intent)
  - `make-demo-input-output-table.png` (fake inputs + expected routes)
  - `make-demo-handoff-sample.pdf` (validation summary and next actions)
- Keep notes centered on:
  - branching by validation criteria
  - required fields
  - runtime placeholder handoff
  - `live_make_called` and `credentials_required` signals
