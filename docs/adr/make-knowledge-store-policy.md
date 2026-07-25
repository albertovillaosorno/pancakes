# Make Knowledge Store Policy

## Status

Accepted

## Scope

repository/make-knowledge

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.make-knowledge.structural-ssot

```json strict-policy
{
  "anchor": "repo.make-knowledge.structural-ssot",
  "rule": "The Pancakes SQLite database is the local runtime and durable SSOT for consumed Make structural knowledge; tracked SQL snapshots are deterministic restore evidence.",
  "database_path": "src/data/pancakes.sqlite",
  "git_posture": "ignored generated binary",
  "tracked_authority_inputs": [
    "docs/adr/*.md",
    "src/data/sql_snapshots/*.sql",
    "deterministic tests",
    "typed source code"
  ],
  "ingest_inputs": [
    "src/data/pancakes.sqlite:make_raw_spec_payloads",
    "src/data/pancakes.sqlite:make_raw_spec_manifest_records",
    "src/languages/make/data/courses/raw/*.md",
    "src/languages/make/data/designer-messages/raw/manifest.json",
    "src/languages/make/data/designer-messages/raw/*.json"
  ],
  "runtime_consumers": [
    "AST validation",
    "catalog query",
    "linter quarantine and rule-surface audit",
    "optimization advice",
    "Windows service status"
  ]
}
```
## repo.make-knowledge.tracked-sql-snapshots

```json strict-policy
{
  "anchor": "repo.make-knowledge.tracked-sql-snapshots",
  "rule": "SQLite is the durable Make knowledge SSOT; small plain-text SQL snapshots are reviewable Git restore evidence.",
  "snapshot_root": "src/data/sql_snapshots/",
  "required_files": [
    "schema.sql",
    "native_module_expectations.sql",
    "aliases.sql",
    "course_rules.sql",
    "designer_message_evidence.sql",
    "live_probe_evidence.sql",
    "transaction_profiles.sql"
  ],
  "service_regenerable_dump": "src/data/sql_snapshots/make.sql",
  "forbidden_posture": [
    "tracking src/data/pancakes.sqlite",
    "treating a large generated Make SQL dump as source-tree authority",
    "committing raw-spec payload JSON as source authority"
  ]
}
```
## repo.make-knowledge.catalog-plan-ingestion

```json strict-policy
{
  "anchor": "repo.make-knowledge.catalog-plan-ingestion",
  "rule": "Catalog-plan semantic-worker progress is persisted directly into the SQLite SSOT.",
  "runtime_tables": [
    "catalog_plan_ranges",
    "catalog_plan_units",
    "catalog_plan_progress_events",
    "catalog_plan_semantic_answers",
    "catalog_plan_quarantine_records"
  ],
  "required_posture": [
    "catalog.next_unit reads one pending SQLite unit",
    "catalog.save_unit writes one answer or structured quarantine record",
    "generated SQLite remains ignored while SQL snapshots stay tracked",
    "tracked SQL snapshots remain the reviewable runtime input",
    "direct manual SQLite edits remain forbidden"
  ],
  "forbidden_posture": [
    "reintroducing src/catalog/plan_artifact as a ledger",
    "storing semantic answers in JSON sidecars",
    "storing secrets or raw customer payloads in catalog evidence",
    "using chat-only decisions as knowledge-store facts"
  ]
}
```
## repo.make-knowledge.raw-spec-normalization

```json strict-policy
{
  "anchor": "repo.make-knowledge.raw-spec-normalization",
  "rule": "Raw specs are normalized into apps, app versions, modules, fields, constraints, ingest runs, and native coverage rows before runtime use.",
  "normalization_tables": [
    "apps",
    "app_versions",
    "modules",
    "fields",
    "constraints",
    "ingest_runs"
  ],
  "required_posture": [
    "raw-spec hashes are verified before ingestion",
    "advanced field setting metadata is preserved as an explicit constraint and restored into catalog projections",
    "malformed noncritical field metadata is skipped instead of crashing normalization",
    "zero-module native app versions are preserved as coverage gaps",
    "native module expectations are explicit tracked rows"
  ]
}
```
## repo.make-knowledge.temporal-facts

```json strict-policy
{
  "anchor": "repo.make-knowledge.temporal-facts",
  "rule": "Durable Make knowledge facts are temporal and carry valid_from plus nullable valid_to.",
  "required_columns": [
    "valid_from",
    "valid_to",
    "source_kind",
    "source_ref",
    "fingerprint",
    "adr_anchor"
  ],
  "history_rule": "When a current fact changes, the old row is closed with valid_to and a new current row is inserted.",
  "version_support": "Old Make app/module behavior remains queryable through historical rows."
}
```
## repo.make-knowledge.linter-audit-ssot

