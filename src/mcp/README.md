# Pancakes MCP

ADR: `docs/adr/catalog-semantic-graph-preview-policy.md`.

The Pancakes MCP is intentionally small, but it is an agent IDE for local Make.com scenario work.
It exposes catalog lookup, catalog work-loop development tools, backlog intake, one linter
quarantine intake tool, guarded linter rule editor tools, bounded project views, semantic project
edits, local verification, Make-native artifact previews, and local Make import packages.

This is a Make.com scenario-oriented local product surface, not a general repository
administration API. Generic JSON read/write, JSON patch, scenario workspace, scenario command,
project test, and scraper refresh tools are not public MCP tools. Make artifact behavior is
exposed through `project.make`, not old blueprint tool families. Future Upwork proposal or
portfolio helpers require a separate ADR.

Pancakes does not track external MCP client configuration such as `.cursor/mcp.json`. Startup is a
repository-local startup contract, and any operator-provided public base URL or client config must
stay local.

SQLite is the source of truth:

- Pancakes Core data lives in `src/data/pancakes.sqlite`.
- Local project technical metadata lives in `src/data/pancakes.sqlite` table
  `local_project_metadata`.
- Business lifecycle, billing, delivery, customer, and dashboard state lives outside Pancakes MCP.
  This MCP does not read or write the Schoenwald SRE business database.
- Markdown, JSON, and SQL snapshots are restore or operator evidence only. They are not active
  ledgers.

SQLite timeout policy:

- Routine public MCP reads such as `catalog.search` and `catalog.inspect` use read-only SQLite URI
  handles, `PRAGMA query_only = ON`, shared cache, and a 5-second busy timeout.
- Lock contention returns a `sqlite_read_busy_timeout` blocked payload with a retry or lock-owner
  inspection recommendation instead of waiting indefinitely.
- Slow SQLite waits are reserved for explicit offline maintenance commands such as catalog rebuild,
  raw-spec refresh, or evidence synchronization. Public MCP read tools do not enter slow
  maintenance mode.

## Public Tools

- `mcp.session.start`
- `catalog.index`
- `catalog.search`
- `catalog.inspect`
- `catalog.modify`
- `catalog.node.modify`
- `catalog.edge.propose`
- `catalog.edge.apply`
- `catalog.review.add`
- `project.search`
- `project.draft.stage`
- `project.draft.import`
- `project.create`
- `project.health`
- `project.view`
- `project.edit`
- `project.verify`
- `project.capabilities.inspect`
- `project.make`
- `project.package.inspect`
- `project.next`
- `project.modules.view`
- `project.modules.add`
- `project.modules.modify`
- `project.modules.delete`
- `project.links.view`
- `project.filters.view`
- `project.filters.add`
- `project.filters.modify`
- `project.filters.delete`
- `project.error_handlers.view`
- `project.error_handlers.add`
- `project.error_handlers.modify`
- `project.error_handlers.delete`
- `linter.quarantine.write`
- `linter.rule.next`
- `linter.rule.inspect`
- `linter.rule.implement`
- `linter.rule.merge_canonical`
- `linter.rule.reject_invalid`
- `linter.rule.edit`
- `linter.rule.status`
- `linter.rule.rollback`
- `backlog.add`
- `backlog.list`
- `backlog.end`

`Catalog Intelligence` is the explicit catalog ingestion worker prompt. It uses `catalog.work.next`
to lease local SQLite work batches, `catalog.graph.search` and `catalog.semantic.preview` to inspect
existing and proposed graph coverage, and `catalog.work.save` to atomically save the complete leased
batch. The accepted legacy operator alias is `Catalog Work`. The canonical technical placeholder index lives in
`src/catalog/placeholder_index.py`; finite catalog value sets live in `src/catalog/value_index.py`.
Both indexes remain available through `catalog.index` and `catalog.search` when worker output needs
canonical placeholders or finite values.

`catalog.work.next` and `catalog.work.save` are explicit write-scoped semantic refill tools. They
are local-only, require a lease handle for saves, and `catalog.work.next` must not implicitly create
a fresh catalog run from raw specs. A new refill queue requires the explicit
`initialize_if_missing=true` argument. Normal lease payloads use safety-shaped source packet
summaries so ChatGPT.com can read worker batches without receiving raw credential-looking schema
keys. Exact raw source remains addressable by `source_ref` and `source_hash`; complete packets are
reserved for local debugging. The legacy `catalog.next_unit` / `catalog.save_unit` aliases remain
inactive and are not registered or dispatchable MCP tools.

