# Make Catalog Schema Policy

## Status

Accepted

## Scope

repository/make-catalog

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-catalog.raw-specs-and-catalog-authority

```json strict-policy
{
  "anchor": "repo.make-catalog.raw-specs-and-catalog-authority",
  "rule": "Pancakes SQLite is the durable Make knowledge SSOT; tracked SQL snapshots are small restore evidence and generated catalog outputs are local projections for app and module existence.",
  "authority_chain": [
    "Make raw spec payloads retained in SQLite with hashes and provenance",
    "tracked ADR-backed restore SQL snapshots",
    "canonical Make catalog snapshot",
    "ignored Pancakes SQLite runtime store",
    "AST validation and blueprint rendering"
  ],
  "forbidden_posture": [
    "generating Make modules that are missing from the validated catalog",
    "letting examples, prompts, graph material, or stale generated artifacts override the catalog",
    "using Refactor material as runtime authority after active migration"
  ]
}
```
## repo.make-catalog.knowledge-store-authority-chain

```json strict-policy
{
  "anchor": "repo.make-catalog.knowledge-store-authority-chain",
  "rule": "Catalog snapshots and the knowledge-store projection must agree on normalized Make entities derived from the same raw-spec manifest.",
  "knowledge_store": "src/data/pancakes.sqlite",
  "tracked_snapshots": "small restore SQL under src/data/sql_snapshots/*.sql",
  "service_regenerable_dump": "src/data/sql_snapshots/make.sql",
  "required_posture": [
    "catalog compilation remains deterministic and JSON serializable",
    "knowledge ensure preserves temporal rows with valid_from and valid_to",
    "SQLite consumers reject stale raw-spec manifest hashes before loading facts",
    "validators may query SQLite projections only after ADR-backed code and tests exist"
  ],
  "forbidden_posture": [
    "letting raw course text override catalog module existence",
    "using generated Make SQL cache dumps as committed repository truth",
    "inventing modules when catalog and knowledge store disagree"
  ]
}
```
## repo.make-catalog.evidence-source-ranking

```json strict-policy
{
  "anchor": "repo.make-catalog.evidence-source-ranking",
  "rule": "Catalog-facing module evidence payloads expose deterministic source labels and ranks whenever candidates, expansions, or module-resolution readiness claims are returned.",
  "rank_semantics": "Lower source_rank values are more authoritative.",
  "source_precedence": [
    { "source_label": "knowledge_db", "source_rank": 0 },
    { "source_label": "raw_spec_manifest", "source_rank": 10 },
    { "source_label": "fixture_snapshot", "source_rank": 20 },
    { "source_label": "fallback_alias", "source_rank": 30 }
  ],
  "tie_breaking": [
    "source_rank",
    "module_id",
    "app_slug",
    "app_version",
    "module_kind",
    "internal_name"
  ],
  "required_posture": [
    "knowledge-store module facts outrank raw-spec manifest projections when both are available",
    "raw-spec manifest projections outrank committed fixture snapshots",
    "fixture snapshots outrank fallback aliases",
    "fallback aliases remain visibly labeled and lower-ranked so they cannot look like reviewed catalog evidence",
    "response payloads that expose module candidates or resolutions include source_label and source_rank"
  ],
  "forbidden_posture": [
    "letting fallback aliases inherit knowledge_db or raw_spec_manifest labels",
    "omitting source labels from catalog plan module entries",
    "silently choosing between equal source-rank candidates without a stable identifier tie-breaker"
  ]
}
```
## repo.make-catalog.entity-families-and-stable-ids

```json strict-policy
{
  "anchor": "repo.make-catalog.entity-families-and-stable-ids",
  "rule": "The canonical catalog schema is shaped around CatalogSnapshot, App, AppVersion, Module, Field, and Constraint entities with deterministic stable IDs.",
  "stable_id_sources": {
    "app": "raw app logical slug",
    "app_version": "raw app slug plus raw app version",
    "module": "raw app slug plus version plus module kind plus internal module name",
    "field": "parent module ID plus field direction plus canonical field path",
    "constraint": "parent field ID plus normalized constraint key"
  },
  "required_module_surfaces": [
    "actions",
    "parameters",
    "advanced field setting metadata",
    "expect schemas",
    "interface schemas",
    "RPC dependencies",
    "deprecated flags",
    "external IDs"
  ],
  "allowed_module_kinds": [
    "action",
    "search",
    "trigger",
    "router",
    "transformer",
    "aggregator",
    "agent",
    "custom",
    "unknown"
  ]
}
```
## repo.make-catalog.deterministic-fingerprints

