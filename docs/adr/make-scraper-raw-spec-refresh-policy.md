# Make Scraper Raw Spec Refresh Policy

## Status

Accepted

## Scope

repository/make-scraper

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-scraper.raw-specs.repo-local-cache

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.repo-local-cache",
  "rule": "Make raw-spec refresh outputs must be written to the repository-local Pancakes SQLite SSOT.",
  "default_database_path": "src/data/pancakes.sqlite",
  "payload_table": "make_raw_spec_payloads",
  "manifest_table": "make_raw_spec_manifest_records",
  "forbidden_posture": [
    "writing raw specs outside the repository",
    "hardcoding an operator checkout path",
    "tracking generated raw spec payloads as source code"
  ]
}
```
## repo.make-scraper.raw-specs.persistent-data-output

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.persistent-data-output",
  "rule": "Raw-spec refresh outputs are SQLite rows; file payloads may exist only as ignored temporary fetch artifacts during a run.",
  "local_temporary_outputs": [
    "cache/make/raw-specs/**",
    "temp/make/raw-specs/**"
  ],
  "git_posture": "ignored",
  "authority_boundary": "Raw specs are an ingestion substrate for refresh and knowledge-store normalization. They are not a repository source of truth and must be reproducible from live Make inputs or deterministic fixtures.",
  "traceability_boundary": "Generated raw-spec payloads are represented by SQLite rows and deterministic SQL snapshots.",
  "cache_allowed_for": ["disposable reports", "test coverage", "temporary local diagnostics"],
  "forbidden_posture": [
    "treating cache/make/raw-specs as the canonical refresh workspace",
    "using temp/ as durable raw-spec storage",
    "tracking generated raw specs in Git",
    "treating temp/raw-specs-json as canonical repository truth",
    "making validation depend on committed raw-spec payloads"
  ]
}
```
## repo.make-scraper.raw-specs.command-query-boundary

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.command-query-boundary",
  "rule": "The Make scraper slice separates write commands from read/query behavior.",
  "command_boundary": "sync_raw_specs writes raw spec payload and manifest rows to SQLite from an injected source; refresh_catalog_from_source coordinates raw-spec sync with catalog persistence.",
  "query_boundary": "raw_spec_refresh_status reads existing SQLite manifest rows without contacting Make.",
  "source_boundary": "MakeRawSpecSource is the only scraper input boundary for tests and future adapters."
}
```
## repo.make-scraper.raw-specs.manifest-required

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.manifest-required",
  "rule": "Every raw-spec sync must emit a deterministic manifest with file hashes and parsed app/module summary fields.",
  "manifest_fields": [
    "generated_at_utc",
    "raw_spec_dir",
    "manifest_sha256",
    "records[].app_slug",
    "records[].app_version",
    "records[].relative_path",
    "records[].sha256",
    "records[].module_count",
    "records[].module_kinds"
  ],
  "determinism_rule": "Records are sorted by app slug and version, and JSON is written with stable key ordering.",
  "load_requirement": "Manifest loading must recompute the canonical digest and reject tampered manifest payloads."
}
```
## repo.make-scraper.raw-specs.parser-fails-closed

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.parser-fails-closed",
  "rule": "The raw-spec parser must fail closed on malformed Make module collection shapes before writing manifest summaries.",
  "required_posture": [
    "known module collections are absent or JSON arrays",
    "module collection items are JSON objects",
    "missing app identity, invalid manifest version, and malformed collection shape errors are explicit exceptions"
  ],
  "forbidden_posture": [
    "treating malformed module collections as empty",
    "silently skipping non-object module collection items",
    "fabricating module summaries from invalid payload shapes"
  ]
}
```
## repo.make-scraper.raw-specs.manifest-digest-verified-on-load

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.manifest-digest-verified-on-load",
  "rule": "Manifest readers must verify the stored manifest SHA-256 before returning a trusted RawSpecManifest.",
  "digest_rule": "The digest is calculated from canonical manifest JSON with manifest_sha256 blank, then stored in manifest_sha256.",
  "failure_posture": "Digest mismatch raises an error and blocks downstream catalog compilation."
}
```
## repo.make-scraper.raw-specs.live-scraping-disabled-by-default

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.live-scraping-disabled-by-default",
  "rule": "Live Make scraping is disabled by default and tests must not require secrets, credentials, or network access.",
  "enable_flag": "MAKE_LIVE_SCRAPER_ENABLED",
  "service_command": "python -B -m catalog.raw_specs --repo-root <repo> refresh",
  "post_refresh_command": "python -B -m catalog.knowledge --repo-root <repo> ensure",
  "service_env_file": ".env",
  "required_live_env": ["MAKE_API_TOKEN", "MAKE_ZONE", "MAKE_ORGANIZATION_ID"],
  "test_requirement": "Tests use deterministic mocked MakeRawSpecSource implementations and fake live transports."
}
```
## repo.make-scraper.raw-specs.refresh-status-explicit-blockers

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.refresh-status-explicit-blockers",
  "rule": "Catalog and scraper status surfaces must describe local freshness, automation coverage, and operator-gated blockers without contacting Make.",
  "status_surfaces": [
    "catalog.status",
    "scraper.refresh_status",
    "python -B -m languages.make.raw_specs --repo-root <repo> status"
  ],
  "required_status_fields": [
    "generated_at_utc",
    "freshness_status",
    "source_type_counts",
    "sanitization_status_counts",
    "automated_refresh_steps",
    "operator_gated_refresh_steps",
    "complete_refresh_blockers",
    "forbidden_refresh_inputs",
    "evidence_generalization_path"
  ],
  "forbidden_posture": [
    "hiding missing live credentials behind a ready status",
    "making live raw-spec refresh a default validation action",
    "using manual scenario-by-scenario repairs as catalog maintenance",
    "storing provider tokens or bearer values in raw-spec artifacts"
  ]
}
```
## repo.make-scraper.raw-specs.platform-target-seeds

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.platform-target-seeds",
  "rule": "Full live raw-spec refreshes must include Make-owned platform and native module specs even when the IMT app index omits them.",
  "seeded_slugs": [
    "ai-agent",
    "ai-local-agent",
    "ai-provider",
    "ai-tools",
    "app-runtime",
    "builtin",
    "csv",
    "datastore",
    "http",
    "json",
    "util",
    "xml"
  ],
  "dedupe_rule": "If the live index advertises any version for one seeded slug, the discovered target wins and no current-version duplicate is added.",
  "fallback_version": "current",
  "applies_to": "full index refreshes only; search-constrained diagnostic runs remain limited to the operator search term",
  "required_posture": [
    "service refreshes include Make-native routers, aggregators, transformers, triggers, app-runtime modules, and AI-agent module families",
    "tests cover omitted platform seeds and de-duplication when the index includes a platform slug",
    "knowledge-store status reports native slugs that still have zero modules or missing expected kinds"
  ]
}
```
## repo.make-scraper.raw-specs.knowledge-store-ingest

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.knowledge-store-ingest",
  "rule": "Successful raw-spec refreshes persist current Make evidence into SQLite and can rebuild projections from small tracked restore snapshots.",
  "database_path": "src/data/pancakes.sqlite",
  "database_git_posture": "ignored generated binary",
  "tracked_review_material": "small restore SQL under src/data/sql_snapshots/*.sql",
  "service_regenerable_dump": "src/data/sql_snapshots/make.sql",
  "refresh_order": [
    "raw-spec refresh writes manifest and payload rows to SQLite",
    "knowledge ensure checks the SQLite manifest hash",
    "knowledge ensure rebuilds SQLite when absent or stale"
  ],
  "forbidden_posture": [
    "using raw-spec payload JSON as runtime truth",
    "committing src/data/pancakes.sqlite",
    "editing the generated SQLite file directly",
    "treating native zero-module specs as complete"
  ]
}
```
## repo.make-scraper.raw-specs.operator-approved-local-stubs

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.operator-approved-local-stubs",
  "rule": "Operator-approved local raw-spec stubs are provenance records for offline development only; they are not Make-confirmed module truth.",
  "required_fields": [
    "module_token",
    "source",
    "operator_approved",
    "approval_timestamp",
    "operator_note",
    "unsupported_fields"
  ],
  "allowed_source": "operator-approved-local-stub",
  "allowed_mode": "offline_development",
  "strict_client_handoff_posture": "block as unresolved raw-spec evidence unless a future ADR explicitly permits draft output",
  "precedence_rule": "Validated catalog and raw-spec evidence takes precedence over a matching local stub.",
  "forbidden_posture": [
    "treating a local stub as a catalog-confirmed Make module",
    "attaching fabricated module IDs, app versions, or raw-spec hashes to a stub",
    "allowing a stub to pass strict client handoff",
    "adding stubs for modules already present in validated catalog evidence"
  ]
}
```
## repo.make-scraper.raw-specs.external-id-normalization

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.external-id-normalization",
  "rule": "Make external identifiers accepted by scraper configuration must be preserved losslessly as positive decimal text.",
  "required_posture": [
    "large organization IDs are never coerced through lossy numeric formats",
    "blank, boolean, non-decimal, and non-positive values fail before live scraping",
    "identifier normalization remains in the Scraper boundary because it protects future live Make adapters"
  ],
  "forbidden_posture": [
    "treating Make organization IDs as floats",
    "trimming invalid values into an accepted placeholder",
    "letting a live adapter receive an unvalidated organization identifier"
  ]
}
```
## repo.make-scraper.raw-specs.lossless-boundary-values

