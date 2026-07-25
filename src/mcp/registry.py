# ruff: noqa: ERA001
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001055#repo.mcp.no-obsolete-domain-tools
# - docs/adr/catalog-semantic-graph-preview-policy.md
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Central public MCP tool registry with stable descriptions and input
# contracts.
# split: Move catalog, project, and linter tool families into registry modules.
# validation: pancakes.mcp.smoke and focused MCP tool contract tests.
# review: Operator-requested Catalog Intelligence lease-handle safety update.

"""MCP tool registry for the minimal public Pancakes surface.

Boundary contract:
- Owns: the active public MCP tool names and minimal input schemas.
- Must not: execute tools, inspect local files, parse intents, or manage
servers.
- Allows: deterministic tool definitions, safety posture, and required ordering.
- Split when: registry needs transport variants or write-capable tool groups.
- Merge when: another registry defines the same active MCP tool surface.
"""

from __future__ import annotations

from typing import Final

from mcp.annotations import public_tool_annotation_specs
from mcp.linter_rule_editor_contracts import (
    LINTER_RULE_EDIT_TOOL,
    LINTER_RULE_IMPLEMENT_TOOL,
    LINTER_RULE_INSPECT_TOOL,
    LINTER_RULE_MERGE_CANONICAL_TOOL,
    LINTER_RULE_NEXT_TOOL,
    LINTER_RULE_REJECT_INVALID_TOOL,
    LINTER_RULE_ROLLBACK_TOOL,
    LINTER_RULE_STATUS_TOOL,
)
from mcp.models import (
    JsonSchemaType,
    McpInputField,
    McpToolAnnotations,
    McpToolDefinition,
)
from mcp.session import MCP_SESSION_START_TOOL

REQUIRED_TOOL_NAMES: Final[tuple[str, ...]] = (
    MCP_SESSION_START_TOOL,
    "catalog.index ",
    "catalog.search ",
    "catalog.inspect ",
    "catalog.graph.search ",
    "catalog.semantic.preview ",
    "catalog.work.next ",
    "catalog.work.save ",
    "catalog.modify ",
    "catalog.node.modify ",
    "catalog.edge.propose ",
    "catalog.edge.apply ",
    "catalog.review.add ",
    "project.search ",
    "project.draft.stage ",
    "project.draft.import ",
    "project.create ",
    "project.health ",
    "project.view ",
    "project.edit ",
    "project.verify ",
    "project.capabilities.inspect ",
    "project.make ",
    "project.package.inspect ",
    "project.next ",
    "project.modules.view ",
    "project.modules.add ",
    "project.modules.modify ",
    "project.modules.delete ",
    "project.links.view ",
    "project.filters.view ",
    "project.filters.add ",
    "project.filters.modify ",
    "project.filters.delete ",
    "project.error_handlers.view ",
    "project.error_handlers.add ",
    "project.error_handlers.modify ",
    "project.error_handlers.delete ",
    "documentation.generate ",
    "documentation.validate ",
    "onboarding.validate ",
    "linter.quarantine.write",
    LINTER_RULE_NEXT_TOOL,
    LINTER_RULE_INSPECT_TOOL,
    LINTER_RULE_IMPLEMENT_TOOL,
    LINTER_RULE_MERGE_CANONICAL_TOOL,
    LINTER_RULE_REJECT_INVALID_TOOL,
    LINTER_RULE_EDIT_TOOL,
    LINTER_RULE_STATUS_TOOL,
    LINTER_RULE_ROLLBACK_TOOL,
    "backlog.add ",
    "backlog.list ",
    "backlog.end",
)


def _field(
    name: str,
    schema_type: JsonSchemaType,
    description: str,
    *,
    required: bool = False,
) -> McpInputField:
    """Return one compact MCP input field."""
    return McpInputField(
        name=name,
        schema_type=schema_type,
        description=description,
        required=required,
    )


def mcp_tool_registry() -> tuple[McpToolDefinition, ...]:
    """Return the public Pancakes local MCP tool registry."""
    annotations = public_tool_annotation_specs()
    tool_map = {
        tool.name: tool
        for tool in (
            _catalog_index(annotations),
            _catalog_search(annotations),
            _catalog_inspect(annotations),
            _catalog_graph_search(annotations),
            _catalog_semantic_preview(annotations),
            _catalog_work_next(annotations),
            _catalog_work_save(annotations),
            _catalog_modify(annotations),
            _catalog_node_modify(annotations),
            _catalog_edge_propose(annotations),
            _catalog_edge_apply(annotations),
            _catalog_review_add(annotations),
            _mcp_session_start(annotations),
            _project_search(annotations),
            _project_draft_stage(annotations),
            _project_draft_import(annotations),
            _project_create(annotations),
            _project_health(annotations),
            _project_view(annotations),
            _project_edit(annotations),
            _project_verify(annotations),
            _project_capabilities_inspect(annotations),
            _project_make(annotations),
            _project_package_inspect(annotations),
            _project_next(annotations),
            _project_modules_view(annotations),
            _project_modules_add(annotations),
            _project_modules_modify(annotations),
            _project_modules_delete(annotations),
            _project_links_view(annotations),
            _project_filters_view(annotations),
            _project_filters_add(annotations),
            _project_filters_modify(annotations),
            _project_filters_delete(annotations),
            _project_error_handlers_view(annotations),
            _project_error_handlers_add(annotations),
            _project_error_handlers_modify(annotations),
            _project_error_handlers_delete(annotations),
            _documentation_generate(annotations),
            _documentation_validate(annotations),
            _onboarding_validate(annotations),
            _linter_quarantine_write(annotations),
            _linter_rule_next(annotations),
            _linter_rule_inspect(annotations),
            _linter_rule_implement(annotations),
            _linter_rule_merge_canonical(annotations),
            _linter_rule_reject_invalid(annotations),
            _linter_rule_edit(annotations),
            _linter_rule_status(annotations),
            _linter_rule_rollback(annotations),
            _backlog_add(annotations),
            _backlog_list(annotations),
            _backlog_end(annotations),
        )
    }
    return tuple(tool_map[name] for name in REQUIRED_TOOL_NAMES)


