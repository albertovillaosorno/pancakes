# AST

This bounded context owns the Pancakes AST for automation blueprint logic. It is
the current runtime model for scenario structure, module references, routes,
filters, source traces, and raw-spec bindings.

The public record names still expose `MakeAst*` compatibility aliases where
current Make-compatible behavior depends on them. Product-facing code should
prefer the `PancakesAst*` aliases and treat Make as a language adapter, not the
system model. Product-level graph semantics belong in `src/ir/**`;
Make-specific source material, translation, and rendering details belong in
`src/languages/make/**`.

Unknown fields are preserved in `unknown_fields` and the original `raw_payload`.
Unsupported module tokens become `unresolved` nodes instead of being dropped.

## File Boundary

This README owns the `blueprints.ast` package behavior summary, public helpers,
and allowed output roots. It must not make catalog, validation, or repair rules
canonical; those remain in their owning contexts until ADR-backed migration.

Use `assemble_blueprint_from_catalog` only when every requested node is backed
by a canonical catalog module ID and caller-supplied mappings. The assembler
does not invent modules or placeholder field values.

Traversal is deterministic preorder through `flow`, route and branch flows,
tool flows, and direct error-handler children.

Catalog, validation, and repair are AST-adjacent contexts. They may be folded
into the AST boundary later only through an explicit ADR-backed migration.

Use `src/languages/make/**` adapter functions when translating Make JSON into
Pancakes AST or IR, or when rendering a Pancakes AST back to Make blueprint
JSON. Use `languages.make.blueprint_export.render_make_blueprint_payload` for
Make-native output. The `blueprints.ast.renderer` and
`blueprints.ast.render_validation` modules are compatibility import paths only;
they must not own Make-specific output shape. `importable` mode requires the
blueprint validation gate to pass before JSON is emitted. `draft` mode preserves
unresolved work for review, but the result is not safe to import into Make.

Use `blueprints.ast.operation_estimator.estimate_blueprint_operations`
for conservative static operation planning. Estimates are labeled as static
planning evidence unless later backed by live Make run history.

Use `blueprints.ast.ast_evidence_report` for deterministic in-memory evidence
paths such as opaque fields and designer message locations. It does not write
generated artifact bundles.

Use `blueprints.ast.persist_make_blueprint_bundle` when a durable blueprint
bundle is needed. Bundles live under `data/blueprints/`; the root `artifacts/`
and `.artifacts/` folders are not valid repository output roots.

Use `blueprints.ast.collect_reference_targets`,
`blueprints.ast.collect_reference_usages`, and
`blueprints.ast.rewrite_cross_node_references` for Make-owned node references.
These helpers do not rewrite arbitrary business IDs.
