# Legacy Brand Name Cleanup Policy

## Status

Accepted

## Scope

repository/naming

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.naming.active-public-surfaces-use-make-brand

```json strict-policy
{
  "anchor": "repo.naming.active-public-surfaces-use-make-brand",
  "rule": "Active runtime surfaces and public/operator documentation must use the Pancakes repository name and must not present the repository as the retired legacy brand.",
  "guard_test": "tests/repository_quality/architecture/legacy_scope_cleanup_fitness.py",
  "scanned_surfaces": [
    "README.md",
    "AGENTS.md",
    "docs/bibliography/**/*",
    "src/**/*",
    "tools/**/*",
    "scripts/**/*",
    "docs/todo/README.md",
    "docs/todo/queue/*.md",
    "docs/todo/pending/*.md"
  ]
}
```
## repo.naming.archival-legacy-evidence-boundary

```json strict-policy
{
  "anchor": "repo.naming.archival-legacy-evidence-boundary",
  "rule": "Legacy brand mentions may remain only where they are archival evidence or explicit ADR guardrails, not active product identity.",
  "allowed_surfaces": [
    "docs/adr/*.md when the mention is a guardrail or historical decision record",
    "docs/todo/completed/**",
    "Refactor/**",
    "docs/quarantine/**"
  ],
  "forbidden_posture": [
    "renaming the active repository away from make",
    "using the retired brand in runtime identifiers, active command labels, or public docs",
    "rewriting completed TODO archives during normal Continue execution just to clean old names"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Active runtime and public/operator docs stay Make-focused.
- ADR guardrails can still name retired scope when the point is to forbid it.
- Completed TODO evidence remains archive-only and is not read or rewritten by
normal cleanup rounds.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001059`.
- Decision ID: `repo.naming.legacy-brand-cleanup-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001059'
decision_id: 'repo.naming.legacy-brand-cleanup-policy'
title: 'Legacy Brand Name Cleanup Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - repository
  - naming
  - testing
scope: 'repository/naming'
applies_to:
  - README.md
  - AGENTS.md
  - docs/bibliography/**/*
  - src/**/*
  - tools/**/*
  - scripts/**/*
  - docs/todo/README.md
  - docs/todo/queue/*.md
  - docs/todo/pending/*.md
applies_when:
  - active_runtime_or_public_documentation_mentions_legacy_branding
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '001035'
  - '001040'
source_material: []
derived_artifacts:
  - tests/repository_quality/architecture/legacy_scope_cleanup_fitness.py
bibliography_refs: []
traceability_anchors:
  - repo.naming.active-public-surfaces-use-make-brand
  - repo.naming.archival-legacy-evidence-boundary
non_goals:
  - rewrite completed TODO archives during normal Continue execution
  - remove explicit ADR guardrails that only forbid retired product scope
  - alter third-party names
```
</details>
