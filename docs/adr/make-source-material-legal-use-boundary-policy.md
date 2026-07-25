# Make Source Material Legal Use Boundary Policy

## Status

Accepted

## Scope

repository/make-source-material

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

This policy is a repository risk boundary, not legal advice. Official sources were checked on
2026-05-08 before this ADR was created. A later commercial or customer deployment must re-check
current Make terms, customer contracts, jurisdiction-specific law, and third-party connector terms.

## repo.make-source-material.source-type-risk-matrix

```json strict-policy
{
  "anchor": "repo.make-source-material.source-type-risk-matrix",
  "rule": "Make-derived source material must be classified by source type before it is retained, normalized, used in tests, or exposed through customer-facing output.",
  "matrix": [
    {
      "source_type": "client_exported_scenario_json",
      "risk_level": "high",
      "allowed_use": "Use only for the authorized customer's static blueprint analysis, local linting, sanitized findings, and agreed report generation.",
      "forbidden_use": "Do not commit, publish, redistribute, cross-train, share across clients, paste into external model providers, or use as a reusable corpus.",
      "required_evidence": "Written customer authorization, intake manifest, source hash, received_at timestamp, deletion status, truncation status, and sanitizer decision.",
      "retention_default": "Reject or delete raw source after verified processing unless the customer contract explicitly requires short retention.",
      "customer_facing_output_limit": "Rule category, affected module or node identifier, sanitized field path, bounded redacted excerpt, and remediation text only.",
      "required_controls": [
        "blueprint-only shape gate",
        "secret rejection",
        "personal-data redaction or rejection",
        "no external model processing",
        "explicit deletion evidence"
      ]
    },
    {
      "source_type": "client_authorized_authenticated_api_response",
      "risk_level": "high",
      "allowed_use": "Use only when the customer or operator explicitly authorizes the endpoint, scope, account, time window, and purpose.",
      "forbidden_use": "Do not use a shared master token, harvest across clients, retain raw dumps, or build a commercial clone of authenticated Make data.",
      "required_evidence": "Token owner, scopes, zone or base URL, endpoint, request time, response source hash, authorization record, and deletion status.",
      "retention_default": "Store no raw response by default; retain only minimized manifest and sanitized derived fields when policy allows.",
      "customer_facing_output_limit": "Status, coverage, normalized capability summary, and sanitized evidence references only.",
      "required_controls": [
        "least-privilege token scope",
        "no committed raw response",
        "manifest source trace",
        "fail-closed truncation status",
        "credential redaction"
      ]
    },
    {
      "source_type": "public_make_docs",
      "risk_level": "medium",
      "allowed_use": "Use as reference material for interoperability, validation, citation, and operator documentation.",
      "forbidden_use": "Do not mirror documentation bodies, bulk-copy prose, redistribute screenshots, publish docs-derived catalogs, or imply Make endorsement.",
      "required_evidence": "Bibliography notice, reviewed URL, accessed date when relied on for policy, and concise paraphrased use.",
      "retention_default": "Retain bibliography notices and short references; do not vendor public documentation bodies.",
      "customer_facing_output_limit": "Short citation, paraphrased platform limitation, and link reference when needed.",
      "required_controls": [
        "bibliography coverage",
        "no docs body vendoring",
        "no trademark asset copying",
        "no endorsement language"
      ]
    },
    {
      "source_type": "normalized_catalog",
      "risk_level": "medium",
      "allowed_use": "Use internally as a functional compatibility map for validation, rendering, diagnostics, and fixture generation.",
      "forbidden_use": "Do not expose as a downloadable module directory, raw-spec browser, public API clone, customer appendix, or marketing asset.",
      "required_evidence": "Source ranking, source label, generation version, source manifest reference, and validation status.",
      "retention_default": "Track only sanitized, functional-minimum snapshots approved by catalog ADRs; keep generated raw inputs ignored.",
      "customer_facing_output_limit": "Only high-level support or unknown-module status and sanitized rule evidence.",
      "required_controls": [
        "functional-minimum fields only",
        "source-rank trace",
        "no raw-spec dump",
        "internal-only default",
        "catalog validation"
      ]
    },
    {
      "source_type": "derived_fixture",
      "risk_level": "low_to_medium",
      "allowed_use": "Use synthetic, minimized, or redacted fixtures to prove validation, rendering, linting, report, and scrubber behavior.",
      "forbidden_use": "Do not embed customer payloads, live credentials, copied documentation prose, third-party screenshots, or full raw schemas.",
      "required_evidence": "Fixture provenance, synthetic or redaction marker, expected behavior, and no-secret assertion.",
      "retention_default": "Tracked when synthetic or redacted enough for repository tests; otherwise ignored or regenerated from safe sources.",
      "customer_facing_output_limit": "Not customer-facing unless explicitly generated as a sanitized example.",
      "required_controls": [
        "synthetic provenance",
        "secret scan",
        "personal-data scan",
        "minimal shape",
        "fixture contract test"
      ]
    },
    {
      "source_type": "third_party_connector_material",
      "risk_level": "medium_to_high",
      "allowed_use": "Use only as minimal interoperability reference when a connector's public or authorized material is necessary for validation.",
      "forbidden_use": "Do not copy provider docs, logos, screenshots, secrets, private schemas, rate-limit tables, or proprietary examples into customer output.",
      "required_evidence": "Provider source URL or customer authorization, usage reason, rights basis, and bibliography notice when public material is referenced.",
      "retention_default": "Prefer no retention; retain only minimal typed facts that are needed by validated rules.",
      "customer_facing_output_limit": "Provider name, sanitized affected surface, and remediation guidance without copied provider material.",
      "required_controls": [
        "rights-basis record",
        "no logo or screenshot default",
        "minimal typed fact extraction",
        "provider-specific terms review"
      ]
    }
  ],
  "forbidden_posture": [
    "using any source type without provenance",
    "assuming a blueprint is harmless because native Make connections are excluded",
    "treating public docs as permission to republish a module directory",
    "turning private customer exports into reusable training or benchmark data",
    "hiding truncation, redaction, retention, or deletion status behind optional fields"
  ]
}
```
## repo.make-source-material.transform-not-redistribute

