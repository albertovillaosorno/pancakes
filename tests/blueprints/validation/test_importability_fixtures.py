# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Validation tests for sanitized Make importability fixtures.

Boundary contract:
- Owns: fixture-level validation coverage for sanitized importability examples.
- Must not: contact Make.com, inspect live workspaces, or snapshot full reports.
- Allows: offline fixture loading, focused finding-code checks, and source-path
checks.
- Split when: broad validator rules move into dedicated contract tests.
- Merge when: another test module owns these exact importability fixtures.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.validation.models import BlueprintValidationReport

FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
VALID_LEAD_ROUTING_FIXTURE = FIXTURE_ROOT / "valid_lead_routing_router.json"
INVALID_NON_ROUTER_ROUTES_FIXTURE = (
    FIXTURE_ROOT / "invalid_routes_on_non_router.json"
)
INVALID_PLACEHOLDER_FIXTURE = (
    FIXTURE_ROOT / "invalid_unresolved_placeholder.json"
)
INVALID_NOTE_FIXTURE = FIXTURE_ROOT / "invalid_metadata_note_string.json"


def test_valid_lead_routing_router_fixture_has_no_error_findings() -> None:
    """The valid sanitized router fixture should remain offline-importability.

    clean.
    """
    report = validate_fixture(VALID_LEAD_ROUTING_FIXTURE)

    error_codes = tuple(
        finding.code
        for finding in report.findings
        if finding.severity == "error"
    )
    assert not (error_codes), (
        f"Valid lead-routing fixture emitted error findings: {report.findings}"
    )


def test_routes_on_non_router_fixture_reports_route_path() -> None:
    """A non-router with direct routes preserves the invalid route source.

    path.
    """
    report = validate_fixture(INVALID_NON_ROUTER_ROUTES_FIXTURE)

    assert_finding(
        report, code="route.empty_flow", source_path=("flow", 0, "routes", 0)
    )


def test_unresolved_placeholder_fixture_reports_parameter_path() -> None:
    """Unresolved runtime placeholders in parameters emit an importability.

    blocker.
    """
    report = validate_fixture(INVALID_PLACEHOLDER_FIXTURE)

    assert_finding(
        report,
        code="importability.placeholder_unresolved",
        source_path=("flow", 0, "parameters", "datastore"),
    )


def test_metadata_note_string_fixture_preserves_note_invalid_behavior() -> None:
    """String metadata notes keep the current note-shape finding."""
    report = validate_fixture(INVALID_NOTE_FIXTURE)

    assert_finding(
        report, code="ast.note_invalid", source_path=("metadata", "notes", 0)
    )


def validate_fixture(path: Path) -> BlueprintValidationReport:
    """Validate one sanitized fixture with the local native-module catalog.

    Returns:
        The blueprint validation report for the fixture.
    """
    return validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(load_fixture(path), sort_keys=True)
        ),
        catalog=native_module_snapshot(),
    )


def assert_finding(
    report: BlueprintValidationReport,
    *,
    code: str,
    source_path: tuple[str | int, ...],
) -> None:
    """Assert one validation finding exists at the exact source path."""
    matches = [
        finding
        for finding in report.findings
        if finding.code == code and finding.source_path == source_path
    ]
    assert matches, (
        f"Expected finding {code!r} at {source_path!r}; got {report.findings}"
    )


def load_fixture(path: Path) -> JsonObject:
    """Load one sanitized JSON object fixture.

    Returns:
        The loaded fixture payload.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))