def _mcp_session_start(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=MCP_SESSION_START_TOOL,
        description=(
            "Create a process-local session intent receipt for typed local "
            "Make scenario "
            "work. Read-only local control metadata: no file writes, no "
            "SQLite writes, no "
            "provider calls, no live Make calls, and no credential values."
        ),
        input_fields=(
            _field(
                "operator_intent ",
                "string ",
                "Bounded local session intent.",
                required=True,
            ),
            _field(
                "worker_id ",
                "string ",
                "Stable local worker identifier.",
                required=True,
            ),
            _field(
                "allowed_local_write_surfaces ",
                "object ",
                "Optional JSON object naming typed local write surfaces.",
            ),
            _field(
                "approved_scope ",
                "object ",
                "Optional local scope metadata object.",
            ),
            _field(
                "expires_at", "string", "Optional ISO-8601 expiration time."
            ),
            _field(
                "session_intent_id ",
                "string ",
                "Optional caller-provided stable id.",
            ),
        ),
        output_description=(
            "Local session intent receipt and no-provider safety posture."
        ),
        read_only=True,
        annotations=annotations[MCP_SESSION_START_TOOL],
    )


def _catalog_index(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.index",
        description=(
            "Return the canonical placeholder and finite value indexes for "
            "Catalog "
            "Intelligence. Read-only, local-only, no provider API call, no "
            "cursor movement."
        ),
        input_fields=(
            _field(
                "query ",
                "string ",
                "Optional example text to map to canonical placeholders.",
            ),
        ),
        output_description=(
            "Canonical placeholder rows, value-index rows, placeholder "
            "matches, and "
            "deterministic replacement spans for example text such as John "
            "Doe or +55 55555."
        ),
        read_only=True,
        annotations=annotations["catalog.index"],
    )


def _catalog_search(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.search",
        description=(
            "Search the Pancakes Core SQLite SSOT for exact modules, "
            "semantic catalog "
            "intelligence, datastore and webhook evidence gaps. "
            "Read-only, local-only, no provider API call, no cursor movement."
        ),
        input_fields=(
            _field(
                "query ",
                "string ",
                "Bounded local catalog search text.",
                required=True,
            ),
            _field(
                "limit ",
                "integer ",
                "Optional compact result limit from 1 through 20.",
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact, micro, or outline.",
            ),
        ),
        output_description=(
            "Bounded local catalog hits ordered by exact matches, semantic "
            "candidates, "
            "structure prerequisites, and missing evidence."
        ),
        read_only=True,
        annotations=annotations["catalog.search"],
    )


def _catalog_inspect(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.inspect",
        description=(
            "Inspect one module, catalog document, or catalog work unit "
            "from the "
            "Pancakes Core SQLite SSOT. Read-only, bounded, local-only, and no "
            "provider API call."
        ),
        input_fields=(
            _field("module_id", "string", "Exact module id to inspect."),
            _field(
                "document_id ",
                "string ",
                "Exact catalog search document id to inspect.",
            ),
            _field("unit_id", "string", "Catalog work unit id to inspect."),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact, full, or debug.",
            ),
        ),
        output_description=(
            "Bounded catalog entity details and evidence posture."
        ),
        read_only=True,
        annotations=annotations["catalog.inspect"],
    )


def _catalog_graph_search(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.graph.search",
        description=(
            "Search and expand the local Pancakes SQLite catalog graph, "
            "saved semantic "
            "outputs, and search documents. Read-only, compact by default, "
            "local-only, "
            "no provider API call, no live Make.com call, and no cursor "
            "movement."
        ),
        input_fields=(
            _field(
                "query", "string", "Optional graph or semantic search text."
            ),
            _field("node_id", "string", "Optional exact node id to expand."),
            _field("edge_id", "string", "Optional exact edge id to expand."),
            _field(
                "unit_id", "string", "Optional exact saved unit id to expand."
            ),
            _field(
                "limit ",
                "integer ",
                "Optional compact result limit from 1 through 50.",
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact, full, or debug.",
            ),
        ),
        output_description=(
            "Compact graph overview, graph node and edge matches, semantic "
            "output matches, "
            "and requested node/edge/unit expansion."
        ),
        read_only=True,
        annotations=annotations["catalog.graph.search"],
    )


def _catalog_semantic_preview(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.semantic.preview",
        description=(
            "Preview proposed catalog.work.save semantic graph outputs "
            "against the local "
            "SQLite graph and value index before saving. Read-only, "
            "local-only, no provider "
            "API call, no live Make.com call, and no credential transfer."
        ),
        input_fields=(
            _field(
                "unit_id ",
                "string ",
                "Single unit id when previewing answer_json.",
            ),
            _field(
                "answer_json ",
                "object ",
                "Semantic output object for one proposed unit.",
            ),
            _field(
                "answers_json ",
                "object ",
                "Batch preview object with a units array.",
            ),
            _field(
                "query ",
                "string ",
                "Optional query to preview against proposed graph output.",
            ),
            _field(
                "preview_queries ",
                "object",
                (
                    "Optional object with a queries array for compact "
                    "search-preview checks."
                ),
            ),
            _field(
                "limit ",
                "integer ",
                "Optional compact result limit from 1 through 50.",
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact, full, or debug.",
            ),
        ),
        output_description=(
            "Validation errors, graph density, disconnected edges, "
            "inferred/source-backed "
            "counts, and compact query previews before a catalog.work.save "
            "call."
        ),
        read_only=True,
        annotations=annotations["catalog.semantic.preview"],
    )


def _catalog_work_next(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.work.next",
        description=(
            "Lease the next source-backed semantic catalog work batch from "
            "an active "
            "Pancakes Core SQLite SSOT run. Local-only, no provider API "
            "call, no live "
            "Make.com state, no credential values, and no implicit run "
            "initialization."
        ),
        input_fields=(
            _field(
                "worker_id ",
                "string ",
                "Stable local catalog worker identifier.",
                required=True,
            ),
            _field(
                "payload_budget_bytes ",
                "integer ",
                "Optional bounded payload budget in bytes.",
            ),
            _field(
                "source_packet_mode ",
                "string",
                (
                    "Optional source packet mode: summary by default, or "
                    "complete for local debugging."
                ),
            ),
            _field(
                "initialize_if_missing ",
                "boolean",
                (
                    "Explicitly create a new empty catalog worker run when no "
                    "active run exists."
                ),
            ),
        ),
        output_description=(
            "Lease handle, selected source-backed catalog units, prompt "
            "payload budget, "
            "and semantic worker progress counters."
        ),
        read_only=False,
        annotations=annotations["catalog.work.next"],
    )


