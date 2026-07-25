# Blueprint Validator Policy

## Status

Accepted

## Scope

repository/blueprint-validation

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.blueprint-validation.findings-model

```json strict-policy
{
  "anchor": "repo.blueprint-validation.findings-model",
  "rule": "Blueprint validation emits typed findings with explicit severity and separate client/internal diagnostics.",
  "required_severities": ["error", "warning", "optimization", "explanation"],
  "required_fields": [
    "finding ID",
    "severity",
    "code",
    "node ID when available",
    "client-safe message",
    "internal diagnostic message",
    "catalog module ID when available",
    "AST source path"
  ]
}
```
## repo.blueprint-validation.designer-warning-local-error-diagnostics

```json strict-policy
{
  "anchor": "repo.blueprint-validation.designer-warning-local-error-diagnostics",
  "rule": "Diagnostic streams must keep repository-owned AST errors separate from reviewed Make designer-message warnings.",
  "source_prefixes": {
    "make_designer_warning": "MAKE-DESIGNER-WARN",
    "make_ast_error": "MAKE-AST-ERROR",
    "make_ast_warning": "MAKE-AST-WARN"
  },
  "required_posture": [
    "designer-message evidence stays warning severity during drafting",
    "local AST, scenario-builder, and validator errors stay error severity",
    "designer warnings never mask, downgrade, or replace local errors",
    "final handoff requires zero local errors and zero applicable reviewed designer warnings"
  ]
}
```
## repo.blueprint-validation.catalog-blocking-rules

```json strict-policy
{
  "anchor": "repo.blueprint-validation.catalog-blocking-rules",
  "rule": "Validators must block nonexistent or unresolved Make modules and required schema mappings before any generation or rendering flow can proceed.",
  "blocking_checks": [
    "unresolved catalog module",
    "missing catalog record for a resolved binding",
    "missing required parameter or mapping",
    "invalid mapping container shape",
    "router without route flows"
  ],
  "nonblocking_checks": [
    "deprecated resolved module",
    "empty route flow",
    "empty filter conditions",
    "webhook-fed event-type router without fallback route evidence",
    "missing schedule metadata",
    "missing AI-agent tools where the AST exposes an AI-agent node",
    "missing direct error handlers on mutating catalog modules"
  ],
  "course_evidence_posture": "Course material is non-authoritative unless later promoted by tests and ADR."
}
```
## repo.blueprint-validation.import-shape-safety

```json strict-policy
{
  "anchor": "repo.blueprint-validation.import-shape-safety",
  "rule": "Validators must reject raw blueprint JSON shapes that Make import or render flows cannot safely interpret.",
  "blocking_checks": [
    "non-string module tokens when a module token is present",
    "boolean module IDs",
    "present module IDs that are neither non-empty strings nor positive integers",
    "duplicate module IDs",
    "non-positive or non-integer module versions when a version is present",
    "non-object node metadata when node metadata is present",
    "non-object designer metadata when designer metadata is present",
    "non-integer designer coordinates when both coordinates are present",
    "non-list designer messages",
    "malformed or non-positive Make note module anchors",
    "Make note anchors that reference missing node IDs",
    "malformed direct error-handler children",
    "empty direct error-handler arrays"
  ],
  "required_posture": [
    "shape checks are local and deterministic",
    "typed AST parsing may preserve raw Make payloads, but validation owns import-safety failures",
    "client messages remain path-safe while internal diagnostics may include source paths"
  ],
  "forbidden_posture": [
    "coercing non-string module tokens into import-safe module names",
    "coercing boolean JSON literals into import-safe module IDs or versions",
    "ignoring malformed designer payloads during validation",
    "coercing boolean or floating-point note anchors into module IDs",
    "treating arbitrary onerror objects as Make modules"
  ]
}
```
## repo.blueprint-validation.filter-condition-aliases

