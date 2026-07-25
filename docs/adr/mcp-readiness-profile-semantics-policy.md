# MCP Readiness Profile Semantics Policy

Status: accepted

## Decision

Pancakes MCP tools must evaluate Make import readiness, parity fixture review, and client handoff
readiness through one shared profile vocabulary. The shared source of truth is
`src/mcp/readiness_profiles.py`; tool handlers may project the profile into output payloads, but
they must not redefine profile behavior locally.

## Profiles

`import_test` is the default profile for `project.import_readiness` and
`project.export_make_blueprint`. It answers whether a local Make-native artifact can be generated
and imported. Missing module and connection notes remain visible as client handoff risk, but they
do not block Make import status or artifact generation.

`parity_fixture` evaluates generated-versus-reexported structure and exposes parity-oriented
summaries. Missing handoff notes are advisory unless they affect zero-trace or native parity
evidence.

`client_handoff` evaluates whether the artifact is ready to hand to a client or operator. Missing
module notes, missing connection notes, weak notes, runtime setup, scenario-test gaps, and delivery
coverage all remain client handoff readiness concerns. Note blockers stop artifact generation in
this profile before zero trace is evaluated.

## Semantics Matrix

| Profile | Notes | Import block | Render block | Handoff | Parity | Compact raw policy |
| --- | --- | --- | --- | --- | --- | --- |
| `import_test` | handoff | no | no | yes | no | grouped only |
| `parity_fixture` | advisory | no | no | yes | yes | grouped only |
| `client_handoff` | handoff | no | yes | yes | no | grouped only |

`strict_handoff_notes=true` remains a legacy alias for `client_handoff` where the export or
readiness tool accepts that flag.

Every profile response that can be partially blocked must name the surface explicitly with
`blocked_surface`, `blocked_surfaces`, `unblocked_surfaces`, and `status_reason`. A client handoff
block with import-safe generation still available must report `blocked_surface=client_handoff`,
keep `import_status=ready`, and include `make_import` in `unblocked_surfaces`.

Stable surface names are `structure`, `make_import`, `client_handoff`, `runtime_setup`,
`zero_trace`, `native_parity`, `scenario_tests`, `artifact_render`, and `catalog_evidence`.
Aggregate labels such as `blocked` or `invalid` must never be the only status when one surface is
blocked and others remain usable.

## Response Contracts

Major MCP outputs expose `response_contract` and `response_schema_version` at the transport
boundary. The current public contracts are `catalog.search`, `project.search`, `project.health`,
`project.view`, the retained node-editor tools for modules, links, filters, and error handlers,
`linter.quarantine.write`, `backlog.add`, `backlog.list`, `backlog.end`, `catalog.next_unit`, and
`catalog.save_unit`.

Version 1 means the original compact shape remains compatible and only bounded additive fields were
added. Version 2 means the contract changed surface semantics, zero-trace tri-state, profile
separation, or compact status names. Version 3 means compact response fields were removed or
renamed to eliminate ambiguous runtime setup or duplicated note surfaces. Do not bump a contract
for bounded additive evidence only. Do bump the affected contract when compact output removes,
renames, or changes the meaning of a field. The registry in `src/mcp/response_contracts.py` is the
single source of truth; tests must compare payload versions against that registry rather than
duplicating ad hoc strings.

## Validation Surfaces

`project.validate_offline` must split aggregate validation into explicit surfaces:

- `structural_validation_status` for graph, schema, catalog, and module resolvability;
- `make_import_validation_status` for Make-importable artifact generation;
- `client_handoff_validation_status` for notes, handoff docs, and operator documentation;
- `runtime_setup_validation_status` for unresolved runtime resources;
- `scenario_tests_status` for local DAMP behavior tests;
- `native_parity_validation_status` for Make-native parity evidence.

Missing handoff notes make `client_handoff_validation_status=invalid`; they must not make
`structural_validation_status` invalid or `make_import_validation_status` non-ready under
`import_test`.

## Zero Trace

Zero trace is a rendered-artifact property. If `client_handoff` blocks before rendering because
handoff notes are incomplete, zero trace must be reported as `not_evaluated`, not as passed or
failed. If an import-test or parity-fixture render succeeds, the rendered artifact must still pass
private-metadata and zero-trace checks before it is reported as generated.

The zero-trace surface is tri-state:

- rendered clean artifact: `zero_trace=true` and `zero_trace_status=passed`;
- rendered private-metadata leak: `zero_trace=false` and `zero_trace_status=failed`;
- pre-render profile or render blocker: `zero_trace=null` and
  `zero_trace_status=not_evaluated`.

`leak_count=0` on a pre-render blocker is not pass evidence. It only means no rendered artifact was
available for leak scanning.

## Compact And Raw Evidence

