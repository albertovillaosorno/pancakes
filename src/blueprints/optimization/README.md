# Optimization

This bounded context emits deterministic, non-mutating optimization advice for
parsed Make.com blueprints. Advice is driven by promoted knowledge-store hints
and the AST traversal boundary.

## File Boundary

This README owns the `blueprints.optimization` package behavior summary and
advisory boundary. It must not rewrite blueprints, refresh raw specs, validate
catalog truth, or read course evidence.

Optimization is AST-adjacent. It consumes parsed AST nodes and reviewed
knowledge-store optimizer hints, then returns client-safe advisory records for
review before any future mutating planner exists.