```json strict-policy
{
  "anchor": "repo.blueprint-validation.filter-condition-aliases",
  "rule": "Filter empty-condition validation reads the normalized AST filter conditions surface, not only a literal raw `conditions` field.",
  "depends_on_anchor": "repo.make-ast.route-filter-condition-normalization",
  "required_posture": [
    "supported filter condition aliases do not produce empty-condition warnings",
    "supported filter condition aliases with empty list, object, or blank-string payloads still produce empty-condition warnings",
    "filters with no normalized condition payload still produce empty-condition warnings",
    "validation tests must prove at least one alias path stays non-empty"
  ]
}
```
## repo.blueprint-validation.pre-render-generation-gate

```json strict-policy
{
  "anchor": "repo.blueprint-validation.pre-render-generation-gate",
  "rule": "Every generated or assembled blueprint must pass the validation gate before rendering emits blueprint JSON.",
  "required_posture": [
    "unknown app/module requests return a typed generation blocker",
    "unsupported modules list the needed raw spec, schema, catalog record, or access requirement",
    "validation errors block rendering instead of triggering generic fallback modules",
    "each validation error maps to a deterministic unique blocker ID even when repeated errors share the same code and node",
    "nonblocking warnings may be returned with an allowed gate result"
  ],
  "forbidden_posture": [
    "freeform module-name invention",
    "generic fake module fallback",
    "rendering a blueprint when validation has blocking errors"
  ]
}
```
## repo.blueprint-validation.semantic-module-usage-rules

