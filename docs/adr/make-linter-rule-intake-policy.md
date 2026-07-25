# Make Linter Rule Intake Policy

## Status

Accepted

## Scope

repository/make-linter-rule-intake

## Decision

## File Boundary

This ADR is a canonical policy record. It owns the manual intake gate for Make linter candidate
rules. It must not be used as a candidate ledger, runtime validator, family implementation plan, or
client-facing diagnostic catalog.

## repo.make-linter.rule-intake-manual-gate

```json strict-policy
{
  "anchor": "repo.make-linter.rule-intake-manual-gate",
  "rule": "Every imported, generated, or model-expanded Make linter rule remains a candidate until manually reviewed one candidate ID at a time.",
  "required_decisions": [
    "accept",
    "rewrite",
    "downgrade",
    "quarantine",
    "reject",
    "alias_to_canonical"
  ],
  "required_posture": [
    "review each candidate ID one by one",
    "record exactly one closed decision per candidate ID before implementation",
    "preserve the original candidate ID even when a canonical rule consolidates duplicates",
    "treat strong-model origin as irrelevant to acceptance",
    "block bulk acceptance, bulk severity promotion, and bulk deletion"
  ],
  "forbidden_posture": [
    "accepting candidates because they sound useful",
    "accepting candidates because they were produced by a capable model",
    "implementing a family TODO before recording candidate decisions",
    "deleting rejected candidates without a reason",
    "collapsing duplicate IDs without alias traceability"
  ]
}
```
## repo.make-linter.rule-intake-evidence-record

```json strict-policy
{
  "anchor": "repo.make-linter.rule-intake-evidence-record",
  "rule": "A linter candidate review row must explicitly state all fields needed to prove what was decided and why.",
  "required_fields": [
    "candidate_id",
    "source_file",
    "original_heading",
    "decision",
    "canonical_rule_code",
    "alias_of_candidate_id",
    "evidence_surfaces",
    "deterministic_predicate",
    "severity_posture",
    "profile_gates",
    "implementation_owner",
    "failing_fixture_plan",
    "passing_fixture_plan",
    "adr_impact",
    "bibliography_impact",
    "false_positive_risk",
    "quarantine_reason",
    "rejection_reason",
    "rationale"
  ],
  "promotion_required_fields": [
    "canonical_rule_code",
    "evidence_surfaces",
    "deterministic_predicate",
    "implementation_owner",
    "failing_fixture_plan",
    "passing_fixture_plan",
    "adr_impact",
    "bibliography_impact",
    "false_positive_risk"
  ],
  "required_posture": [
    "typed records have no default field values",
    "accepted, rewritten, or downgraded rules must include failing and passing fixture plans",
    "rejected rules must include a rejection reason",
    "quarantined rules must include a quarantine reason",
    "aliases must name the canonical rule code or canonical candidate ID"
  ]
}
```
## repo.make-linter.rule-intake-determinism-and-severity

```json strict-policy
{
  "anchor": "repo.make-linter.rule-intake-determinism-and-severity",
  "rule": "Accepted linter behavior must be deterministic from local evidence and must use the weakest severity that still protects the repository contract.",
  "evidence_surfaces": [
    "adr_policy",
    "allowlist",
    "ast_structure",
    "catalog_truth",
    "connection_reference",
    "denylist",
    "knowledge_store",
    "local_failure",
    "mapping_ast",
    "metadata",
    "note_surface",
    "promoted_golden_evidence",
    "raw_spec_field",
    "topology",
    "validation_fixture"
  ],
  "severity_postures": ["error", "warning", "profile_error", "optimization", "quarantine"],
  "required_posture": [
    "use error only when the blueprint, AST, catalog, metadata, route topology, mapping expression, local fixture, or ADR-backed repository rule makes the failure deterministic",
    "use warning or optimization when external runtime, account, plan, provider, traffic, billing, or organization context prevents blocking certainty",
    "use profile_error only with an explicit profile gate",
    "use quarantine when the intuition is useful but not locally enforceable as written",
    "convert subjective prose into deterministic local proxies before implementation"
  ],
  "forbidden_posture": [
    "using live provider behavior to justify default offline severity",
    "raising a warning to error because the text sounds severe",
    "claiming provider guarantees that local evidence cannot prove",
    "using template scenario behavior as business logic authority"
  ]
}
```
## repo.make-linter.rule-intake-non-loss-quarantine

