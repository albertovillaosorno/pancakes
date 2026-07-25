# Language AST IR Boundary Policy

Status: accepted

## Decision

Pancakes separates source automation platform languages, the internal blueprint AST compatibility
runtime, and the language-neutral intermediate representation.

`src/languages/**` owns original automation platform languages. `src/languages/make/**` owns
Make.com source data, Make raw specifications, Make JSON interpretation, and Make-specific
translation behavior. Future source languages such as Zapier or n8n must become peers under
`src/languages/**`, not subdirectories of Make and not generic blueprint code.

`src/blueprints/ast/**` owns the current blueprint AST compatibility runtime. It may keep `MakeAst*`
public names where existing Make behavior depends on them, but those names are compatibility debt
rather than a claim that Make is the product model.

`src/ir/**` owns the product-level semantic contract for a language-neutral automation DAG. It
carries stable graph nodes, edges, source traces, capability references, and metadata without making
Make the system model. Source-specific fields, raw specs, API clients, and rendering behavior stay
in language adapters.

This is the current sellable seam: Pancakes is an IR-centered automation analysis core with Make as
the first implemented source-language adapter. It must not claim completed Zapier, n8n, migration,
or cross-platform runtime support until another source-language adapter, fixture set, translation
contract, and validation suite exist.

Python is not a source automation language for Pancakes. Python is the implementation language and
may later be a translation target through a separate accepted boundary.

## Rationale

Making Make the general system model would lock the product to one provider. Keeping the current AST
Make-compatible preserves working behavior, while promoting stable graph semantics into IR creates
the right product boundary for future adapters.

The implementation order is:

1. Keep Make-specific source evidence in `src/languages/make/**`.
2. Keep current Make-compatible runtime behavior working through
`src/blueprints/ast/**`.
3. Promote stable graph semantics into `src/ir/**` when they are not
platform-specific.
4. Add future source-language adapters as peers under `src/languages/**`.
5. Validate translation round trips before claiming new platform support.

## Consequences

- Make JSON translation belongs to `src/languages/make/**`.
- Generic IR graph semantics belong to `src/ir/**`.
- AST traversal, validation, repair, and optimization belong to
`src/blueprints/**` until they are deliberately promoted or split.
- MCP tools may consume AST and language adapters but must not become the source
of truth for either.
- No Zapier, n8n, or second source-language implementation is approved by this policy.
- No source-language adapter may use Make-specific fields as generic IR truth.
