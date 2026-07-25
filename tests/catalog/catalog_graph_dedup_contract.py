# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for catalog graph deduplication confidence and provenance metadata.

Boundary contract:
- Owns: pure graph node/edge dedup, confidence status, and
  provenance merge tests.
- Must not: write SQLite, call providers, author catalog answers, or
  inspect live Make state.
- Allows: synthetic node and edge inputs with deterministic graph
  metadata assertions.
- Split when: persistent graph projection owns these dedup contracts directly.
- Merge when: catalog graph projection tests own equivalent dedup behavior.
"""

from __future__ import annotations

from catalog.knowledge.catalog_graph_dedup import (
    CatalogGraphEdgeInput,
    CatalogGraphNodeInput,
    deduplicate_catalog_graph,
)


def test_duplicate_operation_entity_and_capability_nodes_collapse() -> None:
    """Duplicate operation, entity, and capability nodes collapse."""
    report = deduplicate_catalog_graph(nodes=_duplicate_nodes(), edges=())
    nodes_by_kind = {node.entity_kind: node for node in report.nodes}

    assert len(report.nodes) == 3
    assert nodes_by_kind["operation"].source_node_ids == (
        "operation-a",
        "operation-b",
    )
    assert nodes_by_kind["entity"].source_node_ids == ("entity-a", "entity-b")
    assert nodes_by_kind["capability"].source_node_ids == (
        "capability-a",
        "capability-b",
    )
    assert nodes_by_kind["operation"].confidence_score == 91
    assert nodes_by_kind["entity"].provenance_refs == (
        "semantic-unit:email-entity",
        "graph-review:email-entity",
    )
    assert len(report.duplicate_links) == 3
    assert {link.duplicate_kind for link in report.duplicate_links} == {"node"}


def test_duplicate_edges_merge_provenance_and_promote_links() -> None:
    """Equivalent edges preserve provenance and max confidence."""
    report = deduplicate_catalog_graph(
        nodes=_duplicate_nodes(),
        edges=(
            CatalogGraphEdgeInput(
                edge_kind="operation_outputs_entity",
                from_source_node_id="operation-a",
                to_source_node_id="entity-a",
                source_ref="semantic-unit:send-email",
                confidence_score=82,
            ),
            CatalogGraphEdgeInput(
                edge_kind="operation_outputs_entity",
                from_source_node_id="operation-b",
                to_source_node_id="entity-b",
                source_ref="graph-review:send-email",
                confidence_score=94,
            ),
        ),
    )

    assert len(report.edges) == 1
    edge = report.edges[0]
    assert edge.status == "promoted_candidate"
    assert edge.hard_project_fact is True
    assert edge.rollback_safe is True
    assert edge.confidence_score == 94
    assert edge.provenance_refs == (
        "graph-review:send-email",
        "semantic-unit:send-email",
    )
    assert report.promoted_edge_count == 1
    assert {link.duplicate_kind for link in report.duplicate_links} == {
        "edge",
        "node",
    }


def test_low_confidence_or_ambiguous_capability_links_do_not_promote() -> None:
    """Weak or ambiguous edges remain advisory, not hard facts."""
    report = deduplicate_catalog_graph(
        nodes=_duplicate_nodes(),
        edges=(
            CatalogGraphEdgeInput(
                edge_kind="operation_requires_capability",
                from_source_node_id="operation-a",
                to_source_node_id="capability-a",
                source_ref="weak-semantic-unit:send-email",
                confidence_score=45,
            ),
            CatalogGraphEdgeInput(
                edge_kind="operation_requires_capability",
                from_source_node_id="operation-a",
                to_source_node_id="entity-a",
                source_ref="ambiguous-semantic-unit:send-email",
                confidence_score=88,
                ambiguous=True,
            ),
        ),
    )
    edges_by_status = {edge.status: edge for edge in report.edges}

    assert edges_by_status["low_confidence"].hard_project_fact is False
    assert edges_by_status["ambiguous"].hard_project_fact is False
    assert edges_by_status["low_confidence"].rollback_safe is True
    assert edges_by_status["ambiguous"].rollback_safe is True
    assert report.promoted_edge_count == 0
    assert report.low_confidence_edge_count == 1
    assert report.ambiguous_edge_count == 1


def _duplicate_nodes() -> tuple[CatalogGraphNodeInput, ...]:
    return (
        CatalogGraphNodeInput(
            source_node_id="operation-a",
            entity_kind="operation",
            label="Send Email",
            aliases=("send_email",),
            source_ref="semantic-unit:send-email",
            confidence_score=88,
        ),
        CatalogGraphNodeInput(
            source_node_id="operation-b",
            entity_kind="operation",
            label="send email",
            aliases=("Gmail send",),
            source_ref="graph-review:send-email",
            confidence_score=91,
        ),
        CatalogGraphNodeInput(
            source_node_id="entity-a",
            entity_kind="entity",
            label="Email Message",
            aliases=("email_message",),
            source_ref="semantic-unit:email-entity",
            confidence_score=84,
        ),
        CatalogGraphNodeInput(
            source_node_id="entity-b",
            entity_kind="entity",
            label="email message",
            aliases=("Gmail message",),
            source_ref="graph-review:email-entity",
            confidence_score=89,
        ),
        CatalogGraphNodeInput(
            source_node_id="capability-a",
            entity_kind="capability",
            label="Outbound Email Capability",
            aliases=("outbound_email_capability",),
            source_ref="semantic-unit:email-capability",
            confidence_score=73,
        ),
        CatalogGraphNodeInput(
            source_node_id="capability-b",
            entity_kind="capability",
            label="outbound email capability",
            aliases=("send mail",),
            source_ref="graph-review:email-capability",
            confidence_score=77,
        ),
    )
