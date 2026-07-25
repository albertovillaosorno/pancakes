# Make Linter Validation Data

This directory stores product-safe Make linter evidence, deterministic fixtures,
and SQLite-derived snapshots owned by the blueprint validation bounded context.
The Make knowledge SQLite database is the SSOT for persistent linter backlog,
quarantine, review, rule-surface, and data-source inventory state.

## File Boundary

This README owns the `src/blueprints/validation/data/linter/` boundary. Linter
runtime code belongs in `src/blueprints/validation/**/*.py` or the importing
bounded context that consumes the evidence. Raw ingest payloads, live service
captures, and generated scratch output belong in ignored owner paths, `cache/`,
or `temp/`.

## Owner

The linter data package is owned by Blueprint Validation and ADR 001079's Make
linter manual-intake policy.

## Allowed Contents

Allowed contents are sanitized corpus accounting projections, legacy candidate
decision migration input, master coverage maps, legacy quarantine review
evidence, SQLite-derived snapshots, completed intake evidence, standards-source
research ledgers, compact reviewed probe summaries, README sentinels, and
product-safe evidence needed to preserve non-loss of imported linter candidate
IDs.

## Forbidden Secrets

Do not store credentials, OAuth tokens, webhook URLs, account IDs, client data,
raw Make API responses, private scenario payloads, bearer tokens, operator
passwords, or private connection values in this linter data package.

## Retention

Keep linter corpus files only while they are deterministic fixtures, migration
input, or SQLite-derived snapshots. Runtime linter authority lives in SQLite;
once a file is consumed into SQLite and no longer needed as fixture evidence,
delete it or regenerate it from SQLite in the same validated work unit.

## Git Posture

Sanitized corpus files and legacy decision ledgers may remain tracked while they
are migration evidence. Raw live probe captures, client-private payloads,
generated logs, generated SQLite databases, and secret-bearing outputs must
remain ignored or stay under `temp/` or `cache/`.
