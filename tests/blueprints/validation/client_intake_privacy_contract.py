# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for customer blueprint intake privacy gates.

Boundary contract:
- Owns: synthetic customer-intake preflight, required manifest, and release-gate
tests.
- Must not: use real client exports, generate reports, call services, or test
catalog rules.
- Allows: minimal Make-shaped JSON fixtures with fake values and forbidden-value
probes.
- Split when: hosted upload or report redaction gains independent
implementation.
- Merge when: another validation test owns the same intake manifest behavior.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from blueprints.validation import (
    CLIENT_BLUEPRINT_REQUIRED_MANIFEST_FIELDS,
    MAX_CLIENT_BLUEPRINT_BYTES,
    ClientBlueprintIntakeManifest,
    ClientBlueprintIntakeRequest,
    client_blueprint_intake_manifest_as_dict,
    client_blueprint_report_release_errors,
    mark_client_blueprint_source_deleted,
    validate_client_blueprint_intake,
)

if TYPE_CHECKING:
    from tests.support.json_payloads import JsonObject


def test_email_first_blueprint_intake_accepts_safe_synthetic_export() -> None:
    """A safe email intake records every privacy boundary before local.

    analysis.
    """
    source_text = _blueprint_json_text()

    manifest = validate_client_blueprint_intake(
        _email_request(
            source_text=source_text,
        )
    )

    _assert_safe_manifest_common(manifest, source_text)

    release_errors = client_blueprint_report_release_errors(manifest)
    assert release_errors == (
        "client_blueprint_source_deletion_not_completed",
    ), f"Unexpected release blockers before deletion evidence: {release_errors}"

    deleted_manifest = mark_client_blueprint_source_deleted(
        manifest,
        deletion_evidence_ref="local-source-delete-confirmed-0001",
    )
    assert not (client_blueprint_report_release_errors(deleted_manifest)), (
        f"Deleted safe intake should allow report release: {deleted_manifest}"
    )


def _assert_safe_manifest_common(
    manifest: ClientBlueprintIntakeManifest,
    source_text: str,
) -> None:
    """Assert invariant fields shared by a safe accepted intake."""
    assert manifest.decision == "accepted_for_local_analysis", (
        f"Safe synthetic blueprint was not accepted: {manifest}"
    )
    assert (
        manifest.source_sha256
        == hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    ), f"Manifest source hash is not deterministic: {manifest.source_sha256}"
    assert manifest.max_size_bytes == MAX_CLIENT_BLUEPRINT_BYTES, (
        f"Manifest lost the approved size boundary: {manifest.max_size_bytes}"
    )
    assert (
        manifest.local_analysis_boundary == "operator_workstation_local_only"
    ), f"Local backend boundary was weakened: {manifest}"
    assert manifest.public_backend_exposure == "forbidden", (
        f"Public backend exposure must be forbidden: {manifest}"
    )
    assert not (manifest.external_model_processing_allowed), (
        "Client blueprint intake must not allow external model processing."
    )
    assert not (manifest.is_truncated), (
        f"Complete intake must state non-truncation explicitly: {manifest}"
    )
    assert manifest.truncation_reason == "not_truncated", (
        f"Complete intake must state non-truncation explicitly: {manifest}"
    )
    assert manifest.deletion_status == "not_started", (
        f"Raw source deletion must still gate report release: {manifest}"
    )
    assert not (manifest.findings), (
        f"Safe synthetic blueprint produced findings: {manifest.findings}"
    )


def _email_request(source_text: str) -> ClientBlueprintIntakeRequest:
    """Return a complete email-first intake request."""
    return ClientBlueprintIntakeRequest(
        file_name="lead-routing.blueprint.json",
        source_text=source_text,
        intake_method="email_attachment",
        received_surface="approved audit mailbox attachment storage",
        customer_authorization_ref="signed-audit-order-0001",
        processor_boundary=(
            "mail provider attachment storage plus operator workstation"
        ),
    )


def test_intake_manifest_fields_are_required_and_json_ready() -> None:
    """The manifest contract has no optional field defaults and serializes all.

    fields.
    """
    assert not (ClientBlueprintIntakeManifest._field_defaults), (
        f"Manifest fields must not have defaults: "
        f"{ClientBlueprintIntakeManifest}"
    )

    manifest = validate_client_blueprint_intake(
        ClientBlueprintIntakeRequest(
            file_name="lead-routing.blueprint.json",
            source_text=_blueprint_json_text(),
            intake_method="offline_handoff",
            received_surface="encrypted offline archive delivered by client",
            customer_authorization_ref="offline-authorization-0001",
            processor_boundary=(
                "offline archive storage plus operator workstation"
            ),
        )
    )
    payload = client_blueprint_intake_manifest_as_dict(manifest)
    missing_fields = set(CLIENT_BLUEPRINT_REQUIRED_MANIFEST_FIELDS).difference(
        payload
    )
    assert not (missing_fields), (
        f"JSON manifest payload missed required fields: {missing_fields}"
    )
    assert not (payload["is_truncated"] is not False), (
        f"JSON payload lost truncation disclosure: {payload}"
    )
    assert payload["truncation_reason"] == "not_truncated", (
        f"JSON payload lost truncation disclosure: {payload}"
    )
    _ = json.dumps(payload, sort_keys=True)


