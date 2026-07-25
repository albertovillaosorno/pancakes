# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.scenario-builder-micro-tools
# - 001064#repo.make-knowledge.structural-ssot
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Bounded graph RAG context for local project building.

Boundary contract:
- Owns: compact graph-neighbor snippets that can inform local project-builder
decisions.
- Must not: include full schemas, raw payload walls, provider state, or
validation bypasses.
- Allows: advisory module/filter/error-handler/data-store suggestions from graph
metadata.
- Split when: project.create or project.next owns persisted graph context state
directly.
- Merge when: project_loop owns the same bounded graph-neighbor response
contract.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from catalog.knowledge.catalog_graph_dedup import (
        CatalogGraphDedupReport,
        CatalogGraphEdgeRecord,
        CatalogGraphNodeRecord,
    )

GRAPH_RAG_DEFAULT_NEIGHBOR_LIMIT: Final = 5
GRAPH_RAG_MAX_NEIGHBOR_LIMIT: Final = 12
GRAPH_RAG_DEFAULT_SNIPPET_CHARS: Final = 240
GRAPH_RAG_MAX_SNIPPET_CHARS: Final = 600
GRAPH_RAG_TOKEN_PATTERN: Final = re.compile(r"[a-z0-9]+")
PROJECT_BUILDER_GRAPH_RAG_USES: Final = (
    "module_selection",
    "filters",
    "error_handlers",
    "data_store_suggestions",
)


class ProjectGraphRagRequest(NamedTuple):
    """Request for bounded graph-neighbor context."""

    query_text: str
    focus_node_ids: tuple[str, ...] = ()
    neighbor_limit: int = GRAPH_RAG_DEFAULT_NEIGHBOR_LIMIT
    snippet_char_limit: int = GRAPH_RAG_DEFAULT_SNIPPET_CHARS


class ProjectGraphRagSnippet(NamedTuple):
    """One compact graph-neighbor snippet for project-builder prompts."""

    node_id: str
    canonical_label: str
    entity_kind: str
    edge_kind: str
    relationship: str
    confidence_score: int
    status: str
    hard_project_fact: bool
    provenance_refs: tuple[str, ...]
    snippet: str
    full_payload_included: bool


class ProjectGraphInspectFollowUp(NamedTuple):
    """Inspect-style follow-up required for full graph payloads."""

    tool: str
    arguments: dict[str, object]
    reason: str


class ProjectGraphRagContext(NamedTuple):
    """Bounded advisory graph context for local project building."""

    status: str
    query_text: str
    returned_neighbor_count: int
    hidden_neighbor_count: int
    snippets: tuple[ProjectGraphRagSnippet, ...]
    max_snippet_chars: int
    full_schema_included: bool
    inspect_required_for_full_schema: bool
    inspect_follow_up: ProjectGraphInspectFollowUp | None
    project_builder_uses: tuple[str, ...]
    graph_replaces_ast_validation: bool
    graph_replaces_linter_validation: bool
    prompt_flood_prevented: bool


class _NeighborCandidate(NamedTuple):
    score: int
    node: CatalogGraphNodeRecord
    edge: CatalogGraphEdgeRecord
    relationship: str


def build_project_graph_rag_context(
    *,
    graph: CatalogGraphDedupReport,
    request: ProjectGraphRagRequest,
) -> ProjectGraphRagContext:
    """Return bounded graph-neighbor snippets for local project-building.

    context.
    """
    neighbor_limit = _bounded_int(
        request.neighbor_limit,
        default=GRAPH_RAG_DEFAULT_NEIGHBOR_LIMIT,
        upper=GRAPH_RAG_MAX_NEIGHBOR_LIMIT,
    )
    snippet_char_limit = _bounded_int(
        request.snippet_char_limit,
        default=GRAPH_RAG_DEFAULT_SNIPPET_CHARS,
        upper=GRAPH_RAG_MAX_SNIPPET_CHARS,
    )
    candidates = _ranked_neighbor_candidates(graph=graph, request=request)
    visible_candidates = candidates[:neighbor_limit]
    snippets = tuple(
        _snippet(candidate=candidate, snippet_char_limit=snippet_char_limit)
        for candidate in visible_candidates
    )
    inspect_follow_up = _inspect_follow_up(snippets)
    return ProjectGraphRagContext(
        status="ok",
        query_text=request.query_text,
        returned_neighbor_count=len(snippets),
        hidden_neighbor_count=max(len(candidates) - len(snippets), 0),
        snippets=snippets,
        max_snippet_chars=snippet_char_limit,
        full_schema_included=False,
        inspect_required_for_full_schema=True,
        inspect_follow_up=inspect_follow_up,
        project_builder_uses=PROJECT_BUILDER_GRAPH_RAG_USES,
        graph_replaces_ast_validation=False,
        graph_replaces_linter_validation=False,
        prompt_flood_prevented=len(candidates) > len(snippets),
    )


