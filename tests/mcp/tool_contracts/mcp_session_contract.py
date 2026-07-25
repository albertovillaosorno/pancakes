# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""MCP session intent contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp import execute_mcp_tool

if TYPE_CHECKING:
    from pathlib import Path


def test_mcp_session_start_is_local_no_write_intent_receipt(
    tmp_path: Path,
) -> None:
    """mcp.session.start produces a no-write local scope receipt."""
    result = execute_mcp_tool(
        tool_name="mcp.session.start",
        arguments={
            "operator_intent": (
                "Run a local Pancakes Make scenario audit session."
            ),
            "worker_id": "worker-session",
            "allowed_local_write_surfaces": {"project.local": True},
            "expires_at": "2099-01-01T00:00:00Z",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["response_contract"] == "mcp.session.start"
    assert payload["permission_posture"] == "read_only_local_no_approval"
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert payload["credential_value_transfer"] is False
    assert payload["secret_output"] is False
    assert payload["requires_operator_approval"] is False
    assert (
        payload["session_security_model"]
        == "intent_marker_not_provider_authorization"
    )


def test_session_token_marks_scoped_local_dry_run_without_writing(
    tmp_path: Path,
) -> None:
    """A session token can scope a dry-run write tool without changing no-write.

    posture.
    """
    session = execute_mcp_tool(
        tool_name="mcp.session.start",
        arguments={
            "operator_intent": "Preview local project changes.",
            "worker_id": "worker-session",
            "allowed_local_write_surfaces": {"project.local": True},
            "expires_at": "2099-01-01T00:00:00Z",
        },
        repo_root=tmp_path,
    )
    session_payload = session.payload
    preview = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "sessioned-preview",
            "dry_run": True,
            "worker_id": "worker-session",
            "session_intent_id": session_payload["session_intent_id"],
            "session_token": session_payload["session_token"],
        },
        repo_root=tmp_path,
    )

    assert preview.ok, preview
    payload = preview.payload
    assert payload["session_scope_validated"] is True
    assert payload["session_intent_id"] == session_payload["session_intent_id"]
    assert payload["permission_posture"] == "local_dry_run_no_write_no_approval"
    assert payload["dry_run"] is True
    assert payload["writes_performed"] is False
    assert payload["write_actions"] == []
    assert not (tmp_path / "projects" / "sessioned-preview").exists()


def test_session_scope_rejects_wrong_worker_and_unapproved_surface(
    tmp_path: Path,
) -> None:
    """Session scope is explicit and cannot be replayed by another worker or.

    surface.
    """
    session = execute_mcp_tool(
        tool_name="mcp.session.start",
        arguments={
            "operator_intent": "Preview local project changes.",
            "worker_id": "worker-session",
            "allowed_local_write_surfaces": {"project.local": True},
            "expires_at": "2099-01-01T00:00:00Z",
        },
        repo_root=tmp_path,
    )
    session_payload = session.payload

    wrong_worker = execute_mcp_tool(
        tool_name="project.create",
        arguments={
            "project_id": "wrong-worker-preview",
            "dry_run": True,
            "worker_id": "other-worker",
            "session_intent_id": session_payload["session_intent_id"],
            "session_token": session_payload["session_token"],
        },
        repo_root=tmp_path,
    )
    wrong_surface = execute_mcp_tool(
        tool_name="catalog.review.add",
        arguments={
            "review_id": "review:session-scope ",
            "domain": "catalog ",
            "target_kind": "unit ",
            "target_id": "unit-session",
            "payload_json": {},
            "dry_run": True,
            "worker_id": "worker-session",
            "session_intent_id": session_payload["session_intent_id"],
            "session_token": session_payload["session_token"],
        },
        repo_root=tmp_path,
    )

    assert not wrong_worker.ok
    assert wrong_worker.error == "session_worker_id_mismatch"
    assert not wrong_surface.ok
    assert wrong_surface.error == "session_scope_does_not_allow_tool"
