# Validation

This bounded context validates parsed ASTs against the canonical catalog before
any renderer or generator may treat a blueprint as executable.

## File Boundary

This README owns the `validation` package behavior summary, render guard, and
finding taxonomy. It must not own AST parsing, catalog compilation, repair
mutation, or renderer output.

Validation is AST-adjacent. It may eventually move under the AST boundary, but
it stays isolated until that migration is explicit and validated.

Use `validate_blueprint` after parsing JSON with the AST boundary and loading
a validated catalog snapshot. Blocking findings use severity `error`; nonfatal
diagnostics use `warning`, `optimization`, or `explanation`.

Use `guard_blueprint_for_render` as the required pre-render boundary for future
generators, assemblers, or renderers. If validation has blocking errors, the
guard returns typed blockers and the caller must not emit blueprint JSON.

Use `validate_client_blueprint_intake` before any customer-supplied Make export
enters local validation, report generation, or PDF rendering. The intake
boundary accepts only `.blueprint.json` source received by the approved email or
offline handoff path, records a required manifest with hash, truncation,
redaction, processor, local-backend, and deletion fields, and fails closed on
hardcoded secrets. Personal identifiers require manual redaction review before
report release. The operator workstation is a local-only analysis backend, not
a public website backend, tunnel target, webhook receiver, or browser-accessible
linter.

Expression and mapping intelligence is deliberately conservative. It detects
common delimiter, function, argument, iterator, aggregator, and pagination risks
from promoted runtime rules only, then emits repair suggestions without
modifying the blueprint.

Output-contract validation rejects downstream Make expressions that reference
fields absent from a source node's declared `interface`, `outputs`, or
`output_schema`. Missing output contracts stay non-blocking because they do not
provide enough deterministic evidence.

Every finding carries a client-safe message and a separate internal diagnostic.
Client messages must not include repository paths, local machine paths, or
implementation details.

## Make Note Surfaces

`note_surfaces.py` owns the non-gating reference model for future note-related
linter rules. It separates connection-line/filter/route notes from module-click
or module-detail notes without making every imported guide example mandatory.

Connection-line, filter, and route notes explain why a bundle passes, drops, or
moves through a branch. Future deterministic rules may inspect route/filter
paths or explicit filter-note metadata for tags such as `Rule`, `Why`,
`Drop Safety`, `Fallback`, `Edge Case`, or `Action`.

Module-click and module-detail notes explain module responsibility, contracts,
side effects, and failure behavior. Future deterministic rules may inspect
module `metadata.notes` paths for tags such as `Why`, `Input Contract`,
`Output Contract`, `Impact`, `Failure Mode`, or `Remediation`.

Ambiguous root notes remain `unknown_note_surface` until local AST path evidence
or explicit note metadata proves the surface. Notes must not require secrets,
full payloads, or customer-confidential data.

## Make Linter Taxonomy

`linter_taxonomy.py` owns the non-gating rule-family taxonomy for local Make
linter work. It is a review and discovery surface, not a validator entry point.
Each family declares an owner path, Make-domain invariant, exact supported
codes, evidence source, focused test path, and severity posture.

`linter_rule_intake.py` owns the mandatory manual intake contract for candidate
rules. A candidate does not become accepted linter behavior until a review row
records one closed decision, the original candidate ID, the canonical rule code
or alias, deterministic local evidence, severity posture, profile gates when
needed, implementation owner, failing and passing fixture plans, ADR impact,
bibliography impact, false-positive risk, and any rejection or quarantine
reason.

Generated, imported, or model-expanded candidates are not trusted by origin.
Every candidate ID must be inspected one by one. Duplicate candidates are
preserved as aliases of a canonical rule; unsafe or subjective candidates remain
quarantined or rejected with an English reason instead of being deleted.

Unknown codes must be promoted into the taxonomy before they are treated as
valid rule output. Prefix-shaped names are not enough: a new HTTP, mapping, or
error-handling rule needs an exact code, a deterministic evidence source, and a
focused test before runtime behavior can emit it.

Current posture:

| Family                                    | Owner                                                  | Severity posture                                         |
| ----------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------- |
| AST import-shape safety                   | `src/blueprints/validation/importability.py`           | Blocking errors possible                                 |
| Catalog resolution and required fields    | `src/blueprints/validation/validator.py`               | Blocking errors possible                                 |
| Route and branch topology                 | `src/blueprints/validation/route_validation.py`        | Blocking errors possible                                 |
| Mapping and reference contracts           | `src/blueprints/validation/expression_intelligence.py` | Blocking errors possible                                 |
| Error-handling reliability                | `src/blueprints/validation/validator.py`               | Missing-handler candidates stay advisory unless promoted |
| Runtime semantic contracts                | `src/blueprints/validation/validator.py`               | Blocking errors possible                                 |
| AI-agent and tool contracts               | `src/blueprints/validation/ai_agent_contracts.py`      | Advisory only                                            |
| Webhook and HTTP safety                   | `src/blueprints/validation/validator.py`               | Advisory only                                            |
| Transaction and state-mutation safety     | `src/blueprints/validation/validator.py`               | Advisory only                                            |
| Operation volume and optimization advice  | `src/blueprints/optimization/advisory.py`              | Advisory only                                            |
| Reviewed designer-message evidence        | `src/catalog/knowledge/linter_probe.py`                | Warning-only secondary signal                            |
| Setup readiness blockers                  | `src/blueprints/validation/setup_readiness.py`         | Blocking errors possible                                 |
| Designer layout and handoff notes         | `src/blueprints/ast/layout_analysis.py`                | Advisory only                                            |
| Generation and render gate blockers       | `src/blueprints/validation/generation_gate.py`         | Blocking errors possible                                 |
| First-principles candidate rule discovery | `src/blueprints/validation/linter_taxonomy.py`         | Candidate-only, non-gating                               |
