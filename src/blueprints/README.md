# Blueprints

This bounded context owns the general Pancakes blueprint model: AST parsing,
validation, repair, optimization, rendering, and evidence derived from automation
blueprints.

`blueprints/ast` is the current compatibility runtime for automation blueprints.
It still exposes Make-named records where existing behavior depends on them, but
Make-specific source material, raw specs, and adapters belong under
`src/languages/make/**`.

`src/ir/**` is the product-level semantic contract for language-neutral
automation DAGs. Stable graph semantics should move toward IR instead of making
Make the general system model. Do not move source-language adapters or platform
payload details into `blueprints/ast`.

The boundary order is DDD first, CQRS only where read/write responsibilities
need separation, and Hexagonal adapter isolation only after stable domain ports
exist.