```json strict-policy
{
  "anchor": "repo.make-catalog.deterministic-fingerprints",
  "rule": "Every catalog entity carries a deterministic SHA-256 fingerprint derived from canonical JSON payloads.",
  "fingerprint_inputs": [
    "stable identifiers",
    "semantic raw-spec fields",
    "child entity fingerprints",
    "raw-spec manifest provenance"
  ],
  "fingerprint_exclusions": [
    "local absolute paths",
    "processing timestamps",
    "array traversal accident",
    "graph topology"
  ]
}
```
## repo.make-catalog.validation-fails-closed

```json strict-policy
{
  "anchor": "repo.make-catalog.validation-fails-closed",
  "rule": "Catalog parsing and validation must fail closed on missing modules, invalid module records, duplicate IDs, unsupported directions, and unknown module lookups.",
  "required_validation": [
    "raw-spec file hash matches the manifest record",
    "each app version has at least one module",
    "each module has a non-empty internal name",
    "custom and unknown module kinds are explicit and legal",
    "malformed noncritical field metadata emits structured diagnostics and preserves the containing module when safe",
    "module lookup failure raises an error instead of fabricating a module"
  ],
  "forbidden_posture": [
    "silently skipping invalid module records",
    "omitting Make advanced field setting metadata from the typed catalog contract",
    "crashing catalog planning or blueprint compilation on a single malformed field metadata item",
    "falling back to prompt guesses for missing modules",
    "treating validation failures as warnings"
  ]
}
```
## repo.make-catalog.custom-module-provenance

```json strict-policy
{
  "anchor": "repo.make-catalog.custom-module-provenance",
  "rule": "Custom and unknown module facts are explicit catalog records only when the raw-spec manifest preserves provenance and module kind.",
  "required_posture": [
    "raw-spec summaries count customModules as custom modules",
    "raw-spec summaries count opaque modules collections as unknown modules",
    "authenticated custom-only records must not be dropped as metadata-only app records",
    "custom catalog modules remain source-labeled and source-ranked during AST resolution",
    "client business custom modules must not be promoted to shared master catalog truth"
  ],
  "forbidden_posture": [
    "treating custom module visibility as permission to reuse private customer schemas",
    "marking a custom module as a known native Make module without source provenance",
    "discarding unsupported customer modules when rendering or validating pass-through ASTs"
  ]
}
```
## repo.make-catalog.generated-snapshots-not-source

```json strict-policy
{
  "anchor": "repo.make-catalog.generated-snapshots-not-source",
  "rule": "Compiled catalog snapshots must not live under src/ and accepted refresh snapshots are persistent data.",
  "default_output_root": "src/languages/make/data/catalog",
  "source_allowed": [
    "typed compiler code",
    "schema validation code",
    "small deterministic tests and fixtures"
  ],
  "source_forbidden": [
    "generated catalog snapshots under src/",
    "large copied Make raw specs under source control",
    "stale cache catalog files used as runtime truth"
  ]
}
```
## repo.make-catalog.persistent-refresh-snapshot

```json strict-policy
{
  "anchor": "repo.make-catalog.persistent-refresh-snapshot",
  "rule": "The source-injected refresh command persists the current accepted catalog snapshot under src/languages/make/data/catalog/.",
  "default_snapshot_path": "src/languages/make/data/catalog/catalog.json",
  "required_posture": [
    "write deterministic catalog JSON",
    "validate snapshots before persistence",
    "keep snapshot paths repository-relative",
    "link the snapshot to the raw-spec manifest SHA-256"
  ],
  "forbidden_posture": [
    "writing catalog snapshots outside the repository",
    "using cache/ as the canonical accepted catalog workspace",
    "letting the Windows service compile catalog data itself"
  ]
}
```
## repo.make-catalog.catalog-only-fallback-utility

