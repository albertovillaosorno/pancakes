# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""MCP linter quarantine SQLite intake contract tests."""

from __future__ import annotations

import sqlite3
from shutil import copytree
from typing import TYPE_CHECKING, cast

from catalog.knowledge import DEFAULT_DB_SNAPSHOT_DIR, DEFAULT_KNOWLEDGE_DB_PATH
from mcp import execute_mcp_tool, mcp_tool_registry

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repo_root()


def test_linter_quarantine_public_surface_keeps_intake_only() -> None:
    """Only the compact candidate intake tool remains public."""
    tool_names = {tool.name for tool in mcp_tool_registry()}

    assert "linter.quarantine.write" in tool_names
    assert _tool("linter", "quarantine", "list") not in tool_names
    assert _tool("linter", "quarantine", "review") not in tool_names


def test_linter_quarantine_write_records_candidate_in_sqlite_only(
    tmp_path: Path,
) -> None:
    """The tool records SQLite state without creating Markdown authority."""
    prepare_snapshot_dir(tmp_path)

    result = execute_mcp_tool(
        tool_name="linter.quarantine.write",
        arguments=_quarantine_arguments(),
        repo_root=tmp_path,
    )

    assert result.ok, f"linter.quarantine.write failed: {result.error}"
    assert result.payload["status"] == "created", result.payload
    assert result.payload["active_rule_written"] is False
    assert result.payload["candidate_markdown_written"] is False
    assert (
        result.payload["source_of_truth"] == "sqlite:linter_quarantine_records"
    )
    assert result.payload["sqlite_record_written"] is True
    assert not (
        tmp_path / "src/blueprints/validation/data/linter/quarantine"
    ).exists()
    assert sqlite_quarantine_rows(tmp_path) == [
        (
            "linter-quarantine:mcp-candidate-001",
            "MCP-CANDIDATE-001",
            "quarantined",
        )
    ]


def test_linter_quarantine_write_rejects_active_rule_states(
    tmp_path: Path,
) -> None:
    """The MCP tool cannot accept, rewrite, or activate linter candidates."""
    prepare_snapshot_dir(tmp_path)
    result = execute_mcp_tool(
        tool_name="linter.quarantine.write",
        arguments={**_quarantine_arguments(), "final_state": "accept"},
        repo_root=tmp_path,
    )

    assert not result.ok, "Active linter acceptance states should fail."


def test_linter_quarantine_removed_internal_tools_are_unknown(
    tmp_path: Path,
) -> None:
    """Internal list/review routes are gone from MCP dispatch."""
    for tool_name in (
        _tool("linter", "quarantine", "list"),
        _tool("linter", "quarantine", "review"),
    ):
        result = execute_mcp_tool(
            tool_name=tool_name, arguments={}, repo_root=tmp_path
        )
        assert not result.ok, result
        assert result.error == f"Unknown MCP tool: {tool_name}"


def _quarantine_arguments() -> dict[str, object]:
    return {
        "candidate_id": "MCP-CANDIDATE-001",
        "source_file": "docs/adr/mcp-server-slice-policy.md",
        "candidate_title": "Webhook Replay Policy Candidate",
        "quarantine_reason": "Missing deterministic fixtures.",
        "missing_evidence": "Needs failing and passing importability fixtures.",
        "proposed_predicate_text": (
            "Webhook payloads should declare bounded replay policy."
        ),
        "final_state": "quarantine",
    }


def _tool(*parts: str) -> str:
    return ".".join(parts)


def prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def sqlite_quarantine_rows(tmp_path: Path) -> list[tuple[str, str, str]]:
    """Return current synthetic quarantine rows."""
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        rows = cast(
            "list[tuple[str, str, str]]",
            connection.execute(
                """
                SELECT quarantine_id, finding_code, status
                FROM linter_quarantine_records
                ORDER BY quarantine_id
                """
            ).fetchall(),
        )
    finally:
        connection.close()
    return rows
