# Assisted Delivery Templates

This directory stores persistent assisted-delivery validation input templates.

## File Boundary

This README owns the
`src/blueprints/validation/data/assisted-delivery/templates/` boundary. Template
validation and rendering behavior belong in source and tests; filled-out
captures and operator scratch files belong in ignored `cache/` or `temp/` roots.

## Owner

Assisted-delivery templates are owned by the Blueprint Validation bounded context
and the assisted-delivery capture validation policy.

## Allowed Contents

Allowed contents are sanitized JSON templates, schema-aligned examples, template
README sentinels, and small redacted fixtures needed for local validation.

## Forbidden Secrets

Do not store credentials, OAuth tokens, webhook URLs, account IDs, client data,
authorization codes, bearer tokens, operator passwords, private connection
values, or filled-out private captures in templates.

## Retention

Templates are durable source material for local assisted-delivery validation
workflows. Retire or replace them only with same-round validation of the
consuming contract tests.

## Git Posture

Templates are tracked when they are sanitized and reusable. Filled-out private
captures, secret-bearing examples, generated archives, and client-specific
payloads must remain ignored or live under `cache/` or `temp/`.
