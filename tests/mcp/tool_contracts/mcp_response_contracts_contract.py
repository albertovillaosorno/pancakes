# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for active MCP response metadata."""

from __future__ import annotations

import pytest
from mcp.registry import REQUIRED_TOOL_NAMES
from mcp.response_contracts import (
    CONTRACT_SCHEMA_VERSIONS,
    attach_response_contract,
)


def test_response_contract_versions_cover_only_active_mcp_tools() -> None:
    """Active public tools have metadata and removed tools do not."""
    assert tuple(CONTRACT_SCHEMA_VERSIONS) == REQUIRED_TOOL_NAMES
    assert _tool("project", "list") not in CONTRACT_SCHEMA_VERSIONS
    assert _tool("project", "tests", "run") not in CONTRACT_SCHEMA_VERSIONS
    assert _tool("scraper", "refresh_status") not in CONTRACT_SCHEMA_VERSIONS


def test_attach_response_contract_uses_active_tool_version() -> None:
    """Shared response metadata remains deterministic for active tools."""
    payload = attach_response_contract(
        tool_name="catalog.search",
        payload={"status": "ok"},
    )

    assert payload["response_contract"] == "catalog.search"
    assert payload["response_schema_version"] == 2
    assert payload["output_mode"] == "compact"
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert payload["credential_value_transfer"] is False
    assert payload["secret_output"] is False
    assert payload["status"] == "ok"
    assert payload["permission_posture"] == "read_only_local_no_approval"
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert payload["requires_operator_approval"] is False


def test_attach_response_contract_reports_dry_run_no_write_posture() -> None:
    """Dry-run write-capable tools are explicitly no-write local previews."""
    payload = attach_response_contract(
        tool_name="project.make",
        payload={
            "status": "ready",
            "dry_run": True,
            "would_change": True,
            "writes_performed": False,
            "write_actions": [],
        },
    )

    assert payload["permission_posture"] == "local_dry_run_no_write_no_approval"
    assert payload["dry_run"] is True
    assert payload["would_change"] is True
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert payload["requires_operator_approval"] is False


def test_attach_response_contract_reports_truthful_local_write_posture() -> (
    None
):
    """Local writes are no-approval only when labeled as writes."""
    payload = attach_response_contract(
        tool_name="project.edit",
        payload={
            "status": "updated",
            "writes_performed": True,
            "write_actions": ["write_project_notes"],
        },
    )

    assert (
        payload["permission_posture"]
        == "local_transactional_write_session_scoped"
    )
    assert payload["writes_performed"] is True
    assert payload["write_actions"] == ["write_project_notes"]
    assert payload["requires_operator_approval"] is False


def test_response_contract_rejects_write_claiming_read_only_posture() -> None:
    """A real write must never be mislabeled as read-only."""
    with pytest.raises(ValueError, match="writes_performed=true"):
        _ = attach_response_contract(
            tool_name="project.edit",
            payload={
                "status": "updated",
                "writes_performed": True,
                "write_actions": ["write_project_notes"],
                "permission_posture": "read_only_local_no_approval",
            },
        )


def test_response_contract_rejects_write_actions_without_write_flag() -> None:
    """No-write responses cannot smuggle write actions."""
    with pytest.raises(ValueError, match="writes_performed=false"):
        _ = attach_response_contract(
            tool_name="project.edit",
            payload={
                "status": "updated",
                "writes_performed": False,
                "write_actions": ["write_project_notes"],
            },
        )


def _tool(*parts: str) -> str:
    return ".".join(parts)