def test_intake_rejects_non_blueprint_or_live_artifact_shapes() -> None:
    """Logs, archives, and non-blueprint names fail before report generation."""
    source_text = json.dumps(
        {
            "name": "run-history",
            "flow": [],
            "logs": [{"bundle": {"payload": "runtime value"}}],
        },
        sort_keys=True,
    )

    manifest = validate_client_blueprint_intake(
        ClientBlueprintIntakeRequest(
            file_name="run-history.json",
            source_text=source_text,
            intake_method="email_attachment",
            received_surface="approved audit mailbox attachment storage",
            customer_authorization_ref="signed-audit-order-0001",
            processor_boundary=(
                "mail provider attachment storage plus operator workstation"
            ),
        )
    )

    codes = {finding.code for finding in manifest.findings}
    expected_codes = {
        "intake.file_name.not_blueprint_json",
        "intake.shape.live_artifact_key",
    }
    assert expected_codes.issubset(codes), (
        f"Non-blueprint live artifact was not rejected precisely: {codes}"
    )
    assert manifest.decision == "rejected", (
        f"Live artifact shape must be rejected: {manifest}"
    )
    assert manifest.shape_status == "blocked", (
        f"Live artifact shape must be rejected: {manifest}"
    )


def test_intake_rejects_hardcoded_secret_values() -> None:
    """Hardcoded Authorization or token values block customer source intake."""
    source_text = _blueprint_json_text(
        parameters={
            "url": "https://example.invalid?access_token=unsafe",
            "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz"},
        }
    )

    manifest = validate_client_blueprint_intake(
        ClientBlueprintIntakeRequest(
            file_name="unsafe-http.blueprint.json",
            source_text=source_text,
            intake_method="email_attachment",
            received_surface="approved audit mailbox attachment storage",
            customer_authorization_ref="signed-audit-order-0001",
            processor_boundary=(
                "mail provider attachment storage plus operator workstation"
            ),
        )
    )

    secret_codes = {
        finding.code
        for finding in manifest.findings
        if finding.finding_class == "secret"
    }
    assert not ("intake.secret.key_detected" not in secret_codes), (
        f"Secret-like key was not blocked: {manifest.findings}"
    )
    assert not ("secret.authorization_header" not in secret_codes), (
        f"Authorization value was not blocked: {manifest.findings}"
    )
    assert not ("secret.url_query" not in secret_codes), (
        f"URL token was not blocked: {manifest.findings}"
    )
    assert manifest.decision == "rejected", (
        f"Secret-bearing source must be rejected: {manifest}"
    )
    assert manifest.redaction_status == "blocked", (
        f"Secret-bearing source must be rejected: {manifest}"
    )
    assert not (
        "client_blueprint_secret_gate_blocked"
        not in client_blueprint_report_release_errors(manifest)
    ), "Secret-bearing intake must block report release."


def test_intake_requires_manual_review_for_personal_identifiers() -> None:
    """Identifier-like values do not silently enter reports."""
    source_text = _blueprint_json_text(
        parameters={"label": "Route contact alpha@example.invalid"}
    )

    manifest = validate_client_blueprint_intake(
        ClientBlueprintIntakeRequest(
            file_name="identifier-review.blueprint.json",
            source_text=source_text,
            intake_method="offline_handoff",
            received_surface="encrypted offline archive delivered by client",
            customer_authorization_ref="offline-authorization-0001",
            processor_boundary=(
                "offline archive storage plus operator workstation"
            ),
        )
    )

    assert manifest.decision == "manual_review_required", (
        f"Personal identifiers should require review: {manifest}"
    )
    assert manifest.personal_data_status == "manual_review_required", (
        f"Identifier gate did not report manual review: {manifest}"
    )
    assert manifest.redaction_status == "required", (
        f"Identifier gate did not require redaction: {manifest}"
    )
    release_errors = client_blueprint_report_release_errors(manifest)
    expected_errors = {
        "client_blueprint_intake_not_accepted",
        "client_blueprint_personal_data_requires_review",
        "client_blueprint_redaction_not_resolved",
        "client_blueprint_source_deletion_not_completed",
    }
    assert expected_errors.issubset(release_errors), (
        f"Identifier-bearing intake did not block release correctly: "
        f"{release_errors}"
    )


def test_intake_requires_authorization_processor_and_handoff_evidence() -> None:
    """Missing legal or processor metadata fails closed."""
    manifest = validate_client_blueprint_intake(
        ClientBlueprintIntakeRequest(
            file_name="lead-routing.blueprint.json",
            source_text=_blueprint_json_text(),
            intake_method="email_attachment",
            received_surface="",
            customer_authorization_ref="",
            processor_boundary="",
        )
    )

    assert manifest.evidence_coverage_status == "incomplete", (
        f"Missing authorization evidence must be explicit: {manifest}"
    )
    codes = {finding.code for finding in manifest.findings}
    expected_codes = {
        "intake.authorization.missing",
        "intake.received_surface.missing",
        "intake.processor_boundary.missing",
    }
    assert expected_codes.issubset(codes), (
        f"Missing metadata findings are incomplete: {codes}"
    )
    release_errors = client_blueprint_report_release_errors(manifest)
    assert not (
        "client_blueprint_evidence_coverage_incomplete" not in release_errors
    ), "Incomplete legal evidence must block report release."


def _blueprint_json_text(parameters: JsonObject | None = None) -> str:
    """Return a minimal synthetic Make-shaped blueprint JSON string."""
    return json.dumps(
        {
            "name": "synthetic lead routing review",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "parameters": parameters
                    or {"method": "GET", "url": "https://example.invalid"},
                }
            ],
            "metadata": {"schedule": {"id": "schedule:manual"}},
        },
        sort_keys=True,
    )
