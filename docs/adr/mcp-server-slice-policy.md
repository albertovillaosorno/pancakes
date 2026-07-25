# MCP Server Slice Policy

## Status

Accepted

## Scope

repository/mcp-server

## Decision

## File Boundary

This ADR is a canonical policy record. It owns durable decision rules, scope, consequences,
traceability anchors, and derived-artifact obligations. It must not be used as round evidence,
migration inventory, or scratch notes.

## repo.mcp.server-identity

```json strict-policy
{
  "anchor": "repo.mcp.server-identity",
  "rule": "The repository MCP surface uses a technical capability server name and repository-local test startup by default.",
  "server_name": "blueprint-mcp",
  "canonical_url": "repo://blueprint/mcp",
  "test_transport": "stdio",
  "live_network_transport": "loopback_http_only_when_explicit"
}
```
## repo.mcp.make-scenario-tool-scope

```json strict-policy
{
  "anchor": "repo.mcp.make-scenario-tool-scope",
  "rule": "Repository MCP tools exist to help Codex/GPT generate, validate, explain, repair, and assess Make.com scenarios, not to expose generic technical repository operations.",
  "primary_domain": "Make.com scenario generation and validation",
  "allowed_tool_categories": [
    "Make catalog readiness and planning",
    "Make scenario builder local draft workspaces",
    "Operator-gated Make live roundtrip review probes",
    "Make blueprint compilation from explicit local inputs",
    "Make blueprint validation and delivery readiness",
    "Make blueprint structured comparison",
    "Make AST explanation and repair advice",
    "Make raw-spec scraper refresh status"
  ],
  "future_possible_domains": [
    "Upwork proposal support only after a future ADR defines a bounded proposal surface",
    "portfolio support only after a future ADR defines a bounded portfolio surface"
  ],
  "forbidden_tool_categories": [
    "generic repository inspection tools",
    "git, shell, dependency, CI, or filesystem administration tools",
    "broad personal productivity tools",
    "write-like live Make mutation without explicit operator-gated ADR approval"
  ],
  "required_posture": [
    "tool names, descriptions, and schemas must be phrased around Make scenario outcomes",
    "repository-local paths may appear only as support inputs for Make scenario artifacts",
    "future non-Make commercial-support tools must stay outside the default MCP surface until separately approved"
  ]
}
```
## repo.mcp.scenario-builder-micro-tools

```json strict-policy
{
  "anchor": "repo.mcp.scenario-builder-micro-tools",
  "rule": "Scenario-builder MCP tools may mutate only repository-local scratch workspace artifacts and finalized project scenario JSON files; they must never mutate live Make.com scenarios or accept raw arbitrary blueprint replacement commands.",
  "workspace_root": "temp/mcp-scenario-builder",
  "final_artifact_root": "projects",
  "timezone": "America/New_York",
  "required_tools": [
    "scenario.workspace.create",
    "scenario.modules.search",
    "scenario.modules.list",
    "scenario.modules.expand",
    "scenario.command.apply",
    "scenario.command.batch",
    "scenario.validate"
  ],
  "command_posture": [
    "commands must be typed JSON objects carried as explicit command_json or commands_json payloads",
    "single commands must validate before any workspace write",
    "ordered command batches must be all-or-nothing against the workspace file",
    "failed commands must return compact linter-like feedback and leave the workspace unchanged",
    "finalized scenario artifacts must be saved as ignored generated drafts under projects/<generated-project-id>/scenario.json",
    "finalized scenario workspaces reject later mutation commands",
    "scenario.modules.expand supports compact planning output while preserving raw/spec-backed expansion for debugging",
    "tool responses must return compact summaries, findings, and tree/cost signals instead of echoing full blueprint JSON by default"
  ],
  "validation_posture": [
    "static complexity and operation-risk signals are advisory indices, not exact Make runtime cost estimates",
    "module aliases and native module kinds come from the Make knowledge store when available",
    "validator feedback may use static AST/catalog/knowledge facts but must not call live Make validation endpoints",
    "realtime feedback includes compact source-prefixed local errors and reviewed Make designer warnings when available",
    "scenario validation reads malformed local drafts without normalizing or repairing them",
    "malformed or non-positive local draft node IDs, module tokens, and versions are reported as feedback findings instead of coerced",
    "malformed or non-positive local draft connection endpoints are reported as feedback findings instead of coerced",
    "draft commands may proceed with designer warnings, but finalization requires a zero-diagnostic feedback result",
    "missing designer-message evidence is reported as an evidence gap instead of a fabricated clean designer result"
  ],
  "forbidden_posture": [
    "accepting a raw JSON replacement as a scenario command",
    "writing finalized project artifacts outside projects",
    "describing static complexity as exact operation or credit cost",
    "opening a browser to scrape Make canvas UI errors",
    "mutating Make.com accounts or external services"
  ]
}
```
## repo.mcp.live-roundtrip-review-tool

