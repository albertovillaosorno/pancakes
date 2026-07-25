# MCP Agent IDE Tool Taxonomy Policy

## Status

Accepted.

## Context

The MCP surface was reduced to remove generic JSON editors, blueprint tool families, project test
tools, scraper status tools, and stale catalog status routes. The remaining problem is product
shape: an AI client needs an IDE for Make.com scenario work, not a database browser and not dozens
of low-level routes.

## Decision

The canonical MCP taxonomy is:

- `catalog.search`
- `catalog.inspect`
- `catalog.work.next`
- `catalog.work.save`
- `project.search`
- `project.create`
- `project.health`
- `project.view`
- `project.edit`
- `project.verify`
- `project.make`
- `project.next`
- `backlog.add`
- `backlog.list`
- `backlog.end`
- `linter.quarantine.write`
- `linter.rule.next`
- `linter.rule.inspect`
- `linter.rule.implement`
- `linter.rule.merge_canonical`
- `linter.rule.reject_invalid`
- `linter.rule.edit`
- `linter.rule.status`
- `linter.rule.rollback`

`catalog.next_unit` and `catalog.save_unit` are retired compatibility aliases for the canonical
`catalog.work.*` development-only operator-approved catalog-worker tools. The catalog work loop
writes only to SQLite, returns a public `lease_handle` for saves, rejects noncanonical coverage
values and sample placeholders, and must not create JSON ledgers. Catalog Intelligence may author
catalog semantic units only when the operator explicitly requests catalog work.

The granular `project.modules.*`, `project.links.view`, `project.filters.*`, and
`project.error_handlers.*` tools remain focused editor primitives and compatibility wrappers. The
normal AI workflow should use `project.view` for reads and `project.edit` for semantic local edits.

The `linter.rule.*` tools are direct-editor infrastructure for future linter workers. They use
lease tokens, evidence-backed dispositions, AST anti-fake checks, severity downgrade proof, SQLite
snapshot invariants, and local one-rule commits. They do not expose raw SQL, raw file editing, live
Make.com calls, provider calls, secret reads, or push.

`project.view` owns the surface selector. It supports `overview`, `graph`, `modules`, `links`,
`filters`, `error_handlers`, `runtime`, `notes`, `make_blueprint`, `readiness`, `parity`,
`issues`, `lineage`, `layout`, and `raw`. There is no top-level BlueprintQL tool; advanced graph
selection belongs in `project.view` arguments.

Every versioned MCP response uses schema version 2 and carries the local/offline safety flags:
`provider_api_call`, `live_make_called`, `credential_value_transfer`, and `secret_output`.
Compact outputs must be bounded, must report hidden counts when they truncate, must provide a next
query when raw or omitted context exists, and must not expose raw JSON walls or credential-shaped
values.

`project.make` previews or writes local Make-native artifact projections only. It never imports into
Make.com, never calls provider APIs, and does not claim live runtime truth. `project.verify` is
deterministic local verification and must distinguish local readiness from external Make runtime
evidence. `project.next` returns the next local IDE action from graph health and runtime setup
posture.

## Consequences

- MCP clients get a small strategic surface instead of a wide route list.
- Raw JSON stays available only as omitted/debug evidence, not the normal workflow.
- Local smoke tests cover catalog search, project health, bounded project views, focused links and
  filters, local Make previews, local verification, and next-step planning.
- Future parity, runtime, and handoff work can extend `project.view`, `project.verify`,
  `project.make`, and `project.next` without restoring removed blueprint or project test families.

## Validation

- `tests/mcp/tool_contracts/mcp_agent_ide_contract.py`
- `tests/mcp/tool_contracts/mcp_response_contracts_contract.py`
- `tests/mcp/tool_contracts/mcp_server_contract.py`
- `pancakes.mcp.smoke`