def _ranked_neighbor_candidates(
    *,
    graph: CatalogGraphDedupReport,
    request: ProjectGraphRagRequest,
) -> tuple[_NeighborCandidate, ...]:
    nodes_by_id = {node.node_id: node for node in graph.nodes}
    query_terms = _tokens(request.query_text)
    focus_node_ids = frozenset(request.focus_node_ids)
    candidates: list[_NeighborCandidate] = []
    for edge in graph.edges:
        from_node = nodes_by_id.get(edge.from_node_id)
        to_node = nodes_by_id.get(edge.to_node_id)
        if from_node is None or to_node is None:
            continue
        candidates.extend(
            _edge_neighbor_candidates(
                edge=edge,
                from_node=from_node,
                to_node=to_node,
                query_terms=query_terms,
                focus_node_ids=focus_node_ids,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.node.entity_kind,
                candidate.node.canonical_label.casefold(),
                candidate.edge.edge_kind,
                candidate.node.node_id,
            ),
        )
    )


def _edge_neighbor_candidates(
    *,
    edge: CatalogGraphEdgeRecord,
    from_node: CatalogGraphNodeRecord,
    to_node: CatalogGraphNodeRecord,
    query_terms: frozenset[str],
    focus_node_ids: frozenset[str],
) -> tuple[_NeighborCandidate, ...]:
    candidates: list[_NeighborCandidate] = []
    for node, relationship in ((to_node, "outbound"), (from_node, "inbound")):
        score = _candidate_score(
            node=node,
            edge=edge,
            query_terms=query_terms,
            focus_node_ids=focus_node_ids,
        )
        if score <= 0:
            continue
        candidates.append(
            _NeighborCandidate(
                score=score,
                node=node,
                edge=edge,
                relationship=relationship,
            )
        )
    return tuple(candidates)


def _candidate_score(
    *,
    node: CatalogGraphNodeRecord,
    edge: CatalogGraphEdgeRecord,
    query_terms: frozenset[str],
    focus_node_ids: frozenset[str],
) -> int:
    score = 0
    node_terms = _node_terms(node)
    edge_terms = _tokens(edge.edge_kind)
    if node.node_id in focus_node_ids:
        score += 500
    score += 120 * len(query_terms.intersection(node_terms))
    score += 80 * len(query_terms.intersection(edge_terms))
    score += edge.confidence_score
    if edge.hard_project_fact:
        score += 50
    if edge.status == "ambiguous":
        score -= 60
    if edge.status == "low_confidence":
        score -= 40
    return score


def _snippet(
    *,
    candidate: _NeighborCandidate,
    snippet_char_limit: int,
) -> ProjectGraphRagSnippet:
    edge = candidate.edge
    node = candidate.node
    text = (
        f"{node.entity_kind} {node.canonical_label} via {edge.edge_kind}; "
        f"status={edge.status}; confidence={edge.confidence_score}; "
        f"provenance={', '.join(edge.provenance_refs)}"
    )
    return ProjectGraphRagSnippet(
        node_id=node.node_id,
        canonical_label=node.canonical_label,
        entity_kind=node.entity_kind,
        edge_kind=edge.edge_kind,
        relationship=candidate.relationship,
        confidence_score=edge.confidence_score,
        status=edge.status,
        hard_project_fact=edge.hard_project_fact,
        provenance_refs=edge.provenance_refs,
        snippet=_truncate(text, snippet_char_limit),
        full_payload_included=False,
    )


def _inspect_follow_up(
    snippets: tuple[ProjectGraphRagSnippet, ...],
) -> ProjectGraphInspectFollowUp | None:
    if not snippets:
        return None
    return ProjectGraphInspectFollowUp(
        tool="catalog.inspect",
        arguments={
            "node_ids": tuple(snippet.node_id for snippet in snippets),
            "include_full_schema": True,
        },
        reason=(
            "Full graph payloads require inspect-style follow-up, not search"
            "context."
        ),
    )


def _node_terms(node: CatalogGraphNodeRecord) -> frozenset[str]:
    return frozenset(
        term
        for value in (node.canonical_label, node.entity_kind, *node.aliases)
        for term in _tokens(value)
    )


def _tokens(value: str) -> frozenset[str]:
    return frozenset(GRAPH_RAG_TOKEN_PATTERN.findall(value.casefold()))


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 3]}..."


def _bounded_int(value: int, *, default: int, upper: int) -> int:
    if isinstance(value, bool):
        message = "Graph RAG bounds must be integers."
        raise TypeError(message)
    if value <= 0:
        return default
    return min(value, upper)
