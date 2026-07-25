# Catalog Fixtures

Catalog fixtures provide deterministic sample raw specs and compiled catalog
payloads.

## File Boundary

This README owns catalog fixture locality. Fixtures must not include credentials,
live account data, or generated cache output.

## Raw-Spec Manifests

`raw_spec_manifest.py` owns reusable synthetic raw-spec manifest materialization
for tests that need catalog-backed module metadata without depending on ignored
`temp/raw-specs-json` assets. The committed `raw_specs/minimal_manifest.json`
is the deterministic manifest snapshot for the synthetic Data Store fixture; the
builder writes matching raw-spec payload files into a caller-supplied temporary
repository root under `tests/catalog/fixtures/raw_specs`.
