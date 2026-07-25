# Catalog Semantic Graph Preview Policy

## Status

Accepted

## Scope

repository/catalog-mcp

## Decision

## File Boundary

This ADR owns the Pancakes catalog semantic graph search and preview policy. It must not define
provider access, live Make.com execution, reset tooling, or credential handling.

## repo.catalog-semantic-graph-preview.native-graph-inspection

```json strict-policy
{
  "anchor": "repo.catalog-semantic-graph-preview.native-graph-inspection",
  "rule": "Catalog graph inspection is a Pancakes SQLite-native MCP surface, not a generic source-code graph query.",
  "tool_surface": [
    "catalog.graph.search",
    "catalog.semantic.preview"
  ],
  "read_model_tables": [
    "entity_nodes",
    "entity_edges",
    "catalog_unit_outputs",
    "catalog_search_documents",
    "catalog_units",
    "make_raw_spec_manifest_records",
    "make_raw_spec_payloads"
  ],
  "required_posture": [
    "read local SQLite only",
    "return compact graph overviews by default",
    "expand node, edge, or unit details only when requested by identifier",
    "include no provider calls, no live Make.com calls, no credential transfer, and no secret output"
  ]
}
```

## repo.catalog-semantic-graph-preview.preview-before-save

```json strict-policy
{
  "anchor": "repo.catalog-semantic-graph-preview.preview-before-save",
  "rule": "Catalog semantic workers can preview proposed graph and search impact before saving leased work.",
  "preview_behavior": [
    "validate proposed semantic output with the same canonical graph and value-index checks used by catalog.work.save",
    "flag empty graph nodes or graph edges before save",
    "show disconnected proposed edges whose endpoints are not present in proposed or saved nodes",
    "preview compact query matches across existing SQLite graph state and proposed unsaved graph state",
    "label preview writes as not performed"
  ],
  "save_gate": [
    "catalog.work.save rejects empty graph_nodes",
    "catalog.work.save rejects empty graph_edges",
    "catalog.work.save still requires full leased-batch atomic saves"
  ]
}
```

## repo.catalog-semantic-graph-preview.platform-safe-worker-leases

```json strict-policy
{
  "anchor": "repo.catalog-semantic-graph-preview.platform-safe-worker-leases",
  "rule": "Catalog Intelligence worker leases expose a platform-safe lease handle and safety-shaped source packets by default.",
  "required_posture": [
    "catalog.work.next returns lease_handle instead of a token-shaped public field",
    "catalog.work.save accepts lease_handle for the atomic save gate",
    "legacy internal SQLite lease token storage may remain private implementation detail",
    "catalog.inspect reports lease status without exposing or naming the internal lease token",
    "normal source packets summarize operation names, labels, descriptions, and field groups instead of emitting raw operation objects",
    "credential-looking source keys and values are normalized before MCP output",
    "exact raw source remains addressable by source_ref and source_hash for local debugging"
  ],
  "concurrency_contract": [
    "workers use stable worker_id values",
    "one active batch is replayed per worker until saved or expired",
    "different workers can lease different queued units concurrently",
    "full leased batches must be saved atomically",
    "partial leased-batch saves are rejected"
  ]
}
```

## repo.catalog-semantic-graph-preview.asymmetric-bet-quality-floor

```json strict-policy
{
  "anchor": "repo.catalog-semantic-graph-preview.asymmetric-bet-quality-floor",
  "rule": "Catalog ingestion should prefer dense, labeled graph intelligence over minimalist semantic rows.",
  "operator_prompt": "Catalog Intelligence",
  "accepted_aliases": [
    "Catalog Work"
  ],
  "required_semantic_content": [
    "practical capabilities",
    "workflow use cases",
    "setup dependencies",
    "auth and connection needs",
    "input and output concepts",
    "risk surfaces",
    "related modules and apps",
    "trigger, action, search, or control classification",
    "search-enhancing graph nodes and edges"
  ],
  "inference_policy": [
    "inferred nodes and edges are allowed for search intelligence",
    "inferred nodes and edges must be labeled as inferred when not directly source-backed",
    "credential values, provider runtime facts, and live Make.com observations must not be fabricated"
  ]
}
```

## Consequences

Catalog workers get a compact graph read model before save, and future workflow-building agents can
use the same graph tools after the catalog is filled. The semantic corpus may include aggressively
inferred search edges, but the payload must preserve evidence posture so later repair and ranking
can distinguish source-backed facts from search-useful inference.

## Validation

Focused MCP contract tests must cover public tool registration, read-only annotations, graph search
over SQLite graph tables, semantic preview over unsaved graph payloads, and save-time rejection of
empty graph output.
