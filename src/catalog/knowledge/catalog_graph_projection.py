# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.structural-ssot
# - repo.catalog-plan-artifact.workspace-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end
# pyright: reportAny=false

"""Deterministic graph projections for canonical catalog runs.

Boundary contract:
- Owns: catalog-run graph projection records and non-blocking projection status
reports.
- Must not: author semantic catalog answers, call providers, or inspect live
Make accounts.
- Allows: deterministic projection rebuilds from typed catalog run and unit
state.
- Split when: graph projections become a separate build pipeline or graph query
service.
- Merge when: another module owns the same canonical catalog graph projection
contract.
"""

from __future__ import annotations

import hashlib
import json
from itertools import starmap
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    import sqlite3

CATALOG_GRAPH_PROJECTION_DOMAIN: Final = "catalog"
CATALOG_GRAPH_PROJECTION_SOURCE_KIND: Final = "catalog_reset_graph_projection"
CATALOG_GRAPH_STATUS_CURRENT: Final = "current"
CATALOG_GRAPH_STATUS_MISSING_NON_BLOCKING: Final = "missing_non_blocking"
CATALOG_GRAPH_STATUS_STALE_NON_BLOCKING: Final = "stale_non_blocking"
CATALOG_GRAPH_STATUS_INCOMPLETE_NON_BLOCKING: Final = "incomplete_non_blocking"
CATALOG_GRAPH_RUN_NODE_KIND: Final = "catalog_run"
CATALOG_GRAPH_PRIORITY_BAND_NODE_KIND: Final = "catalog_priority_band"
CATALOG_GRAPH_UNIT_NODE_KIND: Final = "catalog_unit"
CATALOG_GRAPH_RUN_BAND_EDGE_KIND: Final = "catalog_run_has_priority_band"
CATALOG_GRAPH_BAND_UNIT_EDGE_KIND: Final = "catalog_priority_band_has_unit"


class CatalogGraphProjectionReport(NamedTuple):
    """Status for one deterministic catalog graph projection."""

    run_id: str
    expected_node_count: int
    expected_edge_count: int
    current_node_count: int
    current_edge_count: int
    missing_node_count: int
    missing_edge_count: int
    stale_node_count: int
    stale_edge_count: int
    extra_node_count: int
    extra_edge_count: int
    expected_projection_hash: str
    current_projection_hash: str
    projection_status: str
    catalog_coverage_status: str
    catalog_usable: bool
    max_degree_node_id: str | None
    max_degree: int


class _CatalogRunRow(NamedTuple):
    run_id: str
    run_status: str
    reset_strategy: str
    priority_policy_json: str
    old_semantic_status: str
    incomplete_coverage_policy: str
    created_at_utc: str
    source_kind: str
    source_ref: str
    fingerprint: str


class _CatalogUnitRow(NamedTuple):
    unit_id: str
    unit_type: str
    priority_band: str
    priority_order: int
    source_ref: str
    source_hash: str
    source_size_bytes: int
    complexity_score: int
    status: str
    validation_status: str
    coverage_status: str


class _ProjectionNode(NamedTuple):
    node_id: str
    entity_kind: str
    canonical_label: str
    payload_json: str
    source_ref: str
    fingerprint: str


class _ProjectionEdge(NamedTuple):
    edge_id: str
    edge_kind: str
    from_node_id: str
    to_node_id: str
    payload_json: str
    source_ref: str
    fingerprint: str


class _ProjectionEdgeInput(NamedTuple):
    edge_id: str
    edge_kind: str
    from_node_id: str
    to_node_id: str
    payload: object
    source_ref: str


class _Projection(NamedTuple):
    nodes: tuple[_ProjectionNode, ...]
    edges: tuple[_ProjectionEdge, ...]


class _ProjectionDelta(NamedTuple):
    missing_count: int
    stale_count: int
    extra_count: int


