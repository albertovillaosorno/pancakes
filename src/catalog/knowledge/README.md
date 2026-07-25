# Catalog Knowledge

This subpackage owns the repository-local Make knowledge store and its compact
query projections.

## File Boundary

- Owns: deterministic SQLite materialization from tracked SQL snapshots,
  catalog-plan SSOT schema, knowledge query loading, catalog projection, status
  reports, and reviewed evidence staging helpers.
- Must not: mutate live Make accounts, store raw credentials, replace offline
  validation, own raw-spec scraping, or treat generated SQLite as canon.
- Inputs: tracked `src/data/sql_snapshots/*.sql` rows, raw-spec rows in
  `src/data/pancakes.sqlite`, reviewed linter or live-probe evidence, and
  explicit CLI arguments.
- Outputs: `src/data/pancakes.sqlite`, compact query
  models, catalog projections, status payloads, and deterministic SQL backup
  fragments.
- Split when: materialization, query projection, linter probes, or live-probe
  staging needs separate persistence, service, or approval boundaries.

## Authority Chain

The Pancakes Make knowledge SQLite database is the SSOT for consumed catalog-plan
progress, semantic answers, search documents, MCP backlog rows, quarantine rows,
datastore evidence, webhook evidence, and recurring sync state. Tracked SQL files
are deterministic schema or backup snapshots derived from that database; they are
not a second ledger.

Refresh order is always:

1. Refresh or materialize raw-spec payload and manifest rows in SQLite.
2. Review or update tracked SQL snapshots when durable facts change.
3. Run `python -B -m catalog.knowledge ensure`.
4. Let validators, MCP tools, and planners query the generated SQLite file.

`load_knowledge_store_query` refuses to load a generated SQLite database whose
stored raw-spec manifest hash no longer matches the current SQLite manifest rows.
Consumers then rebuild through `ensure` or fall back to raw-spec catalog
compilation instead of trusting stale module versions.

A Windows service or scheduled task may automate the same sequence, but it must
call the catalog/raw-spec refresh boundary first and then
`python -B -m catalog.knowledge ensure`. Once an external JSON, Markdown, or
legacy ledger artifact has been consumed, the durable state belongs in SQLite.
Old files may remain only as temporary intake, deterministic exports, or explicit
historical evidence until their migration task removes or archives them.