def _catalog_work_save(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.work.save",
        description=(
            "Save one leased semantic catalog work batch after local "
            "validation. "
            "Local-only, no raw SQL mutation surface, no providers, no live "
            "Make.com "
            "state, and no credential values."
        ),
        input_fields=(
            _field(
                "worker_id ",
                "string ",
                "Stable local catalog worker identifier.",
                required=True,
            ),
            _field(
                "lease_handle ",
                "string ",
                "Lease handle returned by catalog.work.next.",
                required=True,
            ),
            _field(
                "unit_id ",
                "string ",
                "Single leased unit id when saving one unit.",
            ),
            _field(
                "answer_json ",
                "object ",
                "Validated semantic output object for one leased unit.",
            ),
            _field(
                "answers_json ",
                "object ",
                "Batch save object with a non-empty units array.",
            ),
        ),
        output_description=(
            "Save receipt with saved unit ids, next queued unit id, and "
            "semantic worker "
            "progress counters."
        ),
        read_only=False,
        annotations=annotations["catalog.work.save"],
    )


def _project_search(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.search",
        description=(
            "Search repository-local Make scenario drafts, fixtures, and "
            "template artifacts. "
            "Local-only, read-only, no provider API call, and no external "
            "business database read."
        ),
        input_fields=(
            _field(
                "query ",
                "string",
                (
                    "Optional text matched against local project ids, display "
                    "names, and paths."
                ),
            ),
            _field(
                "limit ",
                "integer ",
                "Optional compact result limit from 1 through 100.",
            ),
            _field(
                "project_kind ",
                "string",
                (
                    "Optional project kind filter: local_scenario_project, "
                    "fixture_project, "
                    "template_library, deleted_or_archived_project, or "
                    "invalid_project_artifact."
                ),
            ),
            _field(
                "include_templates ",
                "boolean ",
                "Include local template_library artifacts; hidden by default.",
            ),
        ),
        output_description=(
            "Bounded local technical project artifact rows, counts, and "
            "safety flags."
        ),
        read_only=True,
        annotations=annotations["project.search"],
    )


def _project_draft_stage(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.draft.stage",
        description=(
            "Stage a deterministic local Make scenario draft from a short "
            "workflow summary. "
            "`dry_run=true` validates and returns the local draft path and "
            "hash without writing; "
            "non-dry-run writes only one JSON intake file under the "
            "approved local sandbox."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "scenario_summary ",
                "string",
                (
                    "Short neutral workflow summary; do not include literal "
                    "endpoints "
                    "or private values."
                ),
                required=True,
            ),
            _field("name", "string", "Optional local scenario name."),
            _field(
                "staged_draft_file_name ",
                "string ",
                "Optional safe JSON file name under the local intake sandbox.",
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description=(
            "Local staged-draft path, hash, scrub status, and import nextsteps."
        ),
        read_only=False,
        annotations=annotations["project.draft.stage"],
    )


def _project_draft_import(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.draft.import",
        description=(
            "Stage an existing local JSON artifact after a deterministic "
            "local scan. "
            "`dry_run=true` validates and returns the staged path and hash "
            "without writing; "
            "non-dry-run writes only one JSON intake file under the "
            "approved local sandbox."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "source_artifact_path ",
                "string",
                (
                    "Approved local relative JSON artifact path under "
                    "project-intake "
                    "or projects."
                ),
                required=True,
            ),
            _field(
                "source_artifact_sha256 ",
                "string ",
                "Optional SHA-256 guard for the source artifact.",
            ),
            _field(
                "staged_draft_file_name ",
                "string ",
                "Optional safe JSON file name under the local intake sandbox.",
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description=(
            "Local staged-draft path, hash, scrub status, and import nextsteps."
        ),
        read_only=False,
        annotations=annotations["project.draft.import"],
    )


def _project_create(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.create",
        description=(
            "Dry-run or create one repository-local Make scenario draft "
            "under approved "
            "local artifact roots. This writes only local Pancakes "
            "technical artifacts."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field("name", "string", "Optional local scenario name."),
            _field(
                "staged_draft_path ",
                "string",
                (
                    "Optional repo/workspace-relative path to a staged "
                    "local JSON draft. "
                    "Pass only this path for imported drafts."
                ),
            ),
            _field(
                "staged_draft_sha256 ",
                "string ",
                "Optional SHA-256 guard for the staged local JSON draft.",
            ),
            _field(
                "workspace_number ",
                "string ",
                "Optional local workspace folder key; defaults to local-demo.",
            ),
            _field(
                "workspace_key ",
                "string ",
                "Optional local workspace key alias for workspace_number.",
            ),
            _field(
                "workspace_folder_key ",
                "string ",
                "Optional explicit generated project folder workspace key.",
            ),
            _field(
                "scenario_number ",
                "string ",
                "Optional scenario folder key; defaults to 0001.",
            ),
            _field(
                "product_number ",
                "string",
                (
                    "Optional product folder key when the artifact is "
                    "product-scoped."
                ),
            ),
            _field(
                "scenario_or_product_number ",
                "string ",
                "Optional shared scenario/product folder key alias.",
            ),
            _field(
                "scenario_or_product_key ",
                "string",
                (
                    "Optional explicit generated project folder "
                    "scenario/product key."
                ),
            ),
            _field(
                "project_slug ",
                "string",
                (
                    "Optional safe folder slug appended after the "
                    "scenario/product key."
                ),
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Local project creation preview or write receipt.",
        read_only=False,
        annotations=annotations["project.create"],
    )


def _project_health(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.health",
        description=(
            "Summarize a local Make scenario project health view. "
            "Local-only, read-only, "
            "and limited to technical graph, readiness, and package evidence."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact or full.",
            ),
        ),
        output_description=(
            "Compact local project health, blockers, and graph summary."
        ),
        read_only=True,
        annotations=annotations["project.health"],
    )


def _project_view(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.view",
        description=(
            "View a bounded local Make scenario project graph. This tool "
            "reads no external "
            "business, billing, delivery, provider, or web dashboard data."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
            ),
            _field(
                "surface ",
                "string",
                (
                    "Optional surface: overview, graph, modules, links, "
                    "filters, runtime, "
                    "datastores, notes, readiness, parity, issues, lineage, "
                    "layout, or raw."
                ),
            ),
            _field(
                "output_mode ",
                "string",
                (
                    "Optional output mode: micro, compact, outline, full, or "
                    "debug."
                ),
            ),
            _field("node_id", "string", "Optional node focus."),
            _field("module_id", "string", "Optional module focus alias."),
            _field("module", "string", "Optional module token focus."),
            _field("app_slug", "string", "Optional app slug focus."),
            _field("field_ref", "string", "Optional field reference focus."),
            _field("route_index", "integer", "Optional route focus."),
            _field("limit", "integer", "Optional compact limit."),
        ),
        output_description=(
            "Bounded IDE surface over local modules, links, filters, "
            "runtime, notes, "
            "and readiness."
        ),
        read_only=True,
        annotations=annotations["project.view"],
    )


def _project_edit(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.edit",
        description=(
            "Semantic local editor for modules, filters, error handlers, "
            "and notes. It wraps "
            "the narrow node tools and is the normal edit surface instead "
            "of raw JSON walls."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "surface ",
                "string ",
                "modules, filters, error_handlers, datastores, or notes.",
                required=True,
            ),
            _field(
                "operation ",
                "string ",
                "add, modify, delete, or generate_missing for notes.",
                required=True,
            ),
            _field(
                "target ",
                "object",
                (
                    "Optional target object with node_id, route_index, or "
                    "handler_index."
                ),
            ),
            _field(
                "payload_json ",
                "string ",
                "Optional JSON object payload or merge patch.",
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
            _field("confirm", "boolean", "Required true for module deletion."),
            _field(
                "confirm_node_id ",
                "string ",
                "Required for filter/error-handler deletion.",
            ),
        ),
        output_description="Semantic edit preview or write receipt.",
        read_only=False,
        annotations=annotations["project.edit"],
    )


def _project_verify(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.verify",
        description=(
            "Run deterministic local verification profiles for a project. "
            "import_test is "
            "offline projection only; remote workspace execution is outside "
            "this tool."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "profile ",
                "string",
                (
                    "local_structure, import_test, handoff_test, "
                    "parity_fixture, "
                    "live_preflight, runtime_setup, zero_trace, field_test, "
                    "build_test, "
                    "or catalog_test. Invalid values return valid profiles "
                    "and next tools."
                ),
            ),
            _field("output_mode", "string", "Optional output mode."),
        ),
        output_description="Local verification findings and surface statuses.",
        read_only=True,
        annotations=annotations["project.verify"],
    )


def _project_capabilities_inspect(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.capabilities.inspect",
        description=(
            "Inspect detailed local Make.com MCP capability maps that "
            "compact project.verify "
            "responses intentionally omit. Read-only and local-only."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Optional safe repository-local project id.",
            ),
            _field("profile", "string", "Optional verify profile context."),
            _field(
                "capability ",
                "string ",
                "Optional single Make.com MCP capability id.",
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact, full, or debug.",
            ),
        ),
        output_description=(
            "Local Make.com MCP capability summary or detailed matrix."
        ),
        read_only=True,
        annotations=annotations["project.capabilities.inspect"],
    )


