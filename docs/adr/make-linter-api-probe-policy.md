# Make Linter API Probe Policy

## Status

Accepted

## Scope

repository/make-linter-probe

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-linter.browser-scraping-forbidden

```json strict-policy
{
  "anchor": "repo.make-linter.browser-scraping-forbidden",
  "rule": "Make editor linter integration must never scrape the visual editor or DOM-rendered red error indicators.",
  "forbidden_inputs": [
    "browser automation",
    "DOM inspection",
    "canvas inspection",
    "pixel or color detection",
    "screen coordinates",
    "animations",
    "screenshots",
    "visual red-bubble counters"
  ],
  "required_posture": [
    "only structured API or HTTP response bodies may be considered",
    "client-side-only linter behavior without a callable API boundary is a dead end",
    "offline AST and knowledge-store validation remains the supported fallback"
  ]
}
```
## repo.make-linter.api-probe-authorized-only

```json strict-policy
{
  "anchor": "repo.make-linter.api-probe-authorized-only",
  "rule": "Any live Make linter probe is explicit, operator-approved, credential-referenced, and non-default.",
  "required_authorization": [
    "operator_approved true boolean",
    "approved_by non-empty string",
    "credential_ref non-empty non-secret string reference only",
    "purpose string collect_designer_messages or discover_linter_api"
  ],
  "allowed_probe_surfaces": [
    "documented Make scenario blueprint endpoints",
    "documented Make scenario update or clone endpoints only against disposable scenarios",
    "future documented validation endpoints after ADR update"
  ],
  "forbidden_posture": [
    "running from db:build, offline validation, or MCP startup",
    "using browser cookies or exported browser sessions",
    "accepting raw API tokens in source code, tests, reports, or MCP tool arguments",
    "probing private customer scenarios without explicit operator approval"
  ]
}
```
## repo.make-linter.documented-designer-message-signal

```json strict-policy
{
  "anchor": "repo.make-linter.documented-designer-message-signal",
  "rule": "The only accepted current linter signal is documented blueprint designer messages returned through Make scenario blueprint APIs.",
  "current_candidate": {
    "name": "scenario_blueprint_designer_messages",
    "method": "GET",
    "path": "/api/v2/scenarios/{scenarioId}/blueprint",
    "required_scope": "scenarios:read",
    "signal_path": "response.blueprint.flow[].metadata.designer.messages[]"
  },
  "mutation_candidates": [
    {
      "name": "scenario_update_blueprint_roundtrip",
      "method": "PATCH",
      "path": "/api/v2/scenarios/{scenarioId}",
      "required_scope": "scenarios:write",
      "allowed_only_for": "operator-approved disposable scenarios"
    },
    {
      "name": "scenario_clone_analysis",
      "method": "POST",
      "path": "/api/v2/scenarios/{scenarioId}/clone",
      "required_scope": "scenarios:write",
      "allowed_only_for": "operator-approved disposable scenarios"
    }
  ],
  "required_posture": [
    "treat designer messages as supervised live evidence, not as source truth",
    "normalize messages before they can inform AST validation gaps",
    "malformed designer-message evidence fields are skipped or nulled instead of string-coerced",
    "designer-message fingerprints represent normalized warning identity and exclude capture timestamps",
    "SQL promotion emits only reviewed evidence rows with explicit valid_from strings",
    "persist reviewed findings as reports or tracked evidence, never directly into generated SQLite"
  ]
}
```
## repo.make-linter.raw-designer-message-ingestion

```json strict-policy
{
  "anchor": "repo.make-linter.raw-designer-message-ingestion",
  "rule": "Documented Make blueprint designer messages may be collected as temporary raw ingest data, then normalized before any runtime consumer uses them.",
  "raw_dir": "src/catalog/data/make/designer-messages/raw/",
  "git_posture": "ignored temporary ingest input",
  "manifest": "src/catalog/data/make/designer-messages/raw/manifest.json",
  "accepted_method": "GET /api/v2/scenarios/{scenarioId}/blueprint",
  "required_fields": [
    "scenario_id",
    "draft",
    "source_ref",
    "captured_at_utc",
    "payload",
    "normalized_findings"
  ],
  "forbidden_posture": [
    "reading raw designer-message payloads from runtime validators",
    "committing raw private scenario payloads",
    "using PATCH, POST, clone, update, browser, DOM, canvas, or screenshot scraping for this ingest path"
  ]
}
```
## repo.make-linter.background-designer-message-batch