```json strict-policy
{
  "anchor": "repo.blueprint-validation.semantic-module-usage-rules",
  "rule": "Validators may block module-specific semantic misuse when the raw module token makes the misuse deterministic without live Make execution.",
  "active_rules": [
    "download-file modules are not valid HTTP POST action substitutes",
    "scenario triggers must be first in the top-level flow",
    "a scenario flow must not contain multiple root triggers",
    "trigger-like modules are not valid inside nested route or tool flows",
    "authentication or reauthentication designer messages are blocking runtime evidence",
    "iterator, aggregator, search, list, and watch-style modules emit operation-volume review findings",
    "promoted HTTP rules warn when structured GET responses are not parsed",
    "HTTP request nodes missing local accepted success status evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes with redirects enabled and missing local redirect limit, allowed-host, or credential-forwarding policy evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes with redirects enabled and Authorization headers without local allowed-host plus credential-forwarding policy evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes parsing responses that locally accept 204 or empty-body success evidence without local empty-body parse guard evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes parsing JSON responses without local response Content-Type guard or explicit response body coercion evidence produce warnings with raw configuration values redacted",
    "HTTP request retry policies that locally include 400, 401, 403, validation, schema, malformed-payload, or missing-field errors produce warnings with raw configuration values redacted",
    "Retryable mutating HTTP request nodes without local idempotency-key, deterministic transaction-id, or equivalent idempotency evidence produce warnings with raw configuration values redacted",
    "HTTP PATCH request nodes without local JSON Patch, JSON Merge Patch, or provider-specific partial-update semantics evidence produce warnings with raw configuration values redacted",
    "HTTP PUT request nodes without local full-replacement acknowledgement or partial-update conversion evidence produce warnings with raw configuration values redacted",
    "HTTP DELETE request nodes with local body payload evidence and without provider-support or delete-body semantics evidence produce warnings with raw configuration values redacted",
    "HTTP HEAD request nodes with local response-body parsing or response-body schema expectation evidence produce warnings with raw configuration values redacted",
    "HTTP OPTIONS request nodes without local CORS, preflight, or capability-discovery evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes with local response parsing or structured-response expectation evidence and without response-schema or fallback evidence produce warnings with raw configuration values redacted",
    "Mutating HTTP request nodes whose body maps payload, file, or array-like values without local request-body size-budget evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes with local response parsing or structured-response expectation evidence and without response-size budget evidence produce warnings with raw configuration values redacted",
    "HTTP mutating request nodes declaring Content-Type: application/json for raw string body text without local JSON body validation evidence produce warnings with raw configuration values redacted",
    "HTTP mutating request nodes declaring Content-Type: application/json with locally invalid object, array, or string JSON body syntax produce warnings with raw body values redacted",
    "HTTP request nodes whose local accepted status evidence includes 404 without expected-missing, unexpected-missing, stale-reference, or deleted-upstream classification evidence produce warnings with raw configuration values redacted",
    "Mutating HTTP request nodes whose local accepted status evidence includes 409 without local conflict branch or conflict-resolution evidence produce warnings with raw configuration values redacted",
    "Mutating HTTP request nodes whose local accepted status evidence includes 409 plus conflict branch evidence without retrieve-existing, dedupe, or idempotent-resume evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes whose local accepted status evidence includes 429 without local rate-limit branch, Retry-After, or throttle-handling evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes whose local accepted status evidence includes 5xx without local bounded backoff, queueing, or dead-letter evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes whose local accepted status evidence includes 401, 429, and 5xx plus generic error catch-all evidence without distinct auth, rate-limit, and server-error handling evidence produce warnings with raw configuration values redacted",
    "Webhook-entry scenarios with HTTP request nodes declaring non-success upstream status evidence and static 500 webhook response nodes without upstream-status mapping evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes targeting static external HTTP(S) endpoints without local User-Agent, scenario-context, execution-context, or provider-forbids-User-Agent evidence produce warnings with raw configuration values redacted",
    "HTTP request nodes whose restore or label metadata contains URL, method, or auth hints missing from parameters or mapper fields produce warnings with raw metadata values redacted",
    "HTTP request nodes expecting JSON responses without local Accept: application/json or provider-forbids-Accept evidence produce warnings with raw configuration values redacted",
    "HTTP GET request nodes with local body payload evidence and without explicit nonstandard-API allowlist evidence produce warnings with raw configuration values redacted",
    "promoted HTTP rules warn when file uploads do not declare multipart form-data semantics",
    "HTTP request URLs using external http:// transport are blocking unless the host is a local development endpoint",
    "HTTP request URLs embedding userinfo credentials are blocking and must not echo credential text in diagnostics",
    "HTTP request URLs with credential-style query parameter keys produce warnings with raw query values redacted",
    "HTTP request URL query parameter values containing dynamic Make mappings without visible URL-encoding evidence produce warnings with raw query values redacted",
    "HTTP request URL path segments containing dynamic Make mappings without visible URL-encoding evidence produce warnings with raw URL text redacted",
    "HTTP request URLs targeting static non-local HTTP(S) endpoints without local timeout or timeout-policy evidence produce warnings with raw URL text redacted",
    "HTTP request URLs targeting local or private network evidence without both local timeout and retry-policy evidence produce warnings with raw URL text redacted",
    "HTTP request URLs targeting static HTTPS endpoints with disabled TLS certificate verification are blocking and produce diagnostics with raw URL and certificate settings redacted",
    "HTTP request URLs with dynamic scheme or host evidence and without local dynamic-host allowlist evidence produce warnings with raw URL text redacted while dynamic path and query mappings under a static host are allowed",
    "Production-scoped HTTP request URLs targeting static external API endpoints without local approved-domain or vendor evidence produce warnings with raw URL text redacted",
    "HTTP request URLs targeting private, local, link-local, multicast, or metadata hosts produce warnings with raw URL text redacted until endpoint allowlist profiles are canonical",
    "HTTP request configuration for static external targets mapping sensitive source-field names into outbound request surfaces produces warnings with raw URL and mapping text redacted",
    "Slack or Discord webhook destination fields mapping arbitrary runtime values produce warnings with raw destination text redacted while connection and configuration mappings are allowed",
    "Custom webhook entry nodes missing local payload-size or concurrency budget evidence produce warnings with raw configuration values redacted",
    "Custom webhook entry nodes missing local accepted HTTP method evidence produce warnings with raw configuration values redacted",
    "Custom webhook entry nodes missing local queue, dedupe, rate-limit, or worker-limit burst handling evidence produce warnings with raw configuration values redacted",
    "Mailhook entry nodes missing local trusted sender or domain allowlist evidence produce warnings with raw configuration values redacted",
    "Webhook entry nodes declaring signature or hash evidence without local timestamp and bounded drift-window evidence produce warnings with raw configuration values redacted",
    "HTTP header configurations containing CRLF injection markers are blocking and must not echo raw header values",
    "HTTP header configurations containing dynamic mappings without visible header sanitization evidence produce warnings with raw mapping text redacted",
    "HTTP secret-scoped header configurations containing mapped runtime values without visible log or header masking evidence produce warnings with raw header values redacted",
    "HTTP request configuration containing static secret-like literals in secret-scoped fields is blocking and must not echo raw secret values",
    "Unsafe sink module configuration containing static personal identifier literals in message, body, prompt, or response fields produces warnings with raw values redacted",
    "Unsafe sink module configuration directly mapping whole payload-like values into content, record, or response fields produces warnings with raw mapping text redacted",
    "Unsafe sink module configuration mapping secret-like source fields or static secret literals into visible output, variable, or record fields produces warnings with raw values and mapping text redacted",
    "Unsafe sink module configuration mapping sensitive-looking fields from HTTP response bodies without visible redaction produces warnings with raw mapping text redacted",
    "Unsafe sink module configuration containing static internal URL literals in visible output fields produces warnings with raw URL text redacted",
    "Webhook response fields mapping raw error, exception, or stack-like source fields produce warnings with raw mapping text redacted while sanitized error codes and trace IDs are allowed",
    "Webhook response fields mapping raw cursor, scroll ID, continuation token, search-after, or page-token source fields produce warnings with raw mapping text redacted while public page numbers and counts are allowed",
    "Root and module metadata note content containing static email-like or phone-like personal identifier literals produces warnings with raw values redacted",
    "Root and module metadata note content containing non-HTTPS link literals produces warnings with raw values redacted while HTTPS and runtime-mapped URLs are allowed",
    "Security-scoped configuration containing MD5 or SHA-1 hash algorithm names produces warnings with raw values redacted",
    "JWT validation configuration declaring alg or algorithm none is blocking and must not echo raw configuration values; broader expected algorithm allowlists require provider or scenario profile context",
    "Root and module metadata note content containing static secret-like literals produces warnings with raw values redacted while mappings and redacted placeholders are allowed",
    "SQL-like module raw query text containing Make mappings produces warnings with raw SQL and mapping text redacted; parameterized patterns should keep mappings in binding fields outside the query text",
    "Redirect response destinations with dynamic scheme or host evidence produce warnings with raw redirect URL text redacted while dynamic path and query mappings under a static host are allowed",
    "GraphQL query fields containing formatted query text with newlines, tabs, or repeated spaces produce warnings with raw query text redacted",
    "GraphQL query fields directly containing Make mappings without a local variables object produce warnings with raw query text redacted",
    "GraphQL query fields containing anonymous query, mutation, subscription, or shorthand selection-set operations produce warnings with raw query text redacted",
    "GraphQL query fields whose visible selection depth exceeds a declared local depth budget produce warnings with raw query text redacted",
    "GraphQL query fields whose approximate selected field count exceeds a declared local field-count budget produce warnings with raw query text redacted",
    "Production-scoped GraphQL query fields containing introspection evidence produce warnings with raw query text redacted",
    "promoted Parse JSON rules warn when local schema, data-structure, expected-schema, or sample evidence is missing",
    "HTML-capable response, email, or rich-content fields containing Make mappings produce warnings with raw HTML and mapping text redacted unless local HTML escaping or sanitization evidence is visible",
    "Markdown-capable message or block fields containing Make mappings produce warnings with raw Markdown and mapping text redacted unless local Markdown escaping evidence is visible",
    "promoted iterator rules warn when an iterator lacks source-array evidence",
    "promoted iterator performance rules warn when array expansion lacks local item-count limit, record-limit, page-size, slice, or chunking evidence",
    "promoted aggregator performance rules warn when source consumption lacks local bundle-count limit, record-limit, window, or chunking evidence",
    "promoted data-store rules warn when delete operations lack recovery or audit posture",
    "promoted data-store reliability rules warn when ephemeral lock, session, cache, dedupe, or idempotency state lacks TTL or cleanup evidence",
    "promoted scenario governance rules warn only when explicit production or governance profile metadata lacks owner, change reason, rollback plan, incident/runbook evidence, or when production-profiled nodes retain local debug markers",
    "promoted transaction profiles warn when rollback-unsafe mutations lack recovery, idempotency, audit, or compensation posture",
    "scenario self-invocation without a clear local exit condition is blocking cycle evidence"
  ],
  "required_posture": [
    "semantic rules are deterministic and local",
    "semantic rules do not invent catalog modules",
    "semantic rules emit typed findings with client-safe messages"
  ],
  "forbidden_posture": [
    "using semantic warnings to bypass catalog validation",
    "contacting live Make services during validation"
  ]
}
```
## repo.blueprint-validation.theoretical-cycle-rules

