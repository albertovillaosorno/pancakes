# ruff: noqa: ERA001, S608
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# LARGE-FILE:
# owner: pancakes-mcp
# reason: Owns active catalog work lease/save MCP contract coverage.
# split: Separate lease initialization, safety payload, and atomic save behavior
# tests.
# validation: Focused pytest contract plus pancakes.mcp.smoke.
# review: Operator-requested Catalog Intelligence concurrency and safety-block
# repair.

"""Contracts for active guarded catalog work-run MCP tools.

Boundary contract:
- Owns: proof that public MCP clients can lease work without implicit progress
resets.
- Must not: call providers, use raw SQL as the public workflow, or reset runs by
default.
- Allows: synthetic SQLite raw-spec fixtures and deterministic MCP tool calls.
- Split when catalog worker scheduling becomes a dedicated service contract.
"""

from __future__ import annotations

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

ACTIVE_CATALOG_WORK_TOOLS = ("catalog.work.next", "catalog.work.save")
OBSERVED_AT = "2026-06-13T00:00:00+00:00"


def test_catalog_work_run_tools_are_active_public_mcp_tools() -> None:
    """Progress-run tooling remains available for explicit semantic refill.

    work.
    """
    public_tool_names = tuple(tool.name for tool in mcp_tool_registry())
    annotations = public_tool_annotation_specs()

    for tool_name in ACTIVE_CATALOG_WORK_TOOLS:
        assert tool_name in REQUIRED_TOOL_NAMES
        assert tool_name in public_tool_names
        assert tool_name in annotations
        assert tool_name in CONTRACT_SCHEMA_VERSIONS


def test_catalog_work_next_does_not_implicitly_create_fresh_run(
    tmp_path: Path,
) -> None:
    """Raw specs without an active run stay pending until explicit refill.

    approval.
    """
    _prepare_raw_spec_database(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.work.next",
        arguments={"worker_id": "ChatGPT.com"},
        repo_root=tmp_path,
    )

    assert not result.ok, result
    assert "Refusing to implicitly initialize a fresh worker queue" in str(
        result.error
    )
    with closing(_connect(tmp_path)) as connection:
        assert _row_count(connection, "catalog_runs") == 0
        assert _row_count(connection, "catalog_units") == 0
        assert _row_count(connection, "catalog_unit_outputs") == 0


def test_catalog_work_next_requires_explicit_initialization_for_refill(
    tmp_path: Path,
) -> None:
    """Operator-approved refill work may create a new active queue.

    explicitly.
    """
    _prepare_raw_spec_database(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.work.next",
        arguments={
            "worker_id": "ChatGPT.com/refill",
            "initialize_if_missing": True,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    assert result.payload["response_contract"] == "catalog.work.next"
    assert result.payload["run_id"] == "catalog"
    assert result.payload["worker_id"] == "ChatGPT.com/refill"
    assert result.payload["canonical_prompt_trigger"] == "Catalog Intelligence"
    assert "lease_handle" in result.payload
    assert "lease_token" not in result.payload
    parallel_worker_contract = cast(
        "dict[str, object]", result.payload["parallel_worker_contract"]
    )
    lease_contract = cast("dict[str, object]", result.payload["lease_contract"])
    assert parallel_worker_contract["many_workers_supported"] is True
    assert lease_contract["requires_lease_handle"] is True
    assert lease_contract["wrong_worker_or_handle_rejected"] is True
    batch_unit_count = result.payload["batch_unit_count"]
    assert isinstance(batch_unit_count, int)
    assert not isinstance(batch_unit_count, bool)
    assert batch_unit_count > 0
    with closing(_connect(tmp_path)) as connection:
        assert _row_count(connection, "catalog_runs") == 1
        assert _row_count(connection, "catalog_units") > 0
        assert _row_count(connection, "catalog_unit_outputs") == 0


def test_catalog_work_next_defaults_to_safety_shaped_source_packets(
    tmp_path: Path,
) -> None:
    """ChatGPT-safe lease payloads avoid token-shaped public fields and raw.

    operation packets.
    """
    _prepare_raw_spec_database(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.work.next",
        arguments={
            "worker_id": "ChatGPT.com/safe-refill",
            "initialize_if_missing": True,
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload_text = str(result.payload)
    assert "lease_token" not in payload_text
    assert "lease_handle" in result.payload
    units = cast("list[dict[str, object]]", result.payload["units"])
    packet_units = [
        unit
        for unit in units
        if "source_packet" in unit
        and cast("dict[str, object]", unit["source_packet"])["packet_kind"]
        == "operation_batch"
    ]
    assert packet_units
    source_packet = cast("dict[str, object]", packet_units[0]["source_packet"])
    source_packet_policy = cast(
        "dict[str, object]", packet_units[0]["source_packet_policy"]
    )
    assert source_packet["source_packet_mode"] == "summary"
    assert source_packet_policy["complete_packet_included"] is False
    assert source_packet_policy["safety_shaped_summary_default"] is True
    assert "operations" not in source_packet
    assert "operation_summaries" in source_packet


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


def _connect(repo_root: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(repo_root / DEFAULT_KNOWLEDGE_DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _row_count(connection: sqlite3.Connection, table_name: str) -> int:
    if table_name not in {
        "catalog_runs ",
        "catalog_units ",
        "catalog_unit_outputs",
    }:
        msg = f"Unexpected table name: {table_name}"
        raise AssertionError(msg)
    cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name}")
    try:
        row = cast("sqlite3.Row | None", cursor.fetchone())
    finally:
        cursor.close()
    if row is None:
        msg = f"Missing count row for table: {table_name}"
        raise AssertionError(msg)
    return cast("int", row[0])