def _project_make(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.make",
        description=(
            "Preview, render, locally write, or package a Make-native "
            "artifact projection "
            "from the local project graph. Package output is an offline "
            "local handoff "
            "artifact for a separately gated workspace layer."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field("action", "string", "preview, render, write, or package."),
            _field(
                "profile ",
                "string",
                (
                    "import_test, client_handoff, parity_fixture, or "
                    "live_preflight."
                ),
            ),
            _field("output_mode", "string", "Optional output mode."),
            _field(
                "include_blueprint_json ",
                "boolean ",
                "Include raw artifact JSON only in full/debug output.",
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description=(
            "Make-native local artifact preview or write receipt."
        ),
        read_only=False,
        annotations=annotations["project.make"],
    )


def _project_package_inspect(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.package.inspect",
        description=(
            "Inspect one bounded package section instead of returning a "
            "large package payload. "
            "Sections include live_resources, blueprint_summary, parity_plan, "
            "customer_files, and zero_trace."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "profile ",
                "string",
                (
                    "import_test, client_handoff, parity_fixture, or "
                    "live_preflight."
                ),
            ),
            _field(
                "section ",
                "string",
                (
                    "live_resources, blueprint_summary, parity_plan, "
                    "customer_files, "
                    "or zero_trace."
                ),
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact, full, or debug.",
            ),
        ),
        output_description=(
            "One bounded local package section without raw blueprint JSON."
        ),
        read_only=True,
        annotations=annotations["project.package.inspect"],
    )


def _project_next(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.next",
        description=(
            "Return the next deterministic local IDE action or plan for a "
            "project based on "
            "graph health, runtime setup posture, and local readiness."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field("mode", "string", "one or plan."),
            _field(
                "profile", "string", "Optional verification profile context."
            ),
            _field("output_mode", "string", "Optional output mode."),
        ),
        output_description="Next local MCP action and bounded plan.",
        read_only=True,
        annotations=annotations["project.next"],
    )


def _project_modules_view(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.modules.view",
        description="Compatibility wrapper over project.view surface=modules.",
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
            ),
            _field("module_id", "integer", "Optional module id filter."),
            _field("output_mode", "string", "Optional output mode."),
            _field("limit", "integer", "Optional compact module limit."),
        ),
        output_description="Local project module summaries and graph links.",
        read_only=True,
        annotations=annotations["project.modules.view"],
    )


def _project_modules_add(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.modules.add",
        description=(
            "Dry-run or write one repository-local Make module node only."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "module_json ",
                "string ",
                "JSON object for one module node.",
                required=True,
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Module insertion preview or write receipt.",
        read_only=False,
        annotations=annotations["project.modules.add"],
    )


def _project_modules_modify(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.modules.modify",
        description=(
            "Dry-run or modify one repository-local Make module node only."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "module_id ",
                "integer ",
                "Existing local module id.",
                required=True,
            ),
            _field(
                "patch_json ",
                "string ",
                "JSON object patch for the module.",
                required=True,
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Module update preview or write receipt.",
        read_only=False,
        annotations=annotations["project.modules.modify"],
    )


def _project_modules_delete(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.modules.delete",
        description=(
            "Preview one repository-local Make module removal without writing."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "module_id ",
                "integer ",
                "Existing local module id.",
                required=True,
            ),
            _field(
                "dry_run ",
                "boolean ",
                "Accepted for compatibility; this preview never writes.",
            ),
        ),
        output_description="Module removal preview.",
        read_only=True,
        annotations=annotations["project.modules.delete"],
    )


def _project_links_view(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.links.view",
        description="Compatibility wrapper over project.view surface=links.",
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field("module_id", "integer", "Optional module id focus."),
            _field("node_id", "string", "Optional node id focus."),
            _field("output_mode", "string", "Optional output mode."),
            _field("limit", "integer", "Optional compact link limit."),
        ),
        output_description="Derived local project graph links.",
        read_only=True,
        annotations=annotations["project.links.view"],
    )


def _project_filters_view(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.filters.view",
        description="Compatibility wrapper over project.view surface=filters.",
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field("route_id", "string", "Optional route identifier."),
            _field("route_index", "integer", "Optional route focus."),
            _field("node_id", "string", "Optional node focus."),
            _field("output_mode", "string", "Optional output mode."),
            _field("limit", "integer", "Optional compact filter limit."),
        ),
        output_description="Route filter summaries.",
        read_only=True,
        annotations=annotations["project.filters.view"],
    )