def rebuild_catalog_graph_projection(
    *,
    connection: sqlite3.Connection,
    run_id: str | None = None,
    observed_at_utc: str,
) -> CatalogGraphProjectionReport:
    """Rebuild deterministic graph projection rows for one catalog run.

    Returns:
        A non-blocking projection status report after the rebuild.
    """
    _validate_non_empty_text("observed_at_utc", observed_at_utc)
    resolved_run_id = _resolve_run_id(connection=connection, run_id=run_id)
    projection = _expected_projection(
        connection=connection, run_id=resolved_run_id
    )
    with connection:
        _expire_current_projection_rows(
            connection=connection,
            run_id=resolved_run_id,
            observed_at_utc=observed_at_utc,
        )
        _insert_projection_nodes(
            connection=connection,
            run_id=resolved_run_id,
            observed_at_utc=observed_at_utc,
            nodes=projection.nodes,
        )
        _insert_projection_edges(
            connection=connection,
            run_id=resolved_run_id,
            observed_at_utc=observed_at_utc,
            edges=projection.edges,
        )
    return catalog_graph_projection_status(
        connection=connection,
        run_id=resolved_run_id,
    )


def catalog_graph_projection_status(
    *,
    connection: sqlite3.Connection,
    run_id: str | None = None,
) -> CatalogGraphProjectionReport:
    """Compare expected and current graph projection hashes for one catalog run.

    Returns:
        A status report. Missing, stale, or incomplete graph coverage is
        explicit and
        non-blocking.
    """
    resolved_run_id = _resolve_run_id(connection=connection, run_id=run_id)
    expected_projection = _expected_projection(
        connection=connection, run_id=resolved_run_id
    )
    current_projection = _current_projection(
        connection=connection, run_id=resolved_run_id
    )
    expected_nodes = {
        node.node_id: node.fingerprint for node in expected_projection.nodes
    }
    current_nodes = {
        node.node_id: node.fingerprint for node in current_projection.nodes
    }
    expected_edges = {
        edge.edge_id: edge.fingerprint for edge in expected_projection.edges
    }
    current_edges = {
        edge.edge_id: edge.fingerprint for edge in current_projection.edges
    }
    node_delta = _projection_delta(
        expected=expected_nodes, current=current_nodes
    )
    edge_delta = _projection_delta(
        expected=expected_edges, current=current_edges
    )
    catalog_coverage_status = _catalog_coverage_status(
        connection=connection,
        run_id=resolved_run_id,
    )
    projection_status = _projection_status(
        missing_count=node_delta.missing_count + edge_delta.missing_count,
        stale_count=node_delta.stale_count + edge_delta.stale_count,
        extra_count=node_delta.extra_count + edge_delta.extra_count,
        catalog_coverage_status=catalog_coverage_status,
    )
    max_degree_node_id, max_degree = _max_degree(expected_projection)
    return CatalogGraphProjectionReport(
        run_id=resolved_run_id,
        expected_node_count=len(expected_projection.nodes),
        expected_edge_count=len(expected_projection.edges),
        current_node_count=len(current_projection.nodes),
        current_edge_count=len(current_projection.edges),
        missing_node_count=node_delta.missing_count,
        missing_edge_count=edge_delta.missing_count,
        stale_node_count=node_delta.stale_count,
        stale_edge_count=edge_delta.stale_count,
        extra_node_count=node_delta.extra_count,
        extra_edge_count=edge_delta.extra_count,
        expected_projection_hash=_projection_hash(expected_projection),
        current_projection_hash=_projection_hash(current_projection),
        projection_status=projection_status,
        catalog_coverage_status=catalog_coverage_status,
        catalog_usable=True,
        max_degree_node_id=max_degree_node_id,
        max_degree=max_degree,
    )