```json strict-policy
{
  "anchor": "repo.make-linter.rule-intake-non-loss-quarantine",
  "rule": "No imported linter candidate disappears without a recorded decision, alias, rejection reason, or quarantine reason.",
  "quarantine_reasons": [
    "subjective_or_fuzzy",
    "duplicate_without_new_behavior",
    "provider_runtime_only",
    "impossible_to_verify_locally",
    "retired_scope_resurrection",
    "customer_claim_leakage",
    "high_false_positive_risk",
    "template_logic_contamination"
  ],
  "required_posture": [
    "retain duplicate source IDs as aliases",
    "retain bad or vague rules in quarantine with an English reason",
    "preserve imported source file and original heading in the review row",
    "record false-positive risk before severity is chosen",
    "preserve quarantined candidates under src/blueprints/validation/data/linter/quarantine/** until a later one-candidate review promotes, rewrites, aliases, or rejects them"
  ]
}
```
## repo.make-linter.rule-intake-audit-matrix

```json strict-policy
{
  "anchor": "repo.make-linter.rule-intake-audit-matrix",
  "rule": "The linter must declare whether each rule family evaluates source code, SQLite data, or both before the rule can be treated as covered.",
  "sqlite_tables": [
    "linter_rule_surface_matrix",
    "linter_data_source_inventory",
    "linter_quarantine_records",
    "linter_quarantine_review_events"
  ],
  "rule_surfaces": [
    "code_only",
    "sqlite_only",
    "cross_surface"
  ],
  "required_posture": [
    "classify code predicates separately from SQLite predicates",
    "represent tracked linter data files in SQLite before runtime use",
    "treat manifest, review coverage, and MCP review JSON as generated snapshots",
    "treat legacy decision ledgers and Markdown records as migration evidence until consumed",
    "keep source fixtures only when they are deterministic test inputs or generated snapshots"
  ],
  "forbidden_posture": [
    "using JSON or Markdown linter files as runtime authority after SQLite ingestion",
    "running a rule that depends on SQLite rows without a SQLite predicate entry",
    "deleting legacy candidate evidence without preserving the candidate ID in SQLite",
    "letting a code-only test stand in for SQLite data coverage"
  ]
}
```
## repo.make-linter.rule-intake-unquarantine-lane

```json strict-policy
{
  "anchor": "repo.make-linter.rule-intake-unquarantine-lane",
  "rule": "Quarantined linter candidates may be revisited only through a one-candidate unquarantine lane that preserves ADR 001079 manual review before runtime behavior changes.",
  "record_root": "src/blueprints/validation/data/linter/quarantine/",
  "manifest": "src/blueprints/validation/data/linter/quarantine/manifest.json",
  "allowed_final_states": ["kept_quarantined", "promoted", "rewritten", "aliased", "rejected"],
  "required_posture": [
    "select exactly one quarantined candidate record per unquarantine review",
    "keep the original source file, candidate ID, and heading visible",
    "require deterministic local evidence, failing and passing fixtures, severity or profile gates, taxonomy updates, and ADR impact before promotion",
    "update the quarantine record and manifest final state in the same validated work unit",
    "keep unquarantine output review-only until ADR 001079 promotion is complete"
  ],
  "forbidden_posture": [
    "bulk promoting quarantine records",
    "turning quarantine records into runtime findings by path scan",
    "exposing internal quarantine rationale or candidate IDs in client-facing diagnostics",
    "deleting quarantine records after promotion without preserving source traceability"
  ]
}
```
## repo.make-linter.rule-intake-runtime-boundary

