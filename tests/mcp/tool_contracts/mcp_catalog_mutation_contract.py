# ruff: noqa: ERA001, S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Owns catalog mutation and inspect contract coverage for local SQLite
# state.
# split: Separate mutation proposal/apply tests from inspect visibility tests.
# validation: Focused pytest contract plus pancakes.mcp.smoke.
# review: Operator-requested catalog.inspect handle visibility safety update.

"""Typed catalog mutation contracts for MCP tools.

Boundary contract:
- Owns: typed catalog modification, node mutation, edge proposal/apply, and
review writes.
- Must not: expose raw SQL mutation, author semantic catalog answers, or call
live Make.com.
- Allows: synthetic SQLite fixtures and local-only MCP tool execution.
- Split when: graph proposal review becomes an independent service contract.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, cast

from catalog.knowledge import (
    DEFAULT_KNOWLEDGE_DB_PATH,
    CatalogResetUnitInput,
    start_catalog_quality_reset_run,
)
from catalog.knowledge.schema import read_engine_schema_sql
from mcp import execute_mcp_tool, mcp_tool_registry

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

OBSERVED_AT = "2026-05-21T00:00:00+00:00"
RUN_ID = "catalog-run-mutation-test"


def test_catalog_mutation_tools_are_typed_and_no_raw_sql_tool_exists() -> None:
    """Catalog write capability is typed; no raw SQL agent mutation tool is.

    exposed.
    """
    tool_names = tuple(tool.name for tool in mcp_tool_registry())

    assert "catalog.modify" in tool_names
    assert "catalog.node.modify" in tool_names
    assert "catalog.edge.propose" in tool_names
    assert "catalog.edge.apply" in tool_names
    assert "catalog.review.add" in tool_names
    assert all("sql" not in tool_name for tool_name in tool_names)


def test_catalog_modify_updates_unit_notes_and_status(tmp_path: Path) -> None:
    """Typed catalog modification updates note/status surfaces without raw SQL.

    access.
    """
    _prepare_catalog_db(tmp_path)

    note = execute_mcp_tool(
        tool_name="catalog.modify",
        arguments={
            "operation": "update_unit_note",
            "run_id": RUN_ID,
            "unit_id": "unit-note",
            "note_surface": "fallback_behavior",
            "note_text": "Fallback behavior must remain explicit.",
            "worker_id": "catalog-reviewer",
        },
        repo_root=tmp_path,
    )
    status = execute_mcp_tool(
        tool_name="catalog.modify",
        arguments={
            "operation": "update_unit_status",
            "run_id": RUN_ID,
            "unit_id": "unit-note",
            "validation_status": "needs_review",
            "coverage_status": "incomplete_non_blocking",
            "worker_id": "catalog-reviewer",
        },
        repo_root=tmp_path,
    )

    assert note.ok, note
    assert status.ok, status
    assert note.payload["raw_sql_agent_mutation"] is False
    assert status.payload["raw_sql_agent_mutation"] is False
    assert _unit_note(tmp_path) == (
        "present",
        "Fallback behavior must remain explicit.",
    )
    assert _unit_status(tmp_path) == (
        "queued",
        "needs_review",
        "incomplete_non_blocking",
    )
    assert _event_count(tmp_path) == 2


def test_catalog_modify_and_review_dry_runs_are_write_free(
    tmp_path: Path,
) -> None:
    """Catalog modify and review dry-runs validate local inputs without SQLite.

    writes.
    """
    _prepare_catalog_db(tmp_path)
    initial_note_count = _unit_note_count(tmp_path)
    initial_event_count = _event_count(tmp_path)
    initial_graph_counts = _graph_counts(tmp_path)

    note_dry_run = execute_mcp_tool(
        tool_name="catalog.modify",
        arguments={
            "operation": "update_unit_note",
            "run_id": RUN_ID,
            "unit_id": "unit-note",
            "note_surface": "fallback_behavior",
            "note_text": "Dry-run note text must not be written.",
            "worker_id": "catalog-reviewer",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )
    review_dry_run = execute_mcp_tool(
        tool_name="catalog.review.add",
        arguments={
            "review_id": "review:dry-run",
            "domain": "catalog",
            "target_kind": "unit",
            "target_id": "unit-note",
            "payload_json": {
                "review_reason": "dry-run review must not be written"
            },
            "priority": 70,
            "worker_id": "catalog-reviewer",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )

    assert note_dry_run.ok, note_dry_run
    assert note_dry_run.payload["status"] == "dry_run"
    assert (
        note_dry_run.payload["validation_status"] == "validated_without_write"
    )
    assert (
        note_dry_run.payload["target_id"]
        == f"{RUN_ID}/unit-note/fallback_behavior"
    )
    assert note_dry_run.payload["writes_performed"] is False
    assert note_dry_run.payload["permission_posture"] == (
        "local_dry_run_no_write_no_approval"
    )
    assert note_dry_run.payload["write_actions"] == []
    assert note_dry_run.payload["requires_operator_approval"] is False
    assert review_dry_run.ok, review_dry_run
    assert review_dry_run.payload["status"] == "dry_run"
    assert review_dry_run.payload["target_id"] == "review:dry-run"
    assert review_dry_run.payload["writes_performed"] is False
    assert review_dry_run.payload["review_status"] == "open"
    assert review_dry_run.payload["priority"] == 70
    assert review_dry_run.payload["permission_posture"] == (
        "local_dry_run_no_write_no_approval"
    )
    assert review_dry_run.payload["write_actions"] == []
    assert review_dry_run.payload["requires_operator_approval"] is False
    assert _unit_note_count(tmp_path) == initial_note_count
    assert _event_count(tmp_path) == initial_event_count
    assert _graph_counts(tmp_path) == initial_graph_counts


def test_catalog_node_edge_and_review_tools_write_typed_records(
    tmp_path: Path,
) -> None:
    """Node, edge proposal/apply, and review tools write only typed local.

    SQLite.

    records.
    """
    _prepare_catalog_db(tmp_path)

    node_a = execute_mcp_tool(
        tool_name="catalog.node.modify",
        arguments={
            "node_id": "node:make:builtin:router",
            "domain": "catalog",
            "entity_kind": "module",
            "canonical_label": "Basic Router",
            "payload_json": {"app_slug": "builtin", "module": "BasicRouter"},
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    node_b = execute_mcp_tool(
        tool_name="catalog.node.modify",
        arguments={
            "node_id": "node:make:datastore:add-record",
            "domain": "catalog",
            "entity_kind": "module",
            "canonical_label": "Add Record",
            "payload_json": {"app_slug": "datastore", "module": "AddRecord"},
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    proposal = execute_mcp_tool(
        tool_name="catalog.edge.propose",
        arguments={
            "proposal_id": "proposal:router-to-datastore",
            "domain": "catalog",
            "edge_kind": "can_feed",
            "from_node_id": "node:make:builtin:router",
            "to_node_id": "node:make:datastore:add-record",
            "payload_json": {"source": "synthetic"},
            "rationale": (
                "Synthetic graph edge proposal for MCP contract testing."
            ),
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    rejected_apply = execute_mcp_tool(
        tool_name="catalog.edge.apply",
        arguments={
            "proposal_id": "proposal:router-to-datastore",
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    approved = execute_mcp_tool(
        tool_name="catalog.modify",
        arguments={
            "operation": "approve_edge_proposal",
            "proposal_id": "proposal:router-to-datastore",
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    applied = execute_mcp_tool(
        tool_name="catalog.edge.apply",
        arguments={
            "proposal_id": "proposal:router-to-datastore",
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    review = execute_mcp_tool(
        tool_name="catalog.review.add",
        arguments={
            "review_id": "review:router-to-datastore",
            "domain": "catalog",
            "target_kind": "edge",
            "target_id": "proposal:router-to-datastore",
            "payload_json": {"review_reason": "synthetic review row"},
            "priority": 80,
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )

    assert node_a.ok, node_a
    assert node_b.ok, node_b
    assert proposal.ok, proposal
    assert not rejected_apply.ok, rejected_apply
    assert "requires an approved edge proposal" in str(rejected_apply.error)
    assert approved.ok, approved
    assert applied.ok, applied
    assert review.ok, review
    assert _graph_counts(tmp_path) == {
        "entity_nodes": 2,
        "entity_edges": 1,
        "catalog_edge_proposals": 1,
        "catalog_review_records": 1,
    }
    assert applied.payload["raw_sql_agent_mutation"] is False
    assert review.payload["provider_api_call"] is False
    assert review.payload["live_make_called"] is False


def test_catalog_edge_apply_dry_run_validates_proposal_status_without_writes(
    tmp_path: Path,
) -> None:
    """Edge apply dry-run reports missing/unapproved/approved states before any.

    write.
    """
    _prepare_catalog_db(tmp_path)

    missing = execute_mcp_tool(
        tool_name="catalog.edge.apply",
        arguments={
            "proposal_id": "proposal:missing",
            "worker_id": "graph-worker",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )
    node_a = execute_mcp_tool(
        tool_name="catalog.node.modify",
        arguments={
            "node_id": "node:make:builtin:router",
            "domain": "catalog",
            "entity_kind": "module",
            "canonical_label": "Basic Router",
            "payload_json": {"app_slug": "builtin", "module": "BasicRouter"},
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    node_b = execute_mcp_tool(
        tool_name="catalog.node.modify",
        arguments={
            "node_id": "node:make:datastore:add-record",
            "domain": "catalog",
            "entity_kind": "module",
            "canonical_label": "Add Record",
            "payload_json": {"app_slug": "datastore", "module": "AddRecord"},
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    proposal = execute_mcp_tool(
        tool_name="catalog.edge.propose",
        arguments={
            "proposal_id": "proposal:router-to-datastore",
            "domain": "catalog",
            "edge_kind": "can_feed",
            "from_node_id": "node:make:builtin:router",
            "to_node_id": "node:make:datastore:add-record",
            "payload_json": {"source": "synthetic"},
            "rationale": (
                "Synthetic graph edge proposal for dry-run contract testing."
            ),
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    unapproved = execute_mcp_tool(
        tool_name="catalog.edge.apply",
        arguments={
            "proposal_id": "proposal:router-to-datastore",
            "worker_id": "graph-worker",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )
    approved = execute_mcp_tool(
        tool_name="catalog.modify",
        arguments={
            "operation": "approve_edge_proposal",
            "proposal_id": "proposal:router-to-datastore",
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    approved_dry_run = execute_mcp_tool(
        tool_name="catalog.edge.apply",
        arguments={
            "proposal_id": "proposal:router-to-datastore",
            "edge_id": "edge:router-to-datastore",
            "worker_id": "graph-worker",
            "dry_run": True,
        },
        repo_root=tmp_path,
    )
    assert missing.ok, missing
    assert missing.payload["status"] == "proposal_not_found"
    assert missing.payload["writes_performed"] is False
    assert missing.payload["would_change"] is False
    assert node_a.ok, node_a
    assert node_b.ok, node_b
    assert proposal.ok, proposal
    assert unapproved.ok, unapproved
    assert unapproved.payload["status"] == "proposal_not_approved"
    assert unapproved.payload["proposal_status"] == "proposed"
    assert unapproved.payload["writes_performed"] is False
    assert approved.ok, approved
    assert approved_dry_run.ok, approved_dry_run
    assert approved_dry_run.payload["status"] == "dry_run"
    assert approved_dry_run.payload["validation_status"] == "approved_proposal"
    assert approved_dry_run.payload["would_change"] is True
    assert approved_dry_run.payload["edge_id"] == "edge:router-to-datastore"
    assert approved_dry_run.payload["writes_performed"] is False
    assert _graph_counts(tmp_path) == {
        "entity_nodes": 2,
        "entity_edges": 0,
        "catalog_edge_proposals": 1,
        "catalog_review_records": 0,
    }
    applied = execute_mcp_tool(
        tool_name="catalog.edge.apply",
        arguments={
            "proposal_id": "proposal:router-to-datastore",
            "edge_id": "edge:router-to-datastore",
            "worker_id": "graph-worker",
        },
        repo_root=tmp_path,
    )
    assert applied.ok, applied
    assert _graph_counts(tmp_path)["entity_edges"] == 1


def test_catalog_inspect_exposes_incomplete_coverage_without_lease_handle(
    tmp_path: Path,
) -> None:
    """Incomplete catalog coverage is explicit and non-blocking in inspect.

    payloads.
    """
    _prepare_catalog_db(tmp_path)

    inspected = execute_mcp_tool(
        tool_name="catalog.inspect",
        arguments={"unit_id": "unit-note"},
        repo_root=tmp_path,
    )
    searched = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "BasicRouter", "limit": 2},
        repo_root=tmp_path,
    )

    assert inspected.ok, inspected
    assert searched.ok, searched
    assert inspected.payload["catalog_usable"] is True
    assert (
        inspected.payload["catalog_coverage_status"]
        == "incomplete_non_blocking"
    )
    assert searched.payload["catalog_usable"] is True
    assert (
        searched.payload["catalog_coverage_status"] == "incomplete_non_blocking"
    )
    unit = cast("JsonObject", inspected.payload["unit"])
    lease = cast("JsonObject", inspected.payload["lease"])
    assert unit["unit_id"] == "unit-note"
    assert lease["lease_handle_exposed"] is False
    assert "lease_handle" not in lease
    assert "lease_token" not in lease


def _prepare_catalog_db(repo_root: Path) -> None:
    database_path = repo_root / DEFAULT_KNOWLEDGE_DB_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        _ = connection.executescript(read_engine_schema_sql())
        _ = start_catalog_quality_reset_run(
            connection=connection,
            run_id=RUN_ID,
            units=(
                CatalogResetUnitInput(
                    unit_id="unit-note",
                    unit_type="raw_spec",
                    priority_band="make_builtins_core",
                    source_ref="synthetic:unit-note",
                    source_hash="sha256:unit-note",
                    source_size_bytes=1_000,
                    complexity_score=1_000,
                ),
            ),
            source_ref="synthetic:mcp-catalog-mutation-contract",
            observed_at_utc=OBSERVED_AT,
        )
    finally:
        connection.close()


def _unit_note(repo_root: Path) -> tuple[str, str]:
    connection = sqlite3.connect(repo_root / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        return cast(
            "tuple[str, str]",
            connection.execute(
                """
                SELECT note_status, note_text
                FROM catalog_unit_notes
                WHERE run_id = ?
                  AND unit_id = ?
                  AND note_surface = 'fallback_behavior'
                """,
                (RUN_ID, "unit-note"),
            ).fetchone(),
        )
    finally:
        connection.close()


def _unit_note_count(repo_root: Path) -> int:
    connection = sqlite3.connect(repo_root / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        row = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_unit_notes"
            ).fetchone(),
        )
        return row[0]
    finally:
        connection.close()


def _unit_status(repo_root: Path) -> tuple[str, str, str]:
    connection = sqlite3.connect(repo_root / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        return cast(
            "tuple[str, str, str]",
            connection.execute(
                """
                SELECT status, validation_status, coverage_status
                FROM catalog_units
                WHERE run_id = ?
                  AND unit_id = ?
                """,
                (RUN_ID, "unit-note"),
            ).fetchone(),
        )
    finally:
        connection.close()


def _event_count(repo_root: Path) -> int:
    connection = sqlite3.connect(repo_root / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        row = cast(
            "tuple[int]",
            connection.execute(
                "SELECT COUNT(*) FROM catalog_modification_events"
            ).fetchone(),
        )
        return row[0]
    finally:
        connection.close()


def _graph_counts(repo_root: Path) -> dict[str, int]:
    connection = sqlite3.connect(repo_root / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        counts: dict[str, int] = {}
        for table_name in (
            "entity_nodes",
            "entity_edges",
            "catalog_edge_proposals",
            "catalog_review_records",
        ):
            row = cast(
                "tuple[int]",
                connection.execute(
                    f"SELECT COUNT(*) FROM {table_name}"
                ).fetchone(),
            )
            counts[table_name] = row[0]
        return counts
    finally:
        connection.close()
