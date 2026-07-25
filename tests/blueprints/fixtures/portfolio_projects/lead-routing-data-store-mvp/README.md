# Lead Routing Data Store MVP

This is a tracked, sanitized portfolio fixture for the Make JSON IDE loop.

## Purpose

- Show a fake lead-intake flow built entirely in local JSON.
- Route leads into separate destinations by validation and score branching.
  - Qualified: required fields present and `score >= 80`
  - Incomplete: required field missing or `score < 80`
- Persist both branches into Make Data Store AddRecord destinations.

## File Boundary

This README covers the tracked portfolio fixture folder:
`tests/blueprints/fixtures/portfolio_projects/lead-routing-data-store-mvp`.

The folder is documentation and validation fixture context only. It must remain
fake-data-only, with no secrets, no credentials, and no live account
identifiers. Runtime execution readiness is handled separately by offline
validation blockers.

## Safety

- No fake webhook URLs, API keys, tokens, session values, connection IDs,
  account IDs, or private data are present in this folder.
- `live_make_called` must stay `false` for the offline loop.
- `credentials_required` must stay `false` for offline validation.
- `catalog.search` remains advisory; it is not required for the project.create/read_json/write_json/validate_offline workflow.

## Runtime setup

Replace these placeholders before live execution:

- `{{runtime.webhook.lead_intake_hook}}`
- `{{runtime.datastore.qualified_leads}}`
- `{{runtime.datastore.incomplete_leads}}`

## Offline workflow

- Use this fixture as source material for tests or for a generated local draft
  under `projects/<project_id>/scenario.json`.
- `project.create` and `project.read_json` provide deterministic local state in
  generated project workspaces.
- `project.write_json` must reject malformed JSON.
- `project.validate_offline` must report for generated drafts:
  - no missing module blockers
  - no fake-module blockers
  - runtime configuration setup requirements for placeholders
  - actionable `validation_summary` next actions

## Operator support files

- `operator_prompts.md`: reusable LLM/operator prompt pack for this demo.
- `sample_payloads.json`: fake inputs for route walkthrough.
- `expected_outputs.json`: route expectation table for screenshot/data notes.
- `validation_checklist.md`: short pre-delivery review checklist.

## Runbook and smoke checks

- Canonical operator runbook:
  - `src/mcp/README.md`
- Fast smoke:
  - `uv run pytest tests/mcp/tool_contracts/mcp_server_contract.py -k lead_routing`
  - `uv run pytest tests/mcp/tool_contracts/mcp_server_contract.py -k project_json_loop`

## Live handoff

When runtime placeholders and missing blockers are resolved, transition to
operator-gated live validation and Make execution. Do not use real credentials or
live webhooks in the offline draft.
