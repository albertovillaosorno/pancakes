# Importability Fixtures

This folder contains sanitized offline Make blueprint fixtures for validator importability checks.

- `valid_lead_routing_router.json` covers a fake webhook-to-router-to-two-branches lead routing flow.
- `invalid_routes_on_non_router.json` keeps a non-router route-container shape for route path diagnostics.
- `invalid_unresolved_placeholder.json` keeps an unresolved runtime placeholder in `parameters`.
- `invalid_metadata_note_string.json` preserves the current malformed metadata note behavior.

All fixture values are fake, local, and credential-free.

## File Boundary

This README owns the importability fixture boundary. Fixtures here must stay
sanitized, deterministic, and limited to offline validator importability cases.
