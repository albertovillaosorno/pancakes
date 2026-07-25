# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""HTTP transport contracts for the minimal MCP surface."""

from __future__ import annotations

from mcp.http_server import (
    DEFAULT_PUBLIC_BASE_URL,
    LOCAL_ARTIFACT_PERMISSION_COPY,
    PUBLIC_BASE_DOMAIN,
    PUBLIC_HOST_UUID,
)
from mcp.registry import REQUIRED_TOOL_NAMES

EXPECTED_PUBLIC_HOST_UUID = "019e73f6-c164-79b9-8e29-82758c7b3eaa"
EXPECTED_PUBLIC_BASE_URL = (
    f"https://{EXPECTED_PUBLIC_HOST_UUID}.humbertoschoenwald.com"
)


def test_http_tool_copy_mentions_only_active_tools() -> None:
    """HTTP progress copy does not advertise deleted MCP routes."""
    active = set(REQUIRED_TOOL_NAMES)

    assert set(LOCAL_ARTIFACT_PERMISSION_COPY).issubset(active)
    for removed_name in (
        _tool("project", "tests", "write"),
        _tool("scraper", "refresh_status"),
    ):
        assert removed_name not in LOCAL_ARTIFACT_PERMISSION_COPY


def test_remote_mcp_default_public_base_url_uses_operator_uuid_host() -> None:
    """The remote MCP default URL uses the public UUID hostname."""
    assert PUBLIC_HOST_UUID == EXPECTED_PUBLIC_HOST_UUID
    assert PUBLIC_BASE_DOMAIN == "humbertoschoenwald.com"
    assert DEFAULT_PUBLIC_BASE_URL == EXPECTED_PUBLIC_BASE_URL
    assert (
        "mcp.humbertoschoenwald.com" not in DEFAULT_PUBLIC_BASE_URL
    )


def _tool(*parts: str) -> str:
    return ".".join(parts)