`catalog.semantic.preview` is the read-only pre-save companion for the explicit semantic refill
loop. It validates proposed `catalog.work.save` payloads against the same graph/value constraints,
checks graph density and disconnected edges, and previews compact SQLite search matches before the
worker commits a full leased batch atomically.

`project.search` reads only repository-local Make scenario drafts, fixture projects, template
libraries, and SQLite technical metadata. It never reads external SRE business state, provider
state, web dashboard state, credentials, or customer lifecycle records. Local scenario drafts are
classified as `project_kind=local_scenario_project`. Local template libraries are classified as
`project_kind=template_library` and are hidden from normal project search unless callers pass
`include_templates=true` or filter for that kind.

`project.draft.stage` is the public intake bridge from a short workflow summary to a local staged
JSON draft. It does not accept raw blueprint JSON. `dry_run=true` validates the summary, computes
the staged path and SHA-256 guard, and writes nothing. Non-dry-run writes exactly one local intake
draft under `temp/pancakes/project-intake/`; the returned `next_queries` call `project.create` with
only `staged_draft_path` and `staged_draft_sha256`.

`project.draft.import` is the public intake bridge from an existing local JSON artifact to a staged
draft. It accepts only an approved local path plus an optional SHA-256 guard, scans the local JSON
for secret-like values, and writes a normalized staged draft only when the scan passes. It does not
accept raw JSON arguments and its `next_queries` call `project.create` with only the staged path and
hash.

`project.create` writes new local scenario projects as SQLite-backed artifact envelopes. The
technical identity row lives in `local_project_metadata`; generated files live under
`temp/pancakes/project-artifacts/<workspace-folder-key>/<scenario-or-product-key>-<project-slug>/`
from the Schoenwald generated-state root. The default neutral keys are `local-demo` and `0001`.
Legacy one-level drafts at
`projects/<project_id>/scenario.json` remain readable as migration fixtures, but they are reported
as `legacy_folder_without_sqlite_metadata` rather than as the preferred new storage shape. Legacy
artifact reports include a migration plan: create a SQLite metadata envelope, copy the scenario into
`temp/pancakes/project-artifacts/`, validate the migrated project, then remove the repo-local
`projects/<project_id>` folder.
Public ChatGPT-facing descriptors must not ask the model to paste raw draft JSON or sensitive
literals into MCP tool arguments. For imports, stage the JSON under
`temp/pancakes/project-intake/` and pass `staged_draft_path`. `project.create` imports that local
draft through the Make adapter, writes the normalized AST to `scenario.json` as the editable
authority, and stores the original upload separately as bounded local import evidence.

`mcp.session.start` returns a process-local session intent receipt for typed local work. It writes
no files, writes no SQLite rows, calls no remote workspace, reads no credentials, and grants no
provider authorization. Local write tools may echo validated session scope metadata when callers
include its `session_intent_id` and `session_token`, but their normal tool-specific guards still
own the actual mutation decision.

## Write Boundary

The only write-like tool families in this boundary are project node edits, local project draft
creation, local Make artifact projection writes, local package writes, linter quarantine intake,
guarded linter rule editor dispositions, backlog intake/end, and the development-only catalog
semantic loop. Business lifecycle, delivery, dashboard, payment, and customer writes are not
Pancakes MCP tools.

## Agent IDE Contract

`project.view` is the normal read surface. It supports bounded `overview`, `graph`, `modules`,
`links`, `filters`, `error_handlers`, `runtime`, `datastores`, `notes`, `make_blueprint`,
`readiness`, `parity`, `issues`, `lineage`, `layout`, and `raw` surfaces. Compact output must hide
omitted counts and expose structured `next_queries` instead of dumping hundreds of nodes or raw
JSON.

`link_count` means deduped semantic execution links. Full/debug diagnostics may expose
`raw_route_and_flow_edge_count` for pre-dedupe route/flow visibility; the stress fixture drops from
331 raw edge views to 301 semantic handoff links because route-entry links and duplicate flow
edges are counted once for handoff note requirements.

`project.edit` is the normal write surface for modules, filters, error handlers, notes, and local
datastore manifests. The granular `project.modules.*`, `project.filters.*`, and
`project.error_handlers.*` tools remain compatibility wrappers and focused editor primitives; they
are not generic JSON editors.

`project.verify` is deterministic local verification only. Local tests do not claim external Make
runtime truth. `project.make` previews, renders, writes, or packages local Make-native projections
and never imports into Make.com. `project.package.inspect` is the read-only sectioned package
inspector for `live_resources`, `blueprint_summary`, `parity_plan`, `customer_files`, and
`zero_trace`; package responses expose inspector queries for every section so chat clients do not
need to render a truncation-prone full package payload.
`project.verify output_mode=micro` returns counts, statuses, and top blockers only. Compact verify
responses keep linter and capability details behind counts and follow-up queries; full/debug
responses retain diagnostic detail. Use
`project.capabilities.inspect` when a worker needs the detailed Make.com MCP capability matrix.

