# Blueprint QA Claims Boundary Policy

## Status

Accepted

## Scope

repository/blueprint-qa-claims

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

This policy is a repository claim-safety boundary, not legal advice. Official sources were checked
on 2026-05-08 before this ADR was created. Before public advertising, paid delivery terms, or
customer contract language is offered, current regulator materials, Make terms, platform terms,
customer contracts, and counsel advice must be rechecked.

## repo.blueprint-qa-claims.claim-taxonomy

```json strict-policy
{
  "anchor": "repo.blueprint-qa-claims.claim-taxonomy",
  "rule": "Every customer-facing blueprint QA sentence must fit a claim bucket before publication.",
  "claim_buckets": [
    "service_description",
    "observed_fact",
    "inference",
    "measured_result",
    "legal_or_compliance",
    "platform_affiliation",
    "business_outcome",
    "third_party_platform_limit",
    "scope_limit",
    "truncation_limit",
    "implementation_scope"
  ],
  "required_posture": [
    "process claims must describe the actual static or scoped engineering process",
    "evidence claims must identify the available evidence class without exposing raw source",
    "measured-result claims require before and after proof before publication",
    "legal_or_compliance claims require counsel review and must default to non-certification language",
    "platform_affiliation claims require current verified authorization from the named platform",
    "business_outcome claims require prior substantiation and must default to no guarantee",
    "limits must be close to the claim they qualify"
  ],
  "forbidden_posture": [
    "publishing objective claims without prior support",
    "using vague disclaimers to rescue an otherwise false or overbroad claim",
    "letting automated report prose imply legal, platform, uptime, revenue, or compliance certainty",
    "describing the report as independent or neutral when it is commercial delivery output"
  ]
}
```
## repo.blueprint-qa-claims.allowed-claims

```json strict-policy
{
  "anchor": "repo.blueprint-qa-claims.allowed-claims",
  "rule": "The paid offer may claim static audit, deterministic rule checking, scoped repair, and measured local improvement only when matching evidence exists.",
  "allowed_claims": [
    {
      "claim": "Automated static audit of customer-supplied Make blueprint artifacts.",
      "bucket": "service_description",
      "required_evidence": [
        "accepted intake manifest",
        "source hash",
        "validated blueprint artifact"
      ]
    },
    {
      "claim": "Deterministic, rule-based report with evidence linked to sanitized modules, routes, mappings, or affected component labels.",
      "bucket": "observed_fact",
      "required_evidence": ["validation report", "rule category", "sanitized evidence metadata"]
    },
    {
      "claim": "Identifies configuration patterns associated with elevated timeout, duplication, rollback, rate-limit, privacy, or operations-consumption risk.",
      "bucket": "inference",
      "required_evidence": [
        "static artifact evidence",
        "confidence label",
        "third-party platform limitation statement"
      ]
    },
    {
      "claim": "Scoped repair implementation of the issues listed in the order form or statement of work.",
      "bucket": "implementation_scope",
      "required_evidence": ["accepted scope", "change evidence", "acceptance criteria"]
    },
    {
      "claim": "Measured improvement in the tested environment.",
      "bucket": "measured_result",
      "required_evidence": [
        "baseline",
        "measurement method",
        "test window",
        "exclusions",
        "before and after proof"
      ]
    },
    {
      "claim": "A narrow delivery remedy for failure to deliver the scoped audit or implementation deliverable.",
      "bucket": "service_description",
      "required_evidence": ["order form", "delivery checklist", "remedy terms"]
    }
  ],
  "forbidden_posture": [
    "letting allowed claims imply live runtime verification when only static evidence exists",
    "letting measured-result language appear without the baseline, method, window, exclusions, and proof",
    "turning a delivery remedy into a guarantee about Make, third-party services, customer revenue, or customer compliance"
  ]
}
```
## repo.blueprint-qa-claims.denied-claims

```json strict-policy
{
  "anchor": "repo.blueprint-qa-claims.denied-claims",
  "rule": "Public, report, checkout, and customer-facing copy must deny unsupported certainty, affiliation, compliance, managed-service, and business-outcome claims.",
  "denied_claims": [
    "guaranteed fix",
    "zero failures",
    "no more timeouts",
    "bulletproof",
    "fail-proof",
    "mathematical certainty",
    "guaranteed savings",
    "guaranteed ROI",
    "guaranteed revenue increase",
    "guaranteed legal compliance",
    "certified compliant",
    "legally safe",
    "legal opinion",
    "official Make partner",
    "certified Make expert",
    "Make-approved audit",
    "Make-certified repair",
    "Make guarantees our outcomes",
    "continuous monitoring",
    "managed service",
    "on-call platform ownership",
    "independent benchmark when the output is sales collateral"
  ],
  "risk_reasons": [
    "static blueprint evidence cannot guarantee live runtime behavior",
    "third-party services, connectors, rate limits, permissions, and platform changes remain outside repository control",
    "legal and compliance conclusions require broader organizational and counsel review",
    "platform affiliation and trademark claims require current authorization",
    "business outcome claims require prior substantiation and can mislead buyers",
    "managed-service wording creates operational responsibility that the current offer excludes"
  ],
  "forbidden_posture": [
    "using denied phrases with minor punctuation changes",
    "hiding denied meanings behind softer adjectives",
    "placing denied claims in screenshots, checkout descriptions, receipts, PDFs, emails, or support replies"
  ]
}
```
## repo.blueprint-qa-claims.required-report-language

