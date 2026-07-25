# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.server-identity
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""In-process MCP test server factory.

Boundary contract:
- Owns: repository MCP identity and in-process test server construction.
- Must not: run listeners, execute tools, mutate state, or manage services.
- Allows: stdio identity config and test-mode server objects for validation.
- Split when: real transports or Windows service hosting are introduced.
- Merge when: another server module constructs the same MCP test surface.
"""

from __future__ import annotations

from typing import Final

from mcp.context import mcp_prompt_registry, mcp_resource_registry
from mcp.models import McpServerConfig, McpTestServer
from mcp.registry import mcp_tool_registry

MCP_SERVER_NAME: Final[str] = "blueprint-mcp"
MCP_CANONICAL_URL: Final[str] = "repo://blueprint/mcp"


def mcp_server_config(*, test_mode: bool = True) -> McpServerConfig:
    """Return the repository MCP server config."""
    return McpServerConfig(
        server_name=MCP_SERVER_NAME,
        canonical_url=MCP_CANONICAL_URL,
        transports=("stdio",),
        test_mode=test_mode,
    )


def start_mcp_test_server() -> McpTestServer:
    """Start the repository MCP surface in test mode without live networking.

    Returns:
        The test-mode MCP server surface.
    """
    return McpTestServer(
        config=mcp_server_config(test_mode=True),
        tools=mcp_tool_registry(),
        resources=mcp_resource_registry(),
        prompts=mcp_prompt_registry(),
        started=True,
    )
