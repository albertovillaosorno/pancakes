# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Typed language-neutral IR records.

Boundary contract:
- Owns: immutable IR schema records, node kinds, source references, and edges.
- Must not: parse platform payloads, validate catalogs, or render output JSON.
- Allows: stable DAG primitives shared by Make and future language adapters.
- Split when: node families or value schema records gain independent lifecycles.
- Merge when: another model file duplicates these IR records exactly.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

IR_SCHEMA_VERSION: Final = 1

type JsonObject = dict[str, object]
type IrPathPart = str | int
type IrPortDirection = Literal["input", "output"]
type IrEdgeKind = Literal["control", "data", "error", "metadata"]
type IrNodeKind = Literal[
    "trigger",
    "action",
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
    "schedule",
    "unresolved",
]

IR_NODE_KINDS: Final[frozenset[str]] = frozenset(
    (
        "trigger",
        "action",
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
        "schedule",
        "unresolved",
    )
)


class IrSourceRef(NamedTuple):
    """Trace one IR element back to its source payload."""

    language_id: str
    path: tuple[IrPathPart, ...]
    native_id: str | None
    native_kind: str | None


class IrCapabilityRef(NamedTuple):
    """Optional stable capability identity attached to a node."""

    provider: str
    operation: str
    version: str | None


class IrPort(NamedTuple):
    """One typed input or output boundary for an IR node."""

    name: str
    direction: IrPortDirection
    value_schema: JsonObject


class IrNode(NamedTuple):
    """One language-neutral automation DAG node."""

    node_id: str
    kind: IrNodeKind
    label: str
    capability: IrCapabilityRef | None
    inputs: tuple[IrPort, ...]
    outputs: tuple[IrPort, ...]
    metadata: JsonObject
    source_refs: tuple[IrSourceRef, ...]


class IrEdge(NamedTuple):
    """One directed relationship between two IR nodes."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    kind: IrEdgeKind
    condition: JsonObject | None
    metadata: JsonObject
    source_refs: tuple[IrSourceRef, ...]


class IrGraph(NamedTuple):
    """One language-neutral automation DAG."""

    graph_id: str
    nodes: tuple[IrNode, ...]
    edges: tuple[IrEdge, ...]
    metadata: JsonObject


class IrDocument(NamedTuple):
    """Root IR document produced by a language adapter."""

    ir_schema_version: int
    source_language_id: str
    graph: IrGraph
    source_payload_fingerprint: str | None
    metadata: JsonObject