```json strict-policy
{
  "anchor": "repo.mcp.live-roundtrip-review-tool",
  "rule": "The live Make roundtrip review tool is operator-gated, non-default, and exists only to stage reviewed live_probe evidence for knowledge-store needs_review conflicts.",
  "tool_name": "scenario.live_roundtrip.review",
  "operator_working_name": "review and decide El Desempate Seguro",
  "default_mode": "offline validation remains default; live probing never runs implicitly",
  "unattended_allowed": false,
  "idempotency": "not idempotent when a live transport is supplied; staging uses INSERT OR REPLACE evidence ids",
  "required_inputs": [
    "authorization_json with operator_approved, approved_by, credential_ref, and purpose",
    "optional conflict_id; missing conflict_id lists current needs_review conflicts",
    "returned_scenario_json and reviewed_value_json only after operator review"
  ],
  "outputs": [
    "needs_review conflict summaries",
    "minimal probe scenario plan",
    "roundtrip diff report",
    "reviewed live_probe evidence SQL path"
  ],
  "forbidden_posture": [
    "running from default validation paths",
    "requiring browser automation",
    "accepting raw API tokens in MCP tool arguments",
    "mutating SQLite directly",
    "treating unreviewed Make responses as durable truth"
  ]
}
```
## repo.mcp.required-tool-surface

```json strict-policy
{
  "anchor": "repo.mcp.required-tool-surface",
  "rule": "The MCP slice exposes only the minimal SQLite-backed tools needed by Codex/GPT.",
  "required_tools": [
    "catalog.search",
    "project.search",
    "project.health",
    "project.view",
    "project.modules.view",
    "project.modules.add",
    "project.modules.modify",
    "project.modules.delete",
    "project.links.view",
    "project.filters.view",
    "project.filters.add",
    "project.filters.modify",
    "project.filters.delete",
    "project.error_handlers.view",
    "project.error_handlers.add",
    "project.error_handlers.modify",
    "project.error_handlers.delete",
    "linter.quarantine.write",
    "linter.rule.next",
    "linter.rule.inspect",
    "linter.rule.implement",
    "linter.rule.merge_canonical",
    "linter.rule.reject_invalid",
    "linter.rule.edit",
    "linter.rule.status",
    "linter.rule.rollback",
    "backlog.add",
    "backlog.list",
    "backlog.end",
    "catalog.next_unit",
    "catalog.save_unit"
  ],
  "schema_posture": [
    "object input schemas",
    "explicit required fields",
    "no credential fields",
    "no live-service mutation by default",
    "write-like behavior is limited to explicitly named local node-editor, linter editor, and backlog tools",
    "no general technical repository operations"
  ]
}
```
## repo.mcp.linter-rule-direct-editor

