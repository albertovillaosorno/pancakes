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
"""Local dispatcher for the active repository MCP tool surface.

Boundary contract:
- Owns: local tool dispatch against repository-confined state.
- Must not: expose generic automation, mutate live services, or manage
  transports.
- Allows: parsing tool arguments, loading local SQLite-backed state,
  and serialized results.
- Split when: execution gains credentialed or live-provider operations.
- Merge when: another executor dispatches the same MCP tool handlers.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path

from catalog.knowledge import DEFAULT_KNOWLEDGE_DB_PATH, build_knowledge_store

from mcp.backlog import (
    add_backlog_entry,
    end_backlog_entry,
    list_backlog_entries,
)
from mcp.catalog_graph import catalog_graph_search, catalog_semantic_preview
from mcp.catalog_index import catalog_index
from mcp.catalog_mutation import (
    catalog_edge_apply,
    catalog_edge_propose,
    catalog_modify,
    catalog_node_modify,
    catalog_review_add,
)
from mcp.catalog_search import catalog_inspect, catalog_search
from mcp.documentation import (
    generate_documentation,
    validate_documentation,
    validate_onboarding,
)
from mcp.inactive_catalog_work import catalog_work_next, catalog_work_save
from mcp.linter_quarantine import write_linter_quarantine_record
from mcp.linter_rule_editor import (
    edit_linter_rule,
    implement_linter_rule,
    inspect_linter_rule,
    linter_rule_status,
    merge_linter_rule_canonical,
    next_linter_rule,
    reject_invalid_linter_rule,
    rollback_linter_rule,
)
from mcp.models import JsonObject, McpToolCallReport
from mcp.project_loop import (
    add_project_error_handler,
    add_project_filter,
    add_project_module,
    create_project,
    delete_project_error_handler,
    delete_project_filter,
    delete_project_module,
    edit_project,
    import_project_draft,
    inspect_project_capabilities,
    inspect_project_package,
    modify_project_error_handler,
    modify_project_filter,
    modify_project_module,
    project_health,
    project_make,
    project_next,
    project_verify,
    search_projects,
    stage_project_draft,
    view_project,
    view_project_error_handlers,
    view_project_filters,
    view_project_links,
    view_project_modules,
)
from mcp.response_contracts import attach_response_contract
from mcp.session import (
    MCP_SESSION_START_TOOL,
    session_scope_metadata,
    start_mcp_session,
)

ToolHandler = Callable[[Mapping[str, object], Path], JsonObject]


def execute_mcp_tool(
    *,
    tool_name: str,
    arguments: Mapping[str, object],
    repo_root: Path,
) -> McpToolCallReport:
    """Execute one active local MCP tool against repository-local state.

    Returns:
        The local MCP tool execution result.
    """
    handler = _TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return McpToolCallReport(
            tool_name=tool_name,
            ok=False,
            payload={},
            error=f"Unknown MCP tool: {tool_name}",
        )
    try:
        session_metadata = session_scope_metadata(
            tool_name=tool_name,
            arguments=arguments,
        )
        handler_payload = handler(arguments, repo_root)
        handler_payload.update(session_metadata)
        payload = attach_response_contract(
            tool_name=_RESPONSE_CONTRACT_TOOL_ALIASES.get(tool_name, tool_name),
            payload=handler_payload,
        )
        return McpToolCallReport(
            tool_name=tool_name,
            ok=True,
            payload=payload,
        )
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        return McpToolCallReport(
            tool_name=tool_name, ok=False, payload={}, error=str(exc)
        )


def warm_catalog_snapshot(*, repo_root: Path) -> None:
    """Ensure the SQLite catalog exists for low-latency MCP startup."""
    if (repo_root / DEFAULT_KNOWLEDGE_DB_PATH).exists():
        return
    with suppress(
        FileNotFoundError, OSError, PermissionError, TypeError, ValueError
    ):
        _ = build_knowledge_store(repo_root=repo_root)


_TOOL_HANDLERS: dict[str, ToolHandler] = {
    MCP_SESSION_START_TOOL: start_mcp_session,
    "catalog.index": catalog_index,
    "catalog.search": catalog_search,
    "catalog.inspect": catalog_inspect,
    "catalog.graph.search": catalog_graph_search,
    "catalog.semantic.preview": catalog_semantic_preview,
    "catalog.work.next": catalog_work_next,
    "catalog.work.save": catalog_work_save,
    "catalog.modify": catalog_modify,
    "catalog.node.modify": catalog_node_modify,
    "catalog.edge.propose": catalog_edge_propose,
    "catalog.edge.apply": catalog_edge_apply,
    "catalog.review.add": catalog_review_add,
    "project.search": search_projects,
    "project.draft.stage": stage_project_draft,
    "project.draft.import": import_project_draft,
    "project.create": create_project,
    "project.health": project_health,
    "project.view": view_project,
    "project.edit": edit_project,
    "project.verify": project_verify,
    "project.capabilities.inspect": inspect_project_capabilities,
    "project.make": project_make,
    "project.package.inspect": inspect_project_package,
    "project.next": project_next,
    "project.modules.view": view_project_modules,
    "project.modules.add": add_project_module,
    "project.modules.modify": modify_project_module,
    "project.modules.delete": delete_project_module,
    "project.links.view": view_project_links,
    "project.filters.view": view_project_filters,
    "project.filters.add": add_project_filter,
    "project.filters.modify": modify_project_filter,
    "project.filters.delete": delete_project_filter,
    "project.error_handlers.view": view_project_error_handlers,
    "project.error_handlers.add": add_project_error_handler,
    "project.error_handlers.modify": modify_project_error_handler,
    "project.error_handlers.delete": delete_project_error_handler,
    "documentation.generate": generate_documentation,
    "documentation.validate": validate_documentation,
    "onboarding.validate": validate_onboarding,
    "linter.quarantine.write": write_linter_quarantine_record,
    "linter.rule.next": next_linter_rule,
    "linter.rule.inspect": inspect_linter_rule,
    "linter.rule.implement": implement_linter_rule,
    "linter.rule.merge_canonical": merge_linter_rule_canonical,
    "linter.rule.reject_invalid": reject_invalid_linter_rule,
    "linter.rule.edit": edit_linter_rule,
    "linter.rule.status": linter_rule_status,
    "linter.rule.rollback": rollback_linter_rule,
    "backlog.add": add_backlog_entry,
    "backlog.list": list_backlog_entries,
    "backlog.end": end_backlog_entry,
}

_RESPONSE_CONTRACT_TOOL_ALIASES: dict[str, str] = {}