```json strict-policy
{
  "anchor": "repo.make-knowledge.linter-audit-ssot",
  "rule": "Persistent Make linter backlog, quarantine, review, and coverage-audit state belongs in SQLite.",
  "tables": [
    "linter_quarantine_records",
    "linter_quarantine_review_events",
    "linter_rule_surface_matrix",
    "linter_data_source_inventory"
  ],
  "required_posture": [
    "store linter quarantine candidates and review events in SQLite",
    "store rule-family code versus SQLite coverage in SQLite",
    "store tracked linter data-source inventory in SQLite",
    "use tracked JSON and Markdown linter files only as deterministic fixtures, migration input, legacy review evidence, or SQLite-derived snapshots"
  ],
  "forbidden_posture": [
    "using generated JSON as an external linter ledger",
    "leaving consumed persistent linter state scattered across repository files",
    "treating SQLite-only rules as covered by code fixture tests alone",
    "tracking the generated pancakes.sqlite database"
  ]
}
```
## repo.make-knowledge.course-promoted-rules

```json strict-policy
{
  "anchor": "repo.make-knowledge.course-promoted-rules",
  "rule": "Course material affects runtime only through claim-level promotion into ADR-backed SQL, code, and tests.",
  "coverage_ledger": "src/languages/make/data/courses/coverage.json",
  "course_claim_table": "course_claims",
  "runtime_forbidden": [
    "runtime reads src/languages/make/data/courses/raw directly",
    "runtime reads candidate_artifacts_manifest.json",
    "course-only claims alter behavior without ADR, code, and tests"
  ]
}
```
## repo.make-knowledge.claim-conflict-arbitration

```json strict-policy
{
  "anchor": "repo.make-knowledge.claim-conflict-arbitration",
  "rule": "Conflicting course or raw-spec claim evidence must be represented explicitly and arbitrated deterministically before runtime consumers rely on the claim value.",
  "evidence_table": "claim_evidence",
  "materialized_conflict_table": "claim_conflicts",
  "required_evidence_fields": [
    "claim_key",
    "value_json",
    "source_confidence",
    "evidence_observed_at",
    "source_kind",
    "source_ref",
    "valid_from",
    "valid_to",
    "fingerprint",
    "adr_anchor"
  ],
  "arbitration_order": [
    "higher source_confidence wins",
    "newer evidence_observed_at wins",
    "stable evidence_id tie-breaker wins but resolution_status is needs_review"
  ],
  "status_values": ["resolved", "needs_review"],
  "required_posture": [
    "course and raw-spec evidence can participate in the same conflict group",
    "operator-reviewed live_probe evidence can participate only through tracked SQL snapshots",
    "arbitration rows preserve winning and losing source references",
    "changed conflict outcomes close old rows with valid_to before inserting the new current row"
  ],
  "forbidden_posture": [
    "silently choosing the newest course claim without recording the losing evidence",
    "letting equal-confidence equal-recency conflicts look fully resolved",
    "using raw course markdown or raw-spec payload JSON directly at runtime to settle conflicts"
  ]
}
```
## repo.make-knowledge.live-probe-evidence

```json strict-policy
{
  "anchor": "repo.make-knowledge.live-probe-evidence",
  "rule": "Live Make roundtrip probes may settle needs_review claim conflicts only by producing reviewed live_probe evidence for the next deterministic offline SQLite build.",
  "source_kind": "live_probe",
  "source_confidence": 900,
  "tracked_evidence_snapshot": "src/data/sql_snapshots/live_probe_evidence.sql",
  "required_authorization": [
    "operator_approved true",
    "approved_by non-empty",
    "credential_ref non-secret reference only",
    "purpose resolve_claim_conflict"
  ],
  "required_probe_report": [
    "conflict_id",
    "claim_key",
    "generated_probe_scenario",
    "returned_scenario_diff",
    "removed_fields",
    "changed_values",
    "make_side_errors",
    "reviewed_value_json"
  ],
  "build_boundary": [
    "src/catalog/knowledge/storage.py never contacts Make services",
    "knowledge ensure consumes reviewed live_probe SQL like any other tracked snapshot",
    "live probes must not mutate the generated SQLite database directly"
  ],
  "forbidden_posture": [
    "using live_probe evidence without a reviewed tracked SQL row",
    "storing raw API tokens in evidence snapshots or reports",
    "letting equal-confidence conflicts auto-run live validation during knowledge ensure",
    "treating unreviewed probe output as runtime truth"
  ]
}
```
## repo.make-knowledge.designer-message-evidence

