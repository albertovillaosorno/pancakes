# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""IR graph validation helpers.

Boundary contract:
- Owns: local structural checks for the language-neutral IR DAG.
- Must not: perform platform importability checks, catalog lookup, or repair
advice.
- Allows: deterministic duplicate-node, missing-edge-node, and cycle
diagnostics.
- Split when: validation grows into semantic rules owned by another bounded
context.
- Merge when: another IR module duplicates these graph checks exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ir.models import IrGraph

type IrGraphFindingKind = Literal[
    "duplicate_node_id", "missing_edge_node", "cycle"
]


class IrGraphValidationFinding(NamedTuple):
    """One deterministic IR graph structural finding."""

    kind: IrGraphFindingKind
    message: str
    node_id: str | None
    edge_id: str | None


def validate_ir_graph(graph: IrGraph) -> tuple[IrGraphValidationFinding, ...]:
    """Return deterministic structural findings for an IR graph."""
    findings: list[IrGraphValidationFinding] = []
    node_ids: set[str] = set()
    duplicate_node_ids: set[str] = set()

    for node in graph.nodes:
        if node.node_id in node_ids:
            duplicate_node_ids.add(node.node_id)
        node_ids.add(node.node_id)

    findings.extend(
        [
            IrGraphValidationFinding(
                kind="duplicate_node_id",
                message=f"Duplicate IR node id: {node_id}",
                node_id=node_id,
                edge_id=None,
            )
            for node_id in sorted(duplicate_node_ids)
        ]
    )

    adjacency: dict[str, list[str]] = {
        node_id: [] for node_id in sorted(node_ids)
    }
    for edge in graph.edges:
        source_exists = edge.source_node_id in node_ids
        target_exists = edge.target_node_id in node_ids
        if not source_exists:
            findings.append(
                IrGraphValidationFinding(
                    kind="missing_edge_node",
                    message=(
                        f"IR edge source node is missing: {edge.source_node_id}"
                    ),
                    node_id=edge.source_node_id,
                    edge_id=edge.edge_id,
                )
            )
        if not target_exists:
            findings.append(
                IrGraphValidationFinding(
                    kind="missing_edge_node",
                    message=(
                        f"IR edge target node is missing: {edge.target_node_id}"
                    ),
                    node_id=edge.target_node_id,
                    edge_id=edge.edge_id,
                )
            )
        if source_exists and target_exists:
            adjacency[edge.source_node_id].append(edge.target_node_id)

    cycle_node = cycle_start_node(adjacency)
    if cycle_node is not None:
        findings.append(
            IrGraphValidationFinding(
                kind="cycle",
                message=(
                    f"IR graph must be acyclic; cycle reaches node:{cycle_node}"
                ),
                node_id=cycle_node,
                edge_id=None,
            )
        )

    return tuple(findings)


def cycle_start_node(adjacency: Mapping[str, Sequence[str]]) -> str | None:
    """Return one node reached by a cycle, or None when the graph is acyclic."""
    states: dict[str, int] = {}

    def visit(node_id: str) -> str | None:
        states[node_id] = 1
        for child_id in sorted(adjacency[node_id]):
            child_state = states.get(child_id, 0)
            if child_state == 1:
                return child_id
            if child_state == 0:
                detected = visit(child_id)
                if detected is not None:
                    return detected
        states[node_id] = 2
        return None

    for node_id in sorted(adjacency):
        if states.get(node_id, 0) != 0:
            continue
        detected = visit(node_id)
        if detected is not None:
            return detected
    return None
