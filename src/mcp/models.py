# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001055#repo.mcp.server-identity
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed MCP server and tool schema models.

Boundary contract:
- Owns: immutable MCP server, tool, annotation, intent, and result records.
- Must not: register tools, execute handlers, parse intents, or perform IO.
- Allows: small schema helpers derived from model fields.
- Split when: records gain transport behavior or mutable runtime state.
- Merge when: another module defines the same MCP data contracts.
"""

from __future__ import annotations

from typing import Literal, NamedTuple, TypedDict

JsonSchemaType = Literal["string", "boolean", "object", "integer"]
type JsonObject = dict[str, object]
McpTransport = Literal["stdio"]
ToolClassification = Literal["read_only", "write_like", "mixed", "destructive"]
ProjectJsonWriteStatus = Literal["updated", "unchanged"]
ProjectOutputMode = Literal["compact", "full", "client_safe", "debug"]
McpOauthScope = Literal["mcp:read", "mcp:write"]


class MissingCatalogAssetsPayload(TypedDict):
    """Shared MCP payload fields for missing local catalog assets."""

    status: str
    missing_paths: list[str]
    recommended_commands: list[str]
    required_for_claim_level: str


class McpInputField(NamedTuple):
    """One minimal MCP tool input field."""

    name: str
    schema_type: JsonSchemaType
    description: str
    required: bool

    def json_schema(self) -> JsonObject:
        """Return this field as a JSON schema property."""
        return {"type": self.schema_type, "description": self.description}


class McpToolDefinition(NamedTuple):
    """One repository MCP tool definition."""

    name: str
    description: str
    input_fields: tuple[McpInputField, ...]
    output_description: str
    read_only: bool
    annotations: McpToolAnnotations | None = None

    def input_schema(self) -> JsonObject:
        """Return the MCP-compatible input schema."""
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                field.name: field.json_schema() for field in self.input_fields
            },
            "required": [
                field.name for field in self.input_fields if field.required
            ],
        }


class McpResourceDefinition(NamedTuple):
    """One MCP-readable repository documentation resource."""

    uri: str
    name: str
    description: str
    mime_type: str


class McpPromptDefinition(NamedTuple):
    """One MCP prompt entry for agent operating context."""

    name: str
    description: str


class McpServerConfig(NamedTuple):
    """Repository MCP server identity and transport config."""

    server_name: str
    canonical_url: str
    transports: tuple[McpTransport, ...]
    test_mode: bool


class McpTestServer(NamedTuple):
    """In-process MCP test surface used by repository tests."""

    config: McpServerConfig
    tools: tuple[McpToolDefinition, ...]
    resources: tuple[McpResourceDefinition, ...]
    prompts: tuple[McpPromptDefinition, ...]
    started: bool


class McpToolAnnotations(NamedTuple):
    """MCP semantic annotations for one tool."""

    classification: ToolClassification
    read_only_hint: bool
    destructive_hint: bool
    idempotent_hint: bool
    open_world_hint: bool
    local_only: bool
    provider_api_call: bool
    credential_value_transfer: bool
    secret_output: bool
    rationale: str


class McpIntent(NamedTuple):
    """Deterministic natural-language routing hint for the MCP surface."""

    goal: str
    action: str
    tool_name: str
    context: dict[str, str]


class McpLatencySample(NamedTuple):
    """One MCP tool latency sample."""

    tool_name: str
    latency_ms: float
    ok: bool
    error_type: str | None = None


class McpLatencySummary(NamedTuple):
    """Aggregated latency summary for one MCP tool."""

    tool_name: str
    sample_count: int
    success_count: int
    failure_count: int
    median_latency_ms: float
    p95_latency_ms: float
    max_latency_ms: float
    exceeds_threshold: bool


class McpToolCallReport(NamedTuple):
    """Result of one local MCP tool execution."""

    tool_name: str
    ok: bool
    payload: JsonObject
    error: str | None = None
