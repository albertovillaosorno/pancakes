# Make Course Evidence Boundary Policy

## Status

Accepted

## Scope

repository/make-course-evidence

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-course.evidence-only-storage

```json strict-policy
{
  "anchor": "repo.make-course.evidence-only-storage",
  "rule": "Make course material is preserved as evidence-only source material under src/catalog/data/make/courses/; the retired top-level evidence/ root must not exist.",
  "raw_evidence_root": "src/catalog/data/make/courses/raw",
  "candidate_manifest": "src/catalog/data/make/courses/candidate_artifacts_manifest.json",
  "retired_root": "evidence/",
  "runtime_usage_allowed": false,
  "retention_posture": [
    "raw course markdown can be kept for human review",
    "large generated candidate JSON remains non-runtime unless a future TODO curates a small typed artifact",
    "course evidence does not supersede Make raw specs, catalog snapshots, knowledge-store SQL snapshots, ADR policy, or deterministic tests"
  ]
}
```
## repo.make-course.promotion-gate

```json strict-policy
{
  "anchor": "repo.make-course.promotion-gate",
  "rule": "Course-derived knowledge can affect runtime behavior only after explicit promotion.",
  "required_gate_order": [
    "select a small candidate fixture",
    "specify the target behavior in ADR policy",
    "prove canonical Make raw specs or live verification do not contradict it",
    "add deterministic tests for the promoted behavior",
    "record the promoted claim in src/catalog/data/make/courses/coverage.json",
    "insert the promoted durable fact into tracked SQL snapshots",
    "record a rollback path"
  ],
  "forbidden_shortcuts": [
    "runtime imports raw course markdown",
    "runtime imports giant generated candidate JSON",
    "course-only evidence changes validators, renderers, or generation gates"
  ]
}
```
## repo.make-course.claim-level-coverage-ledger

```json strict-policy
{
  "anchor": "repo.make-course.claim-level-coverage-ledger",
  "rule": "Course promotion is tracked at claim level with per-markdown coverage rollups.",
  "coverage_ledger": "src/catalog/data/make/courses/coverage.json",
  "claim_table": "course_claims",
  "required_claim_fields": [
    "source markdown path",
    "source range or manual anchor",
    "domain",
    "promotion status",
    "ADR anchor",
    "code target",
    "test target",
    "remaining percentage"
  ],
  "runtime_usage_allowed": false,
  "required_posture": [
    "each promoted course claim has ADR, code, and test backing",
    "unpromoted course material remains visible as remaining coverage",
    "the useful course knowledge can eventually survive deletion of raw markdown evidence"
  ]
}
```
## repo.make-course.runtime-must-not-read-course-evidence

```json strict-policy
{
  "anchor": "repo.make-course.runtime-must-not-read-course-evidence",
  "rule": "Runtime validation, generation, rendering, and repair code must not read src/catalog/data/make/courses/ directly.",
  "allowed_use": [
    "human review",
    "future bounded TODO analysis",
    "small promoted fixtures after ADR and tests exist"
  ],
  "validation": [
    "tests assert runtime source files do not reference the course evidence path",
    "tests assert candidate manifests declare runtime_usage_allowed=false"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Course material is available in the active repository under `data/` without
becoming Make AST, validator, renderer, or generator authority.
- Future course-derived behavior must pass through a small, reviewable
promotion path instead of importing the raw evidence corpus.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001052`.
- Decision ID: `repo.make-course.evidence-boundary-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001052'
decision_id: 'repo.make-course.evidence-boundary-policy'
title: 'Make Course Evidence Boundary Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - documentation
  - testing
scope: 'repository/make-course-evidence'
applies_to:
  - src/catalog/data/make/courses/**/*
  - src/catalog/data/make/db_snapshots/course_rules.sql
  - src/catalog/data/make/db_snapshots/aliases.sql
  - src/catalog/knowledge/**/*
  - tests/data/course_evidence/course_evidence_boundary_contract.py
  - docs/bibliography/make-academy.md
applies_when:
  - make_course_material_is_preserved
  - course_derived_candidates_are_reviewed
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001035'
  - '001040'
  - '001046'
  - '001048'
source_material:
  - path: 'Refactor/make/courses/**/*'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/catalog/data/make/courses/**/*
  - tests/data/course_evidence/course_evidence_boundary_contract.py
bibliography_refs:
  - 'https://academy.make.com/'
traceability_anchors:
  - repo.make-course.evidence-only-storage
  - repo.make-course.promotion-gate
  - repo.make-course.runtime-must-not-read-course-evidence
  - repo.make-course.claim-level-coverage-ledger
non_goals:
  - make course text canonical runtime authority
  - commit huge generated course candidate JSON as active runtime input
  - use course material to bypass catalog/raw-spec validation
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
