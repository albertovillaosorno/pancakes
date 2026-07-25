# catalog.plan SQLite Worker Policy

## Status

Accepted

## Scope

repository/make-catalog

## Decision

`catalog.plan` progress is owned by the Make knowledge SQLite SSOT and its tracked SQL schema
snapshots. The former `src/catalog/plan_artifact/` workspace and `devtool.catalog_plan.*` file
tools are retired; they must not be recreated as a competing ledger.

## repo.catalog-plan.worker-boundary

```json strict-policy
{
  "anchor": "repo.catalog-plan.worker-boundary",
  "rule": "Catalog semantic-worker progress is persisted in SQLite, not sidecar files.",
  "runtime_database": "src/data/pancakes.sqlite",
  "tracked_schema_snapshot": "src/data/sql_snapshots/schema.sql",
  "public_mcp_tools": [
    "catalog.search",
    "catalog.next_unit",
    "catalog.save_unit"
  ],
  "retired_tools": [
    "devtool.catalog_plan.tree",
    "devtool.catalog_plan.read",
    "devtool.catalog_plan.write"
  ],
  "retired_roots": [
    "src/catalog/plan_artifact",
    "src/mcp/old"
  ],
  "development_worker": "ChatGPT.com via explicit CATALOG INTELLIGENCE prompt"
}
```

## repo.catalog-plan.persistence

```json strict-policy
{
  "anchor": "repo.catalog-plan.persistence",
  "rule": "Catalog-plan completion state lives in SQLite tables and deterministic snapshots.",
  "required_tables": [
    "catalog_plan_ranges",
    "catalog_plan_units",
    "catalog_plan_progress_events",
    "catalog_plan_semantic_answers",
    "catalog_plan_quarantine_records"
  ],
  "required_posture": [
    "work is chunked into independently resumable SQLite units",
    "ledger counters are derived from SQLite rows",
    "ChatGPT.com resumes through catalog.next_unit and catalog.save_unit",
    "weak evidence becomes structured quarantine with retry priority"
  ],
  "forbidden_posture": [
    "chat-only completion claims",
    "JSON answer ledgers",
    "Markdown shard ledgers",
    "sidecar progress SQLite databases",
    "secret-bearing evidence",
    "Codex-authored catalog semantic answers"
  ]
}
```

## repo.catalog-plan.grammar-layer

```json strict-policy
{
  "anchor": "repo.catalog-plan.grammar-layer",
  "rule": "catalog.plan must model Make wiring grammar, not only module lookup.",
  "lookup_role": "find candidate modules and apps",
  "planning_role": [
    "data contracts",
    "unit conversions",
    "array-to-single-item bridges",
    "lookup-before-update chains",
    "runtime setup prerequisites",
    "linter-backed repair rules"
  ],
  "examples": [
    "cent integer amounts require currency normalization before customer-facing text",
    "attachment arrays require iterators before single-file upload modules",
    "row update actions require a row id or a prior search step"
  ]
}
```

## repo.catalog-plan.business-boundary

```json strict-policy
{
  "anchor": "repo.catalog-plan.business-boundary",
  "rule": "Catalog-plan state may reference business boundaries but must not implement web logic.",
  "pancakes_core_posture": "mathematical compiler and Make scenario engine",
  "pancakes_web_posture": "pricing, checkout, Lemon Squeezy, onboarding, PDFs, client package UI",
  "client_script_rule": "client scripts are dumb injectors, not compiler bundles"
}
```

## Rationale

The catalog-plan task is larger than one model context and needs a safe handoff path for
ChatGPT.com, but file ledgers created a second authority next to the Make knowledge SQLite store.
Keeping all durable progress in SQLite prevents orphan JSON, stale Markdown shards, and hidden
sidecar progress databases.

## Consequences

- `catalog.plan` work can continue without hidden thread state.
- Generic MCP repository write tools remain out of scope.
- `catalog.next_unit` and `catalog.save_unit` are development-only ChatGPT.com worker tools.
- Final runtime knowledge flows through SQLite schema, tests, and SQL snapshots instead of sidecar
  artifact folders.

## Validation

- `pancakes.mcp.smoke`
- `pancakes.validate`
