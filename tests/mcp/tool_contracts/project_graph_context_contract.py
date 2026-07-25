# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for bounded graph RAG project-builder context.

Boundary contract:
- Owns: MCP-layer graph-neighbor snippets used as advisory project-builder
context.
- Must not: include full schemas, raw graph payloads, provider state, or
validation bypasses.
- Allows: synthetic graph metadata and bounded context assertions.
- Split when: project.create or project.next owns persisted graph context
integration.
- Merge when: project_loop tests own the same graph RAG response contract.
"""

from __future__ import annotations

from catalog.knowledge.catalog_graph_dedup import (
    CatalogGraphDedupReport,
    CatalogGraphEdgeInput,
    CatalogGraphEntityKind,
    CatalogGraphNodeInput,
    deduplicate_catalog_graph,
)
from mcp.project_graph_context import (
    ProjectGraphRagRequest,
    build_project_graph_rag_context,
)


def test_project_builder_can_request_bounded_relevant_graph_neighbors() -> None:
    """Project graph context returns only a bounded relevant neighbor set."""
    context = build_project_graph_rag_context(
        graph=_project_graph(),
        request=ProjectGraphRagRequest(
            query_text=(
                "send Slack alerts with filters error handler and data store"
            ),
            neighbor_limit=3,
            snippet_char_limit=140,
        ),
    )

    assert context.status == "ok"
    assert context.returned_neighbor_count == 3
    assert context.hidden_neighbor_count > 0
    assert context.prompt_flood_prevented is True
    assert all(len(snippet.snippet) <= 140 for snippet in context.snippets)
    assert all(
        snippet.full_payload_included is False for snippet in context.snippets
    )
    labels = {snippet.canonical_label for snippet in context.snippets}
    assert labels.intersection(
        {"Slack alert", "Filter branch", "Data store record"}
    )


def test_project_graph_context_requires_inspect_for_full_schema_payloads() -> (
    None
):
    """Search context stays compact and routes full graph details to inspect.

    follow-up.
    """
    context = build_project_graph_rag_context(
        graph=_project_graph(),
        request=ProjectGraphRagRequest(
            query_text="data store filters", neighbor_limit=2
        ),
    )

    assert context.full_schema_included is False
    assert context.inspect_required_for_full_schema is True
    assert context.inspect_follow_up is not None
    assert context.inspect_follow_up.tool == "catalog.inspect"
    assert context.inspect_follow_up.arguments["include_full_schema"] is True


def test_graph_rag_informs_project_builder_without_replacing_validation() -> (
    None
):
    """Graph RAG is advisory for project shape and never replaces AST/linter.

    checks.
    """
    context = build_project_graph_rag_context(
        graph=_project_graph(),
        request=ProjectGraphRagRequest(query_text="error handler data store"),
    )

    assert context.project_builder_uses == (
        "module_selection",
        "filters",
        "error_handlers",
        "data_store_suggestions",
    )
    assert context.graph_replaces_ast_validation is False
    assert context.graph_replaces_linter_validation is False
    assert any(snippet.hard_project_fact for snippet in context.snippets)
    assert any(
        snippet.status in {"low_confidence", "ambiguous"}
        for snippet in context.snippets
    )


def _project_graph() -> CatalogGraphDedupReport:
    return deduplicate_catalog_graph(
        nodes=(
            _node(
                "operation-alert",
                "operation",
                "Slack alert",
                ("send slack",),
                91,
            ),
            _node(
                "operation-filter",
                "operation",
                "Filter branch",
                ("route filter",),
                88,
            ),
            _node(
                "operation-error",
                "operation",
                "Error handler",
                ("fallback",),
                86,
            ),
            _node(
                "entity-datastore",
                "entity",
                "Data store record",
                ("datastore",),
                90,
            ),
            _node(
                "capability-routing",
                "capability",
                "Routing capability",
                ("router",),
                76,
            ),
            _node(
                "capability-raw",
                "capability",
                "Raw schema payload",
                ("schema",),
                42,
            ),
        ),
        edges=(
            _edge("operation-alert", "operation-filter", "uses_filter", 92),
            _edge(
                "operation-filter",
                "entity-datastore",
                "writes_datastore_record",
                84,
            ),
            _edge(
                "operation-error",
                "entity-datastore",
                "handles_error_to_datastore",
                78,
            ),
            _edge(
                "operation-alert",
                "capability-routing",
                "requires_capability",
                74,
            ),
            _edge(
                "capability-raw",
                "entity-datastore",
                "maybe_describes_schema",
                41,
            ),
            _edge(
                "operation-error",
                "capability-raw",
                "ambiguous_capability_link",
                88,
                ambiguous=True,
            ),
        ),
    )


def _node(
    source_node_id: str,
    entity_kind: CatalogGraphEntityKind,
    label: str,
    aliases: tuple[str, ...],
    confidence_score: int,
) -> CatalogGraphNodeInput:
    return CatalogGraphNodeInput(
        source_node_id=source_node_id,
        entity_kind=entity_kind,
        label=label,
        aliases=aliases,
        source_ref=f"synthetic:{source_node_id}",
        confidence_score=confidence_score,
    )


def _edge(
    from_source_node_id: str,
    to_source_node_id: str,
    edge_kind: str,
    confidence_score: int,
    *,
    ambiguous: bool = False,
) -> CatalogGraphEdgeInput:
    return CatalogGraphEdgeInput(
        edge_kind=edge_kind,
        from_source_node_id=from_source_node_id,
        to_source_node_id=to_source_node_id,
        source_ref=f"synthetic:{edge_kind}",
        confidence_score=confidence_score,
        ambiguous=ambiguous,
    )
