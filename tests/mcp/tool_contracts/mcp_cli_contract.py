# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for the local MCP command entrypoint.

Boundary contract:
- Owns: tests for deterministic `python -B -m mcp` inspection commands.
- Must not: execute MCP tools, open network listeners, or start live tunnels.
- Allows: in-process CLI calls and captured JSON payload assertions.
- Split when: real MCP transports add separate runtime commands.
- Merge when: the MCP server contract owns only this command behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from mcp import (
    CATALOG_INTELLIGENCE_PROMPT_NAME,
    MCP_SERVER_NAME,
    REQUIRED_TOOL_NAMES,
)
from mcp.__main__ import main as mcp_cli_main

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture

    from tests.support.json_payloads import JsonObject


def test_mcp_cli_reports_stdio_startup_contract(
    capsys: CaptureFixture[str],
) -> None:
    """The local MCP CLI reports startup state without live networking."""
    exit_code = mcp_cli_main(["start"])
    payload = cast("JsonObject", json.loads(capsys.readouterr().out))

    assert exit_code == 0, f"MCP CLI returned {exit_code}."
    assert payload.get("server_name") == MCP_SERVER_NAME, (
        f"MCP CLI server name drifted: {payload}"
    )
    assert payload.get("transports") == ["stdio"], (
        f"MCP CLI must stay stdio-only by default: {payload}"
    )
    assert not (payload.get("live_network_transport") is not False), (
        f"MCP CLI must not enable live network transport: {payload}"
    )
    assert payload.get("tool_names") == list(REQUIRED_TOOL_NAMES), (
        f"MCP CLI tool registry drifted: {payload}"
    )
    assert payload.get("resource_uris") == [], (
        f"MCP startup must not advertise retired Markdown resources: {payload}"
    )
    assert payload.get("prompt_names") == [CATALOG_INTELLIGENCE_PROMPT_NAME], (
        f"MCP startup must expose only the explicit catalog prompt: {payload}"
    )


LOCAL_WORKSPACE_WRITE_TOOLS = (
    "catalog.modify",
    "catalog.node.modify",
    "catalog.edge.propose",
    "catalog.edge.apply",
    "catalog.review.add",
    "project.draft.stage",
    "project.draft.import",
    "project.create",
    "project.edit",
    "project.make",
    "project.modules.add",
    "project.modules.modify",
    "project.filters.add",
    "project.filters.modify",
    "project.error_handlers.add",
    "project.error_handlers.modify",
    "linter.quarantine.write",
    "linter.rule.next",
    "linter.rule.implement",
    "linter.rule.merge_canonical",
    "linter.rule.reject_invalid",
    "linter.rule.edit",
    "backlog.add",
    "backlog.end",
)
LOCAL_WORKSPACE_DESTRUCTIVE_TOOLS = ("linter.rule.rollback",)
OPERATOR_GATED_LIVE_TOOLS: tuple[str, ...] = ()


def test_mcp_cli_reports_registry_safety_posture(
    capsys: CaptureFixture[str],
) -> None:
    """The local MCP CLI lists registry metadata without executing tools."""
    exit_code = mcp_cli_main(["tools"])
    payload = cast("JsonObject", json.loads(capsys.readouterr().out))
    tools = cast("list[JsonObject]", payload.get("tools"))
    tool_names = [tool.get("name") for tool in tools]

    assert exit_code == 0, f"MCP tools CLI returned {exit_code}."
    assert tool_names == list(REQUIRED_TOOL_NAMES), (
        f"MCP tools CLI registry drifted: {payload}"
    )
    for tool in tools:
        expected_read_only = tool.get("name") not in {
            *LOCAL_WORKSPACE_WRITE_TOOLS,
            *LOCAL_WORKSPACE_DESTRUCTIVE_TOOLS,
            *OPERATOR_GATED_LIVE_TOOLS,
        }
        assert not (tool.get("read_only") is not expected_read_only), (
            f"MCP tools CLI reported wrong safety posture: {payload}"
        )


def test_mcp_cli_rejects_retired_resource_registry_command(
    capsys: CaptureFixture[str],
) -> None:
    """The local MCP CLI does not keep a route for retired public resources."""
    with pytest.raises(SystemExit) as exc_info:
        _ = mcp_cli_main(["resources"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "invalid choice: 'resources'" in captured.err