```json strict-policy
{
  "anchor": "repo.make-catalog.catalog-only-fallback-utility",
  "rule": "The canonical catalog must remain independently useful when graph, retrieval, or generated planning material is sparse, stale, contradictory, unknown, or absent.",
  "approved_responsibilities": [
    "catalog-only retrieval of candidate Make modules and app surfaces",
    "catalog-only planning hints from canonical app, module, field, and constraint data",
    "deterministic validation of requested module selections against catalog truth"
  ],
  "required_posture": [
    "catalog-only behavior does not depend on graph material or sidecar infrastructure",
    "outputs preserve the catalog or inventory fingerprint they were derived from",
    "ranking and summaries never invent capability beyond the canonical catalog",
    "deterministic validation remains final when planning hints disagree"
  ],
  "forbidden_posture": [
    "making graph availability a precondition for catalog use",
    "letting examples, course text, prompts, or semantic proximity override catalog truth",
    "fabricating modules because the catalog-only path has no match"
  ]
}
```
## repo.make-catalog.bounded-fallback-query-limits

```json strict-policy
{
  "anchor": "repo.make-catalog.bounded-fallback-query-limits",
  "rule": "Catalog-only fallback query results are bounded advisory candidates, not exact module resolution.",
  "default_candidate_limit": 10,
  "required_posture": [
    "omitted fallback limits use the default candidate limit",
    "zero and negative limits return no advisory candidates",
    "oversized limits are clamped to the default candidate limit",
    "limited result sets expose deterministic truncation diagnostics",
    "fallback candidates expose advisory resolution metadata with confidence lower than exact catalog resolution"
  ],
  "forbidden_posture": [
    "returning unbounded fallback candidate lists",
    "hiding candidate truncation from response payloads",
    "presenting fallback suggestions as exact catalog resolution"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- The Make catalog slice can validate module truth before AST and blueprint
work begins.
- Raw-spec refresh and catalog compilation remain graph-independent and
portable across checkout locations.
- Future AST or validator work must depend on catalog lookups instead of
inventing Make modules from prompts or examples.
- Catalog-only retrieval and planning hints can remain useful without weakening
catalog authority.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001042`.
- Decision ID: `repo.make-catalog.schema-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001042'
decision_id: 'repo.make-catalog.schema-policy'
title: 'Make Catalog Schema Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/make-catalog'
applies_to:
  - src/catalog/**/*
  - src/data/sql_snapshots/**/*
  - tests/catalog/catalog_schema_contract.py
  - tests/catalog/catalog_source_ranking_contract.py
  - tests/catalog/catalog_fallback_query_limit_contract.py
  - tests/catalog/test_raw_spec_field_retention.py
  - tests/catalog/raw_specs/raw_specs_data_refresh_contract.py
  - tests/catalog/fixtures/make_catalog/**/*
  - tests/catalog/fixtures/raw_specs/minimal_restore_expect_interface.json
  - docs/bibliography/make.com.md
applies_when:
  - make_catalog_is_compiled
  - make_blueprint_ast_needs_module_truth
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '000016'
  - '000017'
  - '001033'
  - '001034'
  - '001041'
derived_artifacts:
  - src/catalog/**/*
  - tests/catalog/catalog_schema_contract.py
  - tests/catalog/catalog_source_ranking_contract.py
  - tests/catalog/catalog_fallback_query_limit_contract.py
  - tests/catalog/test_raw_spec_field_retention.py
  - tests/catalog/fixtures/make_catalog/sample_raw_spec.json
  - tests/catalog/fixtures/make_catalog/sample_catalog.json
  - tests/catalog/fixtures/raw_specs/minimal_restore_expect_interface.json
source_material:
  - path: 'Refactor/make/adr/0020-canonical-make-catalog-schema.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/adr/0021-catalog-only-fallback-and-independent-utility.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_canonical_catalog_fallback.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_canonical_catalog_fallback.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_canonical_catalog.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_imt_parser.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_canonical_catalog.py'
    usage: source reference
    copied_verbatim: false
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.make-catalog.raw-specs-and-catalog-authority
  - repo.make-catalog.entity-families-and-stable-ids
  - repo.make-catalog.deterministic-fingerprints
  - repo.make-catalog.validation-fails-closed
  - repo.make-catalog.generated-snapshots-not-source
  - repo.make-catalog.persistent-refresh-snapshot
  - repo.make-catalog.catalog-only-fallback-utility
  - repo.make-catalog.bounded-fallback-query-limits
  - repo.make-catalog.knowledge-store-authority-chain
  - repo.make-catalog.evidence-source-ranking
non_goals:
  - implement blueprint generation in this round
  - contact live Make services
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
