# Catalog Fallback

This subpackage owns catalog-only fallback behavior used when generated graph,
retrieval, or planning material is absent.

## File Boundary

- Owns: deterministic catalog-only retrieval, alias matching, planning hints,
  scoring, and module-selection validation.
- Must not: call AI providers, mutate catalog snapshots, write files, validate
  blueprint semantics, or invent module capability outside catalog truth.
- Inputs: validated `CatalogSnapshot` objects, operator text queries, requested
  module ids, aliases, and source labels supplied by callers.
- Outputs: ranked candidate modules, planning hints, validation reports, source
  labels, source ranks, and catalog fingerprints for downstream consumers.
- Split when: retrieval, scoring, planning, or selection validation gains its
  own IO, persistence, or non-catalog source boundary.