def _project_filters_add(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.filters.add",
        description=(
            "Dry-run or write one repository-local Make route filter only."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "node_id ",
                "string",
                (
                    "Target router module id; may also be supplied as "
                    "filter_json.node_id."
                ),
            ),
            _field(
                "route_index", "integer", "Target route index; defaults to 0."
            ),
            _field(
                "filter_json ",
                "string",
                (
                    "Filter JSON object, or envelope with node_id, "
                    "route_index, "
                    ""
                    "and filter."
                ),
                required=True,
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Filter insertion preview or write receipt.",
        read_only=False,
        annotations=annotations["project.filters.add"],
    )


def _project_filters_modify(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.filters.modify",
        description=(
            "Dry-run or modify one repository-local Make route filter only."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "node_id ",
                "string",
                (
                    "Target router module id; may also be supplied as "
                    "patch_json.node_id."
                ),
            ),
            _field(
                "route_index", "integer", "Target route index; defaults to 0."
            ),
            _field(
                "patch_json ",
                "string",
                (
                    "Filter patch object, or envelope with node_id, "
                    "route_index, and patch."
                ),
                required=True,
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Filter update preview or write receipt.",
        read_only=False,
        annotations=annotations["project.filters.modify"],
    )


def _project_filters_delete(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.filters.delete",
        description=(
            "Preview one repository-local Make route filter removal without "
            "writing."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "node_id", "string", "Target router module id.", required=True
            ),
            _field(
                "route_index", "integer", "Target route index; defaults to 0."
            ),
            _field(
                "dry_run ",
                "boolean ",
                "Accepted for compatibility; this preview never writes.",
            ),
        ),
        output_description="Filter removal preview.",
        read_only=True,
        annotations=annotations["project.filters.delete"],
    )


def _project_error_handlers_view(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.error_handlers.view",
        description=(
            "Compatibility wrapper over project.view surface=error_handlers."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field("module_id", "integer", "Optional parent module id."),
            _field("node_id", "string", "Optional parent node id."),
            _field("output_mode", "string", "Optional output mode."),
            _field("limit", "integer", "Optional compact error-handler limit."),
        ),
        output_description="Local error-handler summaries.",
        read_only=True,
        annotations=annotations["project.error_handlers.view"],
    )


def _project_error_handlers_add(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.error_handlers.add",
        description=(
            "Dry-run or write one repository-local Make error-handler "
            "container "
            "only."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "parent_node_id ",
                "string",
                (
                    "Parent module id; may also be supplied as "
                    "handler_json.parent_node_id."
                ),
            ),
            _field(
                "node_id", "string", "Compatibility alias for parent_node_id."
            ),
            _field(
                "handler_json ",
                "string",
                (
                    "Handler JSON object, or envelope with parent_node_id and "
                    "handler."
                ),
                required=True,
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Error-handler insertion preview or write receipt.",
        read_only=False,
        annotations=annotations["project.error_handlers.add"],
    )


def _project_error_handlers_modify(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.error_handlers.modify",
        description=(
            "Dry-run or modify one repository-local Make error-handler "
            "container only."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "parent_node_id ",
                "string",
                (
                    "Parent module id; may also be supplied as "
                    "patch_json.parent_node_id."
                ),
            ),
            _field(
                "node_id", "string", "Compatibility alias for parent_node_id."
            ),
            _field(
                "handler_index ",
                "integer ",
                "Target error-handler index; defaults to 0.",
            ),
            _field(
                "patch_json ",
                "string",
                (
                    "Handler patch object, or envelope with parent_node_id, "
                    "handler_index, and patch."
                ),
                required=True,
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Error-handler update preview or write receipt.",
        read_only=False,
        annotations=annotations["project.error_handlers.modify"],
    )


def _project_error_handlers_delete(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="project.error_handlers.delete",
        description=(
            "Preview one repository-local Make error-handler removal without "
            "writing."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "parent_node_id", "string", "Parent module id.", required=True
            ),
            _field(
                "node_id", "string", "Compatibility alias for parent_node_id."
            ),
            _field(
                "handler_index ",
                "integer ",
                "Target error-handler index; defaults to 0.",
            ),
            _field(
                "dry_run ",
                "boolean ",
                "Accepted for compatibility; this preview never writes.",
            ),
        ),
        output_description="Error-handler removal preview.",
        read_only=True,
        annotations=annotations["project.error_handlers.delete"],
    )


def _documentation_generate(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="documentation.generate",
        description=(
            "Generate a bounded customer-safe documentation base from "
            "repository-local "
            "project state. Read-only, local-only, no PDF binary rendering, "
            "no provider call, "
            "and no credential reads."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
                required=True,
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact or full.",
            ),
            _field(
                "dry_run ",
                "boolean",
                (
                    "Accepted for schema consistency; this read-only tool "
                    "never "
                    ""
                    "writes."
                ),
            ),
        ),
        output_description=(
            "Documentation sections, source-state counts, validation "
            "status, and safe "
            "manual-generation base fields."
        ),
        read_only=True,
        annotations=annotations["documentation.generate"],
    )


def _documentation_validate(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="documentation.validate",
        description=(
            "Validate a generated documentation base or current local "
            "project documentation "
            "state for missing sections, missing note references, forbidden "
            "content, secrets, "
            "and unsupported guarantee claims."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string ",
                "Safe repository-local project identifier.",
            ),
            _field(
                "documentation_json ",
                "string ",
                "Optional generated documentation JSON object to validate.",
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional output mode: compact or full.",
            ),
        ),
        output_description="Documentation validation status and issue counts.",
        read_only=True,
        annotations=annotations["documentation.validate"],
    )


def _onboarding_validate(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="onboarding.validate",
        description=(
            "Validate Make scenario onboarding placeholder coverage without "
            "accepting credential "
            "values. Send only placeholder names; never API keys, tokens, "
            "or secrets."
        ),
        input_fields=(
            _field(
                "project_id ",
                "string",
                (
                    "Optional local project id whose runtime setup "
                    "placeholders "
                    ""
                    "must be covered."
                ),
            ),
            _field(
                "provided_placeholders_json ",
                "string",
                (
                    "Optional JSON array of placeholder names that are "
                    "present; "
                    ""
                    "never include values."
                ),
            ),
            _field(
                "output_mode ",
                "string ",
                "Optional redacted validation output mode: compact or full.",
            ),
        ),
        output_description=(
            "Onboarding boundary validation counts and credential safety flags."
        ),
        read_only=True,
        annotations=annotations["onboarding.validate"],
    )


