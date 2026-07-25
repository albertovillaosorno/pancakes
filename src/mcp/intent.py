# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001055#repo.mcp.scenario-builder-micro-tools
# - 001055#repo.mcp.no-obsolete-domain-tools
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Deterministic intent routing hints for the MCP surface.

Boundary contract:
- Owns: conservative text-to-tool routing hints for the MCP surface.
- Must not: execute tools, access repositories, call models, or perform IO.
- Allows: deterministic keyword routing with explicit fallback context.
- Split when: intent parsing needs learned classifiers or tool-specific schemas.
- Merge when: another intent module returns the same routing hint model.
"""

from __future__ import annotations

from mcp.models import McpIntent


def parse_mcp_intent(text: str) -> McpIntent:
    """Parse natural text into a conservative MCP routing hint.

    Returns:
        The parsed value.
    """
    lowered = text.casefold()
    context = {"length": str(len(text))}
    action, tool_name, is_fallback = _route_intent(lowered)
    if is_fallback:
        context["fallback"] = "true"
    return McpIntent(
        goal=text.strip(), action=action, tool_name=tool_name, context=context
    )


def _route_intent(lowered: str) -> tuple[str, str, bool]:
    rules = (
        (
            "catalog_index",
            "catalog.index",
            "catalog" in lowered
            and (
                "index" in lowered
                or "placeholder" in lowered
                or "canonical value" in lowered
            ),
        ),
        (
            "list_quarantine_backlog",
            "backlog.list",
            "quarantine" in lowered
            and ("linter" in lowered or "rule" in lowered),
        ),
        (
            "list_backlog",
            "backlog.list",
            "backlog" in lowered and ("list" in lowered or "status" in lowered),
        ),
        (
            "end_backlog",
            "backlog.end",
            "backlog" in lowered and ("close" in lowered or "end" in lowered),
        ),
        (
            "add_backlog",
            "backlog.add",
            "backlog" in lowered and ("add" in lowered or "record" in lowered),
        ),
        (
            "catalog_search",
            "catalog.search",
            "catalog" in lowered or "module" in lowered or "stack" in lowered,
        ),
    )
    for action, tool_name, is_match in rules:
        if is_match:
            return action, tool_name, False
    return "catalog_search", "catalog.search", True