```json strict-policy
{
  "anchor": "repo.mcp.linter-rule-direct-editor",
  "rule": "Linter rule implementation workers must use typed direct-editor tools rather than raw source or SQLite edits.",
  "tools": [
    "linter.rule.next",
    "linter.rule.inspect",
    "linter.rule.implement",
    "linter.rule.merge_canonical",
    "linter.rule.reject_invalid",
    "linter.rule.edit",
    "linter.rule.status",
    "linter.rule.rollback"
  ],
  "required_guards": [
    "lease token and worker id",
    "structured engineering memo",
    "AST anti-fake predicate validation",
    "pass and fail fixture evidence",
    "severity downgrade proof",
    "canonical equivalence proof",
    "invalid artifact proof",
    "SQLite snapshot invariant",
    "one-rule local repository commit",
    "no push"
  ],
  "forbidden_behavior": [
    "raw SQL tool",
    "raw file editor tool",
    "fake implementation",
    "convenience severity downgrade",
    "live Make.com call",
    "provider API call",
    "secret read",
    "push"
  ]
}
```
## repo.mcp.catalog-plan-worker-tools

```json strict-policy
{
  "anchor": "repo.mcp.catalog-plan-worker-tools",
  "rule": "Catalog semantic-worker MCP tools use SQLite only and do not expose artifact file IO.",
  "tools": [
    "catalog.next_unit",
    "catalog.save_unit"
  ],
  "retired_tool_family": "old artifact-file catalog plan tools",
  "allowed_behavior": [
    "read exactly one pending SQLite catalog unit",
    "write exactly one semantic answer or structured quarantine record",
    "return bounded local raw-spec evidence for the selected unit"
  ],
  "forbidden_behavior": [
    "artifact file tree listing",
    "artifact file reads",
    "artifact file writes",
    "generic repository inspection",
    "root TODO mutation",
    "Make.com account mutation",
    "provider API calls",
    "credential fields"
  ],
  "retirement_rule": "Keep these tools development-only and require explicit operator approval."
}
```
## repo.mcp.missing-catalog-assets-model

```json strict-policy
{
  "anchor": "repo.mcp.missing-catalog-assets-model",
  "rule": "MCP tools that report absent local Make catalog assets must share one structured missing_local_assets payload shape.",
  "required_fields": [
    "status",
    "missing_paths",
    "recommended_commands",
    "required_for_claim_level"
  ],
  "status": "missing_local_assets",
  "required_for_claim_level": "catalog_backed_import_ready",
  "required_posture": [
    "missing paths are repository-relative and deterministic",
    "recovery commands are advisory and do not run implicitly",
    "catalog.search and local project views use the same status string and field names",
    "missing local catalog assets return structured payloads instead of raw FileNotFoundError messages"
  ],
  "forbidden_posture": [
    "returning tool-specific missing-catalog status strings for the same local asset absence",
    "exposing credential requirements for offline recovery",
    "calling live Make services to repair missing local catalog assets"
  ]
}
```
## repo.mcp.transport-default-and-expansion-gate

```json strict-policy
{
  "anchor": "repo.mcp.transport-default-and-expansion-gate",
  "rule": "STDIO is the default local MCP transport; the only active HTTP transport is an explicit loopback origin for the operator-managed Cloudflare Tunnel.",
  "default_transport": "stdio",
  "remote_transport_default": "disabled unless python -B -m mcp http is launched explicitly",
  "allowed_http_origin": "http://127.0.0.1:8787",
  "required_posture": [
    "local tests must not require live networking",
    "remote transport must not appear as an accidental side effect of registry work or local inspection commands",
    "transport expansion must keep repository-local path safety and credential boundaries"
  ]
}
```
## repo.mcp.local-cli-startup-contract

```json strict-policy
{
  "anchor": "repo.mcp.local-cli-startup-contract",
  "rule": "The local MCP entrypoint exposes deterministic inspection commands only.",
  "commands": [
    "python -B -m mcp start",
    "python -B -m mcp tools",
    "python -B -m mcp http --repo-root <repo> --host 127.0.0.1 --port 8787"
  ],
  "allowed_behavior": [
    "emit JSON startup state",
    "emit JSON tool registry state",
    "report stdio test transport",
    "serve loopback HTTP only when the explicit http command is used",
    "stay usable through repository-local Python dependencies"
  ],
  "forbidden_behavior": [
    "open a network listener from the start or tools inspection commands",
    "start a credentialed tunnel",
    "execute MCP tool calls as part of startup inspection",
    "treat Cloudflared or a public domain as default validation"
  ]
}
```
## repo.mcp.remote-http-loopback-transport

