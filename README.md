# Pancakes

Pancakes is a static-analysis engine for automation blueprints. It parses them
into a language-neutral IR, validates that IR against a rule set covering
security and delivery correctness, and renders client-safe output.
Make.com is the first implemented source language, not the system model.

> **Archived.** This repository is published as a record of how the engine was
> built. It is not maintained and accepts no issues or pull requests.

## What is here

- `src/ir/` — the language-neutral intermediate representation.
- `src/blueprints/ast/` — blueprint parsing and AST construction.
- `src/blueprints/validation/` — the rule set: content injection, SQL, GraphQL
  and HTTP security, data exposure, webhook response paths, expression
  integrity, delivery coverage, and handoff policy.
- `src/catalog/` — module catalog and knowledge-store logic.
- `src/languages/make/` — the Make.com adapter: tokens, translation, semantics
  matrix, round-trip parity, and export.
- `src/mcp/` — an MCP server exposing the engine to a model client.
- `src/media/` — PDF report rendering.

## What is deliberately not here

This repository contains the engine only. Two things were removed before
publication and will not be restored:

- **Third-party corpora.** Development used Make.com course material and public
  community templates as a test corpus. That content belongs to Make.com and to
  the authors who wrote those templates, so it is not mine to redistribute under
  this licence. The rules that were derived from it remain; the source text does
  not. Tests that depended on that corpus were removed rather than rewritten
  against a substitute.
- **Personal operator infrastructure.** The business site, the SRE database, and
  the Windows service that ran them were specific to one deployment and are
  irrelevant to the engine.

Because of the first point, the linter corpus ledgers under
`src/blueprints/validation/data/linter/` record decisions and coverage without
the excerpts they were originally reviewed against.

## Status

The code is uneven. Some surfaces are carefully built and well covered by
contract tests; others are half-finished sketches that were never revisited.
It is published as history, not as a recommendation.

## File Boundary

This file owns the repository entrypoint, active surface summary, and validation
command map. Canonical policy stays in `docs/adr/*.md`. Executable work is
scheduled outside this repository; historical `docs/todo/**` references in
ADR evidence are archive pointers, not active repository command authority.

## Current Surface

The bullets below describe the live repository surface. They are an orientation
summary for humans using the repository; binding product policy stays in
`docs/adr/*.md`.

- `src/ir`, `src/blueprints/ast`, `src/catalog`, `src/blueprints/validation`,
  `src/blueprints/repair`, and `src/mcp` contain active product-engine Python
  bounded contexts.
- `src/languages/make` contains the active Make language adapter and Make JSON
  interpretation; durable Make knowledge is stored in SQLite under the product
  data boundary.
- `tests` contains the active repository test suite.
- `docs/adr` contains product and repository policy records.
- `data/` is a temporary legacy exception surface governed by ADR 001062; new
  durable product-domain data belongs under the owning `src/<bounded-context>/data/`
  path, and private or commercial side assets must be scrubbed, relocated, or
  rewritten before external handoff.
- `cache/` and `temp/` are the only repository-local roots for generated cache,
  coverage, temporary, and intermediate outputs.
- `logs/`, `dependencies/`, `.venv/`, provider state, and OAuth token stores are
  local runtime surfaces and must stay out of tracked source.

Legacy package scripts, solution files, GitHub workflow files, or tool folders
that still exist in older checkouts are not the local authority for this
checkout. The command profile described below is authoritative.

## Local Reproducibility

A clean local checkout is reproducible without live provider credentials.

1. Restore project dependencies with the product-approved local bootstrap for
   the checkout.
2. Keep dependency caches, coverage, temporary output, and generated runtime
   state outside tracked source.
3. Keep Python bytecode and test caches routed under `cache/`.
4. Do not create or rely on a repository `.venv/` as product state.
5. Do not require live Make.com, Vercel, Cloudflare, Paddle, OAuth, or other
   provider credentials for deterministic local validation.

## Validation

Use the repository's approved local validation profile for compile, lint, type,
and test checks. Validation must run without live provider credentials and must
not promote generated cache, OAuth state, or SQLite runtime files into tracked
source.

Online CI/CD is not authoritative for private development. A future clean-room
hosted check may witness the same product-safe behavior only after an explicit
task approves that delivery surface.