```json strict-policy
{
  "anchor": "repo.blueprint-qa-claims.required-report-language",
  "rule": "Generated customer deliverables must include close, clear limitations for scope, truncation, confidence, third-party platform behavior, legal non-certification, and scoped implementation.",
  "required_statement_classes": [
    "scope_and_evidence",
    "truncation_and_partial_evidence",
    "confidence_labels",
    "third_party_platform_limits",
    "legal_and_compliance_non_certification",
    "implementation_scope"
  ],
  "minimum_semantics": {
    "scope_and_evidence": "The report is a static, rule-based analysis of listed artifacts and does not certify live runtime behavior.",
    "truncation_and_partial_evidence": "Findings apply only to successfully parsed and reviewed artifacts; missing, redacted, split, or truncated evidence means coverage is partial.",
    "confidence_labels": "Findings must distinguish confirmed observations, probable inferences, and possible risk patterns.",
    "third_party_platform_limits": "Runtime outcomes depend on Make, connected services, permissions, rate limits, data quality, and traffic patterns.",
    "legal_and_compliance_non_certification": "The report is not a legal opinion and does not certify regulatory compliance.",
    "implementation_scope": "Repair implementation confirms only scoped changes and accepted tests in the tested environment."
  },
  "forbidden_posture": [
    "rendering a customer report without these limitations",
    "placing limitations only in remote terms when the report or checkout page contains the triggering claim",
    "using optional fields or empty boilerplate to imply complete evidence"
  ]
}
```
## repo.blueprint-qa-claims.client-output-claim-gates

```json strict-policy
{
  "anchor": "repo.blueprint-qa-claims.client-output-claim-gates",
  "rule": "Client-output tooling must deterministically block known unsafe claim shapes before PDF, website, checkout, email, or support copy is treated as releasable.",
  "implementation_tool": "src/pdf/claims.py",
  "required_tests": [
    "unsafe guarantees are reported",
    "platform-affiliation claims are reported",
    "legal and compliance certification claims are reported",
    "business-outcome guarantees are reported",
    "default handoff report text contains required limitation classes"
  ],
  "required_posture": [
    "claim gates are deterministic and local",
    "claim gates complement but do not replace counsel or operator review",
    "client-copy guards call claim guards for report text",
    "required limitation text must be present before report release"
  ],
  "forbidden_posture": [
    "using the guard result as legal approval",
    "letting LLM copy bypass deterministic forbidden-claim checks",
    "treating absence of a forbidden phrase as permission to make a new unreviewed claim"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- The offer can describe static audit, deterministic rule checking, and scoped
repair without implying platform, legal, uptime, or revenue certainty.
- Report, PDF, and future web copy get one local claim gate before publication.
- Public sales and customer deliverables must carry close limitations instead
of relying on hidden terms or vague disclaimers.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001076`.
- Decision ID: `repo.blueprint-qa.claims-boundary`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001076'
decision_id: 'repo.blueprint-qa.claims-boundary'
title: 'Blueprint QA Claims Boundary Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - documentation
  - testing
  - legal-risk
scope: 'repository/blueprint-qa-claims'
applies_to:
  - src/pdf/claims.py
  - src/pdf/client_copy.py
  - src/pdf/models.py
  - src/pdf/README.md
  - tests/pdf/*claims*.py
  - tests/pdf/handoff_pdf_contract.py
  - docs/bibliography/blueprint-qa-claims-boundary-law.md
applies_when:
  - blueprint_qa_offer_claims_are_written
  - customer_static_audit_report_is_generated
  - customer_repair_implementation_offer_is_written
  - public_marketing_or_checkout_copy_mentions_make_blueprint_qa
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001035'
  - '001054'
  - '001061'
  - '001073'
  - '001074'
  - '001075'
derived_artifacts:
  - src/pdf/claims.py
  - src/pdf/client_copy.py
  - src/pdf/models.py
  - src/pdf/README.md
  - tests/pdf/client_claims_contract.py
  - docs/bibliography/blueprint-qa-claims-boundary-law.md
source_material: []
bibliography_refs:
  - 'https://www.ftc.gov/legal-library/browse/ftc-policy-statement-regarding-advertising-substantiation'
  - 'https://www.ftc.gov/system/files/documents/plain-language/bus41-dot-com-disclosures-information-about-online-advertising.pdf'
  - 'https://www.ftc.gov/legal-library/browse/cases-proceedings/donotpay'
  - 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32006L0114'
  - 'https://www.make.com/en/terms-and-conditions'
  - 'https://www.make.com/master-service-agreement.pdf'
  - 'https://help.make.com/blueprints'
  - 'https://www.make.com/en/brand-guidelines.pdf'
  - 'https://www.make.com/en/partners'
  - 'https://www.make.com/en/partners-list'
traceability_anchors:
  - repo.blueprint-qa-claims.claim-taxonomy
  - repo.blueprint-qa-claims.allowed-claims
  - repo.blueprint-qa-claims.denied-claims
  - repo.blueprint-qa-claims.required-report-language
  - repo.blueprint-qa-claims.client-output-claim-gates
non_goals:
  - provide legal advice
  - write public sales copy
  - authorize paid intake or hosted upload flows
  - claim Make affiliation, certification, endorsement, or partnership
  - guarantee legal, compliance, revenue, uptime, or platform outcomes
```
</details>
