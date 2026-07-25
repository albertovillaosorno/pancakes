# Repository header: begin
# Provenance source mode: source_refs
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make adapter translation into Pancakes AST and IR.

Boundary contract:
- Owns: Make payload translation into Pancakes AST and language-neutral IR.
- Must not: validate catalogs, call live Make services, or claim other
platforms.
- Allows: source-preserving Make JSON projection from a Pancakes AST.
- Split when: another source language gains its own tested adapter.
- Merge when: another Make adapter duplicates this translation contract exactly.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from blueprints.ast.parser import normalize_json_object, parse_make_ast
from ir.models import (
    IR_SCHEMA_VERSION,
    IrCapabilityRef,
    IrDocument,
    IrEdge,
    IrGraph,
    IrNode,
    IrSourceRef,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.ast.models import (
        AstNodeKind,
        JsonObject,
        MakeAstFilter,
        MakeAstNode,
        MakeAstRoot,
        MakeAstRoute,
        MakeAstScenarioEndpoint,
        MakeAstScheduleConfig,
        MakeAstSourceTrace,
        PancakesAstRoot,
    )
    from ir.models import IrEdgeKind, IrNodeKind

MAKE_LANGUAGE_ID: Final = "make"
PANCAKES_AST_MODEL_ID: Final = "pancakes.ast"
MAKE_BLUEPRINT_OUTPUT_LANGUAGE_ID: Final = "make.blueprint-json"
AST_TO_IR_NODE_KIND: Final[Mapping[str, str]] = {
    "module": "action ",
    "router": "router ",
    "route": "route ",
    "filter": "filter ",
    "iterator": "iterator ",
    "aggregator": "aggregator ",
    "webhook": "webhook ",
    "http_api": "http_api ",
    "data_store": "data_store ",
    "ai_agent": "ai_agent ",
    "mcp_tool": "mcp_tool ",
    "scenario_input": "scenario_input ",
    "scenario_output": "scenario_output ",
    "error_handler": "error_handler ",
    "schedule_trigger": "schedule ",
    "unresolved": "unresolved",
}


class MakeAdapterProjection(NamedTuple):
    """Source-preserving Make adapter projection."""

    pancakes_ast: PancakesAstRoot
    ir_document: IrDocument
    make_payload: JsonObject


class _ProjectionBuilder:
    """Mutable builder used only inside one deterministic projection."""

    def __init__(self) -> None:
        """Create one empty projection builder."""
        self.nodes: list[IrNode] = []
        self.edges: list[IrEdge] = []


def parse_make_blueprint_to_pancakes_ast(
    payload: JsonObject,
) -> PancakesAstRoot:
    """Parse Make blueprint JSON through the Pancakes AST compatibility runtime.

    Returns:
        The Pancakes AST root carrying current Make-compatible record aliases.
    """
    return parse_make_ast(payload)


def translate_make_blueprint_to_pancakes_projection(
    payload: JsonObject,
) -> MakeAdapterProjection:
    """Translate Make JSON into Pancakes AST, IR, and source-preserving Make.

    output.

    Returns:
        The complete Make adapter projection.
    """
    pancakes_ast = parse_make_blueprint_to_pancakes_ast(payload)
    return MakeAdapterProjection(
        pancakes_ast=pancakes_ast,
        ir_document=translate_pancakes_ast_to_ir(pancakes_ast),
        make_payload=render_pancakes_ast_to_make_blueprint_payload(
            pancakes_ast
        ),
    )


def translate_make_blueprint_to_ir(payload: JsonObject) -> IrDocument:
    """Translate Make blueprint JSON into language-neutral Pancakes IR.

    Returns:
        The IR document produced by the Make adapter.
    """
    return translate_pancakes_ast_to_ir(
        parse_make_blueprint_to_pancakes_ast(payload)
    )


def translate_pancakes_ast_to_ir(root: PancakesAstRoot) -> IrDocument:
    """Translate a Pancakes AST root into language-neutral Pancakes IR.

    Returns:
        The IR document with Make source references preserved as adapter
        evidence.
    """
    builder = _ProjectionBuilder()
    _append_scenario_boundary_nodes(builder, root)
    _append_flow(
        builder, root.flow, entry_node_id=_scenario_entry_node_id(root)
    )
    graph = IrGraph(
        graph_id=_graph_id(root),
        nodes=tuple(builder.nodes),
        edges=tuple(builder.edges),
        metadata={
            "product_ast": PANCAKES_AST_MODEL_ID,
            "source_language": MAKE_LANGUAGE_ID,
            "output_language": MAKE_BLUEPRINT_OUTPUT_LANGUAGE_ID,
        },
    )
    return IrDocument(
        ir_schema_version=IR_SCHEMA_VERSION,
        source_language_id=MAKE_LANGUAGE_ID,
        graph=graph,
        source_payload_fingerprint=_payload_fingerprint(root.raw_payload),
        metadata={
            "adapter": "languages.make",
            "pancakes_ast": PANCAKES_AST_MODEL_ID,
        },
    )


def render_pancakes_ast_to_make_blueprint_payload(
    root: PancakesAstRoot,
) -> JsonObject:
    """Render a source-preserving Make blueprint payload from a Pancakes AST.

    root.

    Returns:
        The normalized Make blueprint payload represented by the AST.
    """
    payload = _copy_json_object(root.raw_payload)
    payload["name"] = root.scenario.name
    payload["flow"] = [
        _copy_json_object(node.raw_payload) for node in root.flow
    ]
    return normalize_json_object(payload)


def _append_scenario_boundary_nodes(
    builder: _ProjectionBuilder, root: MakeAstRoot
) -> None:
    for endpoint in (*root.scenario.inputs, *root.scenario.outputs):
        builder.nodes.append(_endpoint_ir_node(endpoint))
    if root.scenario.schedule is not None:
        builder.nodes.append(_schedule_ir_node(root.scenario.schedule))


def _append_flow(
    builder: _ProjectionBuilder,
    flow: tuple[MakeAstNode, ...],
    *,
    entry_node_id: str | None,
) -> None:
    previous_node_id = entry_node_id
    for node in flow:
        builder.nodes.append(_ast_ir_node(node))
        if previous_node_id is not None:
            builder.edges.append(
                _ir_edge(
                    source_node_id=previous_node_id,
                    target_node_id=node.node_id,
                    kind="control",
                    source_trace=node.source_trace,
                )
            )
        _append_node_children(builder, node)
        previous_node_id = node.node_id


def _append_node_children(
    builder: _ProjectionBuilder, node: MakeAstNode
) -> None:
    for route in (*node.routes, *node.branches, *node.tools):
        route_node_id = _route_node_id(route)
        builder.nodes.append(_route_ir_node(route))
        builder.edges.append(
            _ir_edge(
                source_node_id=node.node_id,
                target_node_id=route_node_id,
                kind="control",
                source_trace=route.source_trace,
            )
        )
        route_entry_node_id = route_node_id
        if route.filter is not None:
            filter_node = _filter_ir_node(route.filter)
            builder.nodes.append(filter_node)
            builder.edges.append(
                _ir_edge(
                    source_node_id=route_node_id,
                    target_node_id=filter_node.node_id,
                    kind="control",
                    source_trace=route.source_trace,
                )
            )
            route_entry_node_id = filter_node.node_id
        _append_flow(builder, route.flow, entry_node_id=route_entry_node_id)
    if node.error_handlers:
        _append_flow(builder, node.error_handlers, entry_node_id=node.node_id)
        for handler in node.error_handlers:
            builder.edges.append(
                _ir_edge(
                    source_node_id=node.node_id,
                    target_node_id=handler.node_id,
                    kind="error",
                    source_trace=handler.source_trace,
                )
            )


def _ast_ir_node(node: MakeAstNode) -> IrNode:
    return IrNode(
        node_id=node.node_id,
        kind=_ir_node_kind(node.kind),
        label=node.label,
        capability=_capability_ref(
            node.module_token, fallback_operation=node.kind
        ),
        inputs=(),
        outputs=(),
        metadata={
            "ast_kind": node.kind,
            "module_token": node.module_token,
            "raw_spec_status": node.raw_spec_binding.status,
            "raw_spec_issues": list(node.raw_spec_binding.issues),
        },
        source_refs=(_source_ref(node.source_trace, native_kind=node.kind),),
    )


def _endpoint_ir_node(endpoint: MakeAstScenarioEndpoint) -> IrNode:
    return IrNode(
        node_id=endpoint.endpoint_id,
        kind=_ir_node_kind(endpoint.kind),
        label=endpoint.name,
        capability=None,
        inputs=(),
        outputs=(),
        metadata={"ast_kind": endpoint.kind},
        source_refs=(
            IrSourceRef(
                language_id=MAKE_LANGUAGE_ID,
                path=("metadata", endpoint.kind, endpoint.name),
                native_id=endpoint.endpoint_id,
                native_kind=endpoint.kind,
            ),
        ),
    )


def _schedule_ir_node(schedule: MakeAstScheduleConfig) -> IrNode:
    return IrNode(
        node_id=schedule.schedule_id,
        kind="schedule",
        label=schedule.schedule_id,
        capability=None,
        inputs=(),
        outputs=(),
        metadata={"ast_kind": schedule.kind},
        source_refs=(
            IrSourceRef(
                language_id=MAKE_LANGUAGE_ID,
                path=("metadata", "schedule"),
                native_id=schedule.schedule_id,
                native_kind=schedule.kind,
            ),
        ),
    )


def _route_ir_node(route: MakeAstRoute) -> IrNode:
    return IrNode(
        node_id=_route_node_id(route),
        kind="route",
        label=route.route_id,
        capability=None,
        inputs=(),
        outputs=(),
        metadata={"container_kind": route.container_kind},
        source_refs=(_source_ref(route.source_trace, native_kind="route"),),
    )


def _filter_ir_node(filter_value: MakeAstFilter) -> IrNode:
    return IrNode(
        node_id=f"filter:{filter_value.filter_id}",
        kind="filter",
        label=filter_value.name,
        capability=None,
        inputs=(),
        outputs=(),
        metadata={"conditions": _copy_json_object(filter_value.conditions)},
        source_refs=(),
    )


def _ir_node_kind(kind: AstNodeKind) -> IrNodeKind:
    return cast("IrNodeKind", AST_TO_IR_NODE_KIND[kind])


def _capability_ref(
    module_token: str, *, fallback_operation: str
) -> IrCapabilityRef | None:
    if not module_token:
        return None
    provider, _, operation = module_token.partition(":")
    return IrCapabilityRef(
        provider=provider or MAKE_LANGUAGE_ID,
        operation=operation or fallback_operation,
        version=None,
    )


def _source_ref(
    source_trace: MakeAstSourceTrace, *, native_kind: str
) -> IrSourceRef:
    return IrSourceRef(
        language_id=MAKE_LANGUAGE_ID,
        path=source_trace.path,
        native_id=source_trace.raw_node_id,
        native_kind=native_kind,
    )


def _ir_edge(
    *,
    source_node_id: str,
    target_node_id: str,
    kind: IrEdgeKind,
    source_trace: MakeAstSourceTrace,
) -> IrEdge:
    return IrEdge(
        edge_id=f"{kind}:{source_node_id}->{target_node_id}",
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        kind=kind,
        condition=None,
        metadata={},
        source_refs=(_source_ref(source_trace, native_kind=kind),),
    )


def _route_node_id(route: MakeAstRoute) -> str:
    return f"route:{route.route_id}"


def _scenario_entry_node_id(root: MakeAstRoot) -> str | None:
    if root.scenario.schedule is not None:
        return root.scenario.schedule.schedule_id
    if root.scenario.inputs:
        return root.scenario.inputs[0].endpoint_id
    return None


def _graph_id(root: MakeAstRoot) -> str:
    return f"pancakes:{root.scenario.name}"


def _payload_fingerprint(payload: JsonObject) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _copy_json_object(value: JsonObject) -> JsonObject:
    return cast("JsonObject", json.loads(json.dumps(value, sort_keys=True)))
