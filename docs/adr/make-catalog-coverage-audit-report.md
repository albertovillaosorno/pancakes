# Make Catalog Coverage Audit Report

## Status

Accepted

## Scope

repository/make-catalog-coverage

## Local Audit

The audit used only local read-only MCP tools:

- `catalog.status`;
- `catalog.generation_audit`;
- `catalog.plan`;
- `scenario.modules.search`.

No live Make or provider calls were made. The local status payload reported
`live_refresh_enabled=false`, `refresh_mode=local_status_only`, and
`credentials_required=false` for planning fallbacks.

## Coverage State

Local raw-spec status on 2026-05-16, using the manifest generated at
`2026-05-16T12:15:35.670074+00:00`:

- status: `ready`;
- manifest: `temp/raw-specs-json/manifest.json`;
- record count: 2931;
- latest record count: 2759;
- total module count: 40656;
- invalid records: 0;
- missing records: 0;
- source type counts: 2931 `client_authorized_authenticated_api_response` records;
- sanitization status counts: 2931 `internal_raw_ignored` records;
- freshness: `manifest_verified`.

Generation audit across the full local catalog reported:

- audited modules: 40656;
- deprecated modules: 375;
- modules with RPC dependencies or dynamic selectors: 20273;
- malformed raw specs: 0;
- blockers: 0.

The targeted Make scenario audit for webhook, router, datastore, Slack, HTTP, and Make AI agent
modules found six local modules and no blockers. Four of those modules require RPC expansion or
dynamic selector handling. The Basic Router is backed by a local Make built-in manifest.

The current targeted module IDs were:

- `module:gateway:1.14.1:trigger:CustomWebHook`;
- `module:builtin:1.8.3:router:BasicRouter`;
- `module:datastore:2.0.5:action:AddRecord`;
- `module:slack:2.14.3:action:ActionCreateMessage`;
- `module:http:4.13.6:action:MakeRequest`;
- `module:ai-agent:0.43.0:action:CreateAIAgentContextFile`.

## What Is Catalog-Backed

The raw-spec manifest and generated knowledge SQLite cover most provider modules, including:

- `gateway:CustomWebHook`;
- `datastore:AddRecord`;
- `slack:ActionCreateMessage`;
- `http:MakeRequest`;
- `ai-agent:CreateAIAgentContextFile`.

`scenario.modules.search` returned knowledge-backed best matches for webhook, datastore, Slack,
HTTP request, AI agent, and OpenAI-related searches. The top local matches included
`module:gateway:1.14.1:trigger:CustomWebHook`,
`module:datastore:2.0.5:action:AddRecord`,
`module:slack:2.14.3:action:ActionCreateMessage`,
`module:http:4.13.6:action:MakeRequest`, and
`module:ai-agent:0.43.0:action:CreateAIAgentContextFile`.

## What Is Manifest-Backed

Make built-ins are not treated as ordinary provider raw specs. The current targeted audit proved
`builtin:BasicRouter` through the local built-in manifest path and labeled it
`make_builtin_manifest_backed`.

## What Is Pass-Through Only

Customer custom modules, private connector modules, and unknown module tokens remain pass-through
unless they have explicit source classification, authorization metadata, deletion status, and
promotion eligibility. Customer visibility alone is not reusable catalog evidence.

## Dynamic-Selector Blockers

Dynamic selectors are the main planning gap. The catalog can identify the module and RPC dependency
count, but it cannot safely expand account-scoped selector choices offline. The audit found 20273
modules with RPC dependencies, including Slack, datastore, HTTP, and AI-agent examples in the
targeted scenario audit.

## Planning Completeness

`catalog.plan` is not yet close to complete for broad natural-language planning. The sample
requirements text produced a recoverable truncation instead of a plan:

- status: `recoverable_truncated_catalog_retrieval`;
- error code: `catalog.plan.retrieval_truncated`;
- recommended fallback: run narrower `scenario.modules.search` queries.

The fallback worked for targeted terms, but broad planning still required query decomposition.
A 2026-05-17 follow-up changed knowledge-backed `catalog.plan` to run those decomposed searches
before the whole-paragraph prefilter. The current recovery payload recommends specific local
searches for gateway custom webhook, basic router, datastore add record, Slack create message,
audit log, dedupe, error handler, idempotency, AI agent, and HTTP request. Pancakes can now produce
bounded knowledge-backed plans for broad paragraphs by passing a small ordered planning slice into
the semantic planner.

## Evidence Gaps

The local corpus is strong enough for module lookup, raw-spec-backed validation, built-in router
coverage, and targeted generation audits. It is not enough for:

- account-scoped dynamic selector expansion;
- reusable customer custom module truth;
- complete broad `catalog.plan` mapping;
- native semantics rows for every high-value AI-agent workflow;
- blueprint diff rules for every app-specific schema behavior.

## Follow-Up Intake

External research is not required to complete this local audit. It is required only before Pancakes
claims complete planning coverage for dynamic selectors, high-value AI-agent workflows, or
app-specific native projector behavior.

The next root queue or pending prompt should request:

- public-source evidence for the highest-frequency AI-agent, OpenAI, Google Sheets, Slack event,
  Google Docs, Telegram, JSON, and Make AI Web Search module shapes observed in Golden fixtures;
- one JSON schema or field-shape summary per module, with source URLs and source-use notes;
- explicit redaction rules forbidding secrets, OAuth tokens, customer account state, private
  payloads, and provider credentials;
- a proposed Pancakes ingestion path for each evidence row: raw-spec refresh, projector manifest,
  native semantics matrix row, blueprint diff rule, or quarantine-only note;
- post-ingestion validation commands: `pancakes.lint`, `pancakes.typecheck`, `pancakes.test`, and
  `schoenwald.markdown.validate` when docs change.