def _linter_quarantine_write(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="linter.quarantine.write",
        description=(
            "Record one candidate-only Make scenario linter quarantine item "
            "in the Pancakes "
            "Core SQLite SSOT. Development intake only; JSON and Markdown "
            "snapshots are not "
            "authority."
        ),
        input_fields=(
            _field(
                "candidate_id ",
                "string ",
                "Safe linter candidate identifier.",
                required=True,
            ),
            _field(
                "source_file ",
                "string ",
                "Repository-relative source reference.",
                required=True,
            ),
            _field(
                "candidate_title ",
                "string ",
                "Candidate record title.",
                required=True,
            ),
            _field(
                "quarantine_reason ",
                "string ",
                "Why the candidate remains inactive.",
                required=True,
            ),
            _field(
                "missing_evidence ",
                "string ",
                "Evidence needed before promotion.",
                required=True,
            ),
            _field(
                "proposed_predicate_text ",
                "string ",
                "Candidate predicate prose kept as inactive evidence only.",
                required=True,
            ),
            _field(
                "final_state ",
                "string ",
                "Candidate-only final state.",
                required=True,
            ),
            _field(
                "observed_linter_severity ",
                "string ",
                "Optional current linter severity.",
            ),
            _field(
                "proposed_severity", "string", "Optional proposed severity."
            ),
            _field(
                "technical_justification ",
                "string ",
                "Required when lowering severity.",
            ),
        ),
        output_description=(
            "SQLite write receipt and proof no active rule was written."
        ),
        read_only=False,
        annotations=annotations["linter.quarantine.write"],
    )


def _linter_rule_next(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_NEXT_TOOL,
        description=(
            "Lease one local Make linter quarantine candidate for guarded "
            "direct-editor review. "
            "Lease-based, SQLite-backed, no raw SQL, no raw file editor, no "
            "provider calls."
        ),
        input_fields=(
            _field(
                "worker_id ",
                "string ",
                "Stable worker identifier.",
                required=True,
            ),
            _field(
                "family_filter", "string", "Optional linter family id filter."
            ),
            _field(
                "priority_floor ",
                "integer ",
                "Optional priority floor for future queues.",
            ),
            _field(
                "mode ",
                "string",
                (
                    "Optional mode: implementable, canonical_merge, "
                    "invalid_disposition, or review."
                ),
            ),
        ),
        output_description=(
            "Leased candidate, token, evidence, allowed dispositions, and "
            "validation contract."
        ),
        read_only=False,
        annotations=annotations[LINTER_RULE_NEXT_TOOL],
    )


def _linter_rule_inspect(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_INSPECT_TOOL,
        description=(
            "Inspect one local Make linter candidate, canonical rule "
            "family, tests, fixtures, "
            "and quarantine evidence without exposing raw SQL or provider "
            "state."
        ),
        input_fields=(
            _field("candidate_id", "string", "Candidate id to inspect."),
            _field(
                "rule_id ",
                "string ",
                "Rule code to inspect when candidate_id is absent.",
            ),
            _field("output_mode", "string", "compact, full, or debug."),
        ),
        output_description=(
            "Candidate classification, source evidence, taxonomy location, "
            "and coverage hints."
        ),
        read_only=True,
        annotations=annotations[LINTER_RULE_INSPECT_TOOL],
    )


def _linter_rule_implement(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_IMPLEMENT_TOOL,
        description=(
            "Validate a leased Make linter rule implementation through "
            "memo, AST, test, severity, "
            "snapshot, and commit guards. No live Make calls, no raw SQL, "
            "and no push."
        ),
        input_fields=(
            _field(
                "worker_id ",
                "string ",
                "Stable worker identifier.",
                required=True,
            ),
            _field(
                "candidate_id", "string", "Leased candidate id.", required=True
            ),
            _field(
                "lease_token ",
                "string ",
                "Lease token from linter.rule.next.",
                required=True,
            ),
            _field(
                "rule_code", "string", "Canonical finding code.", required=True
            ),
            _field(
                "target_family ",
                "string ",
                "Canonical linter family id.",
                required=True,
            ),
            _field("severity", "string", "Rule severity.", required=True),
            _field(
                "technical_implementation_memo ",
                "object",
                (
                    "Structured engineering memo with evidence, pass/fail, and "
                    "risk analysis."
                ),
                required=True,
            ),
            _field(
                "python_predicate_code ",
                "string ",
                "Submitted predicate source.",
                required=True,
            ),
            _field(
                "test_code ",
                "string ",
                "Focused pass/fail test source.",
                required=True,
            ),
            _field(
                "fixture_json ",
                "object ",
                "Pass/fail fixture JSON object.",
                required=True,
            ),
            _field(
                "expected_failure_code ",
                "string ",
                "Expected emitted finding code.",
                required=True,
            ),
            _field(
                "expected_pass_case ",
                "string ",
                "Named passing fixture case.",
                required=True,
            ),
            _field(
                "expected_fail_case ",
                "string ",
                "Named failing fixture case.",
                required=True,
            ),
            _field(
                "source_refs ",
                "object ",
                "JSON array of local evidence refs.",
                required=True,
            ),
            _field(
                "false_positive_analysis ",
                "string ",
                "Concrete false-positive boundary.",
                required=True,
            ),
            _field(
                "evidence_gap_policy ",
                "string ",
                "How missing evidence stays actionable.",
                required=True,
            ),
            _field(
                "commit_message ",
                "string ",
                "One-rule commit message.",
                required=True,
            ),
            _field(
                "dry_run", "boolean", "Validate only; write nothing when true."
            ),
        ),
        output_description=(
            "Guard receipt or actionable rejection before source activation."
        ),
        read_only=False,
        annotations=annotations[LINTER_RULE_IMPLEMENT_TOOL],
    )


def _linter_rule_merge_canonical(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_MERGE_CANONICAL_TOOL,
        description=(
            "Merge a leased candidate into an exact existing canonical Make "
            "linter rule with "
            "proof. Updates SQLite and snapshots only after lease, "
            "coverage, and repository "
            "guards pass."
        ),
        input_fields=(
            _field(
                "worker_id ",
                "string ",
                "Stable worker identifier.",
                required=True,
            ),
            _field(
                "candidate_id", "string", "Leased candidate id.", required=True
            ),
            _field(
                "lease_token ",
                "string ",
                "Lease token from linter.rule.next.",
                required=True,
            ),
            _field(
                "canonical_rule_code ",
                "string ",
                "Existing canonical rule code.",
                required=True,
            ),
            _field(
                "merge_rationale ",
                "string ",
                "Evidence-backed merge rationale.",
                required=True,
            ),
            _field(
                "source_refs ",
                "object ",
                "JSON array of local evidence refs.",
                required=True,
            ),
            _field(
                "equivalence_proof ",
                "string ",
                "Exact equivalence proof.",
                required=True,
            ),
            _field(
                "test_or_evidence_ref ",
                "string ",
                "Coverage test or evidence reference.",
                required=True,
            ),
            _field(
                "commit_message ",
                "string ",
                "One-rule commit message.",
                required=True,
            ),
            _field(
                "dry_run", "boolean", "Validate only; write nothing when true."
            ),
        ),
        output_description=(
            "Canonical merge receipt with snapshot and commit evidence."
        ),
        read_only=False,
        annotations=annotations[LINTER_RULE_MERGE_CANONICAL_TOOL],
    )


