# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Repository MCP server slice boundary.

Boundary contract:
- Owns: public exports for the local repository MCP surface.
- Must not: implement tool dispatch, registry, schema models, or server startup.
- Allows: re-exporting stable MCP APIs from focused sibling modules.
- Split when: exports need transport-specific or credentialed runtime behavior.
- Merge when: another MCP package surface duplicates these exports.

LARGE-FILE:
owner: Pancakes MCP package exports
reason: stable public exports are centralized for MCP package consumers.
split: move prompt, transport, or tool exports to focused surfaces.
validation: pancakes.validate and GitGuard pre-push.
review: next MCP export surface edit.
"""

from __future__ import annotations

from mcp.annotations import (
    build_public_tool_annotation_matrix,
    local_workspace_write_annotation,
    public_tool_annotation_specs,
    read_only_annotation,
)
from mcp.context import (
    CATALOG_INTELLIGENCE_PROMPT_ALIASES,
    CATALOG_INTELLIGENCE_PROMPT_NAME,
    CATALOG_INTELLIGENCE_PROMPT_RELATIVE_PATH,
    get_mcp_prompt,
    mcp_prompt_registry,
    mcp_resource_registry,
    read_mcp_resource,
)
from mcp.executor import execute_mcp_tool
from mcp.http_server import (
    DEFAULT_PUBLIC_BASE_URL,
    DEFAULT_REMOTE_MCP_HOST,
    DEFAULT_REMOTE_MCP_PORT,
    RemoteMcpHttpOptions,
    build_remote_mcp_http_server,
    reset_remote_mcp_oauth_state,
    revoke_remote_mcp_bearer_token,
    revoke_remote_mcp_client,
    serve_remote_mcp_http,
)
from mcp.identity import SLICE_NAME
from mcp.intent import parse_mcp_intent
from mcp.latency import summarize_tool_latency_samples
from mcp.models import (
    JsonObject,
    McpInputField,
    McpIntent,
    McpLatencySample,
    McpLatencySummary,
    McpPromptDefinition,
    McpResourceDefinition,
    McpServerConfig,
    McpTestServer,
    McpToolAnnotations,
    McpToolCallReport,
    McpToolDefinition,
    ToolClassification,
)
from mcp.registry import REQUIRED_TOOL_NAMES, mcp_tool_registry
from mcp.server import (
    MCP_CANONICAL_URL,
    MCP_SERVER_NAME,
    mcp_server_config,
    start_mcp_test_server,
)

__all__ = (
    "CATALOG_INTELLIGENCE_PROMPT_ALIASES",
    "CATALOG_INTELLIGENCE_PROMPT_NAME",
    "CATALOG_INTELLIGENCE_PROMPT_RELATIVE_PATH",
    "DEFAULT_PUBLIC_BASE_URL",
    "DEFAULT_REMOTE_MCP_HOST",
    "DEFAULT_REMOTE_MCP_PORT",
    "MCP_CANONICAL_URL",
    "MCP_SERVER_NAME",
    "REQUIRED_TOOL_NAMES",
    "SLICE_NAME",
    "JsonObject",
    "McpInputField",
    "McpIntent",
    "McpLatencySample",
    "McpLatencySummary",
    "McpPromptDefinition",
    "McpResourceDefinition",
    "McpServerConfig",
    "McpTestServer",
    "McpToolAnnotations",
    "McpToolCallReport",
    "McpToolDefinition",
    "RemoteMcpHttpOptions",
    "ToolClassification",
    "build_public_tool_annotation_matrix",
    "build_remote_mcp_http_server",
    "execute_mcp_tool",
    "get_mcp_prompt",
    "local_workspace_write_annotation",
    "mcp_prompt_registry",
    "mcp_resource_registry",
    "mcp_server_config",
    "mcp_tool_registry",
    "parse_mcp_intent",
    "public_tool_annotation_specs",
    "read_mcp_resource",
    "read_only_annotation",
    "reset_remote_mcp_oauth_state",
    "revoke_remote_mcp_bearer_token",
    "revoke_remote_mcp_client",
    "serve_remote_mcp_http",
    "start_mcp_test_server",
    "summarize_tool_latency_samples",
)