```json strict-policy
{
  "anchor": "repo.make-source-material.transform-not-redistribute",
  "rule": "The repository may transform source material into functional validation facts, but must not redistribute expressive, private, or customer-specific source material.",
  "allowed_internal_fields": [
    "module identifier",
    "app or family identifier",
    "operation name",
    "parameter key",
    "parameter type",
    "required or optional status",
    "enum literal when needed for renderer compatibility",
    "schema shape needed for validation",
    "rate-limit class when verified and needed for linting",
    "source label",
    "source rank",
    "truncation status"
  ],
  "forbidden_republished_fields": [
    "raw customer mapped values",
    "credentials or credential-like strings",
    "account identifiers",
    "connection labels",
    "execution payloads",
    "private API responses",
    "copied documentation prose",
    "vendor screenshots",
    "logos or trademark assets",
    "complete raw specs",
    "downloadable normalized catalog dumps"
  ],
  "required_posture": [
    "prefer typed functional facts over copied source blobs",
    "store generated raw inputs outside tracked source",
    "keep customer exports out of the repository",
    "fail closed when provenance is missing",
    "preserve source trace without exposing source payload"
  ]
}
```
## repo.make-source-material.client-custom-module-boundary

```json strict-policy
{
  "anchor": "repo.make-source-material.client-custom-module-boundary",
  "rule": "Client custom Make modules are customer source material unless a reviewed rights basis proves they describe a generally available public API connector.",
  "classification": [
    {
      "class": "public_api_connector_candidate",
      "allowed_use": "Create a follow-up documentation review task and derive a master connector spec only from public or authorized provider material.",
      "forbidden_use": "Do not reuse client payload values, private endpoint examples, customer business JSON, credentials, or unreviewed authenticated responses."
    },
    {
      "class": "client_business_custom_module",
      "allowed_use": "Preserve the blueprint node as pass-through AST evidence and use only sanitized, customer-authorized facts for that customer's engagement.",
      "forbidden_use": "Do not promote the module into the shared Make catalog, raw-spec corpus, examples, benchmarks, or cross-client training material."
    },
    {
      "class": "private_third_party_or_customer_private_module",
      "allowed_use": "Do not ingest until customer authorization, provider terms, retention, redaction, and deletion behavior are explicit.",
      "forbidden_use": "Do not infer permission from a blueprint export or from the fact that a module can be seen in Make."
    }
  ],
  "required_posture": [
    "unknown custom modules must remain preserved as unresolved pass-through AST nodes",
    "catalog-backed custom modules require source label, source rank, and manifest provenance",
    "raw customer module specs must not be committed as shared catalog truth",
    "future client_raw_module_specs lanes must be ignored or retention-controlled by default",
    "shared master JSON may be created only after public-doc or authorized-source review"
  ]
}
```
## repo.make-source-material.customer-output-limit

```json strict-policy
{
  "anchor": "repo.make-source-material.customer-output-limit",
  "rule": "Customer-facing output may explain findings and remediation but must not expose raw source material, raw catalogs, credentials, private identifiers, or copied platform material.",
  "allowed_customer_outputs": [
    "finding id",
    "finding title",
    "severity",
    "confidence",
    "rule category",
    "affected module or node identifier",
    "sanitized field path",
    "bounded redacted excerpt with explicit truncation status",
    "module support status",
    "remediation guidance",
    "static-analysis limitation statement"
  ],
  "forbidden_customer_outputs": [
    "raw blueprint JSON",
    "full normalized catalog",
    "raw spec data",
    "copied Make documentation prose beyond short citation needs",
    "screenshots or branded assets without a recorded rights basis",
    "mapped values that are not redacted",
    "secrets",
    "connection identifiers",
    "account identifiers",
    "customer email addresses",
    "runtime payloads",
    "private endpoint responses"
  ],
  "required_fields_when_any_evidence_is_presented": [
    "is_truncated",
    "truncation_reason",
    "redaction_status",
    "redaction_reason",
    "evidence_source_type",
    "evidence_limit",
    "sanitization_status"
  ],
  "fail_fast_conditions": [
    "is_truncated is missing",
    "truncation_reason is missing",
    "raw source is about to be emitted",
    "secret-like value is about to be emitted",
    "evidence source type is unknown"
  ]
}
```
## repo.make-source-material.authorization-and-credential-boundary

