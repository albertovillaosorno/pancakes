# Pancakes Test Runtime Profile Report

## Status

Accepted

## Scope

repository/tests-runtime

## Baseline

The canonical `pancakes.test` run initially failed because the command profile used root-level
pytest cache and temporary paths that were inaccessible from the Pancakes worktree. After moving
pytest cache and base temp paths to repo-local ignored paths, the full suite completed with one
test isolation failure:

- result: 1201 passed, 2 skipped, 1 failed;
- runtime: 12:22;
- failure: remote MCP missing-password test discovered the real Schoenwald root `.env`.

The isolation failure was fixed by running that test inside a synthetic operator root with no
`.env` and explicitly deleting `REMOTE_MCP_OPERATOR_PASSWORD` from the test environment.

## Slowest Tests

A clean no-coverage profiling pass after the isolation fix reported:

- result: 1202 passed, 2 skipped;
- runtime: 10:38.

The slowest individual tests were:

- `test_lead_ops_mega_readiness_profiles_are_compact_and_consistent`: 383.84s;
- `test_lead_ops_mega_blueprint_query_outline_stays_bounded`: 136.15s;
- `test_stress_scenario_factory_generates_lead_ops_ladder`: 40.69s;
- `test_stress_scenario_factory_generates_large_compact_draft`: 16.19s.

## Cause

The slow tests are meaningful integration coverage around 202-node and 302-node Make stress
scenarios. The accidental overhead was repeated validation-state computation and repeated
knowledge SQLite query loading for the same project draft during one process.

The original 302-node probe showed repeated calls near these timings:

- stress generation: 134s;
- import-test export: 52s;
- client-handoff export: 48s;
- import readiness: 48s;
- handoff readiness: 48s;
- compact validation: 48s.

## Optimization

The MCP project loop now caches project validation state by repo root, scenario path, scenario
mtime, scenario size, and scenario-test file stats. It also caches knowledge-store query
projections by repo root, structural-facts flag, database mtime, and database size.

After caching, the same 302-node probe improved to:

- stress generation: 53.69s;
- import-test export after note removal: 8.20s;
- client-handoff export: 0.03s;
- import and handoff readiness: 0.09s;
- compact validation: 0.01s.

## Canonical Profile

The four deliberately slow MCP stress integration tests are marked `slow_integration`. The default
`pancakes.test` command excludes that marker and keeps the canonical local test profile below three
minutes. The `pancakes.pre-push` profile still includes the slow integration tests for full local
release confidence.

Latest default canonical result:

- `pancakes.lint`: passed;
- `pancakes.typecheck`: passed;
- `pancakes.test`: 1198 passed, 2 skipped, 4 deselected;
- runtime: 1:45.

Coverage was not deleted. Slow integration coverage remains present, named, and runnable through
the pre-push profile.

## Current Profile

The 2026-05-16 profiling pass mirrored `pancakes.test` with the same sanitized operator
environment, repo-local pytest cache, repo-local base temp path, coverage settings, and
`not slow_integration` marker expression, then added pytest duration reporting.

Current result:

- `pancakes.test`: 1213 passed, 2 skipped, 4 deselected;
- runtime: 96.08s;
- coverage: 87.69%;
- provider and live Make posture: preserved as local-only, with provider credentials sanitized by
  the command environment.

Top slow files, aggregated from the 160 captured duration entries:

- `mcp/tool_contracts/mcp_http_contract.py`: 11.09s;
- `mcp/tool_contracts/mcp_oauth_redirect_uri_contract.py`: 7.67s;
- `mcp/tool_contracts/mcp_scenario_builder_contract.py`: 4.86s;
- `catalog/knowledge_store_contract.py`: 3.75s;
- `mcp/tool_contracts/mcp_server_contract.py`: 3.69s;
- `mcp/tool_contracts/mcp_diff_blueprint_giant_fixture_contract.py`: 3.50s;
- `mcp/tool_contracts/mcp_http_body_limits_contract.py`: 3.19s;
- `mcp/tool_contracts/mcp_oauth_http_contract.py`: 3.08s.

Top individual test calls:

- `mcp_diff_blueprint_giant_fixture_contract.py::`
  `test_blueprint_diff_classifies_giant_corrupted_make_native_fixture`: 3.50s;
- `test_compilation_phase_gates.py::test_render_phase_runs_importability_gate_before_handoff`:
  1.27s;
- `mcp_http_contract.py::test_remote_mcp_http_oauth_clients_survive_origin_restart`: 1.05s;
- `mcp_http_body_limits_contract.py::test_remote_mcp_http_accepts_bounded_json_and_form_content_types`:
  0.64s;
- `mcp_http_contract.py::test_remote_mcp_http_exposes_context_indexes_before_login`: 0.61s;
- `catalog_source_ranking_contract.py::test_scenario_builder_module_payloads_label_knowledge_and_fallback_sources`:
  0.59s.

Slow fixture/setup evidence:

- `blueprint_ast_contract.py::test_make_ast_blueprint_bundles_persist_under_data` setup: 0.60s;
- no repeated raw-spec loading, generated stress fixture setup, or catalog SQLite rebuild setup
  appeared above 0.01s in the captured setup entries;
- the remaining slow time is dominated by call-phase HTTP/OAuth contract coverage rather than
  fixture setup.

## Current Cause

The deliberately slow MCP stress tests remain outside the default `pancakes.test` profile. The
current fast-profile cost is concentrated in remote MCP HTTP and OAuth contract tests. Those tests
are meaningful integration coverage: they exercise OAuth metadata, redirect URI validation, PKCE,
operator password gating, malformed token requests, malformed registration, cache headers, origin
restart behavior, and tool authorization posture.

The likely accidental overhead is repeated local HTTP/OAuth harness setup inside many sub-second
contract tests. Each individual test is under the two-second budget except the giant diff fixture,
but the HTTP/OAuth group contributes the largest aggregate runtime because it repeats similar local
server, client, and OAuth state setup across many cases.

## Next Optimization Patch

The next safe patch should target the MCP HTTP/OAuth contract harness, not coverage removal.

Recommended patch:

- introduce a reusable local HTTP/OAuth test harness fixture for the remote MCP contract tests;
- keep per-test isolation by resetting client, token, and authorization state between cases;
- avoid live provider calls and keep root `.env` values sanitized;
- reuse immutable server metadata and local app context where the test does not mutate it;
- keep redirect URI, PKCE, password-gate, malformed request, no-store, and authorization challenge
  assertions intact;
- rerun `pancakes.lint`, `pancakes.typecheck`, and `pancakes.test` with duration reporting.

Coverage that must not be removed:

- giant blueprint diff regression coverage;
- render-phase importability gating;
- remote MCP OAuth metadata, dynamic client registration, PKCE, redirect URI, token, no-store, and
  authorization failure contracts;
- provider-call and live Make disabled guarantees;
- slow integration stress coverage in the pre-push profile.
