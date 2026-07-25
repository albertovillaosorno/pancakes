# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for the language-neutral IR graph.

Boundary contract:
- Owns: fast structural tests for the public IR models and DAG validation.
- Must not: parse Make JSON, contact live services, or test platform rendering.
- Allows: synthetic IR graphs that prove language-neutral shape and failure
  modes.
- Split when: adapter round-trip tests become executable.
- Merge when: another IR test owns this exact graph contract.
"""

from __future__ import annotations

from ir import (
    IR_SCHEMA_VERSION,
    IrCapabilityRef,
    IrDocument,
    IrEdge,
    IrGraph,
    IrNode,
    IrNodeKind,
    IrPort,
    IrSourceRef,
    JsonObject,
    validate_ir_graph,
)


def test_ir_document_models_make_as_one_source_language_adapter() -> None:
    """IR records keep Make as source evidence, not as the product core."""
    graph = valid_graph()
    document = IrDocument(
        ir_schema_version=IR_SCHEMA_VERSION,
        source_language_id="make",
        graph=graph,
        source_payload_fingerprint="sha256:demo",
        metadata={"supported_language_today": "make"},
    )

    assert document.source_language_id == "make"
    assert document.graph.nodes[0].source_refs[0].language_id == "make"
    assert document.graph.nodes[0].kind == "trigger"
    assert document.graph.nodes[1].kind == "action"
    assert document.graph.edges[0].kind == "control"
    assert validate_ir_graph(document.graph) == ()


def test_ir_graph_validation_reports_duplicate_missing_and_cycle_findings() -> (
    None
):
    """IR validation detects structural graph failures deterministically."""
    start = node("start", "trigger")
    duplicate_start = node("start", "action")
    end = node("end", "action")
    graph = IrGraph(
        graph_id="invalid",
        nodes=(start, duplicate_start, end),
        edges=(
            edge("start-to-end", "start", "end"),
            edge("end-to-start", "end", "start"),
            edge("missing-to-end", "missing", "end"),
        ),
        metadata=empty_json(),
    )

    findings = validate_ir_graph(graph)
    assert [finding.kind for finding in findings] == [
        "duplicate_node_id",
        "missing_edge_node",
        "cycle",
    ]
    assert findings[0].node_id == "start"
    assert findings[1].edge_id == "missing-to-end"
    assert findings[2].node_id == "end"


def valid_graph() -> IrGraph:
    """Return a minimal valid automation DAG."""
    return IrGraph(
        graph_id="lead-routing",
        nodes=(
            node("webhook", "trigger"),
            node("create-record", "action"),
        ),
        edges=(edge("webhook-to-create-record", "webhook", "create-record"),),
        metadata={"graph_kind": "automation"},
    )


def node(node_id: str, kind: IrNodeKind) -> IrNode:
    """Return one synthetic IR node."""
    return IrNode(
        node_id=node_id,
        kind=kind,
        label=node_id.replace("-", " ").title(),
        capability=IrCapabilityRef(
            provider="generic", operation=kind, version=None
        ),
        inputs=(
            IrPort(
                name="payload", direction="input", value_schema=empty_json()
            ),
        ),
        outputs=(
            IrPort(
                name="result", direction="output", value_schema=empty_json()
            ),
        ),
        metadata=empty_json(),
        source_refs=(
            IrSourceRef(
                language_id="make",
                path=("flow", 0),
                native_id=node_id,
                native_kind=kind,
            ),
        ),
    )


def edge(edge_id: str, source_node_id: str, target_node_id: str) -> IrEdge:
    """Return one synthetic control edge."""
    return IrEdge(
        edge_id=edge_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        kind="control",
        condition=None,
        metadata=empty_json(),
        source_refs=(),
    )


def empty_json() -> JsonObject:
    """Return one empty JSON object."""
    return {}