`linter.rule.next`, `linter.rule.inspect`, `linter.rule.implement`,
`linter.rule.merge_canonical`, `linter.rule.reject_invalid`, `linter.rule.edit`,
`linter.rule.status`, and `linter.rule.rollback` are local direct-editor infrastructure for
reviewing linter quarantine candidates. They use leases, structured engineering memos, AST guards,
required pass/fail test evidence, severity downgrade checks, canonical-equivalence proof, invalid
artifact proof, SQLite snapshot invariants, and repository commit guards. They do not expose raw
SQL, do not expose a raw file editor, do not call live Make.com or providers, do not read secrets,
and do not push.

`project.make action=package` creates a local `make_import_package` for a gated Make.com MCP or
live bridge. Compact package output is an executive index with statuses, counts, capability gaps,
and structured `next_queries`; full/debug output exposes detailed datastore manifests, runtime
resource requirements, live apply plan, rollback plan, operator checklist, note/PDF inputs, and
zero-trace evidence. Package responses do not use bare `status=ready`; package status is scoped as
`status=package_ready|package_blocked|package_written` with `status_surface=local_package` and a
`status_reason` when live-validation surfaces differ.

Package readiness surfaces are intentionally separate:

- `package_status`: local package readiness.
- `minimal_import_package_status`: whether the blueprint and required manifests can be handed to
  Make.com MCP for basic import with operator mapping.
- `live_preflight_status`: local preflight readiness plus declared Make.com MCP gaps.
- `full_live_validation_status`: whether the complete live flow can run, including import, resource
  binding, module inspection, auto-align, run-once, export, and parity evidence.

Capability summaries distinguish missing capabilities by surface. A capability can be noncritical
for minimal import and still block full live validation. Full/debug payloads expose capability
details with enum-like capability IDs, owning layer, fallback strategy, minimal/full requirements,
and mapped live tool names when a Make.com MCP tool exists. Pancakes prepares local truth and
packages only; Make.com MCP owns live scenario import, Data Store creation, record mutation, module
inspection, run-once execution, and future browser/auto-align validation after explicit operator
approval.

`live_apply_package` is an available guarded live-bridge contract, not an automatic Pancakes Core
live writer. Typed-MCP evidence proves a zero-trace `project.make` package can pass Make blueprint
schema validation, create an inactive scratch scenario, export and inspect it, then delete it back
to zero scratch scenarios. The bridge is ready for a gated live worker to dry-run against an
inactive scratch scenario, receive explicit operator approval, apply the package through composed
Make.com API/MCP capabilities, export/inspect the result, and follow the rollback plan. The
contract requires scenario import, scenario interface update, module configuration validation,
Data Store create/select, connection metadata and binding, webhook create/select and binding,
scenario inspect/export, dry-run-first behavior, zero automatic run-once budget, and no scenario
activation. Scenario create uses Make's
observed API contract:
`blueprint` and `scheduling` are JSON strings, the created ID is read from `$.scenario.id`,
exported blueprints are read from `$.response.blueprint`, and delete confirmation returns
`$.scenario`.

Module configuration validation has observed typed-MCP live evidence. The bridge uses
`validate_module_configuration` before import/apply to detect module-specific required mapper
fields and to retrieve schema response shapes without creating scenarios, activating scenarios,
running scenarios, or transferring credentials. The Parse JSON live probe proves a missing
`mapper.json` field is returned as a required `expect.json` validation error, while valid mapper
input returns default and expect schema metadata. Local validation mirrors this as catalog-backed
required-field evidence rather than treating Make's `isinvalid` scenario flag as an oracle.

Run-once validation has observed typed-MCP live evidence and remains a separately approved
operation. `scenarios_run` rejects inactive scenarios, so a live worker must activate only a
disposable scratch scenario, run it responsively, inspect `executions_list` for status, operation,
credit, duration, and transfer shapes, then deactivate and delete the scratch scenario. Pancakes
stores only sanitized response shapes and keeps routine local package/preflight output at zero
automatic run-once budget.

Webhook configuration validation has observed typed-MCP evidence. Gateway webhook creation must
validate the required default boolean fields `headers`, `method`, and `stringify` before hook
creation; empty config is rejected by `validate_hook_configuration`, while all-three false is
accepted. This evidence is kept as config shape only, not as webhook URL or credential output.

