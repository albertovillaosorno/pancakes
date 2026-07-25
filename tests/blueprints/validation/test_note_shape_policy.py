# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for Make metadata note shape policy.

Boundary contract:
- Owns: root and module metadata note shape policy tests.
- Must not: test PDF rendering, live Make import, or catalog refresh behavior.
- Allows: sanitized offline fixtures and focused validation finding assertions.
- Split when: note rendering or shorthand note normalization becomes explicit
policy.
- Merge when: another validation test owns these exact note policy cases.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import BlueprintValidationReport, validate_blueprint
from catalog.json_payloads import normalize_json_object

from tests.blueprints.validation.blueprint_validation_contract import (
    assert_client_messages_are_path_safe,
)
from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
VALID_NOTE_OBJECT_FIXTURE = FIXTURE_ROOT / "valid_metadata_note_object.json"
INVALID_NOTE_STRING_FIXTURE = FIXTURE_ROOT / "invalid_metadata_note_string.json"


def test_note_object_with_required_fields_is_valid() -> None:
    """Structured Make-native note objects remain valid for offline handoff."""
    report = validate_fixture(VALID_NOTE_OBJECT_FIXTURE)

    note_codes = _note_codes(report)
    assert not (note_codes), (
        f"Structured note object emitted note findings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_string_note_reports_ast_note_invalid_or_normalizes_by_policy() -> None:
    """String shorthand notes stay rejected under the current strict policy."""
    report = validate_fixture(INVALID_NOTE_STRING_FIXTURE)

    _require_finding(
        report, code="ast.note_invalid", source_path=("metadata", "notes", 0)
    )
    assert_client_messages_are_path_safe(report)


def test_raw_html_note_is_rejected_or_sanitized_before_handoff() -> None:
    """Active HTML/template note content is rejected before handoff surfaces.

    consume it.
    """
    report = validate_payload(
        root_notes=[
            {
                "content": "<script>alert('demo')</script>{{unsafe.template}}",
                "moduleIds": [1],
            }
        ],
        module_notes=[],
    )

    _require_finding(
        report,
        code="importability.metadata_invalid",
        source_path=("metadata", "notes", 0, "content"),
    )
    assert_client_messages_are_path_safe(report)


def test_root_notes_and_module_notes_report_distinct_paths() -> None:
    """Root and module-level note findings identify their separate source.

    paths.
    """
    report = validate_payload(
        root_notes=["Root shorthand note."],
        module_notes=["Module shorthand note."],
    )

    _require_finding(
        report, code="ast.note_invalid", source_path=("metadata", "notes", 0)
    )
    _require_finding(
        report,
        code="ast.note_invalid",
        source_path=("flow", 0, "metadata", "notes", 0),
    )
    assert_client_messages_are_path_safe(report)


def test_note_content_warns_on_static_3e9e17a2() -> None:
    """Root and module notes warn on static personal identifiers without.

    echoing.

    them.
    """
    unsafe_email = "owner@example.invalid"
    unsafe_phone = "+1 (415) 555-0199"
    report = validate_payload(
        root_notes=[
            {
                "content": f"Escalation contact: {unsafe_email}",
                "moduleIds": [1],
            }
        ],
        module_notes=[
            {
                "content": f"Fallback phone: {unsafe_phone}",
            }
        ],
    )

    _require_finding(
        report,
        code="notes.static_personal_literal",
        source_path=("metadata", "notes", 0, "content"),
    )
    _require_finding(
        report,
        code="notes.static_personal_literal",
        source_path=("flow", 0, "metadata", "notes", 0, "content"),
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_email in message or unsafe_phone in message
    )
    assert not (leaked_messages), (
        f"Static personal note text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_note_content_allows_general_or_redacted_personal_references() -> None:
    """General or redacted note content is not treated as static personal.

    data.
    """
    report = validate_payload(
        root_notes=[
            {
                "content": "Escalate through the approved CRM owner record.",
                "moduleIds": [1],
            }
        ],
        module_notes=[
            {
                "content": (
                    "Fallback contact is redacted and kept in the "
                    "support system."
                ),
            }
        ],
    )

    assert "notes.static_personal_literal" not in report.codes(), (
        f"General or redacted note text should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_note_content_warns_on_static_41ebc7db() -> None:
    """Root and module notes warn on static secret-like values without echoing.

    them.
    """
    unsafe_root_value = "Bearer " + ("A" * 20)
    unsafe_module_value = "sk-" + ("B" * 24)
    report = validate_payload(
        root_notes=[
            {
                "content": f"Suppression example used {unsafe_root_value}",
                "moduleIds": [1],
            }
        ],
        module_notes=[
            {
                "content": f"Comment example used {unsafe_module_value}",
            }
        ],
    )

    _require_finding(
        report,
        code="notes.static_secret_literal",
        source_path=("metadata", "notes", 0, "content"),
    )
    _require_finding(
        report,
        code="notes.static_secret_literal",
        source_path=("flow", 0, "metadata", "notes", 0, "content"),
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_root_value in message or unsafe_module_value in message
    )
    assert not (leaked_messages), (
        f"Static secret note text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_note_content_allows_redacted_secret_references() -> None:
    """Redacted secret examples and mappings are not treated as static note.

    secrets.
    """
    report = validate_payload(
        root_notes=[
            {
                "content": (
                    "Suppression example uses redacted credential placeholders."
                ),
                "moduleIds": [1],
            }
        ],
        module_notes=[
            {
                "content": (
                    "Runtime value is {{connection.api_key}}, not a "
                    "static example."
                ),
            }
        ],
    )

    assert "notes.static_secret_literal" not in report.codes(), (
        f"Redacted or mapped note secret text should be allowed: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_note_content_warns_on_insecure_links_without_echoing_url() -> None:
    """Root and module notes warn on non-HTTPS link literals without echoing.

    URLs.
    """
    unsafe_root_url = "http://example.invalid/runbook"
    unsafe_module_url = "file://local/path"
    report = validate_payload(
        root_notes=[
            {
                "content": f"Runbook: {unsafe_root_url}",
                "moduleIds": [1],
            }
        ],
        module_notes=[
            {
                "content": f"Local setup doc: {unsafe_module_url}",
            }
        ],
    )

    _require_finding(
        report,
        code="notes.insecure_link_literal",
        source_path=("metadata", "notes", 0, "content"),
    )
    _require_finding(
        report,
        code="notes.insecure_link_literal",
        source_path=("flow", 0, "metadata", "notes", 0, "content"),
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_root_url in message or unsafe_module_url in message
    )
    assert not (leaked_messages), (
        f"Insecure note link leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_note_content_warns_on_internal_15c6c595() -> None:
    """Root and module notes warn on internal linter mechanics without echoing.

    them.
    """
    unsafe_root_value = "Candidate ID IDM-010 from corpus_count 130."
    unsafe_module_value = (
        "Internal deterministic predicate: route has raw body."
    )
    report = validate_payload(
        root_notes=[
            {
                "content": unsafe_root_value,
                "moduleIds": [1],
            }
        ],
        module_notes=[
            {
                "content": unsafe_module_value,
            }
        ],
    )

    _require_finding(
        report,
        code="notes.internal_linter_marker",
        source_path=("metadata", "notes", 0, "content"),
    )
    _require_finding(
        report,
        code="notes.internal_linter_marker",
        source_path=("flow", 0, "metadata", "notes", 0, "content"),
    )
    leaked_messages = tuple(
        message
        for finding in report.findings
        for message in (finding.client_message, finding.internal_message)
        if unsafe_root_value in message or unsafe_module_value in message
    )
    assert not (leaked_messages), (
        f"Internal linter note text leaked into diagnostics: {leaked_messages}"
    )
    assert_client_messages_are_path_safe(report)


def test_note_content_allows_https_links_and_mapped_urls() -> None:
    """HTTPS and runtime-mapped note links are not treated as insecure.

    literals.
    """
    report = validate_payload(
        root_notes=[
            {
                "content": "Runbook: https://example.invalid/runbook",
                "moduleIds": [1],
            }
        ],
        module_notes=[
            {
                "content": (
                    "Runtime documentation URL is {{1.documentation_url}}."
                ),
            }
        ],
    )

    assert "notes.insecure_link_literal" not in report.codes(), (
        f"HTTPS or mapped note links should be allowed: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def validate_fixture(path: Path) -> BlueprintValidationReport:
    """Validate one sanitized note fixture.

    Returns:
        The validation report for the sanitized fixture.
    """
    return validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(_load_fixture(path), sort_keys=True)
        ),
        catalog=native_module_snapshot(),
    )


def validate_payload(
    *,
    root_notes: object,
    module_notes: object,
) -> BlueprintValidationReport:
    """Validate one inline note policy payload.

    Returns:
        The validation report for the inline payload.
    """
    payload: JsonObject = {
        "name": "note-shape-policy",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "metadata": {"notes": module_notes},
            }
        ],
        "metadata": {
            "notes": root_notes,
            "schedule": {"id": "schedule:manual"},
        },
    }
    return validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )


def _load_fixture(path: Path) -> JsonObject:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def _note_codes(report: BlueprintValidationReport) -> tuple[str, ...]:
    return tuple(
        finding.code
        for finding in report.findings
        if finding.code.startswith("ast.note")
        or (
            finding.code == "importability.metadata_invalid"
            and "note" in finding.internal_message.casefold()
        )
    )


def _require_finding(
    report: BlueprintValidationReport,
    *,
    code: str,
    source_path: tuple[str | int, ...],
) -> None:
    for finding in report.findings:
        if finding.code == code and finding.source_path == source_path:
            return
    failure_message = (
        f"Expected finding {code!r} at {source_path!r}; got {report.findings}"
    )
    assert_unexpected_success(failure_message)
