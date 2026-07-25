# Make AST Fixtures

`lead_routing_blueprint.json` is a synthetic, sanitized fixture authored for
parser tests. It does not contain client data, credentials, live Make export
payloads, or private identifiers.

## File Boundary

This README owns the AST fixture boundary. Fixtures here must stay synthetic and
sanitized, and they must not become canonical Make catalog or raw-spec evidence.

The fixture intentionally includes route, filter, mapping, schedule,
error-handler, tool-flow, and unknown-field examples so AST parsing can be
verified without a renderer or live Make calls.