```json strict-policy
{
  "anchor": "repo.blueprint-validation.theoretical-cycle-rules",
  "rule": "Validators must reject deterministic theoretical scenario cycles before rendering or handoff.",
  "active_rules": [
    "a scenario-invocation node that targets the current scenario by scenario ID, scenario name, current, or self reference must declare explicit local exit evidence",
    "HTTP/API nodes that target Make scenario run endpoints are treated as scenario invocations only when they also contain current-scenario identity evidence",
    "exit evidence must be visible in the local AST node payload through guard, limit, max-depth, stop, termination, idempotency, or equivalent control metadata"
  ],
  "required_posture": [
    "cycle checks are local and deterministic",
    "cycle checks never call live Make APIs or inspect live scenario state",
    "cycle findings are blocking only when self-invocation and missing exit evidence are both present"
  ],
  "forbidden_posture": [
    "treating every scenario-tool call as a cycle",
    "inferring a cycle from module names alone without current-scenario target evidence",
    "using live Make execution to prove termination"
  ]
}
```
## repo.blueprint-validation.ai-agent-contract-rules

```json strict-policy
{
  "anchor": "repo.blueprint-validation.ai-agent-contract-rules",
  "rule": "AI-agent nodes and their tool wrappers must expose enough local contract metadata to be testable before handoff.",
  "active_rules": [
    "AI-agent nodes declare provider or model assumptions",
    "stable instructions and runtime inputs are separated",
    "fallback behavior is declared for tool failure or insufficient input",
    "representative test cases are present",
    "knowledge attachments are reviewed for least-privilege scope",
    "agent tools have clear descriptions",
    "agent tool names are client-readable, unique within the agent, and free of static sensitive literals",
    "agent tool descriptions do not carry static sensitive literals",
    "scenario tools have input/output contracts, on-demand execution, and return-output paths"
  ],
  "required_posture": [
    "AI-agent checks are local and deterministic",
    "designer notes do not create or mask runtime contract evidence",
    "generic start actions are not treated as scenario tools unless scenario evidence is present"
  ],
  "forbidden_posture": [
    "using broad agent instructions as delivery-ready scope",
    "publishing agent-callable tools without input and output contracts",
    "calling live services to infer missing AI-agent configuration"
  ]
}
```
## repo.blueprint-validation.transaction-safety-rules

