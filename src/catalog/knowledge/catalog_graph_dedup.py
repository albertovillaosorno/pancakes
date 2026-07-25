# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - repo.catalog-plan-artifact.workspace-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Deterministic catalog graph deduplication and promotion metadata.

Boundary contract:
- Owns: pure node/edge deduplication, provenance merging, and confidence status.
- Must not: write SQLite rows, author catalog answers, call providers, or
inspect live state.
- Allows: rollback-safe records that upstream projection code can persist later.
- Split when: persisted graph projection owns these records directly.
- Merge when: catalog graph projection owns equivalent dedup and promotion
metadata.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final, Literal, NamedTuple

type CatalogGraphEntityKind = Literal["operation", "entity", "capability"]
type CatalogGraphPromotionStatus = Literal[
    "promoted_candidate",
    "low_confidence",
    "ambiguous",
]

CATALOG_GRAPH_HARD_FACT_CONFIDENCE_FLOOR: Final = 70
CATALOG_GRAPH_MAX_CONFIDENCE: Final = 100
NORMALIZED_GRAPH_KEY_PATTERN: Final = re.compile(r"[a-z0-9]+")


class CatalogGraphNodeInput(NamedTuple):
    """One raw graph node candidate before deduplication."""

    source_node_id: str
    entity_kind: CatalogGraphEntityKind
    label: str
    aliases: tuple[str, ...]
    source_ref: str
    confidence_score: int


class CatalogGraphEdgeInput(NamedTuple):
    """One raw graph edge candidate before deduplication."""

    edge_kind: str
    from_source_node_id: str
    to_source_node_id: str
    source_ref: str
    confidence_score: int
    ambiguous: bool = False


class CatalogGraphDuplicateLink(NamedTuple):
    """One source graph node or edge linked into a deterministic canonical.

    record.
    """

    source_id: str
    canonical_id: str
    duplicate_kind: str
    reason: str


class CatalogGraphNodeRecord(NamedTuple):
    """One deduplicated rollback-safe graph node record."""

    node_id: str
    entity_kind: CatalogGraphEntityKind
    canonical_label: str
    normalized_key: str
    aliases: tuple[str, ...]
    source_node_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    confidence_score: int


class CatalogGraphEdgeRecord(NamedTuple):
    """One deduplicated graph edge with project-building promotion metadata."""

    edge_id: str
    edge_kind: str
    from_node_id: str
    to_node_id: str
    provenance_refs: tuple[str, ...]
    confidence_score: int
    status: CatalogGraphPromotionStatus
    hard_project_fact: bool
    rollback_safe: bool


class CatalogGraphDedupReport(NamedTuple):
    """Deterministic graph deduplication result."""

    nodes: tuple[CatalogGraphNodeRecord, ...]
    edges: tuple[CatalogGraphEdgeRecord, ...]
    duplicate_links: tuple[CatalogGraphDuplicateLink, ...]
    promoted_edge_count: int
    low_confidence_edge_count: int
    ambiguous_edge_count: int


def deduplicate_catalog_graph(
    *,
    nodes: tuple[CatalogGraphNodeInput, ...],
    edges: tuple[CatalogGraphEdgeInput, ...],
) -> CatalogGraphDedupReport:
    """Return the computed result for the caller."""
    node_records, node_links, source_to_node_id = _deduplicate_nodes(nodes)
    edge_records, edge_links = _deduplicate_edges(
        edges=edges, source_to_node_id=source_to_node_id
    )
    duplicate_links = tuple(
        sorted((*node_links, *edge_links), key=lambda link: link.source_id)
    )
    return CatalogGraphDedupReport(
        nodes=node_records,
        edges=edge_records,
        duplicate_links=duplicate_links,
        promoted_edge_count=sum(
            1 for edge in edge_records if edge.hard_project_fact
        ),
        low_confidence_edge_count=sum(
            1 for edge in edge_records if edge.status == "low_confidence"
        ),
        ambiguous_edge_count=sum(
            1 for edge in edge_records if edge.status == "ambiguous"
        ),
    )