Scenario interface update has observed typed-MCP live evidence. Required scenario inputs cannot be
set while the scratch scenario uses immediate scheduling; Make returns a required-input scheduling
error. The live bridge must switch the scratch scenario to `scheduling.type=on-demand` before
calling `scenarios_set_interface`, then verify the roundtrip through `scenarios_interface` and
exported `blueprint.interface`. This is a typed operation, not a raw blueprint edit.

Connection and webhook binding are typed bridge contracts. Inputs are references only: project,
package, inactive scratch scenario, imported module id, and operator-selected connection/webhook
metadata references. Credential values, API keys, passwords, access tokens, refresh tokens, and
secrets are forbidden inputs. Dry-run is mandatory before apply, apply requires an approval token,
and failed or missing Make.com MCP bind capability returns `make_mcp_bind_capability_missing`
instead of falling back to raw JSON edits or secret transfer.
Connection and webhook binding have observed typed-MCP live evidence. Connection binding lists
redacted connection metadata, extracts the `google-email:sendAnEmail` account target, binds an
inactive scratch scenario through `flow[0].parameters.__IMTCONN__`, verifies the exported scenario,
and cleans up to zero scratch scenarios without transferring credential values. Webhook binding can
create a `gateway-webhook`, bind it to an inactive `gateway:CustomWebHook` scenario through
`flow[0].parameters.hook`, verify scenario export and hook metadata, then clean up to zero scratch
hooks and scenarios.

Runtime-resource requirement extraction also has observed typed-MCP live evidence. Inactive
scratch imports with empty `gateway:CustomWebHook.parameters` and empty
`datastore:AddRecord.parameters` remain exportable and `isinvalid=false`, so local preflight cannot
use `isinvalid` as the requirement oracle. Pancakes mirrors Make's component extraction locally:
missing webhook targets are exposed as `hook` requirements, missing Data Store targets are exposed
as `datastore` requirements, and local package/preflight responses surface them as operator-mapped
runtime resources before live apply.

Live/browser parity is represented as offline engine evidence, never as routine browser execution.
Live-preflight verify/package responses expose
`browser_validation_status=offline_parity_no_browser_required`. Scenario auto-align is mirrored by
the deterministic local designer-layout planner, and module-error inspection is mirrored by local
linter findings plus reviewed designer-message ingest. The old zero-operation Browser smoke plan is
retained only as manual proof-limitation evidence, not as a technical package blocker. Pancakes does
not open a browser, call Make.com, run scenarios, create connections, or consume Make operations
during local verification/package output.

Data Store manifests are evidence-based. `key_field` may be `inferred_from_mapper_key` only when
`datastore:AddRecord.mapper.key` or equivalent explicit evidence supplies a source path. Unknown
keys remain `unknown_requires_operator_mapping`; Pancakes never invents Data Store IDs or provider
resource IDs.

Data Store batch upsert is schema-checked before live work. Local manifests may include bounded
seed records for dry-run planning, and `datastore_record_upsert_batch` is bridge-ready only when
record fields match the inferred Data Store schema. Plans cap batches at 100 records, report
create/update/upsert counts, require operator approval before apply, retry only transient record
errors, and never delete or overwrite customer data without explicit approval. Disposable live
evidence covers the full typed MCP lifecycle: create Data Structure, create Data Store,
create/update/list/delete a record, delete the store, delete the structure, and verify both
inventories return to zero.
Strict-schema live evidence proves Make rejects seed records missing required fields or carrying
invalid typed values before accepting a valid record. Pancakes mirrors that as preflight evidence
for batch upsert instead of waiting for live Data Store writes to fail.

Data Store data structures are also evidence-based. `schema_fields` and
`data_structure_status=known_from_mapper_data` require local `datastore:AddRecord.mapper.data` or
equivalent explicit source paths. Compact responses expose only capped source-path examples plus
returned, hidden, and raw-available counts; unknown structures remain operator-mapped instead of
guessing fields.

Runtime setup counts are surface-scoped: occurrence count, affected node count, distinct binding
count, item count, and group count are separate. Zero-trace is tri-state; `zero_trace_status=passed`
requires `zero_trace=true`, `failed` requires leak evidence, and `not_evaluated` must name the
surface rather than implying success.

## AI Privacy

AI assistance is allowed as an operator-directed editing and review aid with applicable account
privacy controls enabled when available. Keep secrets or personal identifiers redacted. raw Make
blueprint JSON is local evidence for narrow debugging, and Manual JSON fine tuning is an exception
for small local slices. Public copy about AI assistance, privacy options, redaction, or local-only
handling requires legal review.