```json strict-policy
{
  "anchor": "repo.make-linter.background-designer-message-batch",
  "rule": "Designer-message collection may run as an explicit read-only batch over an approved scenario allow list, but it is disabled by default and uses injected transports in tests.",
  "required_posture": [
    "operator approval is required before any live call",
    "credential_ref is a reference, never token material",
    "scenario IDs are explicit non-empty string inputs",
    "source references are explicit non-empty string inputs",
    "draft selection is an explicit boolean input",
    "capture timestamps are explicit non-empty string inputs",
    "unauthorized batches report unauthorized counts and do not call transport",
    "offline validation, db:build, and MCP startup never trigger the batch"
  ],
  "status_counts": [
    "collected_count",
    "skipped_count",
    "failed_count",
    "unauthorized_count",
    "finding_count"
  ]
}
```
## repo.make-linter.no-standalone-validate-endpoint-baseline

```json strict-policy
{
  "anchor": "repo.make-linter.no-standalone-validate-endpoint-baseline",
  "rule": "As of 2026-04-30, no standalone documented Make blueprint validation endpoint is accepted by this repository.",
  "not_found_candidate": "POST /api/v2/blueprints/validate",
  "checked_surfaces": [
    "Make scenario API documentation",
    "Make scenario blueprint API documentation",
    "local raw-spec JSON files",
    "local SQL snapshots and source code"
  ],
  "future_change_rule": "A future endpoint requires a refreshed go/no-go report, ADR update, fake transport tests, and explicit authorization rules before use."
}
```
## repo.make-linter.evidence-normalization

```json strict-policy
{
  "anchor": "repo.make-linter.evidence-normalization",
  "rule": "Make linter findings must be normalized into structured, credential-free fields before review or persistence.",
  "required_fields": [
    "finding_id",
    "node_id",
    "module_slug",
    "severity",
    "source_system",
    "source_prefix",
    "message",
    "category",
    "field_path",
    "source_ref",
    "captured_at_utc",
    "fingerprint",
    "adr_anchor"
  ],
  "forbidden_fields": [
    "raw bearer token",
    "browser cookie",
    "private scenario URL",
    "screenshot path as automated proof"
  ]
}
```
## repo.make-linter.designer-warning-local-error-prefixes

```json strict-policy
{
  "anchor": "repo.make-linter.designer-warning-local-error-prefixes",
  "rule": "Make designer probe messages and repository-owned validation errors share diagnostic output only when their source systems, severities, and prefixes remain distinct.",
  "designer_warning_prefix": "MAKE-DESIGNER-WARN",
  "local_error_prefix": "MAKE-AST-ERROR",
  "local_warning_prefix": "MAKE-AST-WARN",
  "severity_mapping": [
    "designer-message evidence is always warning severity while drafting",
    "local AST or scenario-builder errors remain error severity",
    "designer warnings never downgrade or replace local errors"
  ]
}
```
## repo.make-linter.secondary-linter-advisory-gate

```json strict-policy
{
  "anchor": "repo.make-linter.secondary-linter-advisory-gate",
  "rule": "Make linter API evidence may appear as a secondary low-weight diagnostic result but must never replace offline AST, catalog, or knowledge-store validation.",
  "required_fields": ["status", "source", "warnings", "confidence_weight"],
  "statuses": [
    "secondary_linter_unavailable",
    "secondary_linter_passed",
    "secondary_linter_warning"
  ],
  "source": "make_linter_api_designer_messages",
  "confidence_weight": 0.25,
  "required_posture": [
    "missing Make API evidence is reported as secondary_linter_unavailable instead of a fabricated clean result",
    "designer-message findings are represented only as warning diagnostics",
    "generation gates and MCP feedback may surface secondary_linter as informational evidence",
    "offline validation errors and generation blockers remain authoritative"
  ],
  "forbidden_posture": [
    "clearing local errors because secondary linter warnings are absent",
    "blocking local generation solely because live Make linter evidence is unavailable",
    "promoting transient secondary linter output into durable truth without reviewed evidence"
  ]
}
```
## repo.make-linter.zero-diagnostic-delivery-gate