```json strict-policy
{
  "anchor": "repo.mcp.remote-http-loopback-transport",
  "rule": "The remote MCP origin is an explicit loopback HTTP server intended to sit behind the operator-managed Cloudflare Tunnel.",
  "origin": "http://127.0.0.1:8787",
  "public_url": "https://019e73f6-c164-79b9-8e29-82758c7b3eaa.humbertoschoenwald.com",
  "entrypoint": "python -B -m mcp http --repo-root <repo> --host 127.0.0.1 --port 8787 --public-base-url https://019e73f6-c164-79b9-8e29-82758c7b3eaa.humbertoschoenwald.com",
  "request_body_limits": {
    "json_content_type": "application/json",
    "form_content_type": "application/x-www-form-urlencoded",
    "json_max_bytes": 1048576,
    "form_max_bytes": 65536,
    "missing_content_length_status": 411,
    "oversized_status": 413,
    "unsupported_media_type_status": 415
  },
  "allowed_behavior": [
    "serve health and OAuth discovery metadata",
    "serve MCP JSON-RPC on /mcp and accept POST / as a compatibility alias for app clients configured with the hostname root",
    "serve initialize, notifications/initialized, and tools/list before OAuth so clients can start linking and refresh action descriptors without reauthentication loops",
    "gate resources/list, prompts/list, prompts/get, resources/read, and tools/call with bearer-token validation",
    "fail resources/read closed after Markdown resource retirement",
    "enforce each tool's advertised read/write OAuth scope before tools/call execution",
    "enforce declared Content-Length and required media types before JSON or form body parsing",
    "keep per-tool oauth2 securitySchemes empty while exposing server-side authorization scope in local boundary metadata",
    "expose read-only tools and explicitly named non-destructive local scenario workspace tools",
    "bind loopback by default"
  ],
  "forbidden_behavior": [
    "binding non-loopback addresses by default",
    "starting or configuring Cloudflared from the MCP package",
    "adding destructive tools or live-service write tools to the remote surface",
    "using the remote transport to mutate live Make.com accounts"
  ]
}
```
## repo.mcp.remote-oauth-discovery

```json strict-policy
{
  "anchor": "repo.mcp.remote-oauth-discovery",
  "rule": "The loopback HTTP origin must expose OAuth protected-resource and authorization-server metadata for remote MCP clients.",
  "protected_resource_path": "/.well-known/oauth-protected-resource",
  "authorization_server_path": "/.well-known/oauth-authorization-server",
  "dynamic_client_registration_path": "/register",
  "authorization_path": "/authorize",
  "token_path": "/token",
  "client_registration_store": "Schoenwald root data/pancakes-mcp/oauth/clients.json",
  "token_store": "Schoenwald root data/pancakes-mcp/oauth/tokens.json",
  "client_registration_posture": "dynamic OAuth client registrations are persisted as ignored local runtime state so remote clients survive loopback origin restarts",
  "authorization_posture": "when REMOTE_MCP_OPERATOR_PASSWORD is configured in the service environment or repository .env, /authorize requires the local operator password before issuing an OAuth code",
  "token_posture": "authorization codes remain in-memory; bearer token hashes are persisted as ignored local runtime state so a linked MCP client survives loopback origin restarts",
  "public_health_posture": "the public root and /health routes expose only status=ok and never expose host, port, server name, transport, or public base URL metadata",
  "supported_scopes": ["mcp:read", "mcp:write"],
  "tool_scope_policy": {
    "read_only_tools": "mcp:read",
    "write_like_tools": "mcp:write"
  },
  "redirect_uri_policy": {
    "allowed_redirects": [
      "https redirects with an explicit host",
      "http redirects only when the host is localhost or a loopback IP literal",
      "the repository-approved make-mcp custom scheme"
    ],
    "rejected_redirects": [
      "empty redirect URIs",
      "relative redirect URIs",
      "wildcard redirect URIs",
      "javascript redirect URIs",
      "file redirect URIs",
      "credential-bearing redirect URIs",
      "non-loopback http redirect URIs"
    ],
    "matching_rule": "authorization and token exchange must use exact registered redirect_uri string matching"
  },
  "response_policy": {
    "json_error_fields": ["error", "error_code"],
    "token_response_headers": {
      "Cache-Control": "no-store",
      "Pragma": "no-cache"
    },
    "redaction_rule": "OAuth error bodies and MCP auth challenge results must not echo submitted authorization codes, bearer tokens, operator passwords, or private connection values",
    "mcp_auth_challenge_code": "oauth_bearer_token_required"
  },
  "required_posture": [
    "MCP JSON-RPC POST requests require bearer tokens except initialize, notifications/initialized, and tools/list",
    "requested OAuth scopes must be limited to the advertised supported MCP scope set",
    "dynamic client registration and persisted client restoration must reject unsafe redirect URI shapes before authorization codes can be issued",
    "OAuth HTTP errors must include stable error_code values without changing existing human-readable error strings",
    "token endpoint success and failure responses must use no-store and no-cache headers",
    "authorization codes and bearer token records must carry granted scopes",
    "tools/call must reject tokens that lack the called tool's advertised scope before invoking the tool",
    "persist only client ids, registered redirect URIs, issued_at timestamps, bearer token hashes, granted token scopes, and token expiry timestamps under the Schoenwald root data/pancakes-mcp/oauth namespace when the operator root is discoverable",
    "never persist authorization codes, operator passwords, OAuth client secrets, or third-party connection secrets",
    "OAuth discovery tests use ephemeral loopback servers, not the public domain",
    "the operator password must never be accepted through MCP tool arguments or committed to the repository",
    "future client secrets, refresh tokens, or multi-user auth must be ADR-backed before replacing this local operator flow"
  ]
}
```
## repo.mcp.tool-annotation-posture

