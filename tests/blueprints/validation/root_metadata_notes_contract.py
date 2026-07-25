# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Root metadata note validation contract tests.

Boundary contract:
- Owns: root metadata notes shape behavior for Make blueprint validation.
- Must not: test note rendering, catalog compilation, or live Make behavior.
- Allows: small sanitized AST payloads and exact note finding paths.
- Split when: note validation gains independent renderer or repair contracts.
- Merge when: blueprint validation tests already cover these exact note paths.
"""

from __future__ import annotations

import json

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import (
    BlueprintValidationFinding,
    BlueprintValidationReport,
    validate_blueprint,
)

from tests.blueprints.validation.blueprint_validation_contract import (
    assert_client_messages_are_path_safe,
    load_catalog_fixture,
)
from tests.support.assertions import assert_unexpected_success


def test_structured_root_notes_are_validated_without_shape_findings() -> None:
    """Structured Make-native root notes are accepted when anchors are valid."""
    report = validate_payload(
        [
            {
                "content": "Review the accepted route before import.",
                "moduleIds": [1],
                "metadata": {"color": "#ffffcc"},
            }
        ]
    )

    assert not (note_codes(report.findings)), (
        f"Structured notes produced shape findings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_legacy_string_root_notes_report_note_index() -> None:
    """Legacy string notes are rejected with a path to the note item."""
    report = validate_payload(["Legacy draft note.", "Second draft note."])

    finding = require_note_finding(report.findings, "ast.note_invalid")

    assert finding.source_path == ("metadata", "notes", 0), (
        f"Legacy note source path drifted: {finding}"
    )
    assert_client_messages_are_path_safe(report)


def test_mixed_root_note_types_report_bad_list_index() -> None:
    """Mixed legacy and structured note lists are rejected at the bad index."""
    report = validate_payload(
        [
            {"content": "Structured note.", "moduleIds": [1]},
            "Legacy note mixed into structured notes.",
        ]
    )

    finding = require_note_finding(report.findings, "ast.note_invalid")

    assert finding.source_path == ("metadata", "notes", 1), (
        f"Mixed note source path drifted: {finding}"
    )
    assert_client_messages_are_path_safe(report)


def test_non_list_root_notes_report_notes_container_path() -> None:
    """Root metadata.notes must be a list when present."""
    report = validate_payload("not a notes list")

    finding = require_note_finding(report.findings, "ast.notes_invalid")

    assert finding.source_path == ("metadata", "notes"), (
        f"Non-list notes source path drifted: {finding}"
    )
    assert_client_messages_are_path_safe(report)


def test_invalid_structured_root_note_object_reports_nested_paths() -> None:
    """Malformed structured note objects expose path-aware diagnostics."""
    report = validate_payload(
        [
            {
                "content": 123,
                "moduleIds": "not a list",
                "metadata": "not an object",
            }
        ]
    )

    expected_paths = {
        ("metadata", "notes", 0, "content"),
        ("metadata", "notes", 0, "moduleIds"),
        ("metadata", "notes", 0, "metadata"),
    }
    actual_paths = {
        finding.source_path
        for finding in report.findings
        if finding.code
        in {
            "ast.note_content_invalid",
            "ast.note_module_ids_invalid",
            "ast.note_metadata_invalid",
        }
    }

    assert actual_paths == expected_paths, (
        f"Invalid structured note paths drifted: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def validate_payload(notes: object) -> BlueprintValidationReport:
    """Validate one root metadata.notes payload.

    Returns:
        The validation report for the sanitized payload.
    """
    payload: JsonObject = {
        "name": "root-note-contract",
        "flow": [{"id": 1, "module": "http:MakeRequest"}],
        "metadata": {"notes": notes, "schedule": {"id": "schedule:manual"}},
    }
    return validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=load_catalog_fixture(),
    )


def note_codes(
    findings: tuple[BlueprintValidationFinding, ...],
) -> tuple[str, ...]:
    """Return note-specific finding codes."""
    return tuple(
        finding.code
        for finding in findings
        if finding.code.startswith("ast.note")
    )


def require_note_finding(
    findings: tuple[BlueprintValidationFinding, ...],
    code: str,
) -> BlueprintValidationFinding:
    """Return one note finding by code or fail."""
    for finding in findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected note finding code {code!r}; got {findings}"
    assert_unexpected_success(failure_message)
    return None