```json strict-policy
{
  "anchor": "repo.blueprint-validation.transaction-safety-rules",
  "rule": "Blueprint validators may emit deterministic transaction-safety findings only from promoted knowledge-store transaction profiles.",
  "depends_on_anchor": "repo.make-knowledge.transaction-safety-profiles",
  "active_rules": [
    "rollback-unsafe or externally committed operations require recovery, idempotency, audit, or compensation posture",
    "HTTP write requests are treated as external commits unless the blueprint declares transaction-safety evidence",
    "data-store destructive operations are treated as irreversible unless the blueprint declares backup or recovery evidence"
  ],
  "required_posture": [
    "validation remains local and deterministic",
    "findings cite promoted rule facts and ADR-backed profile rows",
    "transaction warnings do not claim true ACID guarantees without source evidence"
  ],
  "forbidden_posture": [
    "contacting live Make services to test rollback behavior",
    "marking a blueprint transaction-safe only because an error handler exists",
    "using transaction warnings to bypass catalog validation"
  ]
}
```
## repo.blueprint-validation.output-contract-reference-rules

```json strict-policy
{
  "anchor": "repo.blueprint-validation.output-contract-reference-rules",
  "rule": "Validators must reject downstream Make expressions that reference fields absent from an explicit source-node output contract.",
  "contract_sources": [
    "interface",
    "outputs",
    "output_schema",
    "metadata.interface",
    "metadata.outputs",
    "metadata.output_schema"
  ],
  "required_posture": [
    "referenced source node IDs must exist in the AST",
    "missing output contracts do not create false blocking certainty",
    "declared scalar outputs do not allow arbitrary child references",
    "declared dynamic object or array outputs may allow child references under the declared dynamic root",
    "known wrapper aliases must be evidence-backed and listed in code"
  ],
  "forbidden_posture": [
    "inventing output fields to satisfy downstream expressions",
    "failing a reference when no source output contract exists",
    "using live Make calls to validate output references"
  ]
}
```
## repo.blueprint-validation.client-safe-diagnostics

