# Client Blueprint Intake Privacy Boundary Policy

## Status

Accepted

## Scope

repository/client-blueprint-intake

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

This policy is a repository privacy and security boundary, not legal advice. Official sources were
checked on 2026-05-08 before this ADR was created. Before paid intake, public web intake, or
customer contract language is offered, current platform documentation, privacy law, mail-provider
terms, and customer contracts must be rechecked.

## repo.client-blueprint-intake.email-offline-only-mvp

```json strict-policy
{
  "anchor": "repo.client-blueprint-intake.email-offline-only-mvp",
  "rule": "The first customer blueprint intake MVP uses email attachment or offline handoff only, not a public upload backend.",
  "accepted_artifact": "Make .blueprint.json export only",
  "maximum_source_bytes": 2000000,
  "required_received_surfaces": [
    "named mailbox or email attachment surface",
    "named offline or encrypted handoff surface"
  ],
  "required_disclosure": [
    "email intake is not local-only",
    "mail provider attachment storage, scanning, backups, and retention are processor surfaces",
    "the operator must name processor and retention boundaries before analysis"
  ],
  "forbidden_posture": [
    "accepting logs, execution history, .env files, screenshots, archives, or live payloads",
    "claiming email intake is in-memory-only",
    "treating a blueprint as safe solely because Make connections are not imported"
  ]
}
```
## repo.client-blueprint-intake.local-workstation-backend-boundary

```json strict-policy
{
  "anchor": "repo.client-blueprint-intake.local-workstation-backend-boundary",
  "rule": "The operator computer may run the private analysis backend only as local workbench infrastructure after manual intake.",
  "local_backend_role": "operator_workstation_local_only",
  "required_hardening_baseline": [
    "no inbound customer routes",
    "no public listener",
    "no local tunnel",
    "loopback-only binding when a listener is unavoidable",
    "firewall posture documented before real intake",
    "isolated working directory for each customer source",
    "local secrets kept outside source and delivery artifacts",
    "source deletion evidence before report release"
  ],
  "forbidden_posture": [
    "using the operator workstation as a website backend",
    "routing customer browsers, forms, scripts, webhooks, or upload controls to the workstation",
    "running the linter in a browser-accessible public runtime",
    "exposing local tokens or the linter rule corpus through an internet-facing surface"
  ]
}
```
## repo.client-blueprint-intake.shape-secret-identifier-gates

```json strict-policy
{
  "anchor": "repo.client-blueprint-intake.shape-secret-identifier-gates",
  "rule": "Customer source must pass blueprint shape, secret, and personal-identifier preflight before local analysis or report generation consumes it.",
  "implementation_tool": "src/blueprints/validation/intake.py",
  "shape_gate": [
    "plain filename ending in .blueprint.json",
    "source size at or below 2000000 bytes",
    "valid JSON object",
    "root name",
    "root flow array",
    "no root execution, history, log, bundle, or payload objects"
  ],
  "secret_gate": [
    "hardcoded authorization headers",
    "API keys",
    "bearer tokens",
    "basic-auth values",
    "private keys",
    "JWT-like strings",
    "secret-like URL query parameters",
    "password, token, cookie, secret, or private-key fields"
  ],
  "identifier_gate": [
    "email-like keys or values require manual redaction review",
    "identifier-bearing input must not silently enter a report",
    "redaction status must be recorded before release"
  ],
  "forbidden_posture": [
    "sending raw client blueprint source to an external LLM or provider tool",
    "letting report generation run before the intake decision is accepted",
    "treating warnings as enough to release a secret-bearing report"
  ]
}
```
## repo.client-blueprint-intake.required-manifest-and-truncation-fields

```json strict-policy
{
  "anchor": "repo.client-blueprint-intake.required-manifest-and-truncation-fields",
  "rule": "Client blueprint intake manifests must use required fields for source, truncation, redaction, deletion, processor, and backend exposure status.",
  "implementation_type": "ClientBlueprintIntakeManifest",
  "required_fields": [
    "decision",
    "file_name",
    "accepted_artifact_type",
    "artifact_source_type",
    "intake_method",
    "received_surface",
    "customer_authorization_ref",
    "processor_boundary",
    "local_analysis_boundary",
    "public_backend_exposure",
    "source_sha256",
    "size_bytes",
    "max_size_bytes",
    "is_truncated",
    "truncation_reason",
    "shape_status",
    "secret_status",
    "personal_data_status",
    "redaction_status",
    "redaction_reason",
    "deletion_status",
    "deletion_reason",
    "evidence_coverage_status",
    "external_model_processing_allowed",
    "findings"
  ],
  "required_posture": [
    "all manifest fields are constructor-required with no defaults",
    "is_truncated and truncation_reason are explicit even when complete",
    "external_model_processing_allowed is false for client blueprint source",
    "public_backend_exposure is forbidden for the MVP"
  ],
  "forbidden_posture": [
    "using optional truncation fields",
    "using null to imply complete source",
    "omitting processor or deletion status from a release decision",
    "assuming a missing field means safe"
  ]
}
```
## repo.client-blueprint-intake.report-release-deletion-gate

