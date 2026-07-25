# Operation Estimator Policy

## Status

Accepted

## Scope

repository/make-ast

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-ast.operation-estimator.conservative-static

```json strict-policy
{
  "anchor": "repo.make-ast.operation-estimator.conservative-static",
  "rule": "Operation estimates are conservative static planning estimates unless live run evidence is explicitly added by a future workflow.",
  "required_labels": [
    "confidence label",
    "source label",
    "horizon hours",
    "run count",
    "operations per run",
    "estimated operations"
  ],
  "caller_contract": [
    "horizon hours must be a positive integer",
    "unsupported execution modes fail before estimate output is produced"
  ],
  "forbidden_posture": [
    "exact billing guarantee",
    "credit guarantee without live evidence",
    "client/private run history use in this slice"
  ]
}
```
## repo.make-ast.operation-estimator.execution-modes

```json strict-policy
{
  "anchor": "repo.make-ast.operation-estimator.execution-modes",
  "rule": "The estimator models scheduled runs, run once, and run-this-module-only planning modes.",
  "modeled_surfaces": [
    "every 30 minutes over 24 hours",
    "daily",
    "weekly",
    "fractional minute intervals",
    "Make API second-based intervals",
    "non-finite interval rejection",
    "text interval metadata",
    "routers and filtered branches",
    "disabled routes",
    "AI agent/tool scenarios",
    "error routes",
    "iterators and aggregators",
    "pagination hints"
  ]
}
```
## repo.make-ast.operation-estimator.warning-labels

```json strict-policy
{
  "anchor": "repo.make-ast.operation-estimator.warning-labels",
  "rule": "Estimator warnings must surface uncertainty instead of pretending static analysis knows runtime volume.",
  "required_warnings": [
    "unknown schedule",
    "disabled route skipped",
    "AI/tool usage",
    "iterator or aggregator multiplier unknown",
    "pagination volume unknown",
    "large test-cost warning"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Proposals can include operation planning numbers without claiming exact
billing.
- Future live evidence can supersede static estimates through a separate
evidence-labeled workflow.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001050`.
- Decision ID: `repo.make-ast.operation-estimator-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001050'
decision_id: 'repo.make-ast.operation-estimator-policy'
title: 'Operation Estimator Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/make-ast'
applies_to:
  - src/blueprints/ast/operation_estimator.py
  - tests/blueprints/ast/operation_estimator_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - make_blueprint_operation_estimates_are_needed
  - planning_or_proposal_text_mentions_estimated_operations
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '000016'
  - '000017'
  - '001044'
source_material:
  - path: 'Refactor/make/src/forge/make_credit_estimator.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_credit_estimator.py'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/blueprints/ast/operation_estimator.py
  - tests/blueprints/ast/operation_estimator_contract.py
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.make-ast.operation-estimator.conservative-static
  - repo.make-ast.operation-estimator.execution-modes
  - repo.make-ast.operation-estimator.warning-labels
non_goals:
  - guarantee exact Make billing or credits
  - contact live Make services
  - use private client run history
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
