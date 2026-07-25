# Make Designer Message Evidence

This directory owns the Make designer-message linter evidence boundary.

## File Boundary

This README owns the
`src/blueprints/validation/data/linter/designer-messages/` boundary. It must
not contain raw Make scenario payloads, credentials, live probe results, or
reviewed SQL facts.

Raw payloads from `GET /api/v2/scenarios/{scenarioId}/blueprint` are written to
`src/languages/make/data/designer-messages/raw/`, which is ignored by Git. Those files are
temporary ingestion evidence only. Runtime code must consume reviewed normalized
facts from the knowledge store, not raw designer-message payloads.

Reviewed findings are promoted through tracked SQL snapshots under
`src/data/sql_snapshots/` before the generated SQLite store can use them.

## Owner

Designer-message linter evidence is owned by Blueprint Validation and the Make
catalog evidence pipeline that promotes reviewed normalized facts.

## Allowed Contents

Allowed contents are README sentinels, compact reviewed designer-message
evidence summaries, and product-safe references to promoted knowledge-store
evidence used by linter review.

## Forbidden Secrets

Do not store credentials, OAuth tokens, webhook URLs, account IDs, client data,
raw Make API responses, private scenario payloads, bearer tokens, operator
passwords, or private connection values in this directory.

## Retention

Keep reviewed designer-message evidence only while it supports linter policy,
knowledge-store promotion, or validation fixture traceability. Replace stale
evidence through a validated refresh or pruning TODO.

## Git Posture

Reviewed compact evidence may be tracked. Raw live probe captures, private
payloads, generated logs, and secret-bearing outputs must remain ignored or stay
under `temp/` or `cache/`.
