# Client-Safe Audit Report Contract Policy

## Status

Accepted

## Scope

repository/client-safe-audit-report

## Decision

# Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

This policy is a repository report-safety boundary, not legal advice. Official sources were checked
on 2026-05-08 before this ADR was created. Before paid report delivery or customer contract language
is offered, current regulator, standards, platform, and customer-contract sources must be rechecked.

## repo.client-safe-audit-report.json-ssot

```json strict-policy
{
  "anchor": "repo.client-safe-audit-report.json-ssot",
  "rule": "Client-safe audit reports use reviewed JSON as the single source of truth.",
  "canonical_artifact": "ClientSafeAuditReport",
  "implementation_tool": "src/blueprints/validation/client_report.py",
  "projection_order": [
    "reviewed JSON contract",
    "operator Markdown preview",
    "customer PDF projection"
  ],
  "required_posture": [
    "JSON carries every release-relevant safety field",
    "Markdown is review-only and deterministic from JSON",
    "future customer PDF must be deterministic from the reviewed JSON contract",
    "projection renderers must fail before output when the JSON guard reports errors"
  ],
  "forbidden_posture": [
    "treating Markdown as a second source of truth",
    "letting PDF templates invent or omit safety metadata",
    "generating customer reports directly from unsanitized blueprint source",
    "using customer-facing report prose that bypasses deterministic claim guards"
  ]
}
```
## repo.client-safe-audit-report.required-fields

```json strict-policy
{
  "anchor": "repo.client-safe-audit-report.required-fields",
  "rule": "The report contract must require every field whose omission could hide scope, evidence, truncation, confidence, sanitization, retention, or delivery risk.",
  "required_top_level_fields": [
    "report_id",
    "generated_at",
    "generator_version",
    "audience",
    "delivery",
    "scope",
    "evidence_policy",
    "is_truncated",
    "truncation",
    "confidence",
    "disclaimer",
    "executive_summary",
    "technical_findings",
    "sanitization",
    "retention"
  ],
  "required_nested_risk_fields": [
    "truncation.reason",
    "scope.evidence_coverage_status",
    "confidence.rating",
    "confidence.score",
    "technical_findings[].technical_severity",
    "technical_findings[].business_impact",
    "technical_findings[].confidence",
    "technical_findings[].evidence[].is_truncated",
    "technical_findings[].evidence[].truncation_reason",
    "technical_findings[].evidence[].redaction_status",
    "technical_findings[].evidence[].redaction_reason",
    "technical_findings[].evidence[].evidence_limit",
    "technical_findings[].evidence[].sanitization_status",
    "technical_findings[].evidence[].evidence_source_type",
    "sanitization.sanitization_passed",
    "retention.retention_class",
    "retention.delete_after",
    "delivery.docx_enabled",
    "delivery.editable_customer_output_allowed"
  ],
  "forbidden_posture": [
    "using optional fields or defaults for truncation state",
    "using null to mean not truncated",
    "letting missing confidence imply high confidence",
    "letting missing retention imply deletion",
    "letting missing delivery flags imply DOCX is disabled"
  ]
}
```
## repo.client-safe-audit-report.projection-boundaries

```json strict-policy
{
  "anchor": "repo.client-safe-audit-report.projection-boundaries",
  "rule": "Report projections are separated by audience and mutability.",
  "allowed_outputs_now": ["canonical JSON contract", "operator-only Markdown preview"],
  "allowed_after_future_pdf_slice": ["customer PDF projection from reviewed JSON"],
  "disabled_outputs": [
    "DOCX",
    "editable customer findings",
    "customer Markdown delivery",
    "spreadsheet finding edits"
  ],
  "required_posture": [
    "operator Markdown must visibly state it is review-only",
    "customer output must remain immutable-looking and generated from reviewed data",
    "delivery flags must explicitly say DOCX and editable customer output are disabled"
  ],
  "forbidden_posture": [
    "letting customers edit finding severity",
    "shipping operator Markdown as the final customer report",
    "using DOCX unless a later ADR explicitly reverses this boundary"
  ]
}
```
## repo.client-safe-audit-report.leakage-and-claim-gates