```json strict-policy
{
  "anchor": "repo.mcp.tool-annotation-posture",
  "rule": "MCP tools must expose explicit safety posture instead of relying on operator guesses.",
  "current_default": "read_only",
  "required_posture": [
    "read-only tools report inspection, validation, explanation, or status only",
    "local scenario workspace tools report write_like annotations, explicit mutation naming, non-destructive hints, and tests",
    "future write-like tools outside local scenario workspaces require explicit mutation naming and tests",
    "future destructive or live-service tools require operator-gated ADR approval",
    "schemas remain closed objects with explicit fields"
  ],
  "forbidden_posture": [
    "using one mixed tool to hide write behavior behind optional flags",
    "adding credential fields to default repository MCP tools",
    "describing live-service mutation as ordinary validation"
  ]
}
```
## repo.mcp.no-hidden-llm-calls

```json strict-policy
{
  "anchor": "repo.mcp.no-hidden-llm-calls",
  "rule": "The MCP runtime must not call GPT, OpenAI, or another LLM provider behind the operator as a hidden fallback.",
  "allowed_current_posture": [
    "Codex or GPT may supply explicit reviewed artifacts through the operator/MCP boundary",
    "runtime code may validate, persist, render, or explain supplied artifacts",
    "deterministic local fallbacks may run when they do not invoke an LLM"
  ],
  "future_exception_requirement": "A future ADR must name the provider, credential boundary, artifacts, tests, and operator consent model before runtime code may call an LLM directly.",
  "forbidden_posture": [
    "treating an API key or model environment variable as authority for hidden LLM execution",
    "silently replacing missing operator review with server-side generation",
    "letting background workers impersonate GPT without an explicit supplied artifact"
  ]
}
```
## repo.mcp.ai-assisted-privacy-and-redaction-boundary

