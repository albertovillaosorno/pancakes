# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""OAuth scope contracts for the minimal MCP surface.

ADR: docs/adr/catalog-semantic-graph-preview-policy.md.
"""

from __future__ import annotations

from mcp import mcp_tool_registry


def test_oauth_scope_inputs_are_derived_from_minimal_tool_classifications() -> (
    None
):
    """Read tools need read scope; write tools need write scope."""
    read_tools: list[str] = []
    write_tools: list[str] = []

    for tool in mcp_tool_registry():
        if tool.read_only:
            read_tools.append(tool.name)
        else:
            write_tools.append(tool.name)

    assert "catalog.index" in read_tools
    assert "catalog.search" in read_tools
    assert "catalog.inspect" in read_tools
    assert "catalog.graph.search" in read_tools
    assert "catalog.semantic.preview" in read_tools
    assert "project.search" in read_tools
    assert "project.verify" in read_tools
    assert "project.capabilities.inspect" in read_tools
    assert "project.next" in read_tools
    assert "project.modules.delete" in read_tools
    assert "backlog.list" in read_tools
    assert "catalog.work.save" not in read_tools
    assert "catalog.modify" in write_tools
    assert "catalog.edge.apply" in write_tools
    assert "project.draft.stage" in write_tools
    assert "project.draft.import" in write_tools
    assert "project.create" in write_tools
    assert "project.edit" in write_tools
    assert "project.make" in write_tools
    assert "project.modules.add" in write_tools
    assert _tool("scraper", "refresh_status") not in read_tools


def _tool(*parts: str) -> str:
    return ".".join(parts)
