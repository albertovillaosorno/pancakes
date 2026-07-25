# Error Handling Repair Diagnostics Policy

## Status

Accepted

## Scope

repository/blueprint-repair

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.blueprint-repair.diagnostics.scoped-candidates

```json strict-policy
{
  "anchor": "repo.blueprint-repair.diagnostics.scoped-candidates",
  "rule": "Repair diagnostics convert validation findings into deterministic scoped repair candidates.",
  "required_categories": [
    "unsupported module discovery",
    "brittle API dependency",
    "missing error strategy",
    "data validation risk",
    "webhook response risk",
    "operation limit risk",
    "incomplete execution risk",
    "repeated error risk",
    "AI tool contract risk",
    "general validation guidance"
  ],
  "severity_projection": ["hard failure", "warning", "optimization", "explanation"],
  "source_trace_rule": "Error-handler path candidates preserve the original onerror/on_error source path evidence without mutating the blueprint.",
  "candidate_limit_rule": "Callers may request a positive maximum candidate count; limits apply after deterministic ordering."
}
```
## repo.blueprint-repair.diagnostics.no-automatic-mutation

```json strict-policy
{
  "anchor": "repo.blueprint-repair.diagnostics.no-automatic-mutation",
  "rule": "Repair diagnostics may describe candidates but must not mutate blueprints or live services.",
  "required_candidate_fields": ["preconditions", "rollback notes", "applies_automatically=false"],
  "forbidden_posture": [
    "claiming to fix unsupported external platform behavior",
    "mutating production systems",
    "changing blueprints without an explicit repair workflow"
  ]
}
```
## repo.blueprint-repair.diagnostics.client-safe-language

```json strict-policy
{
  "anchor": "repo.blueprint-repair.diagnostics.client-safe-language",
  "rule": "Client-facing repair text must avoid internal repository names, local paths, and implementation details.",
  "required_posture": [
    "client explanations describe the practical workflow concern",
    "internal diagnostics may keep validation details",
    "tests prove client-facing text is path-safe"
  ]
}
```
## repo.blueprint-repair.offline-action-contract

```json strict-policy
{
  "anchor": "repo.blueprint-repair.offline-action-contract",
  "rule": "Blueprint repair is an explicit offline action, not hidden behavior inside generation, validation, or live verification.",
  "mcp_tool_name": "blueprint.repair",
  "required_posture": [
    "never constructs a live Make client",
    "preserves unknown fields and cross-node references by default",
    "blocks unsafe family upgrades",
    "can use deterministic planner input when requirements text is available",
    "returns an explicit repair outcome and failure classification"
  ],
  "allowed_outcomes": ["accepted_after_repair", "rejected_with_reasons", "not_applicable"],
  "forbidden_posture": [
    "silently mutating a blueprint during validation",
    "calling live Make services from offline repair",
    "claiming autonomous repair when only diagnostics were produced"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Repair guidance is deterministic and reviewable before any mutation workflow
exists.
- Validation can surface webhook response gaps needed by repair diagnostics
without contacting Make.
- Operator surfaces can expose repair as a bounded offline action with explicit
outcomes.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001049`.
- Decision ID: `repo.blueprint-repair.diagnostics-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001049'
decision_id: 'repo.blueprint-repair.diagnostics-policy'
title: 'Error Handling Repair Diagnostics Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/blueprint-repair'
applies_to:
  - src/blueprints/repair/**/*
  - src/blueprints/validation/validator.py
  - tests/blueprints/repair/repair_diagnostics_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - validation_findings_are_converted_to_repair_candidates
  - repair_guidance_is_presented_to_clients_or_operators
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '000016'
  - '000017'
  - '001046'
  - '001048'
source_material:
  - path: 'Refactor/make/adr/0009-offline-blueprint-repair-tool.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_error_handling_semantics.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_error_handling_semantics.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_ai_agent_intelligence.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_ai_agent_intelligence.py'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/blueprints/repair/**/*
  - tests/blueprints/repair/repair_diagnostics_contract.py
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.blueprint-repair.diagnostics.scoped-candidates
  - repo.blueprint-repair.diagnostics.no-automatic-mutation
  - repo.blueprint-repair.diagnostics.client-safe-language
  - repo.blueprint-repair.offline-action-contract
non_goals:
  - auto-fix production systems
  - mutate live Make scenarios
  - claim to fix unsupported external platform behavior
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