Compact readiness and export responses must keep exact counts, grouped blockers, grouped missing
notes, grouped runtime setup, grouped module translations, and grouped connection bindings. They
must not dump raw missing-note arrays, raw blocker walls, per-node translation rows, or raw
connection replacement paths by default.

Compact validation responses expose `scenario_notes_summary` as the canonical note surface. Omitted
raw evidence must include availability booleans such as `raw_findings_available`,
`raw_missing_notes_available`, or `raw_replacement_paths_available`, plus a `next_query` hint that
names the full/debug/raw expansion path.

Compact `project.notes.list` returns `scenario_notes_summary`, `batch_note_plan`, and bounded note
review evidence. It must not duplicate the same note summary under `scenario_notes`. Full output or
`include_all=true` may expose raw missing-note detail for local debugging.

Full, debug, or explicit raw flags may expose the narrow evidence needed for local debugging:

- `project.import_readiness output_mode=full` may include verbose setup steps, runtime placeholders,
  and exact replacement paths;
- `project.export_make_blueprint output_mode=full` may include raw blockers, raw handoff-note
  evidence, raw module translation rows, and raw connection binding rows;
- internal evidence ledgers stay hidden unless `include_internal_evidence=true`.

## Black-Box Boundary

Customer-facing and compact MCP output should explain whether local Make import, parity review, or
client handoff is ready without revealing compiler recipes, corpus strategy, private evidence
matrices, raw source material, provider credentials, or internal trace keys. Make-specific quirks
belong under `src/languages/make/**` or MCP presentation helpers; language-neutral product code
must not absorb Slack-only, Make-only, or fixture-only policy.

Pancakes Web uses the public phrase "Automated production-readiness reports for Make.com scenario
blueprints." Web and other customer-facing surfaces must not describe Pancakes as manual
consulting, technical support, a security guarantee, a compliance certification, or human advisory.
They must not show raw spec corpus details, native semantics matrices, scoring recipes, compiler
heuristics, `__IMTCONN__`, or internal runtime resource keys such as `slack_imtconn`.

## Runtime Setup And Credentials

Runtime setup requirements must remain visible in readiness and export responses. They must not
imply that Pancakes called Make.com, called another provider, transferred credential values, or
printed secrets. The local MCP tools must keep `provider_api_call`, `credential_value_transfer`,
`secret_output`, and `live_make_called` false for these offline profile evaluations.

Runtime setup count names are strict:

- `runtime_setup_occurrence_count` counts effective unresolved setup slots after generic binding
  overlaps are collapsed by affected node and setup category;
- `runtime_setup_affected_node_count` counts unique affected module nodes;
- `runtime_setup_distinct_binding_count` counts logical binding surfaces before human grouping;
- `runtime_setup_item_count` counts manual setup items shown to the operator;
- `runtime_setup_group_count` counts grouped human setup categories.

The occurrence count must be greater than or equal to both affected node count and distinct binding
count. Distinct binding count must be greater than or equal to item count and group count. Fixtures
where every binding maps to a separate node may also satisfy affected node count greater than or
equal to distinct binding count; fixtures with multiple resources on one module node may not.
Compact responses must not expose ambiguous `runtime_setup_count`, `runtime_setup_usage_count`, or
`runtime_setup_required_node_count`. A `required_node_count` field is allowed only when it truly
counts unique affected nodes and never when it means logical bindings or setup items. Legacy
compatibility belongs under `deprecated_fields.runtime_setup_count` in full/debug output only, with
`value`, `semantics`, and `replacement`.

When render evaluation differs from import or handoff setup evaluation, responses must use the
surface-scoped `runtime_setup` object. A client-handoff block before render reports
`render_runtime_setup_status=not_evaluated` while still reporting import and handoff setup as
`required` when runtime resources remain unresolved.

## Repair Priority

`project.next_step` and `project.repair_plan` must share one surface-priority decision. Structure
and catalog evidence come first, Make import repair comes before zero-trace leak repair when both
are blocked, native parity and runtime setup follow, client handoff follows runtime setup, and
optimization remains last. When the only blocked surface is `client_handoff` and `make_import` is
ready, both tools must choose `client_handoff`, recommend `project.notes.list`, include the batch
note plan, and state that import-safe artifact generation remains available. Generic webhook,
raw-spec, error-handler, or optimization guidance must not lead a handoff-only repair plan.

## Validation

Profile semantics are directly covered by
`tests/mcp/tool_contracts/mcp_readiness_profile_semantics_contract.py`. Tool-level contracts also
verify that export and import-readiness payloads report matching status semantics for the same
profile. `tests/mcp/tool_contracts/mcp_response_contracts_contract.py` covers response metadata and
impossible-state invariants, and `tests/mcp/tool_contracts/mcp_local_smoke_contract.py` is the
canonical local/offline smoke profile.