def _linter_rule_reject_invalid(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_REJECT_INVALID_TOOL,
        description=(
            "Reject a leased candidate only as a proven non-linter or "
            "malformed extraction "
            "artifact for Make scenario review. Evidence-backed, "
            "SQLite-backed, no runtime rule "
            "deletion."
        ),
        input_fields=(
            _field(
                "worker_id ",
                "string ",
                "Stable worker identifier.",
                required=True,
            ),
            _field(
                "candidate_id", "string", "Leased candidate id.", required=True
            ),
            _field(
                "lease_token ",
                "string ",
                "Lease token from linter.rule.next.",
                required=True,
            ),
            _field(
                "invalid_reason ",
                "string ",
                "Evidence-backed invalid reason.",
                required=True,
            ),
            _field(
                "pattern_class ",
                "string ",
                "Allowed invalid class.",
                required=True,
            ),
            _field(
                "source_refs ",
                "object ",
                "JSON array of local evidence refs.",
                required=True,
            ),
            _field(
                "proof_excerpt ",
                "string ",
                "Source excerpt proving invalidity.",
                required=True,
            ),
            _field(
                "commit_message ",
                "string ",
                "One-rule commit message.",
                required=True,
            ),
            _field(
                "dry_run", "boolean", "Validate only; write nothing when true."
            ),
        ),
        output_description=(
            "Invalid rejection receipt with snapshot and commit evidence."
        ),
        read_only=False,
        annotations=annotations[LINTER_RULE_REJECT_INVALID_TOOL],
    )


def _linter_rule_edit(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_EDIT_TOOL,
        description=(
            "Validate an edit to an existing implemented Make linter rule. "
            "Severity downgrades "
            "require false-positive proof and regression evidence."
        ),
        input_fields=(
            _field(
                "worker_id ",
                "string ",
                "Stable worker identifier.",
                required=True,
            ),
            _field(
                "rule_code ",
                "string ",
                "Existing canonical rule code.",
                required=True,
            ),
            _field(
                "lease_token ",
                "string ",
                "Lease token from linter.rule.next.",
                required=True,
            ),
            _field(
                "technical_implementation_memo ",
                "object ",
                "Structured edit memo.",
                required=True,
            ),
            _field(
                "patch_code ",
                "string ",
                "Typed patch payload, not a raw file editor.",
                required=True,
            ),
            _field(
                "updated_test_code ",
                "string ",
                "Updated focused tests.",
                required=True,
            ),
            _field(
                "regression_reason ",
                "string ",
                "Why this edit is needed.",
                required=True,
            ),
            _field(
                "source_refs ",
                "object ",
                "JSON array of local evidence refs.",
                required=True,
            ),
            _field(
                "commit_message ",
                "string ",
                "One-rule commit message.",
                required=True,
            ),
            _field(
                "dry_run", "boolean", "Validate only; write nothing when true."
            ),
        ),
        output_description="Edit guard receipt or actionable rejection.",
        read_only=False,
        annotations=annotations[LINTER_RULE_EDIT_TOOL],
    )


def _linter_rule_status(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_STATUS_TOOL,
        description=(
            "Summarize local Make linter editor status, quarantine "
            "dispositions, duplicate "
            "evidence, leases, stale leases, and validation health."
        ),
        input_fields=(
            _field(
                "include_debug", "boolean", "Include compact lease debug rows."
            ),
        ),
        output_description=(
            "Counts for implemented, canonical, duplicate, invalid, not "
            "implemented, blocked, "
            "and leased records."
        ),
        read_only=True,
        annotations=annotations[LINTER_RULE_STATUS_TOOL],
    )


def _linter_rule_rollback(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name=LINTER_RULE_ROLLBACK_TOOL,
        description=(
            "Rollback one MCP-created Make linter-rule commit when operator "
            "confirmation or "
            "strong automated evidence is present. Local repository only; "
            "never pushes."
        ),
        input_fields=(
            _field(
                "commit_hash ",
                "string ",
                "MCP-created commit hash.",
                required=True,
            ),
            _field(
                "rule_id ",
                "string ",
                "Rule id covered by the commit.",
                required=True,
            ),
            _field(
                "rollback_reason ",
                "string ",
                "Evidence-backed rollback reason.",
                required=True,
            ),
            _field(
                "operator_confirmation ",
                "boolean ",
                "Explicit operator confirmation.",
            ),
            _field(
                "automated_evidence ",
                "string ",
                "High-confidence automated evidence.",
            ),
            _field(
                "dry_run", "boolean", "Validate only; write nothing when true."
            ),
        ),
        output_description=(
            "Rollback receipt or confirmation/evidence rejection."
        ),
        read_only=False,
        annotations=annotations[LINTER_RULE_ROLLBACK_TOOL],
    )


def _backlog_add(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="backlog.add",
        description=(
            "Record one local MCP backlog item for Make catalog, linter, or "
            "project graph "
            "follow-up directly in the Pancakes Core SQLite SSOT. "
            "Local-only and no JSON or "
            "Markdown ledger."
        ),
        input_fields=(
            _field("domain", "string", "Backlog partition.", required=True),
            _field(
                "title", "string", "Short backlog item title.", required=True
            ),
            _field(
                "payload_json ",
                "string ",
                "Optional JSON object with compact details.",
            ),
            _field(
                "priority ",
                "integer ",
                "Optional integer priority from 0 through 1000.",
            ),
            _field("source_kind", "string", "Optional evidence source kind."),
            _field(
                "source_ref", "string", "Optional evidence source reference."
            ),
            _field("entry_id", "string", "Optional stable entry id."),
        ),
        output_description="Backlog SQLite write receipt.",
        read_only=False,
        annotations=annotations["backlog.add"],
    )