def _resolve_run_id(
    *, connection: sqlite3.Connection, run_id: str | None
) -> str:
    if run_id is not None:
        _validate_non_empty_text("run_id", run_id)
        row = connection.execute(
            "SELECT run_id FROM catalog_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            message = f"Unknown catalog run: {run_id}"
            raise ValueError(message)
        return run_id
    row = cast(
        "tuple[str] | None",
        connection.execute(
            """
            SELECT run_id
            FROM catalog_runs
            WHERE run_status = 'active'
            ORDER BY created_at_utc DESC, run_id ASC
            LIMIT 1
            """
        ).fetchone(),
    )
    if row is None:
        message = "No active catalog run is available for graph projection."
        raise ValueError(message)
    return str(row[0])


def _expected_projection(
    *, connection: sqlite3.Connection, run_id: str
) -> _Projection:
    run = _catalog_run(connection=connection, run_id=run_id)
    units = _catalog_units(connection=connection, run_id=run_id)
    band_summaries = _priority_band_summaries(units)
    nodes = (
        _run_node(run=run, unit_count=len(units)),
        *(
            _priority_band_node(run=run, band=band, summary=summary)
            for band, summary in band_summaries
        ),
        *(_unit_node(run=run, unit=unit) for unit in units),
    )
    edges = (
        *(
            _run_band_edge(run=run, band=band)
            for band, _summary in band_summaries
        ),
        *(_band_unit_edge(run=run, unit=unit) for unit in units),
    )
    return _Projection(
        nodes=tuple(sorted(nodes, key=lambda node: node.node_id)),
        edges=tuple(sorted(edges, key=lambda edge: edge.edge_id)),
    )


def _catalog_run(
    *, connection: sqlite3.Connection, run_id: str
) -> _CatalogRunRow:
    row = cast(
        "tuple[str, str, str, str, str, str, str, str, str, str] | None",
        connection.execute(
            """
            SELECT
              run_id,
              run_status,
              reset_strategy,
              priority_policy_json,
              old_semantic_status,
              incomplete_coverage_policy,
              created_at_utc,
              source_kind,
              source_ref,
              fingerprint
            FROM catalog_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone(),
    )
    if row is None:
        message = f"Unknown catalog run: {run_id}"
        raise ValueError(message)
    return _CatalogRunRow(*row)


def _catalog_units(
    *,
    connection: sqlite3.Connection,
    run_id: str,
) -> tuple[_CatalogUnitRow, ...]:
    rows = cast(
        "list[tuple[str, str, str, int, str, str, int, int, str, str, str]]",
        connection.execute(
            """
            SELECT
              unit_id,
              unit_type,
              priority_band,
              priority_order,
              source_ref,
              source_hash,
              source_size_bytes,
              complexity_score,
              status,
              validation_status,
              coverage_status
            FROM catalog_units
            WHERE run_id = ?
            ORDER BY priority_order, unit_id
            """,
            (run_id,),
        ).fetchall(),
    )
    return tuple(starmap(_CatalogUnitRow, rows))


def _priority_band_summaries(
    units: tuple[_CatalogUnitRow, ...],
) -> tuple[tuple[str, dict[str, int]], ...]:
    summaries: dict[str, dict[str, int]] = {}
    band_order: dict[str, int] = {}
    for unit in units:
        summary = summaries.setdefault(
            unit.priority_band,
            {
                "completed_unit_count": 0,
                "total_complexity_score": 0,
                "unit_count": 0,
            },
        )
        _ = band_order.setdefault(unit.priority_band, unit.priority_order)
        summary["unit_count"] += 1
        summary["total_complexity_score"] += unit.complexity_score
        if unit.status == "completed":
            summary["completed_unit_count"] += 1
    return tuple(
        (band, summaries[band])
        for band in sorted(
            band_order, key=lambda value: (band_order[value], value)
        )
    )


def _run_node(*, run: _CatalogRunRow, unit_count: int) -> _ProjectionNode:
    payload = {
        "graph_projection_kind": CATALOG_GRAPH_RUN_NODE_KIND,
        "incomplete_coverage_policy": run.incomplete_coverage_policy,
        "old_semantic_status": run.old_semantic_status,
        "priority_policy_json": run.priority_policy_json,
        "reset_strategy": run.reset_strategy,
        "run_id": run.run_id,
        "run_status": run.run_status,
        "source_ref": run.source_ref,
        "unit_count": unit_count,
    }
    return _projection_node(
        node_id=_run_node_id(run.run_id),
        entity_kind=CATALOG_GRAPH_RUN_NODE_KIND,
        canonical_label=run.run_id,
        payload=payload,
        source_ref=run.source_ref,
    )


def _priority_band_node(
    *,
    run: _CatalogRunRow,
    band: str,
    summary: dict[str, int],
) -> _ProjectionNode:
    payload = {
        "completed_unit_count": summary["completed_unit_count"],
        "graph_projection_kind": CATALOG_GRAPH_PRIORITY_BAND_NODE_KIND,
        "priority_band": band,
        "run_id": run.run_id,
        "source_ref": run.source_ref,
        "total_complexity_score": summary["total_complexity_score"],
        "unit_count": summary["unit_count"],
    }
    return _projection_node(
        node_id=_band_node_id(run.run_id, band),
        entity_kind=CATALOG_GRAPH_PRIORITY_BAND_NODE_KIND,
        canonical_label=band,
        payload=payload,
        source_ref=run.source_ref,
    )


def _unit_node(
    *, run: _CatalogRunRow, unit: _CatalogUnitRow
) -> _ProjectionNode:
    payload = {
        "complexity_score": unit.complexity_score,
        "coverage_status": unit.coverage_status,
        "graph_projection_kind": CATALOG_GRAPH_UNIT_NODE_KIND,
        "priority_band": unit.priority_band,
        "priority_order": unit.priority_order,
        "run_id": run.run_id,
        "source_hash": unit.source_hash,
        "source_ref": unit.source_ref,
        "source_size_bytes": unit.source_size_bytes,
        "status": unit.status,
        "unit_id": unit.unit_id,
        "unit_type": unit.unit_type,
        "validation_status": unit.validation_status,
    }
    return _projection_node(
        node_id=_unit_node_id(run.run_id, unit.unit_id),
        entity_kind=CATALOG_GRAPH_UNIT_NODE_KIND,
        canonical_label=unit.unit_id,
        payload=payload,
        source_ref=unit.source_ref,
    )


def _run_band_edge(*, run: _CatalogRunRow, band: str) -> _ProjectionEdge:
    payload = {
        "edge_kind": CATALOG_GRAPH_RUN_BAND_EDGE_KIND,
        "priority_band": band,
        "run_id": run.run_id,
        "source_ref": run.source_ref,
    }
    return _projection_edge(
        _ProjectionEdgeInput(
            edge_id=_edge_id(
                run.run_id, CATALOG_GRAPH_RUN_BAND_EDGE_KIND, band
            ),
            edge_kind=CATALOG_GRAPH_RUN_BAND_EDGE_KIND,
            from_node_id=_run_node_id(run.run_id),
            to_node_id=_band_node_id(run.run_id, band),
            payload=payload,
            source_ref=run.source_ref,
        )
    )


def _band_unit_edge(
    *, run: _CatalogRunRow, unit: _CatalogUnitRow
) -> _ProjectionEdge:
    payload = {
        "edge_kind": CATALOG_GRAPH_BAND_UNIT_EDGE_KIND,
        "priority_band": unit.priority_band,
        "priority_order": unit.priority_order,
        "run_id": run.run_id,
        "source_hash": unit.source_hash,
        "source_ref": unit.source_ref,
        "unit_id": unit.unit_id,
    }
    return _projection_edge(
        _ProjectionEdgeInput(
            edge_id=_edge_id(
                run.run_id, CATALOG_GRAPH_BAND_UNIT_EDGE_KIND, unit.unit_id
            ),
            edge_kind=CATALOG_GRAPH_BAND_UNIT_EDGE_KIND,
            from_node_id=_band_node_id(run.run_id, unit.priority_band),
            to_node_id=_unit_node_id(run.run_id, unit.unit_id),
            payload=payload,
            source_ref=unit.source_ref,
        )
    )


def _projection_node(
    *,
    node_id: str,
    entity_kind: str,
    canonical_label: str,
    payload: object,
    source_ref: str,
) -> _ProjectionNode:
    payload_json = _stable_json(payload)
    fingerprint = _fingerprint(
        {
            "canonical_label": canonical_label,
            "entity_kind": entity_kind,
            "node_id": node_id,
            "payload_json": payload_json,
            "source_ref": source_ref,
        }
    )
    return _ProjectionNode(
        node_id=node_id,
        entity_kind=entity_kind,
        canonical_label=canonical_label,
        payload_json=payload_json,
        source_ref=source_ref,
        fingerprint=fingerprint,
    )


def _projection_edge(edge: _ProjectionEdgeInput) -> _ProjectionEdge:
    payload_json = _stable_json(edge.payload)
    fingerprint = _fingerprint(
        {
            "edge_id": edge.edge_id,
            "edge_kind": edge.edge_kind,
            "from_node_id": edge.from_node_id,
            "payload_json": payload_json,
            "source_ref": edge.source_ref,
            "to_node_id": edge.to_node_id,
        }
    )
    return _ProjectionEdge(
        edge_id=edge.edge_id,
        edge_kind=edge.edge_kind,
        from_node_id=edge.from_node_id,
        to_node_id=edge.to_node_id,
        payload_json=payload_json,
        source_ref=edge.source_ref,
        fingerprint=fingerprint,
    )


def _current_projection(
    *, connection: sqlite3.Connection, run_id: str
) -> _Projection:
    node_rows = cast(
        "list[tuple[str, str, str, str, str, str]]",
        connection.execute(
            """
            SELECT node_id, entity_kind, canonical_label, payload_json,
            source_ref, fingerprint
            FROM entity_nodes
            WHERE domain = ?
              AND source_kind = ?
              AND ingest_run_id = ?
              AND valid_to IS NULL
            ORDER BY node_id
            """,
            (
                CATALOG_GRAPH_PROJECTION_DOMAIN,
                CATALOG_GRAPH_PROJECTION_SOURCE_KIND,
                run_id,
            ),
        ).fetchall(),
    )
    edge_rows = cast(
        "list[tuple[str, str, str, str, str, str]]",
        connection.execute(
            """
            SELECT edge_id, edge_kind, from_node_id, to_node_id, payload_json,
            source_ref,
                   fingerprint
            FROM entity_edges
            WHERE domain = ?
              AND source_kind = ?
              AND ingest_run_id = ?
              AND valid_to IS NULL
            ORDER BY edge_id
            """,
            (
                CATALOG_GRAPH_PROJECTION_DOMAIN,
                CATALOG_GRAPH_PROJECTION_SOURCE_KIND,
                run_id,
            ),
        ).fetchall(),
    )
    return _Projection(
        nodes=tuple(starmap(_ProjectionNode, node_rows)),
        edges=tuple(starmap(_ProjectionEdge, edge_rows)),
    )


def _projection_delta(
    *, expected: dict[str, str], current: dict[str, str]
) -> _ProjectionDelta:
    stale_count = sum(
        1
        for record_id in expected.keys() & current.keys()
        if expected[record_id] != current[record_id]
    )
    return _ProjectionDelta(
        missing_count=len(expected.keys() - current.keys()),
        stale_count=stale_count,
        extra_count=len(current.keys() - expected.keys()),
    )


def _expire_current_projection_rows(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    observed_at_utc: str,
) -> None:
    _ = connection.execute(
        """
        UPDATE entity_nodes
        SET valid_to = ?
        WHERE domain = ?
          AND source_kind = ?
          AND ingest_run_id = ?
          AND valid_to IS NULL
        """,
        (
            observed_at_utc,
            CATALOG_GRAPH_PROJECTION_DOMAIN,
            CATALOG_GRAPH_PROJECTION_SOURCE_KIND,
            run_id,
        ),
    )
    _ = connection.execute(
        """
        UPDATE entity_edges
        SET valid_to = ?
        WHERE domain = ?
          AND source_kind = ?
          AND ingest_run_id = ?
          AND valid_to IS NULL
        """,
        (
            observed_at_utc,
            CATALOG_GRAPH_PROJECTION_DOMAIN,
            CATALOG_GRAPH_PROJECTION_SOURCE_KIND,
            run_id,
        ),
    )


def _insert_projection_nodes(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    observed_at_utc: str,
    nodes: tuple[_ProjectionNode, ...],
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO entity_nodes (
          node_id, domain, entity_kind, canonical_label, payload_json,
          source_kind,
          source_ref, valid_from, valid_to, fingerprint, ingest_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        [
            (
                node.node_id,
                CATALOG_GRAPH_PROJECTION_DOMAIN,
                node.entity_kind,
                node.canonical_label,
                node.payload_json,
                CATALOG_GRAPH_PROJECTION_SOURCE_KIND,
                node.source_ref,
                observed_at_utc,
                node.fingerprint,
                run_id,
            )
            for node in nodes
        ],
    )


def _insert_projection_edges(
    *,
    connection: sqlite3.Connection,
    run_id: str,
    observed_at_utc: str,
    edges: tuple[_ProjectionEdge, ...],
) -> None:
    _ = connection.executemany(
        """
        INSERT OR REPLACE INTO entity_edges (
          edge_id, domain, edge_kind, from_node_id, to_node_id, payload_json,
          source_kind,
          source_ref, valid_from, valid_to, fingerprint, ingest_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        [
            (
                edge.edge_id,
                CATALOG_GRAPH_PROJECTION_DOMAIN,
                edge.edge_kind,
                edge.from_node_id,
                edge.to_node_id,
                edge.payload_json,
                CATALOG_GRAPH_PROJECTION_SOURCE_KIND,
                edge.source_ref,
                observed_at_utc,
                edge.fingerprint,
                run_id,
            )
            for edge in edges
        ],
    )


def _catalog_coverage_status(
    *, connection: sqlite3.Connection, run_id: str
) -> str:
    row = cast(
        "tuple[str] | None",
        connection.execute(
            "SELECT coverage_status FROM catalog_run_progress WHERE run_id = ?",
            (run_id,),
        ).fetchone(),
    )
    if row is None:
        message = f"Unknown catalog run progress: {run_id}"
        raise ValueError(message)
    return str(row[0])


def _projection_status(
    *,
    missing_count: int,
    stale_count: int,
    extra_count: int,
    catalog_coverage_status: str,
) -> str:
    if missing_count:
        return CATALOG_GRAPH_STATUS_MISSING_NON_BLOCKING
    if stale_count or extra_count:
        return CATALOG_GRAPH_STATUS_STALE_NON_BLOCKING
    if catalog_coverage_status != "complete":
        return CATALOG_GRAPH_STATUS_INCOMPLETE_NON_BLOCKING
    return CATALOG_GRAPH_STATUS_CURRENT


def _projection_hash(projection: _Projection) -> str:
    return _fingerprint(
        {
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "edge_kind": edge.edge_kind,
                    "fingerprint": edge.fingerprint,
                    "from_node_id": edge.from_node_id,
                    "source_ref": edge.source_ref,
                    "to_node_id": edge.to_node_id,
                }
                for edge in projection.edges
            ],
            "nodes": [
                {
                    "canonical_label": node.canonical_label,
                    "entity_kind": node.entity_kind,
                    "fingerprint": node.fingerprint,
                    "node_id": node.node_id,
                    "source_ref": node.source_ref,
                }
                for node in projection.nodes
            ],
            "projection_source_kind": CATALOG_GRAPH_PROJECTION_SOURCE_KIND,
        }
    )


def _max_degree(projection: _Projection) -> tuple[str | None, int]:
    degree_by_node = {node.node_id: 0 for node in projection.nodes}
    for edge in projection.edges:
        degree_by_node[edge.from_node_id] = (
            degree_by_node.get(edge.from_node_id, 0) + 1
        )
        degree_by_node[edge.to_node_id] = (
            degree_by_node.get(edge.to_node_id, 0) + 1
        )
    if not degree_by_node:
        return None, 0
    node_id, degree = min(
        degree_by_node.items(), key=lambda item: (-item[1], item[0])
    )
    return node_id, degree


def _run_node_id(run_id: str) -> str:
    return f"catalog-run:{run_id}"


def _band_node_id(run_id: str, band: str) -> str:
    return f"catalog-priority-band:{run_id}:{band}"


def _unit_node_id(run_id: str, unit_id: str) -> str:
    return f"catalog-unit:{run_id}:{unit_id}"


def _edge_id(run_id: str, edge_kind: str, target: str) -> str:
    return f"catalog-edge:{run_id}:{edge_kind}:{target}"


def _validate_non_empty_text(field_name: str, value: str) -> None:
    if not value.strip():
        message = f"Catalog graph projection {field_name} must not be empty."
        raise ValueError(message)


def _stable_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )


def _fingerprint(value: object) -> str:
    payload = _stable_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
