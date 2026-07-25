# Make To Python Platform Adapter Boundary Policy

Status: accepted

## Decision

Pancakes may treat Make-to-Python translation and other platform adapters as a future portability
strategy, but no translation target or second automation platform adapter is part of the current
executable product boundary.

The current executable adapter remains Make. The product boundary is the language-neutral IR core
plus deterministic analysis, validation, repair guidance, and client-safe handoff for supported
automation blueprints. Platform portability belongs behind the existing language, AST, and IR
boundary. It requires evidence before implementation.

Python is not a source automation language for Pancakes. Python may later become a translation
target only after an accepted design defines the intermediate representation, lowering rules,
fixture coverage, and validation contract.

Zapier, n8n, and other automation platforms may later become source-language adapters under
`src/languages/**`. They must not be represented as Make subdirectories, speculative generic AST
fields, or customer-facing support claims before the adapter exists.

## Deferred Promotion Gates

- Make-focused validation and repair workflows have stable customer evidence.
- The current Make adapter, AST compatibility runtime, linter, MCP, report, and
handoff boundaries are stable.
- A second source automation language has real fixtures that can be compared
against Make field by field.
- Stable shared semantics have been promoted into or proven against `src/ir/**`.
- Platform-specific behavior remains isolated in language adapters.
- Translation round trips have deterministic tests and failure diagnostics.

## Current Non-Goals

- Do not implement Make-to-Python translation.
- Do not implement Zapier, n8n, or other source-language adapters.
- Do not claim migration, portability, or vendor lock-in reduction as a current
supported capability.
- Do not treat Make-specific fields as generic IR truth.
- Do not mix private business strategy into repository-visible adapter policy.

## Consequences

Future portability work must be promoted through explicit ADRs and tests. Until then, Make-to-Python
and platform adapters are documented as deferred expansion paths, not active product behavior.
