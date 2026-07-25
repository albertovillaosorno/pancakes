# Blueprint Validation Data

This directory stores persistent validation-owned data, proof templates, and
compact evidence fixtures.

## File Boundary

This README owns the `src/blueprints/validation/data/` boundary. Validation
runtime code belongs in `src/blueprints/validation/**/*.py`, and generated
scratch output belongs in ignored `cache/` or `temp/` roots.

## Owner

Validation data is owned by the Blueprint Validation bounded context and the
domain-owned data policy.

## Allowed Contents

Allowed contents are validation templates, compact proof fixtures, linter
evidence, reviewed manifests, child README sentinels, and sanitized synthetic
examples.

## Forbidden Secrets

Do not store credentials, OAuth tokens, webhook URLs, account IDs, client data,
raw client blueprints, private live-service payloads, bearer tokens, operator
passwords, or private connection values in validation data.

## Retention

Validation data remains while it defines reusable validation behavior or product
fixtures. Generated reports, scratch captures, and private live-service outputs
must stay in ignored `cache/` or `temp/` roots unless an owner ADR explicitly
promotes a sanitized fixture.

## Git Posture

Sanitized templates and compact fixtures are tracked by default. Secret,
oversized, generated, or client-private validation payloads must remain ignored
or be represented by tracked redacted metadata.
