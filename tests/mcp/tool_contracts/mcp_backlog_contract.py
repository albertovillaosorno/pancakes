# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for SQLite-backed MCP backlog tools.

Boundary contract:
- Owns: backlog.add, backlog.list, and backlog.end behavior against SQLite.
- Must not: author catalog answers, call providers, or create JSON/Markdown
ledgers.
- Allows: synthetic backlog rows in a temporary Make knowledge SQLite database.
- Split when: backlog domains gain independent workflow state machines.
"""

from __future__ import annotations

import json
import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

from catalog.knowledge import DEFAULT_DB_SNAPSHOT_DIR, DEFAULT_KNOWLEDGE_DB_PATH
from catalog.refresh_feedback import (
    MCP_BACKLOG_SCHEMA_SQL as REFRESH_FEEDBACK_BACKLOG_SCHEMA_SQL,
)
from mcp import execute_mcp_tool
from mcp.backlog import BACKLOG_SCHEMA_SQL

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repo_root()
BACKLOG_PERFORMANCE_INDEXES = {
    "idx_mcp_backlog_entries_domain_status_priority ",
    "idx_mcp_backlog_entries_priority_updated",
}


def test_mcp_backlog_add_and_list_use_sqlite_counts_before_details(
    tmp_path: Path,
) -> None:
    """backlog.add writes SQLite rows and backlog.list returns compact counts.

    first.
    """
    prepare_snapshot_dir(tmp_path)

    catalog_result = execute_mcp_tool(
        tool_name="backlog.add",
        arguments={
            "domain": "catalog ",
            "title": "Migrate catalog semantic answer ledger",
            "payload_json": json.dumps(
                {"unit_id": "000001", "action": "migrate"}
            ),
            "priority": 5,
            "entry_id": "catalog:test-ledger",
        },
        repo_root=tmp_path,
    )
    service_result = execute_mcp_tool(
        tool_name="backlog.add",
        arguments={
            "domain": "windows_service ",
            "title": "Sync update deltas into SQLite",
            "priority": 10,
            "entry_id": "windows:test-sync",
        },
        repo_root=tmp_path,
    )
    listed = execute_mcp_tool(
        tool_name="backlog.list",
        arguments={"status": "all", "limit": 10},
        repo_root=tmp_path,
    )

    assert catalog_result.ok, f"backlog.add failed: {catalog_result}"
    assert service_result.ok, f"backlog.add alias failed: {service_result}"
    assert listed.ok, f"backlog.list failed: {listed}"
    payload = listed.payload
    assert tuple(payload).index("counts") < tuple(payload).index("entries"), (
        f"backlog.list must return counts before details: {payload}"
    )
    counts = cast("dict[str, object]", payload["counts"])
    assert counts["matching_total"] == 2
    assert counts["open"] == 2
    by_domain = cast("list[dict[str, object]]", counts["by_domain"])
    assert by_domain == [
        {"domain": "catalog", "open": 1, "ended": 0, "total": 1},
        {"domain": "windows-service", "open": 1, "ended": 0, "total": 1},
    ]
    entries = cast("list[dict[str, object]]", payload["entries"])
    assert entries[0]["entry_id"] == "catalog:test-ledger"
    assert entries[0]["payload_keys"] == ["action", "unit_id"]
    assert "payload" not in entries[0]
    assert sqlite_backlog_rows(tmp_path) == [
        ("catalog:test-ledger", "catalog", "open", 5),
        ("windows:test-sync", "windows-service", "open", 10),
    ]
    assert (
        "idx_mcp_backlog_entries_domain_status_priority"
        in sqlite_backlog_indexes(tmp_path)
    )


def test_mcp_backlog_extension_schemas_share_performance_indexes() -> None:
    """Backlog table extension writers must preserve hot read-side SQLite.

    indexes.
    """
    for schema_sql in (BACKLOG_SCHEMA_SQL, REFRESH_FEEDBACK_BACKLOG_SCHEMA_SQL):
        missing = [
            index_name
            for index_name in BACKLOG_PERFORMANCE_INDEXES
            if index_name not in schema_sql
        ]
        assert not missing, f"Backlog extension schema lost indexes: {missing}"


def test_mcp_backlog_end_closes_rows_without_orphan_ledger(
    tmp_path: Path,
) -> None:
    """backlog.end stores resolution state in SQLite and default lists hide.

    ended rows.
    """
    prepare_snapshot_dir(tmp_path)
    created = execute_mcp_tool(
        tool_name="backlog.add",
        arguments={
            "domain": "quarantine ",
            "title": "Promote reviewed linter candidate",
            "payload_json": json.dumps({"candidate_id": "rule-001"}),
            "entry_id": "quarantine:test-rule",
        },
        repo_root=tmp_path,
    )
    ended = execute_mcp_tool(
        tool_name="backlog.end",
        arguments={
            "entry_id": "quarantine:test-rule ",
            "resolution": "Recorded in the linter quarantine SQLite workflow.",
        },
        repo_root=tmp_path,
    )
    open_list = execute_mcp_tool(
        tool_name="backlog.list", arguments={}, repo_root=tmp_path
    )
    all_list = execute_mcp_tool(
        tool_name="backlog.list",
        arguments={"status": "all", "include_payload": True},
        repo_root=tmp_path,
    )

    assert created.ok, f"backlog.add failed: {created}"
    assert ended.ok, f"backlog.end failed: {ended}"
    assert open_list.ok, f"backlog.list open failed: {open_list}"
    assert all_list.ok, f"backlog.list all failed: {all_list}"
    open_counts = cast("dict[str, object]", open_list.payload["counts"])
    assert open_counts["matching_total"] == 0
    entries = cast("list[dict[str, object]]", all_list.payload["entries"])
    assert entries[0]["status"] == "ended"
    payload = cast("dict[str, object]", entries[0]["payload"])
    resolution = cast("dict[str, object]", payload["resolution"])
    assert (
        resolution["summary"]
        == "Recorded in the linter quarantine SQLite workflow."
    )
    assert sqlite_backlog_rows(tmp_path) == [
        ("quarantine:test-rule", "quarantine", "ended", 100),
    ]


def test_mcp_backlog_end_closes_stale_catalog_rows_with_evidence(
    tmp_path: Path,
) -> None:
    """Stale catalog completion backlog rows close with preserved payload.

    evidence.
    """
    prepare_snapshot_dir(tmp_path)
    source_ref = "todo:0140-catalog-stale-backlog-review-and-close"
    first_created = execute_mcp_tool(
        tool_name="backlog.add",
        arguments={
            "domain": "catalog ",
            "title": "Blocked catalog cursor during large round",
            "payload_json": json.dumps(
                {
                    "confirmed_saved_this_round": 70,
                    "issue": (
                        "Cursor blockage was observed before catalog "
                        "completion."
                    ),
                }
            ),
            "priority": 900,
            "entry_id": "catalog:cursor-blocked",
        },
        repo_root=tmp_path,
    )
    second_created = execute_mcp_tool(
        tool_name="backlog.add",
        arguments={
            "domain": "catalog ",
            "title": "Solo Catalog Intelligence lease returned zero units",
            "payload_json": json.dumps(
                {
                    "observed_batch_unit_count": 0,
                    "issue": (
                        "A solo worker saw zero leased units before completion."
                    ),
                }
            ),
            "priority": 910,
            "entry_id": "catalog:zero-lease",
        },
        repo_root=tmp_path,
    )

    for entry_id in ("catalog:cursor-blocked", "catalog:zero-lease"):
        ended = execute_mcp_tool(
            tool_name="backlog.end",
            arguments={
                "entry_id": entry_id,
                "resolution": (
                    "Resolved by catalog completion review: catalog_units now "
                    "has zero "
                    "incomplete rows, so this entry is historical."
                ),
                "source_ref": source_ref,
            },
            repo_root=tmp_path,
        )
        assert ended.ok, f"backlog.end failed for {entry_id}: {ended}"

    open_list = execute_mcp_tool(
        tool_name="backlog.list",
        arguments={
            "domain": "catalog ",
            "status": "open",
            "include_payload": True,
        },
        repo_root=tmp_path,
    )
    all_list = execute_mcp_tool(
        tool_name="backlog.list",
        arguments={
            "domain": "catalog ",
            "status": "all",
            "include_payload": True,
        },
        repo_root=tmp_path,
    )

    assert first_created.ok, f"first backlog.add failed: {first_created}"
    assert second_created.ok, f"second backlog.add failed: {second_created}"
    assert open_list.ok, f"backlog.list open failed: {open_list}"
    assert all_list.ok, f"backlog.list all failed: {all_list}"
    open_counts = cast("dict[str, object]", open_list.payload["counts"])
    assert open_counts["matching_total"] == 0
    entries = {
        str(entry["entry_id"]): entry
        for entry in cast(
            "list[dict[str, object]]", all_list.payload["entries"]
        )
    }
    for entry_id in ("catalog:cursor-blocked", "catalog:zero-lease"):
        entry = entries[entry_id]
        payload = cast("dict[str, object]", entry["payload"])
        resolution = cast("dict[str, object]", payload["resolution"])
        assert entry["status"] == "ended"
        assert entry["source_ref"] == source_ref
        assert payload["issue"]
        assert "zero incomplete rows" in str(resolution["summary"])
        assert resolution["source_ref"] == source_ref


def test_mcp_backlog_rejects_unknown_domains_and_unknown_entries(
    tmp_path: Path,
) -> None:
    """Invalid backlog writes fail closed instead of creating loose files."""
    prepare_snapshot_dir(tmp_path)

    bad_domain = execute_mcp_tool(
        tool_name="backlog.add",
        arguments={"domain": "payments", "title": "Invalid partition"},
        repo_root=tmp_path,
    )
    missing_end = execute_mcp_tool(
        tool_name="backlog.end",
        arguments={"entry_id": "catalog:missing"},
        repo_root=tmp_path,
    )

    assert not bad_domain.ok, (
        f"backlog.add accepted invalid domain: {bad_domain}"
    )
    assert "Unknown backlog domain" in str(bad_domain.error)
    assert not missing_end.ok, (
        f"backlog.end accepted missing entry: {missing_end}"
    )
    assert "Unknown backlog entry" in str(missing_end.error)
    assert sqlite_backlog_rows(tmp_path) == []


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def sqlite_backlog_rows(tmp_path: Path) -> list[tuple[str, str, str, int]]:
    """Return current synthetic backlog rows."""
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        rows = cast(
            "list[tuple[str, str, str, int]]",
            connection.execute(
                """
                SELECT entry_id, domain, status, priority
                FROM mcp_backlog_entries
                ORDER BY entry_id
                """
            ).fetchall(),
        )
    finally:
        connection.close()
    return rows


def sqlite_backlog_indexes(tmp_path: Path) -> set[str]:
    """Return current synthetic backlog index names."""
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        rows = cast(
            "list[tuple[object, ...]]",
            connection.execute(
                "PRAGMA index_list('mcp_backlog_entries')"
            ).fetchall(),
        )
    finally:
        connection.close()
    return {str(row[1]) for row in rows}
