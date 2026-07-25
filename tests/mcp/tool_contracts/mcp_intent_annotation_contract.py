# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Intent and annotation contracts for the minimal MCP surface."""

from __future__ import annotations

from typing import cast

from mcp import (
    build_public_tool_annotation_matrix,
    mcp_tool_registry,
    parse_mcp_intent,
)


def test_intent_routing_only_targets_active_tools() -> None:
    """Intent routing never points users to deleted MCP tools."""
    active_tool_names = {tool.name for tool in mcp_tool_registry()}

    for text in (
        "search the catalog for a webhook",
        "list backlog status",
        "add backlog item",
        "close backlog item",
        "review linter quarantine rule backlog",
        "plain fallback text",
    ):
        intent = parse_mcp_intent(text)
        assert intent.tool_name in active_tool_names, intent


def test_intent_routing_sends_catalog_index_requests_to_index_tool() -> None:
    """Index-style wording routes to catalog.index."""
    for text in (
        "show the catalog index",
        "lookup the catalog placeholder index",
        "get canonical value terms from catalog",
    ):
        intent = parse_mcp_intent(text)
        assert intent.action == "catalog_index"
        assert intent.tool_name == "catalog.index"
        assert "fallback" not in intent.context


def test_annotation_matrix_has_no_removed_tool_entries() -> None:
    """The public annotation matrix is restricted to the active registry."""
    descriptions = {tool.name: tool.description for tool in mcp_tool_registry()}
    matrix = build_public_tool_annotation_matrix(tool_descriptions=descriptions)
    tools = cast("dict[str, object]", matrix["tools"])

    assert set(tools) == set(descriptions)
    assert _tool("project", "list") not in tools
    assert _tool("scraper", "refresh_status") not in tools
    assert _tool("catalog", "plan") not in tools


def _tool(*parts: str) -> str:
    return ".".join(parts)
