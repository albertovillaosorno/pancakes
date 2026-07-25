# Repair

This bounded context explains validation failures and proposes deterministic
repair candidates. It does not mutate live services and does not silently alter
AST payloads.

## File Boundary

This README owns the `repair` package behavior summary and candidate-output
boundary. It must not mutate blueprints, call live services, or replace the
validation context.

Repair is AST-adjacent. It may eventually move under the AST boundary, but it
stays isolated until that migration is explicit and validated.

Repair output must remain explanatory: callers receive typed candidate actions,
finding references, and client-safe wording that can be reviewed before any
future mutating workflow exists.
