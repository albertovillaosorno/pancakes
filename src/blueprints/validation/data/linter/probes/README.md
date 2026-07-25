# Make Linter Probe Data

This directory stores reviewed Make linter probe summaries.

## File Boundary

This README owns the `src/blueprints/validation/data/linter/probes/` boundary.
Probe execution, normalization, catalog logic, and validation logic belong in
source or tool slices, not in this data directory.

## Owner

The linter probe data is owned by the Make catalog and validation evidence
boundaries that use compact reviewed probe summaries.

## Allowed Contents

Allowed contents are sanitized probe reports, compact JSON summaries, reviewed
diagnostic evidence, and README sentinels that explain the local data boundary.

## Forbidden Secrets

Do not store credentials, OAuth tokens, webhook URLs, account IDs, client data,
raw Make API responses, private scenario payloads, or private connection values
here.

## Retention

Keep probe summaries only while they remain useful as reviewed local evidence.
Replace stale summaries through a validated refresh or pruning TODO.

## Git Posture

Reviewed compact probe summaries may be tracked. Raw live probe captures,
private payloads, generated logs, and secret-bearing outputs must remain ignored
or stay under `temp/` or `cache/`.
