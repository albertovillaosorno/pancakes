# Make AST Module Resolution Policy

## Status

Accepted

## Scope

repository/make-ast

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-ast.module-resolution.catalog-first

```json strict-policy
{
  "anchor": "repo.make-ast.module-resolution.catalog-first",
  "rule": "AST module-like nodes resolve against the canonical Make catalog before they can be treated as valid Make modules.",
  "resolved_fields": [
    "app slug",
    "app version",
    "module kind",
    "module/action internal name",
    "module family",
    "parameter IDs",
    "expect schema IDs",
    "interface schema IDs",
    "RPC dependencies",
    "deprecation status",
    "raw-spec references"
  ],
  "forbidden_posture": [
    "treating an AST module token as valid without a catalog match",
    "using prompts or examples as module truth",
    "fabricating module families when catalog metadata is insufficient"
  ]
}
```
## repo.make-ast.module-resolution.unresolved-categories

```json strict-policy
{
  "anchor": "repo.make-ast.module-resolution.unresolved-categories",
  "rule": "Unresolved AST module bindings must carry typed unresolved categories.",
  "required_categories": [
    "missing_raw_spec",
    "ambiguous_module_family",
    "deprecated_module",
    "unsupported_custom_app",
    "legacy_module_shape",
    "insufficient_blueprint_metadata"
  ],
  "failure_posture": "Nonexistent modules remain unresolved and cannot be promoted to valid modules."
}
```
## repo.make-ast.module-resolution.deprecated-warning

```json strict-policy
{
  "anchor": "repo.make-ast.module-resolution.deprecated-warning",
  "rule": "Deprecated catalog modules may resolve, but the resolution must carry deprecated_module warning metadata.",
  "required_posture": [
    "resolved deprecated modules keep their catalog references",
    "deprecated status is visible to validators and diagnostics",
    "unknown, custom, missing, or ambiguous modules stay unresolved"
  ]
}
```
## repo.make-ast.module-resolution.family-lineage

```json strict-policy
{
  "anchor": "repo.make-ast.module-resolution.family-lineage",
  "rule": "Module resolution is family-aware and must not collapse parallel Make app or module lineages into a single latest-wins result.",
  "required_posture": [
    "generation may prefer the latest compatible raw-spec family when creating new blueprints",
    "older retained families remain available for validation, migration, repair, and lineage-aware analysis",
    "ambiguous families remain explicit unresolved categories until a deterministic compatibility rule selects one",
    "historical retained raw-spec families are not deleted automatically by refresh flows"
  ],
  "forbidden_posture": [
    "silently selecting a latest family when several compatible families exist",
    "deleting older retained families as a side effect of catalog refresh",
    "treating mutable labels or traversal order as family identity"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Future blueprint validation can block nonexistent Make modules without
depending on generation code.
- AST nodes can carry resolved catalog references while preserving explicit
unresolved reasons for diagnostics and repair.
- Family-aware resolution protects migration and repair flows from accidental
latest-only behavior.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001045`.
- Decision ID: `repo.make-ast.module-resolution-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001045'
decision_id: 'repo.make-ast.module-resolution-policy'
title: 'Make AST Module Resolution Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/make-ast'
applies_to:
  - src/blueprints/ast/resolution.py
  - tests/blueprints/ast/module_registry_resolution_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - make_ast_nodes_are_bound_to_catalog_modules
  - blueprint_validation_checks_module_existence
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '000016'
  - '000017'
  - '001042'
  - '001044'
source_material:
  - path: 'Refactor/make/adr/0007-make-blueprint-ast-contract-and-family-doctrine.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/make_module_lifecycle_policy.json'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_spec_registry.py'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/blueprints/ast/resolution.py
  - tests/blueprints/ast/module_registry_resolution_contract.py
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.make-ast.module-resolution.catalog-first
  - repo.make-ast.module-resolution.unresolved-categories
  - repo.make-ast.module-resolution.deprecated-warning
  - repo.make-ast.module-resolution.family-lineage
non_goals:
  - generate blueprint modules in this round
  - contact live Make services
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
