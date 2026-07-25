# Public Demo Aggregate Score Boundary Policy

## Status

Accepted

## Scope

repository/public-demo-aggregate-score

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations for local aggregate demo scoring. It must
not be used as round evidence, migration inventory, scratch notes, or hosted-intake approval.

This policy is a repository product boundary, not security, privacy, legal, or tax advice. Before
public upload, hosted processing, email delivery, checkout, or customer contract language is
offered, current provider documentation, privacy obligations, platform terms, and counsel review
must be checked.

## repo.public-demo-aggregate-score.aggregate-only-output

```json strict-policy
{
  "anchor": "repo.public-demo-aggregate-score.aggregate-only-output",
  "rule": "The public demo score contract exposes aggregate metrics only and withholds exact findings, fixes, rule identities, source snippets, and private implementation details.",
  "allowed_fields": [
    "format_status",
    "error_count",
    "warning_count",
    "info_count",
    "total_quality_score",
    "risk_band",
    "operations_score"
  ],
  "forbidden_fields": [
    "finding_ids",
    "rule_ids",
    "rule_names",
    "fix_instructions",
    "module_paths",
    "source_snippets",
    "prompt_text",
    "scoring_weights",
    "internal_graph_shape",
    "raw_blueprint_payload"
  ],
  "required_posture": [
    "invalid or unsupported input returns an unknown-format status",
    "aggregate counts are deterministic for the same accepted source",
    "paid report output remains a separate contract",
    "the score does not imply compliance approval, Make.com certification, or live runtime proof"
  ],
  "forbidden_posture": [
    "leaking exact diagnostics through parser errors",
    "returning remediation instructions from the public demo path",
    "using aggregate scoring as permission to launch a hosted upload endpoint"
  ]
}
```

## repo.public-demo-aggregate-score.local-engine-only

```json strict-policy
{
  "anchor": "repo.public-demo-aggregate-score.local-engine-only",
  "rule": "This repository may implement a local aggregate score engine, but hosted upload, public API, email delivery, and sandbox runtime remain deferred.",
  "allowed_now": [
    "local aggregate score model",
    "local tests with synthetic or sanitized fixtures",
    "adapter-free pure scoring functions over accepted blueprint analysis results",
    "documentation of the public-safe output shape"
  ],
  "deferred_until_separate_todo": [
    "public upload form",
    "hosted intake API",
    "email-gated demo delivery",
    "sandbox execution service",
    "Vercel or Cloudflare integration",
    "rate-limit enforcement",
    "customer retention and deletion workflow"
  ],
  "forbidden_posture": [
    "binding a public listener to the operator workstation",
    "adding tunnels or callback URLs to local services",
    "storing raw customer blueprints as demo artifacts",
    "using local engine work as live provider approval"
  ]
}
```

## repo.public-demo-aggregate-score.score-semantics

```json strict-policy
{
  "anchor": "repo.public-demo-aggregate-score.score-semantics",
  "rule": "Aggregate scoring summarizes static blueprint readiness and operations risk without revealing the underlying rule corpus.",
  "score_requirements": [
    "risk_band is derived from severity counts and approved aggregate risk factors",
    "total_quality_score is bounded and monotonic with critical aggregate findings",
    "operations_score reflects aggregate operations, cost, timeout, fan-out, and maintenance risk",
    "format_status distinguishes accepted, unknown_format, too_large, and rejected_secret_risk"
  ],
  "required_tests": [
    "invalid payloads do not expose parser detail",
    "known synthetic scenarios produce stable aggregate counts",
    "aggregate output excludes exact finding text and rule identifiers",
    "score output is serializable without raw source"
  ],
  "forbidden_posture": [
    "calculating score from customer identity",
    "using LLM output as the only scoring authority",
    "letting warning/info counts hide format or secret rejection"
  ]
}
```

## repo.public-demo-aggregate-score.readiness-label-boundary

```json strict-policy
{
  "anchor": "repo.public-demo-aggregate-score.readiness-label-boundary",
  "rule": "Any public readiness label generated from aggregate scoring is a scope-limited product label, not legal, compliance, platform, security, or uptime certification.",
  "allowed_label_terms": [
    "readiness label",
    "static blueprint review",
    "dated aggregate result",
    "scope-limited score"
  ],
  "denied_label_terms": [
    "certified compliant",
    "Make.com certified",
    "official Make partner",
    "legally safe",
    "guaranteed uptime",
    "guaranteed savings",
    "enterprise certified"
  ],
  "required_label_context": [
    "artifact identity or hash",
    "date generated",
    "review scope",
    "limits for live runtime behavior",
    "limits for legal, compliance, and business outcomes"
  ]
}
```
