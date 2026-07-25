# Blueprint Rendering Tests

Tests here protect legacy Make renderer compatibility behavior. New Make-native
export/import-shape tests belong under `tests/languages/make/**` because the
Make adapter, not the generic AST boundary, owns Make blueprint JSON output.

## File Boundary

This README owns the legacy rendering test slice. It does not own catalog
refresh, Make adapter export shape, repair diagnostics, or client-facing PDF
generation.
