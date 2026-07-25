# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Parser source-trace regressions for direct Make error handlers.

Boundary contract:
- Owns: focused parser coverage for direct onerror item source trace and
identity.
- Must not: validate catalog truth, render blueprints, or contact live Make
services.
- Allows: small sanitized inline blueprint payloads and typed AST assertions.
- Split when: renderer, validation, or repair behavior needs separate
error-handler tests.
- Merge when: the main AST contract owns these exact parser regressions.
"""

from __future__ import annotations

import json
from typing import Final

import pytest
from blueprints.ast import (
    JsonObject,
    MakeAstNode,
    MakeAstParseError,
    collect_ast_node_ids,
    parse_make_ast,
    parse_make_ast_json_text,
    require_ast_node,
)

EXPECTED_HANDLER_MODULE: Final = "builtin:Ignore"


def test_onerror_handler_preserves_source_path() -> None:
    """Direct onerror handlers keep their parent and error-handler JSON.

    paths.
    """
    root = parse_make_ast(_valid_onerror_source_trace_blueprint())
    parent = require_ast_node(root, "source")
    handler = require_ast_node(root, "handler")

    assert parent.source_trace.path == ("flow", 0), (
        f"Parent source path drifted: {parent.source_trace}"
    )
    assert handler.source_trace.path == ("flow", 0, "onerror", 0), (
        f"Handler source path drifted: {handler.source_trace}"
    )
    assert handler.source_trace.container_kind == "onerror", (
        f"Handler container trace drifted: {handler.source_trace}"
    )
    assert handler.source_trace.parent_node_id == "source", (
        f"Handler parent trace drifted: {handler.source_trace}"
    )


def test_onerror_handler_preserves_handler_node_identity() -> None:
    """Direct onerror handlers remain reachable once with their original node.

    fields.
    """
    root = parse_make_ast(_valid_onerror_source_trace_blueprint())
    parent = require_ast_node(root, "source")
    handler = require_ast_node(root, "handler")

    assert collect_ast_node_ids(root) == ("source", "handler"), (
        f"Handler traversal identity drifted: {collect_ast_node_ids(root)}"
    )
    assert parent.error_handlers == (handler,), (
        f"Parent direct error-handler children drifted: {parent.error_handlers}"
    )
    assert not (parent.error_handlers[0] is not handler), (
        "Traversal returned a duplicate handler instance."
    )
    assert handler.kind == "error_handler", (
        f"Direct handler kind drifted: {handler.kind}"
    )
    assert _handler_module(handler) == EXPECTED_HANDLER_MODULE, (
        f"Direct handler module drifted: {_handler_module(handler)}"
    )
    assert handler.source_trace.raw_node_id == "handler", (
        f"Direct handler raw node ID drifted: {handler.source_trace}"
    )
    assert _handler_raw_module(handler) == EXPECTED_HANDLER_MODULE, (
        f"Direct handler raw module drifted: {handler.source_trace}"
    )


def test_malformed_onerror_handler_reports_path() -> None:
    """Malformed direct onerror items fail with the existing parser error and.

    JSON path.
    """
    with pytest.raises(MakeAstParseError) as raised:
        _ = parse_make_ast_json_text(
            json.dumps(_malformed_onerror_source_trace_blueprint())
        )

    message = str(raised.value)
    assert not ("('flow', 0, 'onerror', 0)" not in message), (
        f"Malformed onerror item did not report its path: {message}"
    )
    assert not ("must be an object" not in message), (
        f"Malformed onerror item did not report the shape problem: {message}"
    )


def _handler_module(node: MakeAstNode) -> str:
    """Return the parsed module identifier for lint-friendly assertions."""
    return node.module_token


def _handler_raw_module(node: MakeAstNode) -> str:
    """Return the computed result for the caller."""
    return node.source_trace.raw_module_token


def _valid_onerror_source_trace_blueprint() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "name": "onerror-source-trace-regression",
        "flow": [
            {
                "id": "source",
                "module": "http:MakeRequest",
                "parameters": {
                    "method": "POST",
                    "url": "https://example.invalid/items",
                },
                "onerror": [
                    {
                        "id": "handler",
                        "module": EXPECTED_HANDLER_MODULE,
                        "parameters": {"reason": "offline regression fixture"},
                    }
                ],
            }
        ],
    }


def _malformed_onerror_source_trace_blueprint() -> JsonObject:
    """Return a sanitized malformed direct error-handler fixture."""
    return {
        "name": "malformed-onerror-source-trace-regression",
        "flow": [
            {
                "id": "source",
                "module": "http:MakeRequest",
                "onerror": ["not-an-object"],
            }
        ],
    }
