# ruff: noqa: ERA001, PLR0913
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Owns graph preview and save-gate coverage for catalog semantic
# workers.
# split: Separate graph search, preview, and catalog work save-gate tests.
# validation: Focused pytest contract plus pancakes.mcp.smoke.
# review: Operator-requested Catalog Intelligence lease-handle update.

"""Contracts for SQLite-native catalog graph search and semantic preview tools.

ADR: docs/adr/catalog-semantic-graph-preview-policy.md.

Boundary contract:
- Owns: public MCP graph search and pre-save semantic preview behavior.
- Must not: call providers, write SQLite, expose raw SQL input, or weaken
batch-save guards.
- Allows: synthetic SQLite graph fixtures and deterministic proposed semantic
outputs.
- Split when graph preview becomes a dedicated planner contract.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, cast

from catalog.knowledge import DEFAULT_KNOWLEDGE_DB_PATH
from catalog.knowledge.schema import read_engine_schema_sql
from mcp import REQUIRED_TOOL_NAMES, execute_mcp_tool, mcp_tool_registry
from mcp.annotations import public_tool_annotation_specs
from mcp.response_contracts import CONTRACT_SCHEMA_VERSIONS

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

OBSERVED_AT = "2026-06-13T00:00:00+00:00"


def test_catalog_graph_preview_tools_are_read_only_public_mcp_tools() -> None:
    """Graph preview tools are public, read-only, and contract-versioned."""
    tool_names = tuple(tool.name for tool in mcp_tool_registry())
    annotations = public_tool_annotation_specs()

    for tool_name in ("catalog.graph.search", "catalog.semantic.preview"):
        assert tool_name in REQUIRED_TOOL_NAMES
        assert tool_name in tool_names
        assert tool_name in annotations
        assert tool_name in CONTRACT_SCHEMA_VERSIONS
        assert annotations[tool_name].read_only_hint is True
        assert annotations[tool_name].provider_api_call is False
        assert annotations[tool_name].credential_value_transfer is False


def test_catalog_graph_search_reads_sqlite_graph_and_expands_node(
    tmp_path: Path,
) -> None:
    """Graph search returns compact matches and explicit node expansion."""
    _prepare_graph_database(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.graph.search",
        arguments={
            "query": "slack message email ",
            "node_id": "app:slack",
            "limit": 5,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["response_contract"] == "catalog.graph.search"
    assert payload["status"] == "ok"
    assert (
        cast("JsonObject", payload["graph_overview"])["valid_node_count"] == 3
    )
    node_matches = cast("list[JsonObject]", payload["node_matches"])
    edge_matches = cast("list[JsonObject]", payload["edge_matches"])
    expansion = cast("JsonObject", payload["expansion"])
    node_expansion = cast("JsonObject", expansion["node"])
    expanded_node = cast("JsonObject", node_expansion["node"])
    neighbor_edges = cast("list[JsonObject]", node_expansion["neighbor_edges"])

    assert any(node["node_id"] == "app:slack" for node in node_matches)
    assert any(edge["edge_kind"] == "connects_to" for edge in edge_matches)
    assert expanded_node["canonical_label"] == "Slack"
    assert neighbor_edges[0]["edge_id"] == "edge:slack-to-email"
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False


def test_catalog_semantic_preview_scores_unsaved_graph_against_sqlite(
    tmp_path: Path,
) -> None:
    """Preview validates candidate output and shows proposed graph query.

    matches.
    """
    _prepare_graph_database(tmp_path)
    answer = _semantic_output(
        unit_id="raw-spec:slack-message:1.0.0",
        graph_nodes=[
            {
                "node_id": "module:slack:create-message ",
                "entity_kind": "make_module ",
                "canonical_label": "Slack Create Message ",
                "inference_status": "inferred",
            },
            {
                "node_id": "capability:team-message ",
                "entity_kind": "capability ",
                "canonical_label": "Team message delivery ",
                "evidence_status": "source_backed",
            },
        ],
        graph_edges=[
            {
                "edge_id": "edge:slack-create-message-delivers-team-message ",
                "edge_kind": "has_capability ",
                "from_node_id": "module:slack:create-message ",
                "to_node_id": "capability:team-message ",
                "inference_status": "inferred",
            }
        ],
    )

    result = execute_mcp_tool(
        tool_name="catalog.semantic.preview",
        arguments={
            "unit_id": "raw-spec:slack-message:1.0.0",
            "answer_json": answer,
            "preview_queries": {"queries": ["slack team message"]},
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["response_contract"] == "catalog.semantic.preview"
    assert payload["status"] == "ready_to_save"
    assert payload["writes_performed"] is False
    assert payload["validation_errors"] == []
    aggregate = cast("JsonObject", payload["aggregate_graph_counts"])
    assert aggregate["graph_node_count"] == 2
    assert aggregate["graph_edge_count"] == 1
    assert aggregate["inferred_edge_count"] == 1
    search_preview = cast("list[JsonObject]", payload["search_preview"])
    assert search_preview[0]["matched_any_proposed_graph"] is True
    assert (
        cast("JsonObject", payload["save_gate"])["empty_graph_nodes_rejected"]
        is True
    )


def test_catalog_semantic_preview_flags_empty_or_disconnected_graphs(
    tmp_path: Path,
) -> None:
    """Preview catches weak graph output before catalog.work.save is.

    attempted.
    """
    _prepare_graph_database(tmp_path)
    answer = _semantic_output(
        unit_id="raw-spec:slack-message:1.0.0",
        graph_nodes=[],
        graph_edges=[
            {
                "edge_id": "edge:missing-endpoints ",
                "edge_kind": "connects_to ",
                "from_node_id": "missing:source ",
                "to_node_id": "missing:target ",
                "inference_status": "inferred",
            }
        ],
    )

    result = execute_mcp_tool(
        tool_name="catalog.semantic.preview",
        arguments={
            "unit_id": "raw-spec:slack-message:1.0.0",
            "answer_json": answer,
            "query": "slack team message",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["status"] == "needs_revision"
    errors = cast("list[JsonObject]", payload["validation_errors"])
    assert errors[0]["error"] == "empty_graph_output: graph_nodes"
    assert any(
        finding["kind"] == "validation_error"
        for finding in cast("list[JsonObject]", payload["quality_findings"])
    )


def test_catalog_work_save_rejects_empty_graph_arrays(tmp_path: Path) -> None:
    """The save path enforces the graph-rich quality floor, not only preview."""
    _prepare_raw_spec_database(tmp_path)
    lease = execute_mcp_tool(
        tool_name="catalog.work.next",
        arguments={
            "worker_id": "test-worker",
            "initialize_if_missing": True,
        },
        repo_root=tmp_path,
    )
    assert lease.ok, lease
    units = cast("list[JsonObject]", lease.payload["units"])
    answers = [
        {
            "unit_id": str(unit["unit_id"]),
            "output_json": _semantic_output(
                unit_id=str(unit["unit_id"]),
                graph_nodes=[],
                graph_edges=[],
            ),
        }
        for unit in units
    ]

    save = execute_mcp_tool(
        tool_name="catalog.work.save",
        arguments={
            "worker_id": "test-worker",
            "lease_handle": lease.payload["lease_handle"],
            "answers_json": {"units": answers},
        },
        repo_root=tmp_path,
    )

    assert not save.ok
    assert save.error == "empty_graph_output: graph_nodes"


def _prepare_graph_database(repo_root: Path) -> None:
    db_path = repo_root / DEFAULT_KNOWLEDGE_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        _ = connection.executescript(read_engine_schema_sql())
        _insert_graph_node(
            connection,
            node_id="app:slack",
            entity_kind="app",
            canonical_label="Slack",
            payload={"aliases": ["team chat", "message"]},
        )
        _insert_graph_node(
            connection,
            node_id="app:google-email",
            entity_kind="app",
            canonical_label="Google Email",
            payload={"aliases": ["gmail", "email"]},
        )
        _insert_graph_node(
            connection,
            node_id="capability:message-delivery",
            entity_kind="capability",
            canonical_label="Message delivery",
            payload={"workflow": "send messages and email"},
        )
        _insert_graph_edge(
            connection,
            edge_id="edge:slack-to-email",
            edge_kind="connects_to",
            from_node_id="app:slack",
            to_node_id="app:google-email",
            payload={
                "rationale": "Slack messages can feed email notifications."
            },
        )
        connection.commit()


def _insert_graph_node(
    connection: sqlite3.Connection,
    *,
    node_id: str,
    entity_kind: str,
    canonical_label: str,
    payload: JsonObject,
) -> None:
    _ = connection.execute(
        """
        INSERT INTO entity_nodes (
          node_id, domain, entity_kind, canonical_label, payload_json,
          source_kind,
          source_ref, valid_from, valid_to, fingerprint, ingest_run_id
        ) VALUES (?, 'catalog', ?, ?, ?, 'test_fixture', ?, ?, NULL, ?,
        'test-ingest')
        """,
        (
            node_id,
            entity_kind,
            canonical_label,
            json.dumps(payload, sort_keys=True),
            f"test:{node_id}",
            OBSERVED_AT,
            "f" * 64,
        ),
    )


def _insert_graph_edge(
    connection: sqlite3.Connection,
    *,
    edge_id: str,
    edge_kind: str,
    from_node_id: str,
    to_node_id: str,
    payload: JsonObject,
) -> None:
    _ = connection.execute(
        """
        INSERT INTO entity_edges (
          edge_id, domain, edge_kind, from_node_id, to_node_id, payload_json,
          source_kind,
          source_ref, valid_from, valid_to, fingerprint, ingest_run_id
        ) VALUES (?, 'catalog', ?, ?, ?, ?, 'test_fixture', ?, ?, NULL, ?,
        'test-ingest')
        """,
        (
            edge_id,
            edge_kind,
            from_node_id,
            to_node_id,
            json.dumps(payload, sort_keys=True),
            f"test:{edge_id}",
            OBSERVED_AT,
            "a" * 64,
        ),
    )


def _prepare_raw_spec_database(repo_root: Path) -> None:
    db_path = repo_root / DEFAULT_KNOWLEDGE_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as connection:
        _ = connection.executescript(read_engine_schema_sql())
        _ = connection.execute(
            """
            INSERT INTO make_raw_spec_manifest_records (
              app_slug, app_version, app_label, latest, manifest_version,
              relative_path,
              sha256, size_bytes, module_count, module_kinds_json,
              source_metadata_json,
              manifest_sha256, generated_at_utc, raw_spec_dir, source_kind,
              source_ref,
              valid_from, valid_to, fingerprint, ingest_run_id
            ) VALUES (?, ?, ?, 1, 2, '', ?, 100, 1, '[]', '{}', ?, ?, '',
              'test_fixture', ?, ?, NULL, ?, 'test-ingest')
            """,
            (
                "slack ",
                "1.0.0 ",
                "Slack",
                "a" * 64,
                "b" * 64,
                OBSERVED_AT,
                "sqlite:make_raw_spec_manifest_records/slack__1.0.0",
                OBSERVED_AT,
                "c" * 64,
            ),
        )
        _ = connection.execute(
            """
            INSERT INTO make_raw_spec_payloads (
              app_slug, app_version, payload_json, sha256, size_bytes,
              module_count,
              module_kinds_json, source_type, is_truncated, truncation_reason,
              sanitization_status, source_kind, source_ref, valid_from,
              valid_to,
              fingerprint, ingest_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                "slack ",
                "1.0.0",
                (
                    '{"app":{"label":"Slack","actions":[{"name":"Create '
                    'message"}]}}'
                ),
                "d" * 64,
                64,
                1,
                '["action"]',
                "local_fixture",
                0,
                "",
                "sanitized ",
                "test_fixture ",
                "sqlite:make_raw_spec_payloads/slack__1.0.0",
                OBSERVED_AT,
                "e" * 64,
                "test-ingest",
            ),
        )
        connection.commit()