```json strict-policy
{
  "anchor": "repo.blueprint-validation.client-safe-diagnostics",
  "rule": "Client-facing validation messages must not expose local paths, repository internals, or implementation details.",
  "required_posture": [
    "client messages describe the user-facing problem",
    "internal messages may include node IDs, catalog IDs, source traces, and schema paths",
    "tests must prove client messages remain path-safe"
  ],
  "forbidden_posture": [
    "placing local filesystem paths in client messages",
    "using validation failures as a reason to generate fake modules",
    "treating examples, courses, or prompts as catalog authority"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- Blueprint validators can fail unsafe scenarios before renderer or generator
work begins.
- Diagnostics stay useful internally without leaking machine-specific paths to
client-facing output.
- Later repair and rendering slices can consume a deterministic report instead
of duplicating catalog and AST checks.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001046`.
- Decision ID: `repo.blueprint-validation.validator-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001046'
decision_id: 'repo.blueprint-validation.validator-policy'
title: 'Blueprint Validator Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - runtime
  - testing
scope: 'repository/blueprint-validation'
applies_to:
  - src/blueprints/validation/**/*
  - tests/blueprints/validation/blueprint_validation_contract.py
  - docs/bibliography/make.com.md
applies_when:
  - make_ast_blueprints_are_validated
  - blueprint_generation_or_rendering_depends_on_validation
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '000010'
  - '000016'
  - '000017'
  - '001042'
  - '001044'
  - '001045'
  - '001079'
source_material:
  - path: 'Refactor/make/src/forge/blueprint_validator.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_blueprint_validator.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_error_handling_semantics.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_error_handling_semantics.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/src/forge/make_ai_agent_intelligence.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/make/tests/unit/test_make_ai_agent_intelligence.py'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/blueprints/validation/**/*
  - tests/blueprints/validation/blueprint_validation_contract.py
bibliography_refs:
  - 'https://developers.make.com/'
  - 'https://csrc.nist.gov/pubs/sp/800/131/a/r2/final'
  - 'https://csrc.nist.gov/projects/hash-functions'
traceability_anchors:
  - repo.blueprint-validation.findings-model
  - repo.blueprint-validation.designer-warning-local-error-diagnostics
  - repo.blueprint-validation.catalog-blocking-rules
  - repo.blueprint-validation.import-shape-safety
  - repo.blueprint-validation.filter-condition-aliases
  - repo.blueprint-validation.pre-render-generation-gate
  - repo.blueprint-validation.semantic-module-usage-rules
  - repo.blueprint-validation.theoretical-cycle-rules
  - repo.blueprint-validation.ai-agent-contract-rules
  - repo.blueprint-validation.output-contract-reference-rules
  - repo.blueprint-validation.transaction-safety-rules
  - repo.blueprint-validation.client-safe-diagnostics
non_goals:
  - implement blueprint auto-repair in this round
  - generate or render final Make blueprint JSON in this round
  - contact live Make services
  - rebuild graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup scope
```
</details>
