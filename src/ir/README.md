# Intermediate Representation

This directory owns the language-neutral Pancakes IR boundary.

The IR is the product-level semantic core for automation graphs. It models a
general directed acyclic graph of automation nodes, edges, source traces,
capabilities, and metadata without making Make.com the system model. This is the
general DAG representation for Pancakes. Make is the first implemented source
language adapter, so Make source evidence may be carried as `source_refs`, but
Make-specific raw specifications, source payload fields, API clients, and
rendering details stay under `src/languages/make/**`.

The current blueprint AST remains the compatibility runtime for existing Make
behavior. It should increasingly project stable semantics into this IR as tests
prove the translation boundary. Future source languages such as Zapier or n8n
must become peer adapters under `src/languages/**` and translate through this IR
instead of inheriting Make-shaped runtime assumptions.

Customer-facing language may claim Make support today and a general architecture
for additional automation languages. It must not claim Zapier, n8n, migration,
or cross-platform runtime support until adapters, fixtures, round-trip tests, and
validation diagnostics exist.
