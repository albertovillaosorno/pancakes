# Make AST Renderer Policy

## Status

Accepted

## Scope

repository/make-ast

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-ast.renderer.importable-gate-required

```json strict-policy
{
  "anchor": "repo.make-ast.renderer.importable-gate-required",
  "rule": "Importable blueprint rendering must pass the blueprint validation generation gate before JSON is emitted.",
  "required_posture": [
    "rendering calls the catalog-backed validation gate",
    "blocking validation errors raise a typed render error",
    "rendered importable JSON parses back into the Make AST and validates without blocking errors"
  ],
  "forbidden_posture": [
    "rendering unresolved critical nodes in importable mode",
    "inventing placeholder modules to satisfy rendering",
    "bypassing the generation gate for convenience"
  ]
}
```
## repo.make-ast.renderer.draft-mode-explicit

```json strict-policy
{
  "anchor": "repo.make-ast.renderer.draft-mode-explicit",
  "rule": "Draft rendering may preserve unresolved AST work only when the caller explicitly requests draft mode.",
  "draft_status": "not importable into Make",
  "required_posture": [
    "draft output keeps validation gate evidence",
    "draft output preserves unresolved module tokens for review",
    "draft output must not be described as importable"
  ]
}
```
## repo.make-ast.renderer.mode-fails-before-validation

```json strict-policy
{
  "anchor": "repo.make-ast.renderer.mode-fails-before-validation",
  "rule": "Unsupported render modes fail before blueprint validation runs so caller contract errors are not hidden by unrelated blueprint blockers.",
  "allowed_modes": ["importable", "draft"],
  "required_posture": [
    "reject unsupported modes with ValueError",
    "do not report validation blockers for an invalid caller mode",
    "keep importable and draft behavior explicit"
  ]
}
```
## repo.make-ast.renderer.semantic-preservation

```json strict-policy
{
  "anchor": "repo.make-ast.renderer.semantic-preservation",
  "rule": "Renderer output preserves AST semantic structure and raw payload fields where possible.",
  "preserved_surfaces": [
    "root name and metadata",
    "flow node IDs",
    "numeric-looking string IDs remain strings when integer conversion would change identity",
    "module tokens",
    "parameters and mappings",
    "routes, branches, tools, filters, and direct error handlers",
    "mixed direct error-handler aliases are rendered through one canonical container",
    "unknown raw payload fields"
  ],
  "validation_requirement": "Round-trip tests must prove rendered JSON parses back into equivalent AST structure."
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Future generators and assemblers have a narrow renderer boundary instead of
writing JSON directly.
- Draft output is available for diagnostics without weakening importable
blueprint safety.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001047`.
- Decision ID: `repo.make-ast.renderer-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001047'
decision_id: 'repo.make-ast.renderer-policy'
title: 'Make AST Renderer Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/make-ast'
applies_to:
  - src/blueprints/ast/renderer.py
  - tests/blueprints/rendering/blueprint_renderer_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - make_ast_roots_are_rendered_to_blueprint_json
  - generated_or_assembled_blueprints_are_prepared_for_import
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
  - '001046'
source_material: []
derived_artifacts:
  - src/blueprints/ast/renderer.py
  - tests/blueprints/rendering/blueprint_renderer_contract.py
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.make-ast.renderer.importable-gate-required
  - repo.make-ast.renderer.draft-mode-explicit
  - repo.make-ast.renderer.mode-fails-before-validation
  - repo.make-ast.renderer.semantic-preservation
non_goals:
  - implement visual Make UI cloning
  - contact live Make services
  - generate modules outside the catalog-backed validation boundary
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
