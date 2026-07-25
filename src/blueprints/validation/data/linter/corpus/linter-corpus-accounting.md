# Make Linter Corpus Accounting

## File Boundary

This ledger owns intake accounting for the imported Make linter corpus. It is a
checksum and source-traceability aid for queued linter work, not an accepted rule
registry and not a validation runtime.

Canonical machine-readable ledger:
`src/blueprints/validation/data/linter/corpus/linter-corpus-accounting.json`.

Canonical master coverage map:
`src/blueprints/validation/data/linter/corpus/linter-master-coverage-map.json`.

The JSON ledger stores every parsed candidate ID for each imported source file.
The table below is a compact count summary only.

## Current Posture

TODO 0016 closed ADR 001079 decision rows for the 176 security, ingress, HTTP,
external API, network, resilience, and GraphQL candidate headings in
`02_security_ingress_http.md`. TODO 0017 closed manual
review for the 182 reliability, state, and concurrency candidate headings in
`03_reliability_state_concurrency.md`. TODO 0018 closed manual review for the 73
performance, memory, and cost candidate headings in `04_performance_memory_cost.md`.
TODO 0019 closed manual review for the 226 type, schema, data, and app candidate
headings in `05_types_schema_data_apps.md`. TODO 0020 closed manual review for
the 121 topology, blueprint, and architecture candidate headings in
`06_topology_blueprint_architecture.md`. TODO 0021 closed manual review for the
121 observability, release, and governance candidate headings in
`07_observability_release_governance.md`. TODO 0022 closed manual review for the
133 documentation-surface candidate headings in
`08_documentation_surface_linter_rules.md`. TODO 0023 closed manual review for
the 14 quarantine and future-family candidate headings in
`09_quarantine_and_future_families.md`.

The reviewed rows live in `src/blueprints/validation/data/linter/decisions/linter-candidate-decisions.json` and
cumulatively record 14 rewritten, 262 downgraded, 678 quarantined, 4 rejected,
and 88 aliased candidates. No candidate headings remain pending manual review.
TODO 0024 also records all 1046 master candidate IDs in
`src/blueprints/validation/data/linter/corpus/linter-master-coverage-map.json`, mapping each master ID to the
canonical split-family decision row without creating duplicate runtime
diagnostics. TODO 0013 did not accept, rewrite, downgrade, quarantine, reject,
alias, or implement any rule.

Every future accepted or rewritten linter rule must still record:

- source file and candidate ID;
- manual decision;
- deterministic predicate;
- evidence surface;
- severity and profile gates;
- implementation owner;
- failing and passing fixtures;
- ADR impact;
- bibliography impact when external facts are used.

## Accounting Summary

| Source file                                | Imported count | Parsed unique IDs | Owner                                                                              |
| ------------------------------------------ | -------------: | ----------------: | ---------------------------------------------------------------------------------- |
| `01_policy_and_intake.md`                  |              0 |                 0 | `docs/adr/make-linter-rule-intake-policy.md`                                       |
| `02_security_ingress_http.md`              |            176 |               176 | `docs/todo/completed/c_0016-make-linter-security-ingress-http-rules.md`            |
| `03_reliability_state_concurrency.md`      |            182 |               182 | `docs/todo/completed/c_0017-make-linter-reliability-state-concurrency-rules.md`    |
| `04_performance_memory_cost.md`            |             73 |                73 | `docs/todo/completed/c_0018-make-linter-performance-memory-cost-rules.md`          |
| `05_types_schema_data_apps.md`             |            226 |               226 | `docs/todo/completed/c_0019-make-linter-types-schema-data-apps-rules.md`           |
| `06_topology_blueprint_architecture.md`    |            121 |               121 | `docs/todo/completed/c_0020-make-linter-topology-blueprint-architecture-rules.md`  |
| `07_observability_release_governance.md`   |            121 |               121 | `docs/todo/completed/c_0021-make-linter-observability-release-governance-rules.md` |
| `08_documentation_surface_linter_rules.md` |            133 |               133 | `docs/todo/completed/c_0022-make-linter-documentation-surface-rules.md`            |
| `09_quarantine_and_future_families.md`     |             14 |                14 | `docs/todo/completed/c_0023-make-linter-quarantine-and-future-families.md`         |
| `11_notes_use_case_separation.md`          |              0 |                 0 | completed by TODO 0011 note-surface reference model                                |
| `make_linter_MASTER_complete.md`           |           1046 |              1046 | `docs/todo/completed/c_0024-make-linter-master-candidate-ledger.md`                |

The split linter document total is 1046, matching the master non-loss reference.
No duplicate candidate IDs were detected inside any parsed source file.
