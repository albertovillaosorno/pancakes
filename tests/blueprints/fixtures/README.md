# Blueprint Fixtures

Fixtures here support blueprint AST, validation, rendering, repair, and demo
scenario tests.

## File Boundary

This README owns blueprint fixture locality. Fixture files must stay
deterministic, credential-free, and close to the tests that use them.

## Diff Blueprint

`diff_blueprint/` contains synthetic generated, exported, and known-good
blueprint triplets for structured comparison tests. These files are fake,
sanitized, and must not be replaced with live Make exports or private customer
blueprints.
