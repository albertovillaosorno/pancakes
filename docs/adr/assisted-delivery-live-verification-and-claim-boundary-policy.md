# Assisted Delivery Live Verification And Claim Boundary Policy

## Status

Accepted

## Scope

repository/assisted-delivery-and-live-verification

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.delivery.assisted-stack-selection-auditable

```json strict-policy
{
  "anchor": "repo.delivery.assisted-stack-selection-auditable",
  "rule": "GPT-assisted delivery may plan over a compact supported inventory, but the selected stack must stay explicit, catalog-backed, and auditable.",
  "required_posture": [
    "surface a deterministic supported inventory instead of hidden universal routing",
    "preserve the chosen module stack",
    "preserve the inventory fingerprint when one is available",
    "preserve the stack rationale",
    "check parity between an explicit module stack and the emitted AST"
  ],
  "forbidden_posture": [
    "hardcoding a universal natural-language router",
    "letting GPT invent modules outside the catalog-backed validation boundary",
    "leaving stack choice implicit in freeform prose"
  ]
}
```
## repo.delivery.client-ready-handoff-contract

```json strict-policy
{
  "anchor": "repo.delivery.client-ready-handoff-contract",
  "rule": "Client-ready delivery uses derived handoff views over authoritative AST, validation, repair, placeholder, and PDF data instead of creating a second source of truth.",
  "authoritative_surfaces": [
    "typed AST",
    "validation report",
    "repair outcome",
    "placeholder manifest when a blueprint contains client replacement paths",
    "metadata.notes for Make-native notes",
    "PDF handoff document"
  ],
  "make_native_note_fields": [
    "metadata.notes[].content",
    "metadata.notes[].moduleIds",
    "metadata.notes[].metadata.color"
  ],
  "required_verdicts": ["accepted_as_generated", "accepted_after_repair", "rejected_with_reasons"],
  "required_metrics": [
    "first-pass validation status",
    "repair success status",
    "unrecoverable failure class"
  ],
  "forbidden_posture": [
    "persisting a compact delivery view as new core state",
    "marking client-ready coverage as complete when exact requested token parity is lost",
    "using cosmetic status labels when operation parity is unknown",
    "generating arbitrary note color metadata without an approved palette and tests"
  ]
}
```
## repo.delivery.live-verification-explicit-only

```json strict-policy
{
  "anchor": "repo.delivery.live-verification-explicit-only",
  "rule": "Live Make verification is an explicit opt-in boundary and must never run as hidden design-time behavior.",
  "future_tool_name": "blueprint.verify_live",
  "required_posture": [
    "uses documented Make scenario and blueprint endpoints",
    "creates disposable verification scenarios only",
    "runs auth-capability preflight before broader verification",
    "imports, exports, diffs, and cleans up disposable scenarios when cleanup is enabled",
    "records endpoint-level auth evidence, cleanup fallout, and failure classification"
  ],
  "default_design_time_path": "offline",
  "forbidden_posture": [
    "silently calling live Make services from generation, validation, repair, or rendering",
    "treating live verification as required for ordinary local tests",
    "setting live_import_verified without a matching explicit round trip"
  ]
}
```
## repo.delivery.manual-canary-review-packet

```json strict-policy
{
  "anchor": "repo.delivery.manual-canary-review-packet",
  "rule": "Human live canary review is allowed only as manual evidence and must not be described as autonomous live proof.",
  "required_packet_fields": [
    "reviewed blueprint run",
    "operator verdict",
    "observed errors",
    "screenshot or artifact evidence paths",
    "requested revision path",
    "cleanup and credential notes when relevant"
  ],
  "required_posture": [
    "manual canary packets are bounded evidence",
    "manual canary findings may inform a repair or revision TODO",
    "manual canary evidence does not set live_import_verified by itself"
  ],
  "forbidden_posture": [
    "treating screenshots as automated round-trip proof",
    "using manual canary review as a substitute for archived exact-token proof",
    "storing credentialed or private live-service data in the repository"
  ]
}
```
## repo.delivery.manual-capture-template

