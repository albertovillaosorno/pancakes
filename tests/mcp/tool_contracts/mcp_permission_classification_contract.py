# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Permission classification contracts for the minimal MCP surface.

ADR: docs/adr/catalog-semantic-graph-preview-policy.md.
"""

from __future__ import annotations

from mcp import mcp_tool_registry

READ_ONLY_TOOLS = {
    "mcp.session.start",
    "catalog.index",
    "catalog.search",
    "catalog.inspect",
    "catalog.graph.search",
    "catalog.semantic.preview",
    "project.search",
    "project.health",
    "project.view",
    "project.verify",
    "project.capabilities.inspect",
    "project.package.inspect",
    "project.next",
    "project.modules.view",
    "project.modules.delete",
    "project.links.view",
    "project.filters.view",
    "project.filters.delete",
    "project.error_handlers.view",
    "project.error_handlers.delete",
    "documentation.generate",
    "documentation.validate",
    "onboarding.validate",
    "linter.rule.inspect",
    "linter.rule.status",
    "backlog.list",
}
WRITE_LIKE_TOOLS = {
    "catalog.modify",
    "catalog.node.modify",
    "catalog.edge.propose",
    "catalog.edge.apply",
    "catalog.review.add",
    "project.draft.stage",
    "project.draft.import",
    "project.create",
    "project.edit",
    "project.make",
    "project.modules.add",
    "project.modules.modify",
    "project.filters.add",
    "project.filters.modify",
    "project.error_handlers.add",
    "project.error_handlers.modify",
    "linter.quarantine.write",
    "linter.rule.next",
    "linter.rule.implement",
    "linter.rule.merge_canonical",
    "linter.rule.reject_invalid",
    "linter.rule.edit",
    "backlog.add",
    "backlog.end",
}
DESTRUCTIVE_TOOLS = {"linter.rule.rollback"}


def test_mcp_tool_permission_classifications_are_explicit() -> None:
    """Every active public MCP tool has the expected safety classification."""
    tools = {tool.name: tool for tool in mcp_tool_registry()}

    assert set(tools) == READ_ONLY_TOOLS | WRITE_LIKE_TOOLS | DESTRUCTIVE_TOOLS
    for name in READ_ONLY_TOOLS:
        tool = tools[name]
        assert tool.read_only is True
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.provider_api_call is False
        assert tool.annotations.classification == "read_only"

    for name in WRITE_LIKE_TOOLS:
        tool = tools[name]
        assert tool.read_only is False
        assert tool.annotations is not None
        assert tool.annotations.classification == "write_like"
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.provider_api_call is False
        assert tool.annotations.read_only_hint is False

    for name in DESTRUCTIVE_TOOLS:
        tool = tools[name]
        assert tool.read_only is False
        assert tool.annotations is not None
        assert tool.annotations.classification == "destructive"
        assert tool.annotations.destructive_hint is True
        assert tool.annotations.provider_api_call is False
