# Compliance Standards Source-Rights And Profile-Gate Policy

## Status

Accepted. Reviewed source date: 2026-05-13.

## Scope

repository/standards-derived-linter-research

## Decision

Pancakes may keep a standards-derived linter research lane for ISO/IEC, PCI DSS, GDPR, SOC 2,
OWASP, NIST, and similar governance sources. The lane is advisory source metadata only. It does not
activate runtime validator behavior, create customer-facing diagnostics, or approve public claims.

Every standards-derived idea must remain candidate-only until a later task records all of the
following:

- current official source URL;
- current terms or rights URL;
- repository bibliography notice;
- rights posture;
- no-copying posture for licensed, paywalled, contractual, or private text;
- deterministic local predicate;
- supported canonical linter code;
- explicit profile gate;
- passing and failing fixture plans;
- false-positive risk;
- client-safe output wording.

## File Boundary

The enforceable research metadata lives in:

- `src/blueprints/validation/data/linter/compliance/standards-source-ledger.json`
- `src/blueprints/validation/data/linter/compliance/standards-candidate-intake.json`

The bibliography notices live in `docs/bibliography/`. They are legal traceability records only and
must not define runtime policy by themselves.

## Rule Payload

```json strict-policy
{
  "anchor": "repo.compliance-standards.source-rights-profile-gate",
  "rule": "Standards-derived linter ideas require source-rights review, bibliography coverage, manual candidate intake, deterministic local predicates, and explicit profile gates before implementation.",
  "standards_lane_status": "advisory_only",
  "active_runtime_behavior": false,
  "required_profile_gate_before_runtime": true,
  "copying_policy": "metadata-and-original-analysis-only",
  "allowed_research_use": [
    "source metadata",
    "official source and terms URLs",
    "original engineering summaries",
    "deterministic local predicate notes",
    "profile-gated candidate records",
    "bibliography notice pointers"
  ],
  "forbidden_research_use": [
    "licensed standard text copying",
    "paywalled standard text copying",
    "private customer contract text copying",
    "public control catalog publication",
    "default runtime findings",
    "certification claims",
    "compliance claims",
    "audit-readiness claims",
    "legal advice"
  ]
}
```

## Source-Rights Findings

PCI SSC material is available through official standards and document-library pages, but PCI SSC
terms and intellectual property policy reserve rights beyond limited personal, non-commercial,
review, study, and informational use. Pancakes can retain metadata and original local-predicate
notes, but it must not copy or redistribute PCI DSS text or claim PCI DSS compliance.

ISO/IEC 27001 and ISO/IEC 27002 are licensed ISO/IEC standards. ISO copyright terms require written
permission for reproduction and restrict AI or similar technology use of ISO content except for ISO
Open data under its own terms. Pancakes may cite public standard pages and write original
summaries, but it must not vendor clauses, controls, annexes, or standard text.

GDPR source work must distinguish legal text, Commission guidance, and repository engineering
boundaries. European Commission guidance is not legal advice, and the Commission legal notice
distinguishes EU-owned content reuse from third-party rights and industrial property. Pancakes may
create local personal-data exposure predicates, but it must not claim GDPR compliance or legal
sufficiency.

AICPA and CIMA SOC material frames SOC 2 as reporting or examination work over controls relevant to
security, availability, processing integrity, confidentiality, or privacy. Their terms restrict
public or commercial reuse without permission. Pancakes may use phrases such as `SOC 2-oriented
control checks` or `trust-control review` with close limitations, but it must not claim
certification, compliance, audit readiness, formal attestation, or trust-report issuance.

NIST CSF material is official government framework material and NIST notes that CSF and NIST
publications are generally public domain in the United States. Pancakes may cite NIST CSF as a
source for original cybersecurity risk-management predicates, but it must not claim CSF adoption,
outcome achievement, certification, compliance, or audit readiness.

OWASP ASVS and OWASP API Security Top 10 material are open project materials under Creative Commons
Attribution-ShareAlike 4.0 terms where indicated. Pancakes may cite OWASP material and create
original local predicates, but it must not claim ASVS level achievement, OWASP accreditation, OWASP
endorsement, API security certification, or assessment completion.

## Promotion Rule

A later implementation task may promote a standards-derived candidate only through the existing
linter manual-intake process. Promotion must be one candidate at a time. The promoted rule must
operate only on local blueprint evidence and must use the weakest severity that still protects the
repository contract. `profile_error` severity requires explicit profile evidence in the blueprint
or engagement context.

## Bibliography

- `docs/bibliography/aicpa-cima-soc.md`
- `docs/bibliography/european-union-gdpr.md`
- `docs/bibliography/iso-iec-27000-series.md`
- `docs/bibliography/nist-cybersecurity-framework.md`
- `docs/bibliography/owasp-application-security.md`
- `docs/bibliography/pci-security-standards-council.md`

## Validation

`tests/blueprints/validation/compliance_standards_research_lane_contract.py` verifies that the
standards ledger stays advisory, points every standard at a bibliography notice, records official
source and terms URLs, requires profile gates, keeps runtime activation disabled, and avoids
customer assurance claims.
