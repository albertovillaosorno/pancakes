# Assisted Delivery Validation Data

This directory stores persistent assisted-delivery validation templates and proof
metadata.

## File Boundary

This README owns the `src/blueprints/validation/data/assisted-delivery/`
boundary. Assisted-delivery validators belong in source, while filled-out
captures and operator scratch packets belong in ignored `cache/` or `temp/`
roots.

## Owner

Assisted-delivery validation data is owned by the Blueprint Validation bounded
context and the assisted-delivery claim boundary policy.

## Allowed Contents

Allowed contents are manual capture templates, proof metadata schemas, sanitized
review packets, child README sentinels, and small redacted examples needed for
local validation.

## Forbidden Secrets

Do not store credentials, OAuth tokens, webhook URLs, account IDs, client data,
bearer tokens, operator passwords, private connection values, live-service
secrets, or filled-out private captures in assisted-delivery validation data.

## Retention

Templates and compact proof metadata remain while they define validation
contracts. Filled captures, generated archives, and private operator packets
belong in ignored roots or outside the product repository.

## Git Posture

Sanitized templates and compact proof metadata are tracked by default. Secret,
oversized, generated, or client-private assisted-delivery payloads must remain
ignored or be represented by tracked redacted metadata.