```json strict-policy
{
  "anchor": "repo.make-linter.zero-diagnostic-delivery-gate",
  "rule": "Drafting may continue with designer warnings, but final scenario handoff requires zero local errors and zero applicable reviewed designer warnings.",
  "drafting_posture": "designer warnings are advisory and nonblocking during incremental local work",
  "finalization_posture": "local finalization rejects any diagnostic finding still present",
  "missing_designer_evidence_posture": "missing designer evidence is reported as an evidence gap instead of a fabricated clean designer result"
}
```
## repo.make-linter.offline-validator-remains-default

```json strict-policy
{
  "anchor": "repo.make-linter.offline-validator-remains-default",
  "rule": "Offline AST, catalog, and knowledge-store validation remains the default path even if Make linter API probes later become available.",
  "allowed_use": [
    "identify gaps in local AST validation",
    "inform blueprint repair diagnostics after review",
    "settle knowledge-store needs_review conflicts only through reviewed evidence"
  ],
  "forbidden_posture": [
    "blocking local generation on live Make availability",
    "silently replacing offline validation with Make responses",
    "treating transient Make linter output as durable repository truth"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- The repository may investigate Make-native linter findings only through
structured API evidence.
- The visual editor is explicitly out of scope for scraping.
- Current implementation can normalize documented designer messages while
recording that a standalone validation endpoint has not been accepted.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001066`.
- Decision ID: `repo.make-linter.api-probe-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001066'
decision_id: 'repo.make-linter.api-probe-policy'
title: 'Make Linter API Probe Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - data
  - testing
scope: 'repository/make-linter-probe'
applies_to:
  - src/blueprints/validation/data/linter/probes/api_probe_report.json
  - src/blueprints/validation/data/linter/designer-messages/README.md
  - src/catalog/data/make/designer-messages/raw/**/*
  - src/catalog/data/make/db_snapshots/designer_message_evidence.sql
  - src/catalog/knowledge/linter_probe.py
  - src/blueprints/validation/generation_gate.py
  - src/mcp/project_loop.py
  - src/mcp/scenario_builder.py
  - tests/catalog/knowledge_linter_probe_contract.py
  - tests/catalog/knowledge_linter_secondary_gate_contract.py
  - tests/blueprints/validation/make_linter_secondary_gate_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - make_editor_linter_signal_is_investigated
  - live_make_validation_evidence_is_requested
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001035'
  - '001046'
  - '001055'
  - '001061'
  - '001064'
derived_artifacts:
  - src/blueprints/validation/data/linter/probes/api_probe_report.json
  - src/blueprints/validation/data/linter/designer-messages/README.md
  - src/catalog/data/make/db_snapshots/designer_message_evidence.sql
  - src/catalog/knowledge/linter_probe.py
  - src/blueprints/validation/generation_gate.py
  - src/mcp/project_loop.py
  - src/mcp/scenario_builder.py
  - tests/catalog/knowledge_linter_probe_contract.py
  - tests/catalog/knowledge_linter_secondary_gate_contract.py
  - tests/blueprints/validation/make_linter_secondary_gate_contract.py
  - docs/bibliography/make.com.md
source_material: []
bibliography_refs:
  - 'https://developers.make.com/api-documentation/api-reference/scenarios-greater-than-blueprints'
  - 'https://developers.make.com/api-documentation/api-reference/scenarios'
traceability_anchors:
  - repo.make-linter.browser-scraping-forbidden
  - repo.make-linter.api-probe-authorized-only
  - repo.make-linter.documented-designer-message-signal
  - repo.make-linter.raw-designer-message-ingestion
  - repo.make-linter.background-designer-message-batch
  - repo.make-linter.no-standalone-validate-endpoint-baseline
  - repo.make-linter.evidence-normalization
  - repo.make-linter.designer-warning-local-error-prefixes
  - repo.make-linter.secondary-linter-advisory-gate
  - repo.make-linter.zero-diagnostic-delivery-gate
  - repo.make-linter.offline-validator-remains-default
non_goals:
  - call live Make services in this ADR
  - automate the Make visual editor
  - replace offline AST validation with a live linter
  - store raw API tokens, browser sessions, screenshots, or private scenario payloads
```
</details>