```json strict-policy
{
  "anchor": "repo.client-blueprint-intake.report-release-deletion-gate",
  "rule": "No client report may be released from customer blueprint source until intake is accepted and raw-source deletion evidence is recorded.",
  "implementation_tool": "client_blueprint_report_release_errors",
  "required_release_state": {
    "decision": "accepted_for_local_analysis",
    "shape_status": "passed",
    "secret_status": "passed",
    "personal_data_status": "passed",
    "redaction_status": "not_required or redacted",
    "deletion_status": "completed",
    "evidence_coverage_status": "complete",
    "is_truncated": false,
    "truncation_reason": "not_truncated"
  },
  "required_behavior": [
    "release gates fail closed",
    "deletion evidence is explicit",
    "manual-review inputs remain blocked until a later redaction workflow records resolution",
    "only sanitized findings and bounded excerpts may enter customer output"
  ],
  "forbidden_posture": [
    "releasing a report while source deletion is not_started",
    "releasing a report from secret-bearing source",
    "releasing a report while identifier redaction remains unresolved"
  ]
}
```
## repo.client-blueprint-intake.hosted-upload-deferred

```json strict-policy
{
  "anchor": "repo.client-blueprint-intake.hosted-upload-deferred",
  "rule": "Full web upload, external HTTPS hosting, object storage, and UI-designed customer portals remain pending until a separate hosted-intake ADR approves the threat model.",
  "pending_owner": "docs/todo/pending/web-upload-backend-and-external-hosting-review.md",
  "allowed_now": [
    "static public page with email or offline handoff instructions",
    "no file handling",
    "no public API call",
    "no upload form",
    "no customer route to the operator workstation"
  ],
  "promotion_requirements": [
    "external server or managed provider selected",
    "HTTPS, WAF, rate limit, object storage, and deletion model reviewed",
    "processor and subprocessor boundaries named",
    "client-side encryption decision recorded",
    "linter corpus exposure threat model approved"
  ],
  "forbidden_posture": [
    "building hosted intake from this ADR",
    "treating a dumb frontend as if third-party storage is not a processing surface",
    "claiming local-only handling when hosted storage, mail storage, logs, or queues retain source"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Customer blueprint intake now has a typed local preflight boundary before AST
validation, PDF rendering, or client report release.
- The first sales web surface can be static instructions only; public upload and
hosted processing remain pending.
- The operator workstation can be the private analysis backend, but only behind
a local-only hardening posture with no customer-routable network path.
- Real customer files remain out of tests and active source control.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001075`.
- Decision ID: `repo.client-blueprint-intake.privacy-boundary`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001075'
decision_id: 'repo.client-blueprint-intake.privacy-boundary'
title: 'Client Blueprint Intake Privacy Boundary Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - security
  - privacy
  - tooling
  - testing
scope: 'repository/client-blueprint-intake'
applies_to:
  - src/blueprints/validation/intake.py
  - src/blueprints/validation/README.md
  - tests/blueprints/validation/client_intake_privacy_contract.py
  - docs/bibliography/client-blueprint-intake-privacy-law.md
  - docs/todo/pending/web-upload-backend-and-external-hosting-review.md
applies_when:
  - customer_blueprint_source_is_received
  - customer_blueprint_preflight_runs
  - client_report_generation_is_requested
  - public_web_intake_is_considered
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001035'
  - '001044'
  - '001046'
  - '001054'
  - '001073'
  - '001074'
derived_artifacts:
  - src/blueprints/validation/intake.py
  - src/blueprints/validation/README.md
  - tests/blueprints/validation/client_intake_privacy_contract.py
  - docs/bibliography/client-blueprint-intake-privacy-law.md
source_material:
  - path: 'docs/todo/completed/c_0003-local-first-client-intake-privacy-mvp.md'
    usage: source evidence after completion archive
    copied_verbatim: false
bibliography_refs:
  - 'https://help.make.com/blueprints'
  - 'https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-072020-concepts-controller-and-processor-gdpr_en'
  - 'https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/accountability-and-governance/contracts-and-liabilities-between-controllers-and-processors-multi/'
  - 'https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=CIV&sectionNum=1798.100.'
  - 'https://www.cppa.ca.gov/regulations/pdf/cppa_act.pdf'
  - 'https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPDPPP.pdf'
  - 'https://www.diputados.gob.mx/LeyesBiblio/regley/Reg_LFPDPPP.pdf'
  - 'https://csrc.nist.gov/pubs/sp/800/88/r1/final'
traceability_anchors:
  - repo.client-blueprint-intake.email-offline-only-mvp
  - repo.client-blueprint-intake.local-workstation-backend-boundary
  - repo.client-blueprint-intake.shape-secret-identifier-gates
  - repo.client-blueprint-intake.required-manifest-and-truncation-fields
  - repo.client-blueprint-intake.report-release-deletion-gate
  - repo.client-blueprint-intake.hosted-upload-deferred
non_goals:
  - provide legal advice
  - accept real customer files in repository tests
  - build a public upload portal
  - expose the operator workstation to customer traffic
  - replace customer contracts, data processing agreements, or counsel review
```
</details>
