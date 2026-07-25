# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Importability tests for Make direct error-handler policy.

Boundary contract:
- Owns: focused importability and cycle checks for direct onerror structures.
- Must not: validate live Make behavior, repair blueprints, or infer business
rollback.
- Allows: sanitized offline fixtures and exact validation finding assertions.
- Split when: automatic repair of error paths becomes an implemented workflow.
- Merge when: broader importability tests own these exact onerror policies.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, iter_ast_nodes, parse_make_ast_json_text
from blueprints.validation.cycle_validation import validate_scenario_cycles
from blueprints.validation.importability import (
    IMPORTABILITY_ERROR_HANDLER_NESTED_UNSUPPORTED,
    validate_importability,
)

from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from blueprints.ast import MakeAstRoot
    from blueprints.validation.models import BlueprintValidationFinding

REPO_ROOT = repo_root()
FIXTURE_ROOT = REPO_ROOT / "tests" / "blueprints" / "fixtures" / "importability"
VALID_ONERROR_FIXTURE = FIXTURE_ROOT / "valid_onerror_flow.json"
INVALID_ONERROR_FIXTURE = FIXTURE_ROOT / "invalid_onerror_shape.json"


def test_valid_onerror_flow_does_not_break_cycle_validation() -> None:
    """Error-handler paths do not create normal forward-route cycle blockers."""
    root = parse_fixture(VALID_ONERROR_FIXTURE)
    findings = validate_scenario_cycles(root)

    assert not (findings), (
        f"Valid direct onerror flow created cycle findings: {findings}"
    )


def test_invalid_onerror_shape_reports_importability_finding() -> None:
    """Unsupported nested error-handler structures emit importability.

    findings.
    """
    root = parse_fixture(INVALID_ONERROR_FIXTURE)
    findings = validate_importability(iter_ast_nodes(root), root=root)
    finding = require_finding(
        findings, IMPORTABILITY_ERROR_HANDLER_NESTED_UNSUPPORTED
    )

    assert finding.severity == "error", (
        f"Nested onerror shape should be blocking: {finding}"
    )
    assert finding.node_id == "2", (
        f"Nested onerror finding should attach to handler node 2: {finding}"
    )
    expected_path = ("flow", 0, "onerror", 0, "onerror")
    assert finding.source_path == expected_path, (
        f"Nested onerror finding path drifted: {finding}"
    )
    assert not ("flow" not in finding.internal_message), (
        f"Nested onerror internal detail lost source context: {finding}"
    )
    assert not ("onerror" not in finding.internal_message), (
        f"Nested onerror internal detail lost source context: {finding}"
    )


def parse_fixture(path: Path) -> MakeAstRoot:
    """Parse one sanitized importability fixture through JSON text.

    Returns:
        The parsed AST root.
    """
    payload = object_from_json_file(path)
    return parse_make_ast_json_text(json.dumps(payload, sort_keys=True))


def object_from_json_file(path: Path) -> JsonObject:
    """Return one JSON object fixture."""
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), (
        f"Expected JSON object in {path}: {payload}"
    )
    return cast("JsonObject", payload)


def require_finding(
    findings: tuple[BlueprintValidationFinding, ...],
    code: str,
) -> BlueprintValidationFinding:
    """Return one validation finding by code or fail."""
    for finding in findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected finding code {code!r}; got {findings}"
    assert_unexpected_success(failure_message)
    return None