def _backlog_list(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="backlog.list",
        description=(
            "List local Make catalog, linter, or project graph backlog rows "
            "from the "
            "Pancakes Core SQLite SSOT only."
        ),
        input_fields=(
            _field("domain", "string", "Optional backlog partition filter."),
            _field("status", "string", "Optional status filter."),
            _field("limit", "integer", "Optional result limit."),
            _field(
                "include_payload ",
                "boolean ",
                "Include evidence payloads when true.",
            ),
        ),
        output_description="Bounded backlog rows and hidden count.",
        read_only=True,
        annotations=annotations["backlog.list"],
    )


def _backlog_end(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="backlog.end",
        description=(
            "Close one Make catalog, linter, or project graph backlog item "
            "directly in the "
            "Pancakes Core SQLite SSOT."
        ),
        input_fields=(
            _field(
                "entry_id", "string", "Stable backlog entry id.", required=True
            ),
            _field("resolution", "string", "Resolution note.", required=True),
            _field(
                "source_ref", "string", "Optional closure evidence reference."
            ),
        ),
        output_description="Backlog close receipt.",
        read_only=False,
        annotations=annotations["backlog.end"],
    )


def _catalog_modify(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.modify",
        description=(
            "Typed catalog mutation surface for unit notes, unit status, "
            "and edge-proposal "
            "review decisions. Local SQLite only, no raw SQL, no providers, "
            "and no live "
            "Make.com state. dry_run validates locally without writing."
        ),
        input_fields=(
            _field(
                "operation ",
                "string",
                (
                    "update_unit_note, update_unit_status, "
                    "approve_edge_proposal, "
                    "or reject_edge_proposal."
                ),
                required=True,
            ),
            _field("run_id", "string", "Catalog run id for unit mutations."),
            _field("unit_id", "string", "Catalog unit id for unit mutations."),
            _field(
                "note_surface ",
                "string",
                (
                    "Catalog note surface such as error_handlers, filters, "
                    "data_stores, "
                    "data_structures, routers_control_structures, edge_cases, "
                    "fallback_behavior, or usage_guidance."
                ),
            ),
            _field("note_text", "string", "Typed catalog note text."),
            _field("status", "string", "Optional catalog unit status update."),
            _field(
                "validation_status ",
                "string ",
                "Optional unit validation status update.",
            ),
            _field(
                "coverage_status ",
                "string ",
                "Optional unit coverage status update.",
            ),
            _field(
                "proposal_id ",
                "string ",
                "Edge proposal id for review decisions.",
            ),
            _field(
                "worker_id", "string", "Optional local catalog tool worker id."
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description=(
            "Typed catalog mutation receipt and audit-event pointer."
        ),
        read_only=False,
        annotations=annotations["catalog.modify"],
    )


def _catalog_node_modify(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.node.modify",
        description=(
            "Typed graph node upsert for derived catalog projections. Local "
            "SQLite only, "
            "no raw SQL mutation surface, no providers, and no live "
            "Make.com state."
        ),
        input_fields=(
            _field("node_id", "string", "Stable graph node id.", required=True),
            _field("domain", "string", "Catalog graph domain.", required=True),
            _field(
                "entity_kind ",
                "string ",
                "Typed graph entity kind.",
                required=True,
            ),
            _field(
                "canonical_label ",
                "string ",
                "Human-readable canonical node label.",
                required=True,
            ),
            _field(
                "payload_json", "object", "Typed graph node payload object."
            ),
            _field("source_kind", "string", "Optional evidence source kind."),
            _field(
                "source_ref", "string", "Optional evidence source reference."
            ),
            _field(
                "worker_id", "string", "Optional local catalog tool worker id."
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Typed catalog graph node mutation receipt.",
        read_only=False,
        annotations=annotations["catalog.node.modify"],
    )


def _catalog_edge_propose(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.edge.propose",
        description=(
            "Propose a typed graph edge before applying it to derived "
            "catalog projections. "
            "Local SQLite only, no raw SQL, no providers, and no live "
            "Make.com state."
        ),
        input_fields=(
            _field(
                "proposal_id", "string", "Optional stable edge proposal id."
            ),
            _field("domain", "string", "Catalog graph domain.", required=True),
            _field(
                "edge_kind", "string", "Typed graph edge kind.", required=True
            ),
            _field("from_node_id", "string", "Source node id.", required=True),
            _field("to_node_id", "string", "Target node id.", required=True),
            _field("payload_json", "object", "Typed edge payload object."),
            _field(
                "rationale ",
                "string ",
                "Evidence-backed proposal rationale.",
                required=True,
            ),
            _field("source_kind", "string", "Optional evidence source kind."),
            _field(
                "source_ref", "string", "Optional evidence source reference."
            ),
            _field(
                "worker_id", "string", "Optional local catalog tool worker id."
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Typed catalog graph edge proposal receipt.",
        read_only=False,
        annotations=annotations["catalog.edge.propose"],
    )


def _catalog_edge_apply(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.edge.apply",
        description=(
            "Apply one approved catalog edge proposal into the derived "
            "graph projection. "
            "Local SQLite only, no raw SQL, no providers, and no live "
            "Make.com state."
        ),
        input_fields=(
            _field(
                "proposal_id ",
                "string ",
                "Approved edge proposal id.",
                required=True,
            ),
            _field(
                "edge_id", "string", "Optional stable graph edge id override."
            ),
            _field(
                "worker_id", "string", "Optional local catalog tool worker id."
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Typed catalog graph edge apply receipt.",
        read_only=False,
        annotations=annotations["catalog.edge.apply"],
    )


def _catalog_review_add(
    annotations: dict[str, McpToolAnnotations],
) -> McpToolDefinition:
    return McpToolDefinition(
        name="catalog.review.add",
        description=(
            "Add one typed catalog review or backlog record when a catalog "
            "issue needs "
            "later attention. Local SQLite only, no raw SQL, no providers, "
            "and no live "
            "Make.com state. dry_run validates locally without writing."
        ),
        input_fields=(
            _field("review_id", "string", "Optional stable review id."),
            _field("domain", "string", "Catalog review domain.", required=True),
            _field(
                "target_kind", "string", "Review target kind.", required=True
            ),
            _field("target_id", "string", "Review target id.", required=True),
            _field(
                "review_status ",
                "string ",
                "Optional review status; defaults to open.",
            ),
            _field("priority", "integer", "Optional integer priority."),
            _field("payload_json", "object", "Typed review payload object."),
            _field("source_kind", "string", "Optional evidence source kind."),
            _field(
                "source_ref", "string", "Optional evidence source reference."
            ),
            _field(
                "worker_id", "string", "Optional local catalog tool worker id."
            ),
            _field("dry_run", "boolean", "Preview without writing when true."),
        ),
        output_description="Typed catalog review/backlog record receipt.",
        read_only=False,
        annotations=annotations["catalog.review.add"],
    )
