# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for deterministic catalog graph rebaseline behavior.

Boundary contract:
- Owns: graph projection determinism, provenance, hash comparison, and coverage
status.
- Must not: author semantic catalog answers, call providers, or use live
Make.com state.
- Allows: in-memory SQLite schemas and synthetic catalog unit source fixtures.
- Split when: graph query service tests own projection rebuild and status
behavior.
- Merge when: catalog quality reset tests own this exact graph rebaseline
contract.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import cast

from catalog.knowledge import (
    CatalogResetUnitInput,
    catalog_graph_projection_status,
    rebuild_catalog_graph_projection,
    start_catalog_quality_reset_run,
)
from catalog.knowledge.catalog_graph_projection import (
    CATALOG_GRAPH_STATUS_CURRENT,
    CATALOG_GRAPH_STATUS_INCOMPLETE_NON_BLOCKING,
    CATALOG_GRAPH_STATUS_MISSING_NON_BLOCKING,
    CATALOG_GRAPH_STATUS_STALE_NON_BLOCKING,
)
from catalog.knowledge.schema import read_engine_schema_sql

OBSERVED_AT = "2026-05-21T12:00:00+00:00"


def test_catalog_graph_projection_reports_missing_8202cc90() -> None:
    """A new active run is usable even when deterministic graph rows are.

    missing.
    """
    connection = _schema_connection()
    try:
        _start_run(connection, run_id="catalog-run-missing")

        report = catalog_graph_projection_status(connection=connection)
    finally:
        connection.close()

    assert report.run_id == "catalog-run-missing"
    assert report.expected_node_count == 4
    assert report.expected_edge_count == 3
    assert report.current_node_count == 0
    assert report.current_edge_count == 0
    assert report.missing_node_count == 4
    assert report.missing_edge_count == 3
    assert report.projection_status == CATALOG_GRAPH_STATUS_MISSING_NON_BLOCKING
    assert report.catalog_coverage_status == "incomplete_non_blocking"
    assert report.catalog_usable is True


def test_catalog_graph_projection_rebuild_is_241a52f4() -> None:
    """Rebuilds produce stable hashes and graph rows preserve unit/source.

    provenance.
    """
    connection = _schema_connection()
    try:
        _start_run(connection, run_id="catalog-run-deterministic")
        _complete_units(connection, run_id="catalog-run-deterministic")

        first_report = rebuild_catalog_graph_projection(
            connection=connection,
            run_id="catalog-run-deterministic",
            observed_at_utc=OBSERVED_AT,
        )
        second_report = rebuild_catalog_graph_projection(
            connection=connection,
            run_id="catalog-run-deterministic",
            observed_at_utc=OBSERVED_AT,
        )
        unit_payload, source_ref = _unit_node_payload(
            connection,
            node_id="catalog-unit:catalog-run-deterministic:unit-router",
        )
    finally:
        connection.close()

    assert (
        first_report.expected_projection_hash
        == second_report.expected_projection_hash
    )
    assert (
        second_report.expected_projection_hash
        == second_report.current_projection_hash
    )
    assert second_report.projection_status == CATALOG_GRAPH_STATUS_CURRENT
    assert second_report.max_degree_node_id == (
        "catalog-priority-band:catalog-run-deterministic:make_control_data_structures"
    )
    assert second_report.max_degree == 3
    assert unit_payload["unit_id"] == "unit-router"
    assert unit_payload["source_hash"] == _sha256("router raw spec")
    assert unit_payload["source_ref"] == "synthetic:raw/router"
    assert source_ref == "synthetic:raw/router"


def test_catalog_graph_projection_reports_stale_hash_without_blocking() -> None:
    """Projection status flags stale graph rows instead of hiding or blocking.

    them.
    """
    connection = _schema_connection()
    try:
        _start_run(connection, run_id="catalog-run-stale")
        _complete_units(connection, run_id="catalog-run-stale")
        _ = rebuild_catalog_graph_projection(
            connection=connection,
            run_id="catalog-run-stale",
            observed_at_utc=OBSERVED_AT,
        )
        _ = connection.execute(
            """
            UPDATE entity_nodes
            SET fingerprint = ?
            WHERE node_id = ?
              AND valid_to IS NULL
            """,
            ("stale-fingerprint", "catalog-unit:catalog-run-stale:unit-router"),
        )

        report = catalog_graph_projection_status(
            connection=connection,
            run_id="catalog-run-stale",
        )
    finally:
        connection.close()

    assert report.stale_node_count == 1
    assert report.stale_edge_count == 0
    assert report.expected_projection_hash != report.current_projection_hash
    assert report.projection_status == CATALOG_GRAPH_STATUS_STALE_NON_BLOCKING
    assert report.catalog_usable is True


def test_catalog_graph_projection_current_rows_bcb8988d() -> None:
    """A graph can be current for known units while catalog completion remains.

    incomplete.
    """
    connection = _schema_connection()
    try:
        _start_run(connection, run_id="catalog-run-incomplete")

        report = rebuild_catalog_graph_projection(
            connection=connection,
            run_id="catalog-run-incomplete",
            observed_at_utc=OBSERVED_AT,
        )
    finally:
        connection.close()

    assert report.expected_projection_hash == report.current_projection_hash
    assert report.missing_node_count == 0
    assert report.missing_edge_count == 0
    assert (
        report.projection_status == CATALOG_GRAPH_STATUS_INCOMPLETE_NON_BLOCKING
    )
    assert report.catalog_coverage_status == "incomplete_non_blocking"
    assert report.catalog_usable is True


def _schema_connection() -> sqlite3.Connection:
    """Return the computed result for the caller."""
    connection = sqlite3.connect(":memory:")
    _ = connection.executescript(read_engine_schema_sql())
    return connection


def _start_run(connection: sqlite3.Connection, *, run_id: str) -> None:
    _ = start_catalog_quality_reset_run(
        connection=connection,
        run_id=run_id,
        units=(
            _unit(
                "unit-router",
                "make_control_data_structures",
                "synthetic:raw/router",
                "router raw spec",
            ),
            _unit(
                "unit-filter",
                "make_control_data_structures",
                "synthetic:raw/filter",
                "filter raw spec",
            ),
        ),
        source_ref=f"synthetic:{run_id}",
        observed_at_utc=OBSERVED_AT,
    )


def _complete_units(connection: sqlite3.Connection, *, run_id: str) -> None:
    _ = connection.execute(
        """
        UPDATE catalog_units
        SET status = 'completed',
            validation_status = 'valid',
            coverage_status = 'complete',
            completed_at_utc = ?
        WHERE run_id = ?
        """,
        (OBSERVED_AT, run_id),
    )


def _unit(
    unit_id: str,
    priority_band: str,
    source_ref: str,
    raw_spec_text: str,
) -> CatalogResetUnitInput:
    return CatalogResetUnitInput(
        unit_id=unit_id,
        unit_type="raw_spec",
        priority_band=priority_band,
        source_ref=source_ref,
        source_hash=_sha256(raw_spec_text),
        source_size_bytes=len(raw_spec_text.encode("utf-8")),
        complexity_score=len(raw_spec_text),
    )


def _unit_node_payload(
    connection: sqlite3.Connection, *, node_id: str
) -> tuple[dict[str, object], str]:
    row = cast(
        "tuple[str, str]",
        connection.execute(
            """
            SELECT payload_json, source_ref
            FROM entity_nodes
            WHERE node_id = ?
              AND valid_to IS NULL
            """,
            (node_id,),
        ).fetchone(),
    )
    return cast("dict[str, object]", json.loads(row[0])), str(row[1])


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