```json strict-policy
{
  "anchor": "repo.delivery.manual-capture-template",
  "rule": "Manual assisted-delivery capture templates are repository data, not loose root documentation.",
  "template_path": "src/blueprints/validation/data/assisted-delivery/templates/assisted_delivery_capture_template.json",
  "required_posture": [
    "templates must reflect current Make.com, AST, validation, repair, PDF, MCP, and optional media scope only",
    "templates must not mention obsolete Axiom, GraphRAG, Nerve, TigerGraph, dataset, Notion, Life Engine, or backup scope",
    "templates must not hardcode an operator checkout path",
    "manual capture may record blockers honestly without fabricating blueprint, telemetry, or canary values"
  ],
  "forbidden_posture": [
    "using loose docs/*.md runbooks as the active capture template",
    "treating manual capture as automated live proof",
    "storing credentialed or private live-service data in the repository"
  ]
}
```
## repo.delivery.manual-capture-validation-library

```json strict-policy
{
  "anchor": "repo.delivery.manual-capture-validation-library",
  "rule": "Assisted-delivery capture validation belongs in the active Validation bounded context, not in loose phase scripts.",
  "implementation": "src/blueprints/validation/assisted_delivery_capture.py",
  "required_posture": [
    "validate the current capture schema version",
    "reject obsolete scope terms and hardcoded local path markers",
    "preserve explicit blocker text for honestly blocked manual runs",
    "keep phase-specific ChatGPT runbook mechanics out of active source unless a future ADR reintroduces them"
  ],
  "forbidden_posture": [
    "recreating old Phase 9 scripts as active scripts",
    "treating blocked manual capture as completion evidence",
    "reviving generic ingest, graph, or product telemetry scope through capture helpers"
  ]
}
```
## repo.delivery.strong-proof-archives-required

```json strict-policy
{
  "anchor": "repo.delivery.strong-proof-archives-required",
  "rule": "Strong delivery claims require immutable archived proof records; mutable latest artifacts are pointers only.",
  "archive_root": "src/blueprints/validation/data/assisted-delivery/history",
  "latest_pointer_examples": [
    "src/blueprints/validation/data/assisted-delivery/make_quality/strong_proof_artifact_manifest.json"
  ],
  "required_archive_fields": [
    "source artifact path",
    "source content hash",
    "generated_at timestamp when available",
    "generated_from_commit when available",
    "archived_at timestamp",
    "archive run identifier",
    "surface fingerprint when relevant",
    "auth mode and region or zone when relevant",
    "deployment identity when relevant"
  ],
  "freshness_invalidation": [
    "archive missing",
    "bound surface fingerprint changed",
    "auth mode changed",
    "region or zone changed",
    "deployment identity changed",
    "commit changed for a commit-scoped claim",
    "configured max age elapsed"
  ]
}
```
## repo.delivery.claims.exact-dynamic-surface-only

```json strict-policy
{
  "anchor": "repo.delivery.claims.exact-dynamic-surface-only",
  "rule": "A current dynamic Make support-surface claim is allowed only when exact-token proof is archived, fresh, and bound to the current surface identity.",
  "allowed_wording": "The current dynamic Make support surface is live-verified by automated import/export round-trip proof.",
  "required_bound_identity": [
    "dynamic surface fingerprint",
    "requested token count",
    "auth mode",
    "region or zone",
    "archived proof run identifier",
    "source hash",
    "deployment identity when relevant"
  ],
  "forbidden_substitutes": [
    "offline compile-only success",
    "client-ready or schema-shape-only validation",
    "git-tracked benchmark snapshots",
    "batch-level import success without deterministic per-token reconstruction",
    "stale latest files without a matching archived run",
    "manual canary evidence"
  ]
}
```
## repo.delivery.claims.universal-freeform-nl-prohibited