```json strict-policy
{
  "anchor": "repo.make-linter.rule-intake-runtime-boundary",
  "rule": "The intake gate is local and review-only; it does not contact Make.com, execute templates, or expose internal rule predicates to clients.",
  "required_posture": [
    "candidate review may cite local AST, catalog, raw-spec, Golden, knowledge-store, ADR, and fixture evidence",
    "official external facts must be verified before they affect severity or bibliography",
    "Golden and public templates can validate JSON shape and missing tool surfaces, but must not donate scenario business logic",
    "client-facing reports must use sanitized categories rather than internal rule IDs or predicates"
  ],
  "forbidden_posture": [
    "calling live Make services during candidate intake",
    "scraping the Make UI during candidate intake",
    "copying template scenario logic into canonical rules",
    "revealing internal linter corpus mechanics in client-facing artifacts"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Linter family TODOs cannot accept, reject, or implement imported candidates
without a one-by-one manual decision ledger.
- The default state of the imported corpus stays pending manual review.
- Later linter implementation can be aggressive only where local deterministic
evidence and tests justify that behavior.
- Quarantined candidates remain durable review evidence under the validation
data package until a later one-candidate unquarantine review changes their final state.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001079`.
- Decision ID: `repo.make-linter.rule-intake-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001079'
decision_id: 'repo.make-linter.rule-intake-policy'
title: 'Make Linter Rule Intake Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - testing
  - tooling
scope: 'repository/make-linter-rule-intake'
applies_to:
  - src/blueprints/validation/data/linter/corpus/linter-corpus-accounting.json
  - src/blueprints/validation/data/linter/corpus/linter-corpus-accounting.md
  - src/blueprints/validation/data/linter/decisions/linter-candidate-decisions.json
  - src/blueprints/validation/data/linter/corpus/linter-master-coverage-map.json
  - src/blueprints/validation/data/linter/quarantine/manifest.json
  - src/blueprints/validation/data/linter/quarantine/**/*.md
  - docs/todo/completed/c_0016-make-linter-security-ingress-http-rules.md
  - docs/todo/completed/c_0017-make-linter-reliability-state-concurrency-rules.md
  - docs/todo/completed/c_0018-make-linter-performance-memory-cost-rules.md
  - docs/todo/completed/c_0019-make-linter-types-schema-data-apps-rules.md
  - docs/todo/completed/c_0020-make-linter-topology-blueprint-architecture-rules.md
  - docs/todo/completed/c_0021-make-linter-observability-release-governance-rules.md
  - docs/todo/completed/c_0022-make-linter-documentation-surface-rules.md
  - docs/todo/completed/c_0023-make-linter-quarantine-and-future-families.md
  - docs/todo/completed/c_0024-make-linter-master-candidate-ledger.md
  - src/blueprints/validation/linter_rule_intake.py
  - src/blueprints/validation/linter_taxonomy.py
  - tests/blueprints/validation/make_linter_rule_intake_policy_contract.py
  - tests/blueprints/validation/make_linter_taxonomy_contract.py
  - tests/repository_policy/linter_corpus_accounting_contract.py
applies_when:
  - linter_candidate_rule_is_reviewed
  - linter_family_todo_accepts_or_rejects_candidate
  - linter_rule_code_is_promoted
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001032'
  - '001035'
  - '001046'
  - '001066'
derived_artifacts:
  - src/blueprints/validation/data/linter/corpus/linter-corpus-accounting.json
  - src/blueprints/validation/data/linter/corpus/linter-corpus-accounting.md
  - src/blueprints/validation/data/linter/decisions/linter-candidate-decisions.json
  - src/blueprints/validation/data/linter/corpus/linter-master-coverage-map.json
  - src/blueprints/validation/data/linter/quarantine/manifest.json
  - src/blueprints/validation/data/linter/quarantine/**/*.md
  - src/blueprints/validation/linter_rule_intake.py
  - src/blueprints/validation/linter_taxonomy.py
  - tests/blueprints/validation/make_linter_rule_intake_policy_contract.py
  - tests/blueprints/validation/make_linter_taxonomy_contract.py
  - tests/repository_policy/linter_corpus_accounting_contract.py
source_material:
  - path: 'docs/todo/completed/c_0014-make-linter-rule-intake-policy.md'
    usage: source evidence after completion archive
    copied_verbatim: false
bibliography_refs: []
traceability_anchors:
  - repo.make-linter.rule-intake-manual-gate
  - repo.make-linter.rule-intake-evidence-record
  - repo.make-linter.rule-intake-determinism-and-severity
  - repo.make-linter.rule-intake-non-loss-quarantine
  - repo.make-linter.rule-intake-unquarantine-lane
  - repo.make-linter.rule-intake-runtime-boundary
non_goals:
  - accept all imported linter candidates
  - implement a full linter-family rule set in this ADR
  - replace offline validation with live Make services
  - treat template scenarios as source logic
  - expose internal rule predicates to clients
```
</details>
