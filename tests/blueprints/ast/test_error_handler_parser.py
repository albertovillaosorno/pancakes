# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Parser regression tests for Make direct error-handler flows.

Boundary contract:
- Owns: focused parser coverage for direct onerror source trace preservation.
- Must not: validate importability, render, or inspect catalog records.
- Allows: sanitized offline fixture payloads and typed AST assertions.
- Split when: renderer or repair behavior needs separate error-handler tests.
- Merge when: the main AST contract owns these exact parser regressions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blueprints.ast import parse_make_ast_json_text, require_ast_node

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repo_root()
VALID_ONERROR_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "importability"
    / "valid_onerror_flow.json"
)


def test_parser_preserves_onerror_flow_and_source_path() -> None:
    """Parser keeps direct onerror children and their original JSON path."""
    root = parse_make_ast_json_text(
        VALID_ONERROR_FIXTURE.read_text(encoding="utf-8")
    )
    parent = require_ast_node(root, "1")
    handler = require_ast_node(root, "2")

    assert tuple(node.node_id for node in parent.error_handlers) == ("2",), (
        f"Direct onerror handler was not preserved: {parent.error_handlers}"
    )
    assert handler.kind == "error_handler", (
        f"Direct onerror child kind drifted: {handler.kind}"
    )
    assert handler.source_trace.parent_node_id == "1", (
        f"Direct onerror parent trace drifted: {handler.source_trace}"
    )
    assert handler.source_trace.container_kind == "onerror", (
        f"Direct onerror container trace drifted: {handler.source_trace}"
    )
    expected_path = ("flow", 0, "onerror", 0, "flow", 0)
    assert handler.source_trace.path == expected_path, (
        f"Direct onerror source path drifted: {handler.source_trace.path}"
    )
    assert handler.raw_payload.get("parameters") == {"scenario": "current"}, (
        f"Direct onerror raw payload was not preserved: {handler.raw_payload}"
    )
    assert_fixture_is_sanitized(VALID_ONERROR_FIXTURE)


def assert_fixture_is_sanitized(path: Path) -> None:
    """Fail if an offline fixture contains obvious private markers."""
    text = path.read_text(encoding="utf-8")
    forbidden_markers = ("api_key", "secret", "token", "client", "account_id")
    leaked_markers = tuple(
        marker for marker in forbidden_markers if marker in text.casefold()
    )
    assert not (leaked_markers), (
        f"Fixture contains private markers {leaked_markers}: {path}"
    )