```json strict-policy
{
  "anchor": "repo.make-source-material.authorization-and-credential-boundary",
  "rule": "Live Make access and customer material handling require explicit authorization, least privilege, local credential isolation, and no hidden live-service behavior.",
  "required_posture": [
    "do not read .env unless the operator explicitly asks for a credentialed task",
    "do not commit real credentials",
    "do not use one master Make token across unrelated clients",
    "scope tokens to the minimum endpoint and account needed",
    "record endpoint, scope, zone, and time window for authorized API pulls",
    "disable live scrapers by default",
    "make live-service behavior explicit before execution",
    "do not expose the operator workstation as a public upload or linting backend"
  ],
  "forbidden_posture": [
    "silent Make API calls during offline validation",
    "shared customer harvest token",
    "committed raw authenticated responses",
    "public upload endpoint routed to local analysis tools",
    "external model processing of client blueprint source material",
    "marketing copy that hides email, hosted, or local retention surfaces"
  ]
}
```
## repo.make-source-material.unresolved-counsel-review

```json strict-policy
{
  "anchor": "repo.make-source-material.unresolved-counsel-review",
  "rule": "This ADR is an engineering risk boundary and must leave legal conclusions that require counsel or contract review unresolved.",
  "requires_counsel_or_operator_review": [
    "negotiated Make enterprise terms or private API commitments",
    "customer master services agreement and data-processing terms",
    "jurisdiction-specific implementation of copyright, database, privacy, and trade-secret rules",
    "third-party connector documentation and trademark terms",
    "sector-specific regulated-data obligations",
    "retention, deletion, breach, and subprocessor promises in customer contracts",
    "public distribution of any docs-derived or catalog-derived artifact"
  ],
  "safe_default_until_review": [
    "internal functional use only",
    "no public redistribution",
    "no customer source retention by default",
    "no raw-source customer output",
    "no live Make access without explicit authorization",
    "no full upload portal until provider and workstation exposure boundaries are approved"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Raw Make source material is classified before use instead of being treated as
one generic input bucket.
- The repository may keep building validators, catalogs, and fixtures, but only
by retaining functional facts and source trace rather than redistributing raw source material.
- Customer-facing report surfaces must be sanitized summaries with required
truncation and redaction metadata.
- Future live Make access, customer blueprint intake, and hosted upload work
must prove authorization, processor boundaries, and deletion behavior before implementation.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001074`.
- Decision ID: `repo.make-source-material.legal-use-boundary`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001074'
decision_id: 'repo.make-source-material.legal-use-boundary'
title: 'Make Source Material Legal Use Boundary Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - security
  - persistence
  - tooling
scope: 'repository/make-source-material'
applies_to:
  - src/catalog/raw_specs/**/*
  - src/catalog/**/*
  - src/blueprints/**/*
  - src/pdf/**/*
  - data/make/**/*
  - tests/catalog/**/*
  - tests/blueprints/**/*
  - docs/bibliography/make.com.md
  - docs/bibliography/software-interoperability-ip-law.md
applies_when:
  - make_source_material_is_ingested
  - raw_specs_are_normalized
  - catalog_or_fixture_evidence_is_prepared
  - customer_report_output_is_prepared
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001041'
  - '001042'
  - '001061'
  - '001062'
  - '001073'
derived_artifacts:
  - src/catalog/README.md
  - src/catalog/raw_specs/README.md
  - data/make/README.md
  - docs/bibliography/make.com.md
  - docs/bibliography/software-interoperability-ip-law.md
  - docs/todo/completed/c_0002-make-source-provenance-and-report-output-guards.md
source_material:
  - path: 'docs/todo/completed/c_0001-raw-spec-ip-and-commercial-legality-review.md'
    usage: source evidence after completion archive
    copied_verbatim: false
bibliography_refs:
  - 'https://www.make.com/en/terms-and-conditions'
  - 'https://www.make.com/master-service-agreement.pdf'
  - 'https://www.make.com/en/disclaimer'
  - 'https://help.make.com/blueprints'
  - 'https://developers.make.com/api-documentation/authentication'
  - 'https://www.supremecourt.gov/opinions/20pdf/18-956diff_n6p1.pdf'
  - 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024'
  - 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:31996L0009'
  - 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016L0943'
traceability_anchors:
  - repo.make-source-material.source-type-risk-matrix
  - repo.make-source-material.transform-not-redistribute
  - repo.make-source-material.customer-output-limit
  - repo.make-source-material.authorization-and-credential-boundary
  - repo.make-source-material.unresolved-counsel-review
non_goals:
  - provide legal advice
  - publish a Make module directory or raw-spec wiki
  - authorize live Make scraping by default
  - authorize customer payload retention without engagement authorization
  - override negotiated customer, Make, or third-party connector terms
```
</details>
