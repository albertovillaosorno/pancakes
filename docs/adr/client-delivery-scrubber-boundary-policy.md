# Client Delivery Scrubber Boundary Policy

## Status

Accepted

## Scope

repository/client-delivery-scrubber

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.delivery.client-scrubber.output-class

```json strict-policy
{
  "anchor": "repo.delivery.client-scrubber.output-class",
  "rule": "Scrubbed client delivery packages are generated outputs, not active source, and the default repository output root is temp/client-delivery/.",
  "output_root": "temp/client-delivery/",
  "implementation_tool": "product-owned scrubber implementation when promoted",
  "first_implementation_mode": "dry-run by default; synthetic test writes only",
  "cleanup_boundary": "Only a resolved child of temp/client-delivery/ may be removed before rewrite.",
  "required_posture": [
    "plan before writing",
    "default to dry-run planning",
    "write only to the declared output root",
    "treat generated output as disposable",
    "keep real client packaging behind explicit operator authorization"
  ],
  "forbidden_posture": [
    "mutating active source in place",
    "writing scrubbed packages under src, tools, tests, data, docs, or the repository root",
    "using cache, logs, dependencies, or an operating-system temp directory as the canonical package root",
    "generating a real client package as an incidental TODO side effect"
  ]
}
```
## repo.delivery.client-scrubber.path-safety

```json strict-policy
{
  "anchor": "repo.delivery.client-scrubber.path-safety",
  "rule": "The client delivery scrubber must reject escaping paths, active-source output roots, and secret-bearing local environment files before reading file contents.",
  "source_path_policy": "repository-relative only",
  "output_path_policy": "repository-relative and nested under temp/client-delivery/",
  "env_file_posture": "path-only exclusion; never read contents",
  "required_tests": [
    "dry-run does not create output",
    "active source files are unchanged after synthetic package write",
    ".env and .env.* are excluded without content reads",
    "absolute and parent-escaping paths are rejected"
  ],
  "forbidden_posture": [
    "following symlinks into unknown locations",
    "copying ignored secret files",
    "deleting output roots without proving they are under temp/client-delivery/",
    "using .env.example as a client package configuration file by default"
  ]
}
```
## repo.delivery.client-scrubber.package-contracts

```json strict-policy
{
  "anchor": "repo.delivery.client-scrubber.package-contracts",
  "rule": "Client delivery package contracts define internal, local-only handoff shapes; they are not public products, sales funnels, or live-service automation.",
  "implementation": "product-owned package-contract module when promoted",
  "allowed_package_kinds": [
    "blueprint_validation_summary",
    "blueprint_diff_report",
    "blueprint_handoff_report",
    "golden_comparison_report",
    "privacy_filter_report"
  ],
  "required_manifest_fields": [
    "sanitized_inputs",
    "sanitized_outputs",
    "validation_summary",
    "is_truncated",
    "truncation_reason",
    "operator_notes"
  ],
  "required_posture": [
    "inventory only local commands and repository-owned tools",
    "require explicit operator authorization before producing a real client handoff",
    "require sanitized inputs and sanitized outputs",
    "preserve explicit truncation status and reason",
    "keep operator notes separate from generated validation evidence"
  ],
  "forbidden_posture": [
    "defining pricing, payments, lead generation, or public sales claims",
    "calling live Make, marketplace, Vercel, Cloudflare, or client services",
    "including credentials, raw client payloads, raw Make exports, webhook URLs, or local environment files",
    "treating package contracts as permission to ship without scrubber output validation"
  ]
}
```
## repo.delivery.client-scrubber.private-surface-exclusions

```json strict-policy
{
  "anchor": "repo.delivery.client-scrubber.private-surface-exclusions",
  "rule": "Client delivery output excludes private repository machinery and scrubs internal policy references from retained text.",
  "excluded_path_classes": [
    "local environment files",
    "cache, temp, log, dependency, and virtual-environment roots",
    "docs/adr policy records",
    "todo workflow files",
    "repository tooling",
    "private linter probe data",
    "raw designer-message ingest",
    "internal MCP OAuth state",
    "root governance and package-manager configuration"
  ],
  "scrubbed_text_classes": [
    "repository header blocks",
    "file boundary contract blocks",
    "ADR anchors and docs/adr path references",
    "internal designer-message paths",
    "private linter probe paths",
    "machine-specific user profile paths"
  ],
  "required_posture": [
    "preserve user-facing behavior and professional structure",
    "replace internal references with client-safe labels when text remains useful",
    "exclude a file entirely when safe scrubbing cannot be proven"
  ],
  "forbidden_posture": [
    "leaking private ADR references",
    "leaking private linter internals",
    "leaking internal designer messages",
    "leaking local credentials or path-specific secret state",
    "leaking internal architecture comments"
  ]
}
```
## repo.delivery.client-scrubber.required-truncation-reporting

```json strict-policy
{
  "anchor": "repo.delivery.client-scrubber.required-truncation-reporting",
  "rule": "Every scrubber plan or manifest must explicitly report whether the result was truncated and why.",
  "required_fields": ["is_truncated", "truncation_reason"],
  "allowed_truncation_reasons": ["not_truncated", "entry_limit_reached"],
  "required_posture": [
    "truncation fields are required constructor fields, not optional defaults",
    "manifests preserve the truncation fields even when not truncated",
    "callers must not assume completeness unless is_truncated is false and truncation_reason is not_truncated"
  ],
  "forbidden_posture": [
    "omitting truncation fields",
    "using null as the normal complete-result marker",
    "silently dropping files from a plan"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Client delivery package generation now has an ADR-owned output class before
tool code writes anything.
- `.env` remains path-only local secret state and is never copied or read by the
scrubber.
- Private ADR, linter, designer-message, and local machine surfaces are removed
from delivery output instead of being trusted to manual review alone.
- The first implementation can prove path safety with synthetic tests without
producing a real client handoff package.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001073`.
- Decision ID: `repo.delivery.client-scrubber-boundary`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001073'
decision_id: 'repo.delivery.client-scrubber-boundary'
title: 'Client Delivery Scrubber Boundary Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - security
  - tooling
  - testing
scope: 'repository/client-delivery-scrubber'
applies_to:
  - product-owned scrubber implementation when promoted
  - product-owned package-contract module when promoted
  - product-owned scrubber tests when promoted
  - temp/client-delivery/**/*
  - .env
  - .env.*
  - .env.example
applies_when:
  - client_delivery_package_is_prepared
  - repository_slice_is_prepared_for_external_handoff
  - scrubbed_delivery_output_is_written
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000006'
  - '001053'
  - '001054'
  - '001061'
  - '001062'
  - '001063'
  - '001072'
source_material: []
derived_artifacts:
  - product-owned scrubber implementation when promoted
  - product-owned package-contract module when promoted
  - product-owned scrubber tests when promoted
bibliography_refs: []
traceability_anchors:
  - repo.delivery.client-scrubber.output-class
  - repo.delivery.client-scrubber.package-contracts
  - repo.delivery.client-scrubber.path-safety
  - repo.delivery.client-scrubber.private-surface-exclusions
  - repo.delivery.client-scrubber.required-truncation-reporting
non_goals:
  - generate a real client package without explicit operator request
  - define commercial pricing or service tiers
  - compile Make scenarios to Python
  - authorize live Make or marketplace calls
  - read local .env contents
```
</details>
