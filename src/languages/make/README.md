# Make Language

This directory owns the Make.com language adapter boundary.

It contains Make-owned source data, raw specifications, source-specific token
helpers, live/raw-spec adapters, and Make JSON interpretation. Make-specific
fields remain here when they do not represent stable cross-platform automation
semantics.

Current Pancakes behavior is intentionally Make-compatible because Make is the
only executable source language adapter today. The Make layer may translate Make
JSON into the language-neutral IR and the current blueprint compatibility AST,
and it may render Make-compatible JSON from validated product models. It must
not treat Make as the product core. Generic IR graph semantics, AST traversal,
validation, repair, optimization, and MCP behavior belong under `src/ir/**`,
`src/blueprints/**`, and `src/mcp/**`.

Make-native import/export shape belongs here, not in the generic AST boundary.
`blueprint_export.py` owns Make module token translation, Make module version
injection, native parameter projection, Make designer metadata, and zero-trace
filtering for importable `.blueprint.json` payloads. `parameter_aliases.py`
owns Make-specific field aliases such as legacy connection keys mapping to
`__IMTCONN__`; generic product code must not duplicate those provider names.
`data/native_semantics_matrix.json` is the private internal matrix for supported
Make-native module contracts. It records mapper, parameter, metadata, runtime
placeholder, volatile-field, fixture, confidence, and evidence posture for the
adapter. It also records family-level coverage rows for core Make patterns such
as routers, aggregators, error handlers, dynamic selectors, provider connectors,
and AI modules. It is engine input, not customer-facing copy.
`data/non_raw_evidence_inventory.json` is the private index for Make evidence
that does not live in raw specs. It inventories built-in and app projector
manifests, Golden blueprint shape evidence, Make Academy course material, SQL
snapshots, generated SQLite knowledge, and template manifests. Raw specs remain
the catalog source of truth, and SQLite remains a generated artifact; this index
only explains what each non-raw surface may prove, which tests guard it, and
which Make-native gaps remain evidence candidates.
`data/expression_palette.json` and `expression_palette.py` own private
browser-observed expression palette facts. Parsers, linters, planners, and docs
may use those facts to recognize known Make functions, variables, operators,
keywords, and system-variable display labels offline. Palette evidence does not
prove function arity, hidden variable identifiers, evaluator semantics, or full
expression parity; those require separate browser/API roundtrip evidence.
`data/priority_module_families.json` and `priority_modules.py` own the private
priority connector registry for high-value non-built-in Make apps. Catalog
search may use those aliases to recover public names that differ from raw-spec
slugs, but dynamic RPC selector and account-scoped behavior still require
separate read-only Browser evidence before deterministic promotion.
`data/public_research_evidence.json` and `public_research.py` own the compact
public/sanitized source ledger for Make catalog research. It records official
source IDs, local evidence surfaces, promotion gates, and live Browser follow-up
needs without storing public documentation bodies, authenticated Make state, or
customer payloads.
`data/roundtrip_reexport_parity_corpus.json` and `roundtrip_parity.py` own the
private local generated-vs-reexport parity corpus. The corpus maps every stable
roundtrip delta class to synthetic fixture triplets, deterministic tests, and
generalized rule targets. It does not claim live Make.com parity; live import
and export checks remain a separate Browser maintenance gate before runtime
claims are promoted.
`modules/**/*.manifest.json` and `builtins/*.manifest.json` are the executable
Make projector contracts for supported modules. The Make exporter uses these
manifests to choose native versions, projector kinds, connection families,
metadata policies, and placeholder posture; core AST code must stay unaware of
these Make UI and import-shape details.
`parity_gates.py` owns the declared-scope Make-native completion vocabulary:
`not_supported`, `pass_through`, `import_safe`, `native_shape`, and
`roundtrip_stable`. A scope item may be called perfect only within declared
scope after every required evidence gate is satisfied; this must never imply
complete Make.com platform coverage.
`parity_doctrine.py` owns the first-principles Make-native parity doctrine:
Pancakes targets Make graph semantics, runtime bindings, native module shapes,
router/filter semantics, editor state, import/re-export behavior, risk model,
and report abstraction through reusable patterns, manifests, projectors, matrix
records, diff rules, fixture families, and deterministic tests. Browser/API
observations become redacted local fixtures and generalized rules before they
support product claims.
`parity_confidence.py` owns the internal evidence-breadth scale for Make-native
rules. Low-confidence or single-fixture observations stay advisory/parity-gap
signals unless a safety or lineage hard gate applies; client output receives a
compact confidence posture, not the private scoring recipe.
Pancakes-private DSL metadata such as raw spec bindings, runtime placeholder
registries, rollback posture, idempotency evidence, SRE notes, and scenario
tests must never appear in Make-native importable output. An importable Make
export must fail closed if those keys leak at any depth.

The source scenario draft remains a Pancakes artifact. The Make blueprint export
is a provider adapter artifact. Future Zapier, n8n, or other automation platform
support must add peer adapters under `src/languages/**` instead of expanding
Make-specific behavior into product core.

Do not add Zapier or another platform here. Future source languages must be peer
directories under `src/languages/**`.
