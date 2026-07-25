# Pancakes Deliverable Repository Boundary Policy

## Status

Accepted

## Scope

repository/pancakes-deliverable-boundary

## Decision

## File Boundary

This ADR defines what belongs in the `pancakes` deliverable repository and what must be extracted,
removed, or rewritten before an external product handoff. It does not execute extraction work or
store private business strategy.

## repo.pancakes.deliverable-boundary.core-product-scope

```json strict-policy
{
  "anchor": "repo.pancakes.deliverable-boundary.core-product-scope",
  "rule": "The pancakes repository owns the IR-centered product engine with Make as the first language adapter, not private operator workflow or public sales infrastructure.",
  "owned_capabilities": [
    "Language-neutral IR graph records and structural validation.",
    "Blueprint AST parsing, traversal, validation, repair, rendering, importability, and delivery-safe output.",
    "Catalog and knowledge-store logic required to analyze, validate, and generate supported language artifacts.",
    "MCP IDE surfaces that are part of the product engine and operate within explicit authorization boundaries.",
    "Linter taxonomy, rule intake, quarantine records, deterministic predicates, fixtures, and proof tests.",
    "Product-safe ADRs and validation commands that explain how to operate, validate, and extend the engine."
  ],
  "required_posture": [
    "describe the repository as a product engine",
    "keep executable product behavior runnable through repository-local commands",
    "keep client-facing and handoff output behind explicit scrubber and privacy boundaries",
    "preserve deterministic validation as the central product value"
  ],
  "forbidden_posture": [
    "describing the repository through private founder strategy",
    "mixing public sales funnels with engine source",
    "treating private operator automation as automatically included in product scope",
    "treating personal media or commercial side assets as core engine behavior"
  ]
}
```
## repo.pancakes.deliverable-boundary.context-classification

```json strict-policy
{
  "anchor": "repo.pancakes.deliverable-boundary.context-classification",
  "rule": "Current source bounded contexts are classified by deliverable posture before cleanup or extraction work begins.",
  "context_classification": [
    {
      "path": "src/blueprints/",
      "classification": "deliverable",
      "reason": "Owns blueprint AST, validation, repair, and supported automation artifact behavior."
    },
    {
      "path": "src/catalog/",
      "classification": "deliverable",
      "reason": "Owns catalog and knowledge-store behavior needed by the engine."
    },
    {
      "path": "src/ir/",
      "classification": "deliverable",
      "reason": "Owns language-neutral graph semantics and structural validation for the product core."
    },
    {
      "path": "src/languages/make/",
      "classification": "deliverable",
      "reason": "Owns the first supported source-language adapter, Make raw specs, Make data, and Make JSON interpretation."
    },
    {
      "path": "src/golden/",
      "classification": "deliverable",
      "reason": "Owns regression evidence and deterministic comparison workflow for engine behavior."
    },
    {
      "path": "src/make_to_python/",
      "classification": "deferred",
      "reason": "May become product translation capability, but sale scope and runtime boundary must be explicit before promotion."
    },
    {
      "path": "src/mcp/",
      "classification": "deliverable",
      "reason": "Owns agent-native product IDE surfaces when authorization and offline/live boundaries remain explicit."
    },
    {
      "path": "src/pdf/",
      "classification": "deliverable",
      "reason": "Owns client-safe report and handoff output only inside scrubber, privacy, and claims boundaries."
    },
    {
      "path": "src/public_web/",
      "classification": "public-web",
      "reason": "Deployable public website or sales implementation belongs outside the engine repository."
    },
    {
      "path": "src/windows_service/",
      "classification": "private-operator",
      "reason": "Private local orchestration is not part of the engine unless explicitly sold or reclassified."
    },
    {
      "path": "src/wav/",
      "classification": "media-personal",
      "reason": "Voice or audio generation is not core engine behavior unless explicitly sold or rewritten as generic product capability."
    },
    {
      "path": "src/srt/",
      "classification": "media-personal",
      "reason": "Subtitle and media handoff support is not core engine behavior unless explicitly sold or rewritten as generic product capability."
    },
    {
      "path": "src/mp4/",
      "classification": "media-personal",
      "reason": "Video generation is not core engine behavior unless explicitly sold or rewritten as generic product capability."
    }
  ],
  "required_posture": [
    "classify new bounded contexts before adding them to source",
    "route extraction work through focused TODOs",
    "reclassify deferred contexts only with an explicit ADR or superseding policy"
  ]
}
```
## repo.pancakes.deliverable-boundary.non-deliverable-surfaces

```json strict-policy
{
  "anchor": "repo.pancakes.deliverable-boundary.non-deliverable-surfaces",
  "rule": "Non-deliverable business, public-web, private-operator, and personal media surfaces must not be treated as core engine assets.",
  "must_not_own": [
    "private founder pitch, negotiation framing, tax strategy, entity planning, or M&A cleanup instructions",
    "deployable public website implementation for pre-sale or checkout flows",
    "private Windows service or workstation orchestration unless explicitly sold",
    "personal voice, video, subtitle, or media package assets unless explicitly sold",
    "Upwork, lead-magnet, or commercial side assets unless retained as product-safe historical evidence",
    "general cross-repository agent doctrine that applies outside this repository",
    "raw payment-provider or public-web provider decisions that are not part of the sold product"
  ],
  "required_posture": [
    "relocate private strategy outside the deliverable repository",
    "rewrite reusable product facts into neutral product documentation before keeping them",
    "preserve useful evidence before removal",
    "avoid deleting user work or evidence as an incidental cleanup side effect"
  ],
  "forbidden_posture": [
    "storing private business strategy under docs/adr",
    "leaving acquisition cleanup rationale in product docs",
    "shipping public sales infrastructure with the engine by accident",
    "removing useful evidence without a preservation target"
  ]
}
```
## repo.pancakes.deliverable-boundary.external-repository-extraction

