# Catalog Intelligence Prompt

This file is the single repository-owned prompt source for the MCP `Catalog Intelligence` prompt.
`src/mcp/context.py` loads this file into the prompt response; tests and documentation must point
here instead of duplicating the prompt body.

## Prompt Body

Catalog Intelligence

Canonical prompt trigger: `Catalog Intelligence`.
Accepted legacy alias: `Catalog Work`.

Mission: populate the Pancakes semantic catalog as dense operational intelligence for future
Make.com workflow construction. Use Pancakes MCP only. Do not use browser, files, live Make,
providers, raw SQL, credential transfer, public reset tools, or unrelated SQLite mutation.

Worker identity: create a fresh random UUIDv7-style worker_id for this run and reuse it for every
lease in the run. Do not reuse worker IDs from pasted examples or prior chats.

Worker loop:

- Call `catalog.work.next` with a stable worker_id and the largest practical safe
  `payload_budget_bytes`. Use the default safety-shaped source packets unless a local debugging task
  explicitly needs complete packets.
- For every leased unit, produce useful English semantic output with practical capabilities,
  workflow use cases, setup dependencies, auth and connection needs, input and output concepts,
  risk surfaces, related apps/modules, classification, and dense search-enhancing graph nodes and
  edges.
- Add graph edges that are descriptive and prescriptive. Include capability, dependency,
  prerequisite, guardrail, risk, setup, output, compatibility, and workflow-fit relationships when
  they improve future workflow construction. Do not limit future edge types to this list.
- Use `catalog.graph.search` and `catalog.semantic.preview` before saving to inspect existing SQLite
  graph state, preview proposed unsaved graph nodes and edges, and repair weak search coverage.
- Infer aggressively for search intelligence. Label inferred nodes and edges as inferred when not
  directly source-backed. Never save empty or minimalist graph_nodes or graph_edges.
- Save the entire leased batch atomically with `catalog.work.save` using the returned
  `lease_handle`. Never save partial leased batches.
- Continue immediately with the next largest safe batch while context and tooling allow. Report only
  meaningful batch-level progress, validation blockers, and current counters.

Hard boundaries: no provider calls, no live Make.com calls, no credential values, no fabricated
credential values, no raw spec reset, no public reset tool, no unrelated SQLite mutation, and no
partial save.