```json strict-policy
{
  "anchor": "repo.delivery.claims.universal-freeform-nl-prohibited",
  "rule": "The repository must not claim universal freeform natural-language Make delivery without stack control.",
  "current_answer": "NO",
  "allowed_narrower_posture": [
    "bounded assisted delivery over surfaced supported inventory",
    "catalog-backed explicit stack selection",
    "benchmark statements limited to the tested finite surface"
  ],
  "forbidden_substitutes": [
    "workflow benchmark coverage",
    "chaotic-prompt cases",
    "requirements_text support",
    "semantic default planning mode",
    "exact-token dynamic-surface proof",
    "manual canary evidence"
  ],
  "future_supersession_requirement": "A future ADR must define one finite supported universe, stack-control semantics, failure semantics, omitted-stack judging rules, and exact evidence metrics before any stronger claim is allowed."
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Assisted delivery can stay practical while preserving catalog-backed stack
traceability.
- Live verification remains a separate opt-in boundary and not a hidden local
dependency.
- Strong proof and natural-language claims are blocked unless the evidence
contract is explicit, fresh, archived, and narrow.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001061`.
- Decision ID: `repo.delivery.live-verification-and-claim-boundary-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001061'
decision_id: 'repo.delivery.live-verification-and-claim-boundary-policy'
title: 'Assisted Delivery Live Verification And Claim Boundary Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - documentation
  - testing
scope: 'repository/assisted-delivery-and-live-verification'
applies_to:
  - src/blueprints/ast/**/*
  - src/blueprints/validation/**/*
  - src/blueprints/repair/**/*
  - src/mcp/**/*
  - src/pdf/**/*
  - src/blueprints/validation/data/assisted-delivery/**/*
  - src/pdf/data/**/*
  - data/blueprints/**/*
  - docs/bibliography/make.com.md
applies_when:
  - assisted_delivery_output_is_prepared
  - live_blueprint_verification_is_requested
  - make_delivery_claims_are_written
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000016'
  - '000017'
  - '001033'
  - '001035'
  - '001041'
  - '001042'
  - '001044'
  - '001046'
  - '001049'
  - '001054'
  - '001055'
source_material:
  - path: 'Refactor/make/adr/0008-make-client-ready-quality-placeholders-notes-and-handoff.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/adr/0010-live-blueprint-verification.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/adr/0014-strong-proof-artifact-persistence-and-freshness.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/adr/0015-dynamic-surface-strong-claim-contract.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/adr/0016-universal-freeform-nl-claim-prohibition.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/chatgpt_assisted_delivery_capture_template.json'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/chatgpt_assisted_delivery_capture_template.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/chatgpt_assisted_delivery_unblock_runbook.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/mcp_operating_protocol.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/apply_chatgpt_assisted_delivery_capture.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/check_chatgpt_assisted_delivery_gate.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/finalize_chatgpt_assisted_delivery_phase9.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/mark_chatgpt_assisted_delivery_capture_blocked.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/prefill_chatgpt_assisted_delivery_capture.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/validate_chatgpt_assisted_delivery_capture.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/artifacts/make_quality/make_client_ready_coverage.json'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/make_canary_feedback_template.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/make_canary_operator_checklist.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/make_canary_review_protocol.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/root-material/make_runtime_promotion_policy.json'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/blueprints/validation/data/assisted-delivery/templates/assisted_delivery_capture_template.json
  - src/blueprints/validation/assisted_delivery_capture.py
  - tests/blueprints/validation/assisted_delivery_capture_contract.py
bibliography_refs:
  - 'https://developers.make.com/'
traceability_anchors:
  - repo.delivery.assisted-stack-selection-auditable
  - repo.delivery.client-ready-handoff-contract
  - repo.delivery.live-verification-explicit-only
  - repo.delivery.manual-canary-review-packet
  - repo.delivery.manual-capture-template
  - repo.delivery.manual-capture-validation-library
  - repo.delivery.strong-proof-archives-required
  - repo.delivery.claims.exact-dynamic-surface-only
  - repo.delivery.claims.universal-freeform-nl-prohibited
non_goals:
  - implement a live verifier in this round
  - make live verification a design-time dependency
  - claim universal natural-language coverage
  - mutate live Make accounts without an explicit operator request
  - restore graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