```json strict-policy
{
  "anchor": "repo.mcp.ai-assisted-privacy-and-redaction-boundary",
  "rule": "AI assistance is allowed only as an operator-directed editing and review aid after privacy, source, and secret boundaries are preserved.",
  "allowed_assistance_surfaces": [
    "ChatGPT.com or equivalent operator-directed client with account privacy controls enabled when available",
    "repository MCP tools that operate on local draft artifacts and deterministic validation output",
    "AST, diff, and schema summaries generated from repository-owned code or sanitized artifacts"
  ],
  "normal_input_posture": [
    "prefer project context indexes, semantic summaries, validation findings, DAMP tests, and targeted JSON paths over raw blueprint dumps",
    "redact secrets, webhook URLs, account ids, emails, customer identifiers, and private payload values before any external model-assisted review",
    "keep real client source, logs, execution history, screenshots, and provider payloads outside AI prompts unless a separate reviewed exception authorizes that processing",
    "treat raw Make blueprint JSON as local evidence for narrow debugging, not the normal AI prompt surface"
  ],
  "manual_json_exception": {
    "allowed": "narrow local JSON slices may be inspected or fine-tuned manually when semantic tools cannot express the repair",
    "required_controls": [
      "intake and redaction gates have already passed or the data is synthetic",
      "only the minimum relevant JSON path or line window is used",
      "the final change is validated by deterministic repository tests",
      "client-facing delivery remains scrubbed and zero-trace checked"
    ]
  },
  "public_claim_boundary": [
    "do not claim local-only handling when ChatGPT.com, email, hosted storage, or another vendor has received data",
    "do not claim compliance, certification, no-training status, or privacy guarantees without current legal and vendor review",
    "public copy about AI assistance, privacy options, or redaction requires legal review before publication"
  ],
  "forbidden_posture": [
    "sending raw customer Make blueprint JSON to an external AI provider as the normal path",
    "sending secrets, credentials, cookies, tokens, webhook secrets, or private provider payloads to AI",
    "using AI output as a substitute for repository validation, importability checks, or human legal review",
    "letting public product copy imply that all processing is local when model-assisted review is used"
  ]
}
```
## repo.mcp.legacy-remote-and-profiling-scripts-retired

```json strict-policy
{
  "anchor": "repo.mcp.legacy-remote-and-profiling-scripts-retired",
  "rule": "Old remote MCP sampling and profiling scripts are retired; the active MCP slice stays local, typed, and test-backed until a future ADR introduces a live remote surface.",
  "current_validation_surface": ["src/mcp/**/*", "tests/mcp/tool_contracts/mcp_server_contract.py"],
  "required_posture": [
    "default MCP validation uses in-process test startup",
    "remote sampling requires explicit credentialed operator approval in a future task",
    "performance profiling must target current tools and repository-local artifacts"
  ],
  "forbidden_posture": [
    "keeping live OAuth or SSE samplers as generic scripts",
    "profiling retired tool names or old performance artifact shapes",
    "using scripts to bypass MCP ADR tool-surface review"
  ]
}
```
## repo.mcp.no-obsolete-domain-tools

```json strict-policy
{
  "anchor": "repo.mcp.no-obsolete-domain-tools",
  "rule": "MCP tool names, descriptions, and schemas must not mention obsolete Axiom-era or out-of-scope domains.",
  "forbidden_terms": [
    "Axiom",
    "GraphRAG",
    "TigerGraph",
    "Nerve",
    "dataset",
    "Notion",
    "Life Engine",
    "backup"
  ]
}
```
## Rationale

This ADR preserves the accepted repository decision while moving the Pancakes documentation canon
from numbered ADR records to flat, unnumbered common Markdown ADRs.

## Consequences

- The MCP slice has a typed repository registry before any live transport is
added.
- Future work can bind these schemas to a real MCP SDK server after tests keep
the name, tools, and obsolete-domain guardrails stable.

## Validation

- The migrated ADR must be readable as normal Markdown.
- The migrated filename must be flat, unnumbered, lowercase, and descriptive under `docs/adr/`.
- Repository validation or focused documentation checks must report any remaining blockers.

## Related Material

- Former ADR ID: `001055`.
- Decision ID: `repo.mcp.server-slice-policy`.
- Previous authority level: `policy`.
- Previous numeric filename was removed during the common Markdown ADR migration.

<details>
<summary>Former metadata retained during migration</summary>

