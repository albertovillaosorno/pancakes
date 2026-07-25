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

"""Future gate for non-deterministic catalog graph expansion.

Boundary contract:
- Owns: inactive prerequisite checks for future neural-style catalog graph
proposals.
- Must not: create non-deterministic links, call providers, or author semantic
answers.
- Allows: deterministic policy reports based on catalog graph and semantic
coverage state.
- Split when: an explicit future TODO implements reviewed non-deterministic
proposal scoring.
- Merge when: deterministic graph projection owns this future-gate policy
directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog.knowledge.catalog_graph_projection import (
    CATALOG_GRAPH_STATUS_CURRENT,
    CATALOG_GRAPH_STATUS_INCOMPLETE_NON_BLOCKING,
    catalog_graph_projection_status,
)

if TYPE_CHECKING:
    import sqlite3

CATALOG_NEURAL_GRAPH_RUNTIME_ENABLED: Final = False
CATALOG_NEURAL_GRAPH_ACTIVATION_ALLOWED: Final = False
CATALOG_NEURAL_GRAPH_GATE_WAITING: Final = "waiting_on_prerequisites"
CATALOG_NEURAL_GRAPH_GATE_READY_FOR_FUTURE_TODO: Final = (
    "ready_for_future_operator_todo"
)
CATALOG_NEURAL_GRAPH_EXPLICIT_FUTURE_TODO_REQUIRED: Final = True
CATALOG_NEURAL_GRAPH_REQUIRED_PREREQUISITES: Final[tuple[str, ...]] = (
    "deterministic_graph_rebaseline_current ",
    "semantic_catalog_coverage_complete ",
    "provenance_back_to_catalog_units_and_source_refs ",
    "confidence_score_defined ",
    "validation_status_defined ",
    "rollback_metadata_defined ",
    "typed_mutation_history_available",
)
CATALOG_NEURAL_GRAPH_REQUIRED_PROPOSAL_FIELDS: Final[tuple[str, ...]] = (
    "proposal_id ",
    "domain ",
    "edge_kind ",
    "from_node_id ",
    "to_node_id ",
    "provenance_ref ",
    "source_run_id ",
    "source_unit_ids ",
    "confidence_score ",
    "validation_status ",
    "rollback_metadata_json ",
    "typed_mutation_event_id ",
    "review_status",
)
CATALOG_NEURAL_GRAPH_TYPED_HISTORY_TABLES: Final[tuple[str, ...]] = (
    "catalog_modification_events ",
    "catalog_edge_proposals ",
    "catalog_review_records",
)


class CatalogNeuralGraphFutureGateReport(NamedTuple):
    """Inactive gate status for future non-deterministic catalog graph.

    expansion.
    """

    run_id: str
    neural_runtime_enabled: bool
    activation_allowed: bool
    explicit_future_todo_required: bool
    gate_status: str
    required_prerequisites: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    required_proposal_fields: tuple[str, ...]
    deterministic_graph_status: str
    catalog_coverage_status: str
    graph_semantic_separation_required: bool


def catalog_neural_graph_future_gate_status(
    *,
    connection: sqlite3.Connection,
    run_id: str | None = None,
) -> CatalogNeuralGraphFutureGateReport:
    """Return inactive prerequisite status for future neural-style graph.

    proposals.

    Returns:
        A policy report. This function never enables non-deterministic graph
        behavior.
    """
    graph_report = catalog_graph_projection_status(
        connection=connection, run_id=run_id
    )
    missing_prerequisites = _missing_prerequisites(
        connection=connection,
        deterministic_graph_status=graph_report.projection_status,
        catalog_coverage_status=graph_report.catalog_coverage_status,
    )
    gate_status = (
        CATALOG_NEURAL_GRAPH_GATE_READY_FOR_FUTURE_TODO
        if not missing_prerequisites
        else CATALOG_NEURAL_GRAPH_GATE_WAITING
    )
    return CatalogNeuralGraphFutureGateReport(
        run_id=graph_report.run_id,
        neural_runtime_enabled=CATALOG_NEURAL_GRAPH_RUNTIME_ENABLED,
        activation_allowed=CATALOG_NEURAL_GRAPH_ACTIVATION_ALLOWED,
        explicit_future_todo_required=CATALOG_NEURAL_GRAPH_EXPLICIT_FUTURE_TODO_REQUIRED,
        gate_status=gate_status,
        required_prerequisites=CATALOG_NEURAL_GRAPH_REQUIRED_PREREQUISITES,
        missing_prerequisites=missing_prerequisites,
        required_proposal_fields=CATALOG_NEURAL_GRAPH_REQUIRED_PROPOSAL_FIELDS,
        deterministic_graph_status=graph_report.projection_status,
        catalog_coverage_status=graph_report.catalog_coverage_status,
        graph_semantic_separation_required=True,
    )


def _missing_prerequisites(
    *,
    connection: sqlite3.Connection,
    deterministic_graph_status: str,
    catalog_coverage_status: str,
) -> tuple[str, ...]:
    missing: list[str] = []
    if deterministic_graph_status not in {
        CATALOG_GRAPH_STATUS_CURRENT,
        CATALOG_GRAPH_STATUS_INCOMPLETE_NON_BLOCKING,
    }:
        missing.append("deterministic_graph_rebaseline_current")
    if catalog_coverage_status != "complete":
        missing.append("semantic_catalog_coverage_complete")
    if not _typed_history_tables_available(connection):
        missing.append("typed_mutation_history_available")
    return tuple(missing)


def _typed_history_tables_available(connection: sqlite3.Connection) -> bool:
    for table_name in CATALOG_NEURAL_GRAPH_TYPED_HISTORY_TABLES:
        row = cast(
            "tuple[str] | None",
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND "
                "name = "
                "?",
                (table_name,),
            ).fetchone(),
        )
        if row is None:
            return False
    return True