def _semantic_output(
    *,
    unit_id: str,
    graph_nodes: list[JsonObject],
    graph_edges: list[JsonObject],
) -> JsonObject:
    return {
        "schema_version": "catalog_intelligence_answer_v1",
        "unit_id": unit_id,
        "unit_type": "raw_spec ",
        "source_ref": "sqlite:make_raw_spec_payloads/slack__1.0.0",
        "source_hash": "d" * 64,
        "semantic_summary": (
            "Slack message operations are useful for notifying teams, routing "
            "workflow "
            "events, and connecting chat context to downstream email or CRM "
            "actions."
        ),
        "app_family_aliases": ["slack", "team chat"],
        "module_roles": ["action", "message_delivery"],
        "setup_dependencies": [
            "Slack connection ",
            "target channel or recipient",
        ],
        "workflow_edges": [
            {
                "from": "trigger or webhook event ",
                "to": "Slack message action ",
                "inference_status": "inferred",
            }
        ],
        "module_semantics": [
            {
                "module_id": "module:slack:1.0.0:action:CreateMessage ",
                "classification": "action ",
                "auth_type": "oauth2 ",
                "output_cardinality": "single_bundle",
            }
        ],
        "capability_semantics": [
            {
                "capability": "team message delivery ",
                "risk_surface": "wrong channel or noisy notification",
            }
        ],
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "quarantine": [],
        "coverage": {
            "status": "complete_evidence_bound",
            "semantic_output": True,
            "graph_output": True,
            "credential_value_transfer": False,
            "provider_api_call": False,
            "live_make_called": False,
        },
        "evidence": {"source": "local raw spec fixture"},
        "control_surfaces": {"previewed_with": "catalog.semantic.preview"},
        "validation": {"language": "English"},
    }
