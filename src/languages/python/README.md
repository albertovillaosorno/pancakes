# Make To Python Stub

## File Boundary

This directory is a placeholder for a possible future Pancakes-to-Python
translation slice. Python is not a source automation language for Pancakes. It
owns no active runtime code today. Implementation belongs here only after a
future ADR accepts the output class, source truth, generated artifact location,
validation responsibility, and delivery boundary.

## Status

This is intentionally not a pending implementation priority. The active Make
work remains Golden coverage, Blueprint AST/validation, MCP tooling, local
linter taxonomy, and scraper boundaries.

## Allowed Future Inputs

- Validated Blueprint AST structures.
- Catalog and raw-spec truth that already passes repository checks.
- Local rule evidence promoted through ADR-backed validation or linter work.

## Must Not

- Infer Make behavior that is not represented by local evidence.
- Call live Make services or use credentials.
- Generate client deliverables without the client delivery scrubber boundary.
- Become a catch-all router or dumping ground for unrelated Python services.
