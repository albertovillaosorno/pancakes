# Catalog

This bounded context compiles repository-local Make.com raw specs into the
canonical catalog surface. The catalog describes app, module, field, and
constraint existence before AST validation or blueprint rendering.

Under ADR 001074, the catalog is an internal transform-not-redistribute surface.
It may retain functional compatibility facts needed for validation, rendering,
and diagnostics, but it must not become a downloadable Make module directory,
raw-spec browser, customer appendix, or marketing asset.

## File Boundary

This README owns the `catalog` package behavior summary and catalog-first
fallback posture. Raw-spec scraping, AST validation, and blueprint rendering
remain outside this package boundary.

Child subpackages with distinct persistent contracts keep their own sentinels:

- `src/catalog/fallback/README.md` owns catalog-only fallback retrieval and
  planning boundaries.
- `src/catalog/knowledge/README.md` owns knowledge-store materialization,
  projection, and evidence-staging boundaries.
- `src/languages/make/raw_specs/live/README.md` owns the explicit live Make API adapter
  boundary.

Catalog is AST-adjacent. It may eventually move under the AST boundary, but it
stays isolated until that migration is explicit and validated.

Use `compile_catalog_from_manifest` only with a manifest produced by the
scraper boundary. The compiler validates raw-spec hashes, rejects missing
module records, and produces deterministic stable IDs and fingerprints.
The generated knowledge SQLite file is downstream from that manifest and the
tracked SQL snapshots. Run `python -B -m catalog.knowledge ensure` after
raw-spec refreshes so runtime consumers never trust stale module versions.

Use `detect_catalog_drift` to compare a previous catalog snapshot with the
current snapshot before downstream validators trust persisted fixture anchors.
Use `revalidate_catalog_targets` to fail stale, missing, or unknown module
targets and to select the catalog-first fallback posture when raw specs are
stale or unavailable.

Use `retrieve_catalog_modules`, `build_catalog_planning_hints`, and
`validate_catalog_module_selection` when graph, retrieval, or generated planning
material is absent. These helpers are catalog-only: they rank and validate from
the canonical snapshot, preserve the snapshot fingerprint, and never invent
module capability outside catalog truth.

Accepted refresh catalog snapshots belong under `src/languages/make/data/catalog/` as
persistent project data. Scratch projections may use `cache/`, but they must
never become runtime truth unless a narrower ADR declares that artifact
canonical and validated. Catalog snapshots must not be checked into `src/`.
Customer-facing projections must summarize support status and sanitized evidence
only; they must not expose raw specs, full normalized catalog dumps, copied Make
documentation prose, private API responses, or customer blueprint values.
