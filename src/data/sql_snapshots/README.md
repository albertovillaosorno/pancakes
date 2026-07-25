# SQL Snapshot Inventory

This directory contains reviewable SQL restore snapshots for the Pancakes local SQLite
knowledge store. Pancakes uses SQLite as the local/offline source of truth. SQL files here
are restore evidence, review aids, generated local backup material, or generated projections;
they are not live provider output and they are not the operational database.

The editable engine schema authority is `src/catalog/knowledge/schema.sql`, with table group
contracts in `src/catalog/knowledge/schema.py`. `schema.sql` in this directory is a reviewable
projection/restore aid. Bootstrap executes the editable schema authority first and skips this
projection, so changing generated snapshots is no longer the only path for schema work.

## SQLite SSOT

`src/data/pancakes.sqlite` is the local SQLite source of truth for Pancakes engine state:
catalog source truth, Make evidence, exact semantic state, deterministic graph projections,
technical linter inputs, package-readiness inputs, and versioned technical records. Runtime
workflow state such as MCP scratchpad backlog rows, project progress metadata, and linter
quarantine workflow rows is owned by runtime extension tools, not by the engine schema
bootstrap. The database is ignored by Git because it can be large, machine-local, and
regenerated from the editable schema authority, tracked restore data, and local ingest evidence.

Tracked SQL snapshots are intentionally small and reviewable. They preserve schema and durable
reference data needed to rebuild or audit the local SQLite store. Large generated dumps remain
local-only and must not be uploaded to GitHub.

## Tracked Restore Snapshots

| File | Owner surface | Purpose | Git posture |
| --- | --- | --- | --- |
| `aliases.sql` | catalog aliases | Restore alias evidence. | Tracked, small. |
| `course_rules.sql` | course rules | Restore course-rule evidence. | Tracked, small. |
| `designer_message_evidence.sql` | Make messages | Restore local rows. | Tracked, small. |
| `live_probe_evidence.sql` | local probes | Restore probe records. | Tracked, small. |
| `native_module_expectations.sql` | Make projector | Restore native evidence. | Tracked, small. |
| `schema.sql` | SQLite schema projection | Review/restore projection of the editable engine schema authority. | Tracked, small. |
| `transaction_profiles.sql` | transaction profiles | Restore profile evidence. | Tracked, small. |

## Ignored Local Artifacts

| Artifact class | Example | Retention rule |
| --- | --- | --- |
| SQLite database | `../pancakes.sqlite` | Keep locally; never commit. |
| SQLite sidecars | `../pancakes.wal` | Keep locally; never commit. |
| Alternate DB names | `../*.db` | Keep locally only when operator-owned. |
| Canonical full SQL dump | `make.sql` | Preserve locally; regenerate when needed. |
| Generated SQL dumps | `*.dump.sql` | Preserve locally or externalize; never commit. |
| Full SQL dumps | `*.full.sql` | Preserve locally or externalize; never commit. |
| Backup SQL dumps | `*.backup.sql` | Preserve locally or externalize; never commit. |
| Generated SQL evidence | `*.generated.sql` | Preserve locally or externalize; never commit. |
| SQLite copies in snapshots | `*.sqlite*` | Preserve locally only; never commit. |

## Regeneration

Use the repository-local knowledge commands when snapshot maintenance is required:

```powershell
python -B -m catalog.knowledge ensure
python -B -m catalog.knowledge --repo-root . dump
```

`ensure` rebuilds or validates the local SQLite store from the editable schema authority,
tracked restore snapshots, and available local ingest evidence. `dump` writes the canonical
ignored review dump at
`src/data/sql_snapshots/make.sql`.

These commands are local/offline. Snapshot maintenance must not call Make.com live, browser
automation, provider APIs, or credential stores.

## SQLite Supersedes Model Gate

Measured result: no query currently requires explicit supersedes edges. The temporal fields
`valid_from` and `valid_to`, plus `fingerprint`, `ingest_run_id`, `source_ref`, and source hashes,
answer the current audit questions for raw-spec refresh, catalog invalidation, dashboard history,
and rollback evidence.

Current query policy:

- Raw-spec refresh uses `valid_to IS NULL` for current rows and point-in-time predicates for
  historical rows.
- Catalog invalidation compares catalog unit `source_hash` values against the current raw-spec
  `sha256` for the same `source_ref`.
- Dashboard history uses the same point-in-time validity predicate as raw-spec lookup.
- Rollback evidence uses the row whose `valid_to` equals the refresh boundary, ordered by
  `valid_from`.

Do not add a broad supersedes graph table for these cases. Future explicit supersedes edges
require a new TODO with a measured query that cannot be answered by temporal validity, such as
manual lineage across different source refs, simultaneous branch/merge rows that remain valid, or
operator-selected rollback to a non-adjacent predecessor.

## Retention Policy

- Keep `src/data/pancakes.sqlite` as local operator state and ignore it in Git.
- Keep `src/data/sql_snapshots/make.sql` when present; it is valuable local backup evidence.
- Do not delete generated dumps unless a current operator task owns cleanup and a usable mirror
  or regeneration path exists.
- Commit only small, deterministic, reviewable restore snapshots.
- Store large dumps in local disk mirrors or external backup systems, not in the repository.
- Document new generated dump classes in this README and `.gitignore` before producing them.
- Keep generated dump classes in `.ignore` as well so local agent search and `rg` avoid the
  operator's large restore dumps by default.
- Never store secrets, provider credentials, tokens, webhook IDs, connection IDs, or customer
  payloads in tracked snapshots.

## Restore Policy

1. Prefer restoring `src/data/pancakes.sqlite` from the operator's current local mirror when one
   exists.
2. If the database is missing, run `python -B -m catalog.knowledge ensure` from the repository
   root.
3. If a full local SQL review dump is needed, regenerate `make.sql` with the `dump` command.
4. If the editable schema authority or tracked restore snapshots change, validate them through
   the command layer before commit.

## Review Budget

Tracked snapshots must remain small enough for code review and deterministic tests. If a snapshot
would grow into a large generated dump, keep the dump ignored and promote only a narrow restore
snapshot or schema delta that reviewers can inspect.