```json strict-policy
{
  "anchor": "repo.make-scraper.raw-specs.lossless-boundary-values",
  "rule": "Make-facing boundary values are untrusted external values first and must be preserved losslessly before any repository-local interpretation.",
  "default_identifier_type": "str",
  "required_posture": [
    "configuration, MCP inputs, future live adapters, logs, and manifests preserve Make identifiers as text unless numeric semantics are explicitly audited",
    "blank, boolean, non-decimal, and non-positive identifier values fail before live scraping",
    "signed 64-bit compatibility is not a validity rule for external identifiers",
    "external enum-like values must fail closed when they drift outside audited local assumptions"
  ],
  "forbidden_posture": [
    "coercing external IDs through floats or bounded native integers",
    "truncating or normalizing away significant identifier representation",
    "patching an overflow exception in one caller while leaving the boundary contract mixed"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- The active scraper foundation and service command can be tested without Make credentials.
- Raw specs and manifests have a repo-confined, ignored, temporary ingest
contract for both mocked sources and explicitly enabled live scraping.
- Catalog and AST work can depend on manifest shape without depending on a graph
or stale generated payloads.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001041`.
- Decision ID: `repo.make-scraper.raw-spec-refresh-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001041'
decision_id: 'repo.make-scraper.raw-spec-refresh-policy'
title: 'Make Scraper Raw Spec Refresh Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - tooling
  - runtime
scope: 'repository/make-scraper'
applies_to:
  - .gitignore
  - src/catalog/raw_specs/**/*
  - tests/catalog/test_operator_approved_raw_spec_bootstrap.py
  - tests/fixtures/catalog/operator_approved_datastore_add_record_stub.json
  - src/catalog/knowledge/**/*
  - src/catalog/refresh.py
  - tests/catalog/raw_specs/raw_specs_refresh_contract.py
  - tests/catalog/knowledge_store_contract.py
  - tests/catalog/raw_specs/raw_specs_data_refresh_contract.py
  - .env.example
  - docs/bibliography/make.com.md
applies_when:
  - make_raw_specs_are_refreshed
  - make_scraper_tests_run
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '000017'
  - '001033'
  - '001034'
  - '001040'
derived_artifacts:
  - .gitignore
  - src/catalog/raw_specs/**/*
  - tests/catalog/raw_specs/raw_specs_refresh_contract.py
source_material:
  - path: 'Refactor/make/adr/0020-canonical-make-catalog-schema.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/adr/0033-make-raw-spec-refresh-drift-revalidation-and-fallback.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_imt_parser.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_imt_scraper.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_imt_refresh.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_external_ids.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/integrations/make_client.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_client.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/integration/test_make_imt_scraper.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/adr/0042-external-boundary-hardening-and-lossless-identifier-preservation.md'
    usage: source reference
    copied_verbatim: false
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.make-scraper.raw-specs.repo-local-cache
  - repo.make-scraper.raw-specs.persistent-data-output
  - repo.make-scraper.raw-specs.command-query-boundary
  - repo.make-scraper.raw-specs.manifest-required
  - repo.make-scraper.raw-specs.parser-fails-closed
  - repo.make-scraper.raw-specs.manifest-digest-verified-on-load
  - repo.make-scraper.raw-specs.live-scraping-disabled-by-default
  - repo.make-scraper.raw-specs.refresh-status-explicit-blockers
  - repo.make-scraper.raw-specs.platform-target-seeds
  - repo.make-scraper.raw-specs.external-id-normalization
  - repo.make-scraper.raw-specs.lossless-boundary-values
  - repo.make-scraper.raw-specs.knowledge-store-ingest
  - repo.make-scraper.raw-specs.operator-approved-local-stubs
non_goals:
  - enable live credentialed Make API scraping without explicit operator configuration
  - promote generated raw spec JSON into tracked source
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