```json strict-policy
{
  "anchor": "repo.client-safe-audit-report.leakage-and-claim-gates",
  "rule": "Report guards must block raw source, private identifiers, unsupported platform guarantees, and unsafe professional-service claims before projection.",
  "implementation_tool": "client_safe_audit_report_guard_errors",
  "blocked_customer_output": [
    "credentials",
    "webhook URLs",
    "contact data",
    "account identifiers",
    "raw payloads",
    "raw blueprint JSON",
    "raw-spec terminology",
    "raw specs",
    "raw_spec fields",
    "source-evidence pipeline mechanics",
    "rule-corpus mechanics",
    "full normalized catalogs",
    "copied documentation prose",
    "third-party screenshots without a rights basis",
    "unsupported Make affiliation or certification claims",
    "legal, compliance, uptime, revenue, or zero-failure guarantees"
  ],
  "required_disclosures": [
    "static-analysis scope",
    "partial-evidence and truncation limits",
    "confidence labels",
    "third-party platform behavior limits",
    "legal and compliance non-certification",
    "scoped implementation limits"
  ],
  "forbidden_posture": [
    "releasing a report while sanitization_status is blocked",
    "releasing a report while redaction_status is rejected",
    "hiding unsupported modules, complexity limits, or evidence ceilings",
    "using absence of a forbidden phrase as legal approval"
  ]
}
```
## repo.client-safe-audit-report.pdf-profile-deferred

```json strict-policy
{
  "anchor": "repo.client-safe-audit-report.pdf-profile-deferred",
  "rule": "Archival PDF and advanced PDF signature behavior are explicit deferred profiles, not current renderer guarantees.",
  "current_renderer_profile": "internal_text_pdf",
  "deferred_profiles": ["PDF/A conformance", "PAdES or equivalent advanced PDF signature"],
  "required_future_work": [
    "select and document a renderer or signing library",
    "add standards bibliography for the chosen PDF/A and signature profiles",
    "add conformance and failure tests before claiming support",
    "keep signature keys outside the repository and customer source fixtures"
  ],
  "forbidden_posture": [
    "claiming PDF/A conformance because a file has a .pdf extension",
    "claiming tamper evidence before signature implementation exists",
    "treating deferred profile labels as customer-facing promises"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- The repository can now test the report contract without issuing real customer
reports or consuming unsanitized source.
- JSON, Markdown, and future PDF behavior have separate responsibilities and
shared guard checks.
- Omitted truncation, confidence, sanitization, retention, and delivery fields
are release blockers rather than silent defaults.
- PDF/A and advanced signatures remain explicit future work.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001077`.
- Decision ID: `repo.client-safe-audit-report.contract-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001077'
decision_id: 'repo.client-safe-audit-report.contract-policy'
title: 'Client-Safe Audit Report Contract Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - security
  - privacy
  - testing
  - legal-risk
scope: 'repository/client-safe-audit-report'
applies_to:
  - src/blueprints/validation/client_report.py
  - tests/blueprints/validation/client_safe_audit_report_contract.py
  - docs/bibliography/client-safe-audit-report-generator.md
applies_when:
  - sanitized_blueprint_audit_report_contract_is_prepared
  - operator_markdown_report_projection_is_rendered
  - customer_pdf_audit_report_is_considered
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001035'
  - '001054'
  - '001073'
  - '001074'
  - '001075'
  - '001076'
derived_artifacts:
  - src/blueprints/validation/client_report.py
  - tests/blueprints/validation/client_safe_audit_report_contract.py
  - docs/bibliography/client-safe-audit-report-generator.md
source_material: []
bibliography_refs:
  - 'https://www.ncsc.gov.uk/guidance/penetration-testing'
  - 'https://owasp.org/www-community/Source_Code_Analysis_Tools'
  - 'https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng'
  - 'https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/storage-limitation/'
  - 'https://csrc.nist.gov/pubs/sp/800/88/r2/final'
  - 'https://www.iso.org/standard/71832.html'
  - 'https://www.etsi.org/deliver/etsi_en/319100_319199/31914201/01.02.01_60/en_31914201v010201p.pdf'
traceability_anchors:
  - repo.client-safe-audit-report.json-ssot
  - repo.client-safe-audit-report.required-fields
  - repo.client-safe-audit-report.projection-boundaries
  - repo.client-safe-audit-report.leakage-and-claim-gates
  - repo.client-safe-audit-report.pdf-profile-deferred
non_goals:
  - provide legal advice
  - generate real customer audit reports
  - inspect unsanitized customer blueprint source
  - emit DOCX or editable customer findings
  - claim PDF/A or signature conformance before implementation
```
</details>