```json strict-policy
{
  "anchor": "repo.make-knowledge.designer-message-evidence",
  "rule": "Reviewed Make designer-message linter findings are promoted as temporal knowledge facts without making raw live payloads runtime authority.",
  "table": "designer_message_evidence",
  "tracked_evidence_snapshot": "src/data/sql_snapshots/designer_message_evidence.sql",
  "source_kind": "designer_message",
  "required_columns": [
    "finding_id",
    "node_id",
    "module_slug",
    "severity",
    "message",
    "category",
    "field_path",
    "review_status",
    "source_kind",
    "source_ref",
    "valid_from",
    "valid_to",
    "fingerprint",
    "adr_anchor"
  ],
  "required_posture": [
    "only reviewed normalized warning rows are queryable by validators and MCP feedback",
    "designer-message rows are warnings while drafting",
    "raw payloads remain ignored temporary ingest files",
    "conflicts with local validation are visible as separate diagnostics instead of silent replacement"
  ]
}
```
## repo.make-knowledge.promoted-aliases

```json strict-policy
{
  "anchor": "repo.make-knowledge.promoted-aliases",
  "rule": "Human course terminology and known Make names are normalized through tracked aliases.",
  "examples": {
    "trigger": "trigger_imt",
    "scenario trigger": "trigger_imt",
    "webhook response": "webhooks.respond"
  },
  "table": "module_aliases"
}
```
## repo.make-knowledge.optimizer-hints

```json strict-policy
{
  "anchor": "repo.make-knowledge.optimizer-hints",
  "rule": "Optimization advice is non-mutating and may only emit deterministic advisory records from promoted hints.",
  "active_hint_domains": ["operation volume", "pagination", "webhook queue review"],
  "forbidden_posture": [
    "rewriting ASTs from advice",
    "calling live Make services to infer optimization",
    "reading raw course markdown at runtime"
  ]
}
```
## repo.make-knowledge.transaction-safety-profiles

```json strict-policy
{
  "anchor": "repo.make-knowledge.transaction-safety-profiles",
  "rule": "Rollback and ACID safety must be modeled as explicit temporal knowledge facts rather than inferred ad hoc by validators.",
  "table": "module_transaction_profiles",
  "required_columns": [
    "profile_id",
    "module_selector_kind",
    "module_selector",
    "operation_kind",
    "mutates_state",
    "rollback_capability",
    "acid_compatibility",
    "safety_level",
    "source_kind",
    "source_ref",
    "valid_from",
    "valid_to",
    "fingerprint",
    "adr_anchor"
  ],
  "selector_kinds": ["module_id", "app_slug", "module_kind", "module_token_contains"],
  "required_posture": [
    "treat rollback support as an evidence-backed profile, not a validator guess",
    "preserve current and historical transaction profile facts with valid_from and valid_to",
    "mark irreversible or externally committed operations as requiring recovery, idempotency, audit, or compensation posture"
  ],
  "forbidden_posture": [
    "claiming full ACID compatibility for external API writes without source evidence",
    "collapsing rollback-unsafe modules into the generic mutating-module category only",
    "using live Make execution to infer transaction safety during validation"
  ]
}
```
## repo.make-knowledge.native-module-expectations

```json strict-policy
{
  "anchor": "repo.make-knowledge.native-module-expectations",
  "rule": "Make-owned native/platform slugs have explicit tracked coverage expectations.",
  "seeded_slugs": [
    "ai-agent",
    "ai-local-agent",
    "ai-provider",
    "ai-tools",
    "app-runtime",
    "builtin",
    "csv",
    "datastore",
    "http",
    "json",
    "util",
    "xml"
  ],
  "status_rule": "A native slug with fewer modules or missing expected kinds is reported as a native module gap."
}
```
## repo.make-knowledge.runtime-source-label

```json strict-policy
{
  "anchor": "repo.make-knowledge.runtime-source-label",
  "rule": "Runtime consumers that return normalized module facts from the generated SQLite knowledge store label that evidence as knowledge_db and rank it above raw-spec, fixture, and alias evidence.",
  "source_label": "knowledge_db",
  "source_rank": 0,
  "required_consumers": [
    "catalog.plan when the generated knowledge store contains structural module facts",
    "scenario.modules.search",
    "scenario.modules.list",
    "scenario.modules.expand",
    "AST module resolution for knowledge-store projected catalog snapshots"
  ],
  "required_posture": [
    "knowledge_db labels indicate normalized local SQLite projections built from tracked SQL snapshots and current raw-spec ingest data",
    "knowledge_db labels do not make the ignored SQLite binary a committed repository artifact",
    "promoted aliases from the knowledge store may carry knowledge_db labels, but hardcoded fallback aliases must carry fallback_alias labels"
  ],
  "forbidden_posture": [
    "returning knowledge-store module facts without source_label and source_rank",
    "allowing fallback aliases to masquerade as knowledge_db evidence",
    "using untracked SQLite-only facts as committed repository truth"
  ]
}
```
## repo.make-knowledge.build-command

