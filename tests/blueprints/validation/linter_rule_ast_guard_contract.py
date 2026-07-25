# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for MCP linter rule predicate AST guards."""

from __future__ import annotations

from blueprints.validation import validate_linter_predicate_source


def test_linter_rule_ast_guard_rejects_constant_predicates() -> None:
    """A submitted predicate must inspect scenario payload, not return a fixed.

    result.
    """
    report = validate_linter_predicate_source(
        """
def fake_predicate(node: dict[str, object]) -> bool:
    return True
""",
        expected_failure_code="http.method_url_missing",
    )

    assert not report.ok
    assert (
        "fake_predicate_detected: predicate is constant boolean"
        in report.errors
    )
    assert (
        "fake_predicate_detected: predicate does not inspect blueprint payload"
        in report.errors
    )


def test_linter_rule_ast_guard_rejects_89f835b2() -> None:
    """Submitted predicate code cannot read secrets, files, SQLite, or network.

    clients.
    """
    report = validate_linter_predicate_source(
        """
import os
import sqlite3
from urllib import request

def unsafe_predicate(node: dict[str, object]) -> bool:
    value = open(".env").read()
    return node.get("module") == "http:ActionSendData" and bool(value)
""",
        expected_failure_code="http.method_url_missing",
    )

    assert not report.ok
    assert "unauthorized_import: os" in report.errors
    assert "unauthorized_import: sqlite3" in report.errors
    assert "unauthorized_import: urllib" in report.errors
    assert "unauthorized_call: open" in report.errors
    assert "secret_or_credential_marker_not_allowed: .env" in report.errors


def test_linter_rule_ast_guard_accepts_payload_field_predicate() -> None:
    """A deterministic predicate with typed input, field checks, and finding.

    code.

    passes.
    """
    report = validate_linter_predicate_source(
        """
from collections.abc import Mapping

def detect_missing_http_method(node: Mapping[str, object]) -> bool:
    failure_code = "http.method_url_missing"
    parameters = node.get("parameters", {})
    if not isinstance(parameters, Mapping):
        return False
    return bool(
        failure_code
        and node.get("module") == "http:ActionSendData"
        and not parameters.get("method")
    )
""",
        expected_failure_code="http.method_url_missing",
    )

    assert report.ok, report.errors
    assert report.predicate_name == "detect_missing_http_method"
    assert "module" in report.inspected_payload_terms
    assert "parameters" in report.inspected_payload_terms
