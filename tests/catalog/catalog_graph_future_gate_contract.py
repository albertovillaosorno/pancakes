# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for the inactive future neural graph gate.

Boundary contract:
- Owns: future-gate prerequisites and protection against accidental neural graph
activation.
- Must not: create non-deterministic links, call providers, or use live Make.com
state.
- Allows: in-memory SQLite schemas and synthetic catalog unit source fixtures.
- Split when: an explicit future TODO implements reviewed non-deterministic
proposal scoring.
- Merge when: catalog graph projection tests own this exact future-gate
contract.
"""

from __future__ import annotations

import hashlib
import sqlite3

from catalog.knowledge import (
    CatalogResetUnitInput,
    catalog_neural_graph_future_gate_status,
    rebuild_catalog_graph_projection,
    start_catalog_quality_reset_run,
)
from catalog.knowledge.catalog_graph_future_gate import (
    CATALOG_NEURAL_GRAPH_REQUIRED_PROPOSAL_FIELDS,
)
from catalog.knowledge.schema import (
    GRAPH_PROJECTION_TABLES,
    PURE_SEMANTIC_TABLES,
    read_engine_schema_sql,
)

OBSERVED_AT = "2026-05-21T13:00:00+00:00"


def test_neural_graph_future_gate_waits_9593aee5() -> None:
    """The future gate stays inactive when graph and semantic coverage are.

    incomplete.
    """
    connection = _schema_connection()
    try:
        _start_run(connection, run_id="catalog-run-future-waiting")

        report = catalog_neural_graph_future_gate_status(connection=connection)
    finally:
        connection.close()

    assert report.run_id == "catalog-run-future-waiting"
    assert report.neural_runtime_enabled is False
    assert report.activation_allowed is False
    assert report.explicit_future_todo_required is True
    assert report.gate_status == "waiting_on_prerequisites"
    assert (
        "deterministic_graph_rebaseline_current" in report.missing_prerequisites
    )
    assert "semantic_catalog_coverage_complete" in report.missing_prerequisites
    assert report.graph_semantic_separation_required is True


def test_neural_graph_future_gate_requires_bcae78a9() -> None:
    """Future proposals must include provenance, confidence, validation, and.

    rollback fields.
    """
    connection = _schema_connection()
    try:
        _start_run(connection, run_id="catalog-run-future-fields")

        report = catalog_neural_graph_future_gate_status(
            connection=connection,
            run_id="catalog-run-future-fields",
        )
    finally:
        connection.close()

    assert (
        report.required_proposal_fields
        == CATALOG_NEURAL_GRAPH_REQUIRED_PROPOSAL_FIELDS
    )
    assert {
        "provenance_ref",
        "source_run_id",
        "source_unit_ids",
        "confidence_score",
        "validation_status",
        "rollback_metadata_json",
        "typed_mutation_event_id",
        "review_status",
    } <= set(report.required_proposal_fields)
    assert (
        "typed_mutation_history_available" not in report.missing_prerequisites
    )


def test_neural_graph_future_gate_ready_dbf60124() -> None:
    """Even when prerequisites are met, a future TODO is required before.

    activation.
    """
    connection = _schema_connection()
    try:
        _start_run(connection, run_id="catalog-run-future-ready")
        _complete_units(connection, run_id="catalog-run-future-ready")
        _ = rebuild_catalog_graph_projection(
            connection=connection,
            run_id="catalog-run-future-ready",
            observed_at_utc=OBSERVED_AT,
        )

        report = catalog_neural_graph_future_gate_status(
            connection=connection,
            run_id="catalog-run-future-ready",
        )
    finally:
        connection.close()

    assert report.missing_prerequisites == ()
    assert report.gate_status == "ready_for_future_operator_todo"
    assert report.neural_runtime_enabled is False
    assert report.activation_allowed is False
    assert report.explicit_future_todo_required is True


def test_neural_graph_future_gate_preserves_semantic_and_graph_separation() -> (
    None
):
    """The future gate cannot collapse graph projection tables into semantic.

    tables.
    """
    assert set(GRAPH_PROJECTION_TABLES).isdisjoint(PURE_SEMANTIC_TABLES)
    assert "catalog_plan_semantic_answers" in PURE_SEMANTIC_TABLES
    assert "entity_nodes" in GRAPH_PROJECTION_TABLES
    assert "entity_edges" in GRAPH_PROJECTION_TABLES


def _schema_connection() -> sqlite3.Connection:
    """Return an in-memory knowledge schema for future-gate contract tests."""
    connection = sqlite3.connect(":memory:")
    _ = connection.executescript(read_engine_schema_sql())
    return connection


def _start_run(connection: sqlite3.Connection, *, run_id: str) -> None:
    _ = start_catalog_quality_reset_run(
        connection=connection,
        run_id=run_id,
        units=(
            CatalogResetUnitInput(
                unit_id="unit-router",
                unit_type="raw_spec",
                priority_band="make_control_data_structures",
                source_ref="synthetic:raw/router",
                source_hash=_sha256("router raw spec"),
                source_size_bytes=15,
                complexity_score=15,
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


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
