# Make Project Workspace

This folder is the generated Make project workspace for local project JSON
drafts created by the MCP IDE loop.

## File Boundary

This README owns the repository-root `projects/` workspace boundary. Blueprint
validation, rendering, repair, catalog facts, persistent fixtures, and MCP
runtime behavior belong in their owning source, test, and tool slices.

## Owner

Generated project workspaces are owned by the Make scenario/project MCP tools.
Persistent examples and regression fixtures are owned by `tests/**`, and
reusable starter payloads are owned by `projects/templates/**`.

SQLite project metadata lives in `src/data/pancakes.sqlite` table
`local_project_metadata`. That table is the technical source of truth for new
local project identity, folder keys, and artifact envelope paths. The folders in
`projects/**` are generated envelopes and can be reconstructed from SQLite plus
the local package/render process.

## Allowed Contents

Allowed generated contents are local project folders containing `scenario.json`,
`scenario.tests.json`, previous revisions, archives, and draft-local support
files produced by the IDE loop. Reusable redacted templates may live under
`projects/templates/**`.

## Forbidden Secrets

Do not store credentials, OAuth tokens, webhook URLs, account IDs, client data,
private Make connection values, raw account-specific exports, or private lead
records here.

## Retention

Project folders are runtime artifacts. They may be created, patched, archived,
deleted, or cleaned by MCP tools and should not be treated as repository source.
Keep long-lived regression evidence under `tests/**`, not under `projects/**`.

## Git Posture

Generated project artifacts are ignored by default. The repository may track
this README and reusable redacted templates under `projects/templates/**`.
Operator-provided real Make exports, private blueprints, raw webhook payloads,
and other secret or client-private files belong in ignored `temp/`, `cache/`, or
generated project workspaces.

## Project JSON

New projects created through `project.create` use:

`projects/<customer-folder-key>/<scenario-or-product-key>-<project-slug>/scenario.json`

The default neutral folder keys are `local-demo` and `0001`. Real customer,
payment, subscription, delivery, and approval lifecycle state does not live in
Pancakes Core; Schoenwald SRE owns that business state outside this repository.

Legacy local drafts may still exist at:

`projects/<project_id>/scenario.json`

That legacy path remains readable for tests and migration, but new project
creation should prefer the SQLite-backed envelope policy above.

Nested legacy local drafts such as
`projects/local-demo/0001-catalog-ide-real-use-smoke-20260524/scenario.json`
are also readable when their `metadata.project_id` is unique. `project.search`
reports those folders as `legacy_repo_project_artifact` with a migration plan,
and `project.verify` resolves the same `project_id` for deterministic local
checks. Advisory linter or package-surface statuses on ignored legacy stress
artifacts are accepted only as local generated-state evidence; they are not
client deliverables and should be removed only after the SQLite metadata
envelope exists and verification passes for the migrated copy.

`projects/templates/**` is the exception to generated-state cleanup. Reusable
redacted templates are allowed tracked source and are reported as
`approved_repo_template_library`, not as migration debt.

## Diff Blueprint Artifacts

`blueprint.diff` accepts blueprint inputs only from these repository-local roots:

- `projects/`
- `temp/diff-blueprint/`
- `tests/blueprints/fixtures/diff_blueprint/`

Use `temp/diff-blueprint/` for operator-provided real Make exports and uploaded
blueprints by default. `temp/` is ignored and short-lived, so private raw export
payloads do not become tracked repository data.

Use `projects/` for local draft comparison only. If a sanitized artifact becomes
durable regression evidence, promote it into an owned fixture or template path
outside generated project workspaces before committing it.

Use `tests/blueprints/fixtures/diff_blueprint/` only for synthetic committed
fixtures that exercise comparison behavior.

`blueprint.diff` rejects paths outside the approved roots and still rejects
parent-directory escapes outside the repository.