def _deduplicate_nodes(
    nodes: tuple[CatalogGraphNodeInput, ...],
) -> tuple[
    tuple[CatalogGraphNodeRecord, ...],
    tuple[CatalogGraphDuplicateLink, ...],
    dict[str, str],
]:
    canonical_by_key: dict[
        tuple[CatalogGraphEntityKind, str], CatalogGraphNodeRecord
    ] = {}
    key_aliases: dict[tuple[CatalogGraphEntityKind, str], str] = {}
    source_to_node_id: dict[str, str] = {}
    duplicate_links: list[CatalogGraphDuplicateLink] = []
    for node in sorted(
        nodes,
        key=lambda item: (item.entity_kind, item.label, item.source_node_id),
    ):
        _validate_node_input(node)
        normalized_keys = _node_normalized_keys(node)
        existing_id = _existing_node_id(
            entity_kind=node.entity_kind,
            normalized_keys=normalized_keys,
            key_aliases=key_aliases,
        )
        if existing_id is None:
            canonical_key = min(normalized_keys)
            record = _new_node_record(node=node, normalized_key=canonical_key)
        else:
            canonical_key = existing_id.rsplit(":", 1)[-1]
            record = _merge_node_record(
                canonical_by_key[node.entity_kind, canonical_key], node
            )
            duplicate_links.append(
                CatalogGraphDuplicateLink(
                    source_id=node.source_node_id,
                    canonical_id=record.node_id,
                    duplicate_kind="node",
                    reason="normalized_label_or_alias_match",
                )
            )
        canonical_by_key[node.entity_kind, canonical_key] = record
        source_to_node_id[node.source_node_id] = record.node_id
        for normalized_key in normalized_keys:
            key_aliases[node.entity_kind, normalized_key] = record.node_id
    return (
        tuple(
            sorted(canonical_by_key.values(), key=lambda record: record.node_id)
        ),
        tuple(duplicate_links),
        source_to_node_id,
    )


def _deduplicate_edges(
    *,
    edges: tuple[CatalogGraphEdgeInput, ...],
    source_to_node_id: dict[str, str],
) -> tuple[
    tuple[CatalogGraphEdgeRecord, ...], tuple[CatalogGraphDuplicateLink, ...]
]:
    edge_records: dict[tuple[str, str, str], CatalogGraphEdgeRecord] = {}
    duplicate_links: list[CatalogGraphDuplicateLink] = []
    for edge in sorted(
        edges, key=lambda item: (item.edge_kind, item.source_ref)
    ):
        _validate_edge_input(edge, source_to_node_id=source_to_node_id)
        from_node_id = source_to_node_id[edge.from_source_node_id]
        to_node_id = source_to_node_id[edge.to_source_node_id]
        key = (edge.edge_kind, from_node_id, to_node_id)
        if key not in edge_records:
            edge_records[key] = _new_edge_record(
                edge=edge,
                from_node_id=from_node_id,
                to_node_id=to_node_id,
            )
            continue
        edge_records[key] = _merge_edge_record(edge_records[key], edge)
        duplicate_links.append(
            CatalogGraphDuplicateLink(
                source_id=_source_edge_id(edge),
                canonical_id=edge_records[key].edge_id,
                duplicate_kind="edge",
                reason="same_kind_and_canonical_endpoints",
            )
        )
    return (
        tuple(sorted(edge_records.values(), key=lambda record: record.edge_id)),
        tuple(duplicate_links),
    )


def _new_node_record(
    *,
    node: CatalogGraphNodeInput,
    normalized_key: str,
) -> CatalogGraphNodeRecord:
    return CatalogGraphNodeRecord(
        node_id=f"catalog-graph-node:{node.entity_kind}:{normalized_key}",
        entity_kind=node.entity_kind,
        canonical_label=node.label.strip(),
        normalized_key=normalized_key,
        aliases=_dedupe_texts(node.aliases),
        source_node_ids=(node.source_node_id,),
        provenance_refs=(node.source_ref,),
        confidence_score=node.confidence_score,
    )


def _merge_node_record(
    record: CatalogGraphNodeRecord,
    node: CatalogGraphNodeInput,
) -> CatalogGraphNodeRecord:
    return record._replace(
        aliases=_dedupe_texts((*record.aliases, *node.aliases, node.label)),
        source_node_ids=_dedupe_texts(
            (*record.source_node_ids, node.source_node_id)
        ),
        provenance_refs=_dedupe_texts(
            (*record.provenance_refs, node.source_ref)
        ),
        confidence_score=max(record.confidence_score, node.confidence_score),
    )


