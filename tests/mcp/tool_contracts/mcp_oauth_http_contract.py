# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""OAuth HTTP contracts for the minimal MCP registry."""

from __future__ import annotations

from mcp.http_server import OAUTH_READ_SCOPE, OAUTH_SCOPE, OAUTH_WRITE_SCOPE
from mcp.registry import REQUIRED_TOOL_NAMES


def test_oauth_scope_constants_remain_bounded_for_minimal_mcp() -> None:
    """OAuth exposes only read/write scopes for the retained MCP tools."""
    assert OAUTH_READ_SCOPE == "mcp:read"
    assert OAUTH_WRITE_SCOPE == "mcp:write"
    assert OAUTH_SCOPE == "mcp:read mcp:write"
    assert "catalog.index" in REQUIRED_TOOL_NAMES
    assert "catalog.search" in REQUIRED_TOOL_NAMES
    assert _tool("project", "create") in REQUIRED_TOOL_NAMES
    assert _tool("project", "tests", "run") not in REQUIRED_TOOL_NAMES


def _tool(*parts: str) -> str:
    return ".".join(parts)