```json strict-policy
{
  "anchor": "repo.pancakes.deliverable-boundary.external-repository-extraction",
  "rule": "Extraction targets are explicit and future work must preserve product behavior while moving non-engine assets out of the repository.",
  "extraction_targets": [
    {
      "source": "src/public_web/",
      "target": "separate public-web repository",
      "default_action": "extract_or_remove_deployable_web_code"
    },
    {
      "source": "src/windows_service/",
      "target": "separate private orchestrator repository",
      "default_action": "extract_or_remove_private_orchestration"
    },
    {
      "source": "src/wav/",
      "target": "separate media or tooling repository when retained",
      "default_action": "extract_or_remove_personal_media_surface"
    },
    {
      "source": "src/srt/",
      "target": "separate media or tooling repository when retained",
      "default_action": "extract_or_remove_personal_media_surface"
    },
    {
      "source": "src/mp4/",
      "target": "separate media or tooling repository when retained",
      "default_action": "extract_or_remove_personal_media_surface"
    }
  ],
  "required_posture": [
    "perform one extraction responsibility per TODO",
    "keep the engine testable after each extraction",
    "replace retained links with public-safe product boundaries",
    "update affected ADRs, path maps, spelling inputs, and focused tests in the same work unit"
  ],
  "forbidden_posture": [
    "creating nested repositories inside this repository",
    "moving code without preserving tests or validation",
    "publishing private operator automation",
    "mixing extraction with unrelated cleanup"
  ]
}
```
## repo.pancakes.deliverable-boundary.acquirer-safe-docs

```json strict-policy
{
  "anchor": "repo.pancakes.deliverable-boundary.acquirer-safe-docs",
  "rule": "Repository documentation must be safe to share as product documentation after legal and IP review.",
  "allowed_documentation": [
    "product architecture ADRs",
    "repository validation and extension instructions",
    "Make source-material legal-use boundaries",
    "client-safe output and report contracts",
    "deterministic validation and linter behavior backed by code or tests",
    "neutral implementation history needed for maintainability"
  ],
  "forbidden_documentation": [
    "private business pitch",
    "private acquisition cleanup strategy",
    "personal notes",
    "tax or entity planning",
    "private agent prompts",
    "cross-repository operator workflow rules",
    "payment, web, or negotiation strategy not included in product scope"
  ],
  "required_posture": [
    "rewrite private material as neutral product facts before retaining it",
    "keep docs/adr focused on product and repository policy",
    "use bibliography for source support rather than private strategy",
    "keep completed TODO archives as evidence rather than normal agent input"
  ]
}
```
## repo.pancakes.deliverable-boundary.validation-before-handoff

```json strict-policy
{
  "anchor": "repo.pancakes.deliverable-boundary.validation-before-handoff",
  "rule": "A handoff-ready repository must validate without relying on external private repositories or root operator control-plane files.",
  "required_checks": [
    "repository-local canonical validation passes or has an explicit emergency waiver",
    "engine tests do not require public-web, private-orchestrator, or personal media repositories",
    "private-material search finds no unresolved strategy, secret, or personal-note leakage",
    "path maps and ADR indexes are regenerated or the remaining generated drift is explicitly reported"
  ],
  "required_posture": [
    "run focused validation after each boundary cleanup",
    "run canonical validation before external handoff",
    "report any validation blocker separately from product boundary decisions",
    "do not push or publish without the repository guarded workflow"
  ],
  "forbidden_posture": [
    "treating missing external repositories as engine test prerequisites",
    "using raw git push",
    "rewriting history to hide cleanup without explicit authorization",
    "showing a handoff package before private-material review"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Pancakes now has an explicit product-engine boundary before extraction work
begins.
- Current public-web, private-orchestrator, and media slices are classified for
future extraction or removal without moving code in this ADR task.
- Future cleanup TODOs must preserve engine validation and update affected
product-safe policy surfaces in the same work unit.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001080`.
- Decision ID: `repo.pancakes.deliverable-boundary`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001080'
decision_id: 'repo.pancakes.deliverable-boundary'
title: 'Pancakes Deliverable Repository Boundary Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - repository
  - product
  - architecture
scope: 'repository/pancakes-deliverable-boundary'
applies_to:
  - README.md
  - docs/adr/*.md
  - src/**/*
  - tests/**/*
  - tools/**/*
  - docs/todo/**/*
applies_when:
  - repository_scope_is_described_for_external_review
  - bounded_context_is_added_removed_or_reclassified
  - implementation_slice_is_considered_for_extraction
  - repository_documentation_is_prepared_for_handoff
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000001'
  - '000003'
  - '001035'
  - '001069'
  - '001073'
  - '001074'
  - '001075'
  - '001077'
  - '001078'
  - '001079'
derived_artifacts: []
source_material: []
bibliography_refs: []
traceability_anchors:
  - repo.pancakes.deliverable-boundary.core-product-scope
  - repo.pancakes.deliverable-boundary.context-classification
  - repo.pancakes.deliverable-boundary.non-deliverable-surfaces
  - repo.pancakes.deliverable-boundary.external-repository-extraction
  - repo.pancakes.deliverable-boundary.acquirer-safe-docs
  - repo.pancakes.deliverable-boundary.validation-before-handoff
non_goals:
  - perform the extraction work in this ADR
  - create external repositories
  - define private business strategy
  - authorize public deployment
  - rewrite Git history
```
</details>