def _new_edge_record(
    *,
    edge: CatalogGraphEdgeInput,
    from_node_id: str,
    to_node_id: str,
) -> CatalogGraphEdgeRecord:
    confidence_score = edge.confidence_score
    status = _edge_status(
        confidence_score=confidence_score, ambiguous=edge.ambiguous
    )
    return CatalogGraphEdgeRecord(
        edge_id=_edge_id(
            edge_kind=edge.edge_kind,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
        ),
        edge_kind=edge.edge_kind,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        provenance_refs=(edge.source_ref,),
        confidence_score=confidence_score,
        status=status,
        hard_project_fact=status == "promoted_candidate",
        rollback_safe=True,
    )


def _merge_edge_record(
    record: CatalogGraphEdgeRecord,
    edge: CatalogGraphEdgeInput,
) -> CatalogGraphEdgeRecord:
    confidence_score = max(record.confidence_score, edge.confidence_score)
    status = _edge_status(
        confidence_score=confidence_score,
        ambiguous=edge.ambiguous or record.status == "ambiguous",
    )
    return record._replace(
        provenance_refs=_dedupe_texts(
            (*record.provenance_refs, edge.source_ref)
        ),
        confidence_score=confidence_score,
        status=status,
        hard_project_fact=status == "promoted_candidate",
    )


def _edge_status(
    *,
    confidence_score: int,
    ambiguous: bool,
) -> CatalogGraphPromotionStatus:
    if ambiguous:
        return "ambiguous"
    if confidence_score < CATALOG_GRAPH_HARD_FACT_CONFIDENCE_FLOOR:
        return "low_confidence"
    return "promoted_candidate"


def _existing_node_id(
    *,
    entity_kind: CatalogGraphEntityKind,
    normalized_keys: tuple[str, ...],
    key_aliases: dict[tuple[CatalogGraphEntityKind, str], str],
) -> str | None:
    matching = tuple(
        key_aliases[entity_kind, normalized_key]
        for normalized_key in normalized_keys
        if (entity_kind, normalized_key) in key_aliases
    )
    if not matching:
        return None
    return min(matching)


def _node_normalized_keys(node: CatalogGraphNodeInput) -> tuple[str, ...]:
    return _dedupe_texts(
        tuple(
            normalized_key
            for value in (node.label, *node.aliases)
            if (normalized_key := _normalized_graph_key(value))
        )
    )


def _edge_id(*, edge_kind: str, from_node_id: str, to_node_id: str) -> str:
    digest = hashlib.sha256(
        f"{edge_kind}\n{from_node_id}\n{to_node_id}".encode()
    )
    return f"catalog-graph-edge:{edge_kind}:{digest.hexdigest()[:16]}"


def _source_edge_id(edge: CatalogGraphEdgeInput) -> str:
    return (
        f"{edge.edge_kind}:{edge.from_source_node_id}:"
        f"{edge.to_source_node_id}:{edge.source_ref}"
    )


def _validate_node_input(node: CatalogGraphNodeInput) -> None:
    if node.entity_kind not in {"operation", "entity", "capability"}:
        message = f"Unsupported graph entity kind: {node.entity_kind}"
        raise ValueError(message)
    if (
        not node.source_node_id.strip()
        or not node.label.strip()
        or not node.source_ref.strip()
    ):
        message = (
            "Catalog graph nodes require source ID, label, and provenance."
        )
        raise ValueError(message)
    _validate_confidence(node.confidence_score)


def _validate_edge_input(
    edge: CatalogGraphEdgeInput,
    *,
    source_to_node_id: dict[str, str],
) -> None:
    if not edge.edge_kind.strip() or not edge.source_ref.strip():
        message = "Catalog graph edges require edge kind and provenance."
        raise ValueError(message)
    if edge.from_source_node_id not in source_to_node_id:
        message = f"Unknown graph edge source node: {edge.from_source_node_id}"
        raise ValueError(message)
    if edge.to_source_node_id not in source_to_node_id:
        message = f"Unknown graph edge target node: {edge.to_source_node_id}"
        raise ValueError(message)
    _validate_confidence(edge.confidence_score)


def _validate_confidence(confidence_score: int) -> None:
    if (
        isinstance(confidence_score, bool)
        or not 0 <= confidence_score <= CATALOG_GRAPH_MAX_CONFIDENCE
    ):
        message = (
            "Catalog graph confidence must be an integer between 0 and 100."
        )
        raise ValueError(message)


def _normalized_graph_key(value: str) -> str:
    return "_".join(NORMALIZED_GRAPH_KEY_PATTERN.findall(value.casefold()))


def _dedupe_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = value.strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return tuple(deduped)