```json strict-policy
{
  "anchor": "repo.make-knowledge.build-command",
  "rule": "The ensure command rebuilds the ignored SQLite database from tracked SQL and current raw-spec ingest data when the generated artifact is absent or stale.",
  "command": "python -B -m catalog.knowledge --repo-root <repo> ensure",
  "bootstrap_requirement": "scripts/bootstrap-dependencies.ps1 may run ensure after Python dependencies are available."
}
```
## repo.make-knowledge.generated-freshness

```json strict-policy
{
  "anchor": "repo.make-knowledge.generated-freshness",
  "rule": "Runtime consumers must reject generated SQLite when its stored raw-spec manifest hash differs from the current raw-spec manifest.",
  "authority_order": [
    "current raw-spec manifest and payload files",
    "tracked SQL snapshots",
    "generated SQLite runtime projection"
  ],
  "rebuild_command": "python -B -m catalog.knowledge --repo-root <repo> ensure",
  "service_rule": "A Windows service or scheduled task may call ensure after raw-spec refresh; it must not mutate SQLite directly.",
  "forbidden_posture": [
    "using stale generated SQLite to choose current module versions",
    "treating SQLite rows as durable authority when raw specs changed",
    "repairing version drift by editing generated SQLite directly"
  ]
}
```
## repo.make-knowledge.snapshot-dump-command

```json strict-policy
{
  "anchor": "repo.make-knowledge.snapshot-dump-command",
  "rule": "The dump command writes a deterministic service-regenerable SQL cache file for backup review.",
  "command": "python -B -m catalog.knowledge --repo-root <repo> dump",
  "dump_output": "src/data/sql_snapshots/make.sql",
  "review_requirement": "Large generated Make SQL dumps are not committed; promote durable changes into SQLite and small tracked restore snapshots."
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Raw specs and courses remain ingestion/evidence inputs rather than runtime
authority.
- Validators and optimization advice can consume a compact SQLite projection
while Git reviews plain-text SQL, ADRs, source code, and tests.
- Historical Make capability changes can be represented with valid_from and
valid_to rows without committing binary database files.
- Conflicting evidence is visible as queryable arbitration rows instead of
being collapsed into a single untraceable claim.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001064`.
- Decision ID: `repo.make-knowledge.store-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001064'
decision_id: 'repo.make-knowledge.store-policy'
title: 'Make Knowledge Store Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - data
  - runtime
  - testing
scope: 'repository/make-knowledge'
applies_to:
  - src/data/sql_snapshots/**/*
  - src/data/pancakes.sqlite
  - src/languages/make/data/courses/coverage.json
  - src/catalog/knowledge/**/*
  - src/blueprints/optimization/**/*
  - src/blueprints/validation/**/*
  - scripts/bootstrap-dependencies.ps1
  - tests/catalog/knowledge_store_contract.py
  - tests/catalog/catalog_source_ranking_contract.py
  - tests/catalog/test_raw_spec_field_retention.py
applies_when:
  - make_structural_knowledge_is_materialized
  - raw_specs_are_ingested
  - course_claims_are_promoted
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001041'
  - '001042'
  - '001046'
  - '001052'
  - '001056'
  - '001062'
derived_artifacts:
  - src/data/sql_snapshots/**/*
  - src/languages/make/data/courses/coverage.json
  - src/catalog/knowledge/**/*
  - src/blueprints/optimization/**/*
  - src/blueprints/validation/**/*
  - scripts/bootstrap-dependencies.ps1
  - tests/catalog/knowledge_store_contract.py
  - tests/catalog/catalog_source_ranking_contract.py
  - tests/catalog/test_raw_spec_field_retention.py
source_material:
  - path: 'src/languages/make/data/courses/raw/**/*'
    usage: evidence reference
    copied_verbatim: false
bibliography_refs:
  - 'https://developers.make.com/'
  - 'https://academy.make.com/'
traceability_anchors:
  - repo.make-knowledge.structural-ssot
  - repo.make-knowledge.tracked-sql-snapshots
  - repo.make-knowledge.catalog-plan-artifact-ingestion
  - repo.make-knowledge.raw-spec-normalization
  - repo.make-knowledge.temporal-facts
  - repo.make-knowledge.course-promoted-rules
  - repo.make-knowledge.claim-conflict-arbitration
  - repo.make-knowledge.live-probe-evidence
  - repo.make-knowledge.designer-message-evidence
  - repo.make-knowledge.promoted-aliases
  - repo.make-knowledge.optimizer-hints
  - repo.make-knowledge.transaction-safety-profiles
  - repo.make-knowledge.native-module-expectations
  - repo.make-knowledge.runtime-source-label
  - repo.make-knowledge.build-command
  - repo.make-knowledge.generated-freshness
  - repo.make-knowledge.snapshot-dump-command
non_goals:
  - commit generated SQLite binaries
  - make raw specs or course markdown runtime authority
  - contact live Make services from database query paths
  - rewrite blueprints as part of optimization advice
```
</details>
