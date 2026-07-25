# Expression And Mapping Intelligence Policy

## Status

Accepted

## Scope

repository/blueprint-validation

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.blueprint-validation.expression-risks.promoted-rules-only

```json strict-policy
{
  "anchor": "repo.blueprint-validation.expression-risks.promoted-rules-only",
  "rule": "Runtime expression intelligence uses only rules promoted through ADR, code, and tests.",
  "modeled_function_categories": [
    "text",
    "numeric",
    "datetime",
    "collection",
    "array",
    "parsing",
    "control"
  ],
  "modeled_patterns": [
    "get()",
    "map()",
    "Make-style semicolon-separated function arguments",
    "trim()",
    "match()",
    "parseNumber()",
    "regex",
    "parse/substitution",
    "array and collection handling",
    "iterator and aggregator source/target mapping",
    "pagination stop-condition hints"
  ],
  "forbidden_posture": [
    "course-only evidence changes runtime behavior",
    "unknown functions are silently accepted as valid",
    "expression warnings modify the blueprint automatically"
  ]
}
```
## repo.blueprint-validation.expression-risks.node-attached

```json strict-policy
{
  "anchor": "repo.blueprint-validation.expression-risks.node-attached",
  "rule": "Expression and mapping risks must attach to AST node IDs and source paths.",
  "risk_fields": [
    "risk ID",
    "severity",
    "code",
    "node ID",
    "source path",
    "expression excerpt",
    "client-safe message",
    "internal diagnostic",
    "evidence source"
  ]
}
```
## repo.blueprint-validation.expression-risks.repair-suggestions

```json strict-policy
{
  "anchor": "repo.blueprint-validation.expression-risks.repair-suggestions",
  "rule": "Mapping intelligence may produce specific repair suggestions but must not apply them unless a later explicit repair workflow requests mutation.",
  "required_posture": [
    "repair suggestions are client-safe",
    "suggestions identify the missing delimiter, argument, function verification, iterator source, aggregator target, or pagination guard",
    "blueprint mutation remains outside this slice"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Validators can report common mapping mistakes before blueprint rendering.
- Repair work has structured hints without silently changing customer or test
blueprints.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001048`.
- Decision ID: `repo.blueprint-validation.expression-intelligence-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001048'
decision_id: 'repo.blueprint-validation.expression-intelligence-policy'
title: 'Expression And Mapping Intelligence Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/blueprint-validation'
applies_to:
  - src/blueprints/validation/expression_intelligence.py
  - src/blueprints/validation/expression_paths.py
  - src/blueprints/validation/expression_templates.py
  - src/blueprints/validation/validator.py
  - tests/blueprints/validation/mapping_expression_intelligence_contract.py
  - tests/blueprints/validation/mapping_expression_template_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - make_mapping_expressions_are_analyzed
  - blueprint_validation_reports_mapping_risks
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
  - '001046'
source_material:
  - path: 'Refactor/make/src/forge/make_expression_intelligence.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_expression_intelligence.py'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/blueprints/validation/expression_intelligence.py
  - src/blueprints/validation/expression_paths.py
  - src/blueprints/validation/expression_templates.py
  - tests/blueprints/validation/mapping_expression_intelligence_contract.py
  - tests/blueprints/validation/mapping_expression_template_contract.py
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.blueprint-validation.expression-risks.promoted-rules-only
  - repo.blueprint-validation.expression-risks.node-attached
  - repo.blueprint-validation.expression-risks.repair-suggestions
non_goals:
  - implement automatic blueprint repair in this round
  - use unpromoted course text as runtime authority
  - contact live Make services
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