```yaml
alwaysApply: true
adr_id: '001055'
decision_id: 'repo.mcp.server-slice-policy'
title: 'MCP Server Slice Policy'
status: 'ACTIVE'
authority_level: 'policy'
decision_type:
  - architecture
  - testing
  - documentation
scope: 'repository/mcp-server'
applies_to:
  - src/mcp/README.md
  - src/mcp/**/*
  - tests/mcp/tool_contracts/mcp_server_contract.py
  - tests/mcp/tool_contracts/mcp_http_contract.py
  - tests/mcp/tool_contracts/mcp_http_body_limits_contract.py
  - tests/mcp/tool_contracts/mcp_oauth_http_contract.py
  - tests/mcp/tool_contracts/mcp_oauth_redirect_uri_contract.py
  - tests/mcp/tool_contracts/mcp_oauth_scope_enforcement_contract.py
  - tests/mcp/tool_contracts/mcp_diff_blueprint_command_contract.py
  - tests/mcp/tool_contracts/mcp_missing_catalog_assets_model_contract.py
  - docs/bibliography/model-context-protocol.md
  - docs/bibliography/oauth-2.md
applies_when:
  - repository_mcp_surface_is_started
  - codex_or_gpt_uses_repository_tools
profiles:
  - base
  - make
supersedes: []
superseded_by: []
depends_on:
  - '001035'
  - '001040'
  - '001044'
  - '001046'
  - '001049'
source_material:
  - path: 'Refactor/docs/adr/0002-mcp-stdio-transport-for-v1.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/adr/0047-chatgpt-mcp-exclusive-llm-authority.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/adr/0055-compact-chatgpt-bootstrap-and-per-turn-operator-context-tool.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/docs/mcp_operating_protocol.md'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/check_mcp_performance_reports.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/profile_mcp_integrated_baseline.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/sample_remote_mcp_tool_surface.py'
    usage: source reference
    copied_verbatim: false
  - path: 'Refactor/scripts/verify_codex_mcp.py'
    usage: source reference
    copied_verbatim: false
derived_artifacts:
  - src/mcp/README.md
  - src/mcp/**/*
  - tests/mcp/tool_contracts/mcp_server_contract.py
  - tests/mcp/tool_contracts/mcp_http_contract.py
  - tests/mcp/tool_contracts/mcp_http_body_limits_contract.py
  - tests/mcp/tool_contracts/mcp_oauth_http_contract.py
  - tests/mcp/tool_contracts/mcp_oauth_redirect_uri_contract.py
  - tests/mcp/tool_contracts/mcp_oauth_scope_enforcement_contract.py
  - tests/mcp/tool_contracts/mcp_diff_blueprint_command_contract.py
  - tests/mcp/tool_contracts/mcp_missing_catalog_assets_model_contract.py
bibliography_refs:
  - 'https://modelcontextprotocol.io/'
  - 'https://www.rfc-editor.org/rfc/rfc6749'
  - 'https://www.rfc-editor.org/rfc/rfc6750'
  - 'https://www.rfc-editor.org/rfc/rfc8252'
traceability_anchors:
  - repo.mcp.server-identity
  - repo.mcp.make-scenario-tool-scope
  - repo.mcp.scenario-builder-micro-tools
  - repo.mcp.live-roundtrip-review-tool
  - repo.mcp.required-tool-surface
  - repo.mcp.temporary-catalog-plan-devtools
  - repo.mcp.missing-catalog-assets-model
  - repo.mcp.transport-default-and-expansion-gate
  - repo.mcp.local-cli-startup-contract
  - repo.mcp.tool-annotation-posture
  - repo.mcp.no-hidden-llm-calls
  - repo.mcp.remote-http-loopback-transport
  - repo.mcp.remote-oauth-discovery
  - repo.mcp.ai-assisted-privacy-and-redaction-boundary
  - repo.mcp.legacy-remote-and-profiling-scripts-retired
  - repo.mcp.no-obsolete-domain-tools
non_goals:
  - expose graph/RAG, TigerGraph, Nerve, generic dataset, Notion, Life Engine, or backup tools
  - expose generic technical repository operations as MCP tools
  - start a live network service in tests
  - use Axiom-era names
  - mutate live Make.com accounts or external services
```
</details>
