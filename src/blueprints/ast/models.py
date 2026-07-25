# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Typed Pancakes blueprint AST model contract.

Boundary contract:
- Owns: immutable blueprint AST records, node kinds, and JSON path aliases.
- Must not: parse raw JSON, traverse nodes, validate truth, or render JSON.
- Allows: typed records, aliases, and constants shared by blueprint modules.
- Split when: model families gain independent lifecycle or dependency needs.
- Merge when: another model file duplicates these AST records exactly.

Current record names retain `MakeAst*` compatibility because the active adapter
is Make. The architecture boundary is the Pancakes blueprint AST, with
language-neutral graph semantics promoted through `src/ir/**`.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

AST_SCHEMA_VERSION: Final = 1

type JsonObject = dict[str, object]
type AstPathPart = str | int
type AstNodeKind = Literal[
    "module",
    "router",
    "route",
    "filter",
    "iterator",
    "aggregator",
    "webhook",
    "http_api",
    "data_store",
    "ai_agent",
    "mcp_tool",
    "scenario_input",
    "scenario_output",
    "error_handler",
    "schedule_trigger",
    "unresolved",
]

AST_NODE_KINDS: Final[frozenset[str]] = frozenset(
    (
        "module",
        "router",
        "route",
        "filter",
        "iterator",
        "aggregator",
        "webhook",
        "http_api",
        "data_store",
        "ai_agent",
        "mcp_tool",
        "scenario_input",
        "scenario_output",
        "error_handler",
        "schedule_trigger",
        "unresolved",
    )
)


class MakeAstSourceTrace(NamedTuple):
    """Source trace for one node inside the original blueprint payload."""

    path: tuple[AstPathPart, ...]
    container_kind: str
    parent_node_id: str | None
    raw_node_id: str
    raw_module_token: str


class MakeAstRawSpecBinding(NamedTuple):
    """Catalog/raw-spec binding carried by an AST node."""

    status: str
    catalog_module_id: str | None
    raw_spec_sha256: str | None
    issues: tuple[str, ...]


class MakeAstFilter(NamedTuple):
    """Typed filter wrapper attached to a route-like AST boundary."""

    filter_id: str
    kind: AstNodeKind
    name: str
    conditions: JsonObject
    raw_payload: JsonObject


class MakeAstRoute(NamedTuple):
    """Typed route or branch boundary containing child nodes."""

    route_id: str
    container_kind: str
    source_trace: MakeAstSourceTrace
    filter: MakeAstFilter | None
    flow: tuple[MakeAstNode, ...]
    raw_payload: JsonObject


class MakeAstNode(NamedTuple):
    """One typed Make AST node with preserved raw and unknown fields."""

    node_id: str
    kind: AstNodeKind
    module_token: str
    label: str
    source_trace: MakeAstSourceTrace
    raw_spec_binding: MakeAstRawSpecBinding
    routes: tuple[MakeAstRoute, ...]
    branches: tuple[MakeAstRoute, ...]
    tools: tuple[MakeAstRoute, ...]
    error_handlers: tuple[MakeAstNode, ...]
    raw_payload: JsonObject
    unknown_fields: JsonObject


class MakeAstScenarioEndpoint(NamedTuple):
    """One scenario input or output declaration."""

    endpoint_id: str
    kind: AstNodeKind
    name: str
    raw_payload: JsonObject


class MakeAstScheduleConfig(NamedTuple):
    """Scenario trigger or schedule configuration."""

    schedule_id: str
    kind: AstNodeKind
    raw_payload: JsonObject


class MakeAstScenario(NamedTuple):
    """Typed scenario metadata for a Make blueprint."""

    name: str
    inputs: tuple[MakeAstScenarioEndpoint, ...]
    outputs: tuple[MakeAstScenarioEndpoint, ...]
    schedule: MakeAstScheduleConfig | None
    metadata: JsonObject


class MakeAstRoot(NamedTuple):
    """Root typed Make blueprint AST."""

    ast_schema_version: int
    scenario: MakeAstScenario
    flow: tuple[MakeAstNode, ...]
    raw_payload: JsonObject
    unknown_fields: JsonObject


type PancakesAstSourceTrace = MakeAstSourceTrace
type PancakesAstRawSpecBinding = MakeAstRawSpecBinding
type PancakesAstFilter = MakeAstFilter
type PancakesAstRoute = MakeAstRoute
type PancakesAstNode = MakeAstNode
type PancakesAstScenarioEndpoint = MakeAstScenarioEndpoint
type PancakesAstScheduleConfig = MakeAstScheduleConfig
type PancakesAstScenario = MakeAstScenario
type PancakesAstRoot = MakeAstRoot
