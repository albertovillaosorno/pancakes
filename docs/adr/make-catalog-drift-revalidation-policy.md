# Make Catalog Drift Revalidation Policy

## Status

Accepted

## Scope

repository/make-catalog

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-catalog.drift-compares-catalog-snapshots

```json strict-policy
{
  "anchor": "repo.make-catalog.drift-compares-catalog-snapshots",
  "rule": "Raw-spec refresh drift is detected by comparing previous and current canonical catalog snapshots, not by trusting mutable labels or traversal order.",
  "required_drift_classes": [
    "added modules",
    "removed modules",
    "changed modules",
    "added parameters",
    "removed parameters",
    "changed parameters"
  ],
  "determinism_rule": "Drift reports are sorted by stable IDs and include snapshot fingerprints.",
  "forbidden_posture": [
    "silently accepting raw-spec changes without a deterministic drift report",
    "comparing graph nodes as the source of Make truth",
    "letting parameter drift bypass downstream revalidation"
  ]
}
```
## repo.make-catalog.revalidation-fails-stale-or-unknown-modules

```json strict-policy
{
  "anchor": "repo.make-catalog.revalidation-fails-stale-or-unknown-modules",
  "rule": "Dependent fixtures and blueprints must be revalidated against the current catalog before they are trusted after raw-spec drift.",
  "failure_cases": [
    "target module is missing from the current catalog",
    "target module fingerprint differs from the expected fingerprint",
    "required parameter IDs are missing from the current module"
  ],
  "required_posture": [
    "unknown modules fail instead of being fabricated",
    "stale module anchors produce explicit issues",
    "reports are deterministic and machine-readable"
  ]
}
```
## repo.make-catalog.fallback-when-raw-specs-stale-or-unavailable

```json strict-policy
{
  "anchor": "repo.make-catalog.fallback-when-raw-specs-stale-or-unavailable",
  "rule": "When raw specs are stale, unavailable, or produce catalog drift, the repository must fall back to current catalog truth and block stale dependent runtime assumptions.",
  "fallback_reasons": [
    "baseline_without_previous_snapshot",
    "raw_specs_unavailable",
    "catalog_drift",
    "validation_failed"
  ],
  "canonical_path_rule": "Raw-spec drift may require dependent fixture or graph fallback, but it must not invalidate the current canonical catalog path.",
  "forbidden_posture": [
    "treating stale raw specs as silently acceptable",
    "allowing persisted targets to outrank the current catalog",
    "downgrading missing modules to warnings"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Raw-spec refresh can now produce a replayable drift and revalidation report.
- Future blueprint validators have a deterministic boundary for checking
persisted module and parameter anchors.
- Graph or fixture material can degrade to catalog-first fallback without
weakening canonical module truth.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001043`.
- Decision ID: `repo.make-catalog.drift-revalidation-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001043'
decision_id: 'repo.make-catalog.drift-revalidation-policy'
title: 'Make Catalog Drift Revalidation Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/make-catalog'
applies_to:
  - src/catalog/drift.py
  - src/catalog/models.py
  - tests/catalog/catalog_schema_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - make_raw_specs_are_refreshed
  - make_catalog_drift_is_checked
  - dependent_blueprints_or_fixtures_are_revalidated
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
  - '001042'
derived_artifacts:
  - src/catalog/drift.py
  - tests/catalog/catalog_schema_contract.py
source_material:
  - path: 'Refactor/make/adr/0033-make-raw-spec-refresh-drift-revalidation-and-fallback.md'
    usage: source reference
    copied_verbatim: false
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.make-catalog.drift-compares-catalog-snapshots
  - repo.make-catalog.revalidation-fails-stale-or-unknown-modules
  - repo.make-catalog.fallback-when-raw-specs-stale-or-unavailable
non_goals:
  - implement a production scheduler in this round
  - contact live Make services
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
