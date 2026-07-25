# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for Make linter API probe boundaries.

Boundary contract:
- Owns: fake-transport linter probe checks and designer-message normalization.
- Must not: contact Make.com, require credentials, or use browser automation.
- Allows: documented Make API response fixtures and probe report assertions.
- Split when: real HTTP adapters or persistence gain separate ownership.
- Merge when: knowledge_live_probe_contract owns the same linter behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from catalog.knowledge import (
    MAKE_AST_ERROR_PREFIX,
    MAKE_DESIGNER_MESSAGE_RAW_DIR,
    MAKE_DESIGNER_WARNING_PREFIX,
    MAKE_LINTER_REPORT_PATH,
    MakeDesignerMessageBatchRequest,
    MakeLinterFinding,
    MakeLinterProbeAuthorization,
    build_linter_probe_status,
    collect_designer_message_batch,
    designer_message_findings_to_sql,
    normalize_linter_findings,
    probe_linter_findings,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from languages.make.raw_specs.models import JsonObject

REPO_ROOT = repo_root()
FIXED_CAPTURED_AT = "2026-04-30T00:00:00+00:00"
SHA256_HEX_LENGTH = 64
MALFORMED_SCENARIO_SKIP_COUNT = 2
COLLISION_RECORD_COUNT = 2
MAX_RAW_DESIGNER_MESSAGE_FILENAME_LENGTH = 120
BLANK_OPTIONAL_SQL_NULL_COUNT = 5
MULTI_FINDING_SQL_INSERT_COUNT = 2


class FakeBlueprintTransport:
    """Fake Make blueprint transport for linter probe tests."""

    def __init__(self, payload: JsonObject) -> None:
        """Store the fake API response payload."""
        self.payload = payload
        self.called = False

    def get_scenario_blueprint(
        self, scenario_id: str, *, draft: bool
    ) -> JsonObject:
        """Return a documented blueprint payload without network access."""
        assert scenario_id == "112", (
            f"Unexpected probe request: {scenario_id}, draft={draft}"
        )
        assert not (draft is not True), (
            f"Unexpected probe request: {scenario_id}, draft={draft}"
        )
        self.called = True
        return self.payload


class SecretFailingBlueprintTransport:
    """Fake transport that raises a secret-bearing error message."""

    def __init__(self) -> None:
        """Track whether the fake transport was called."""
        self.called = False

    def get_scenario_blueprint(
        self, scenario_id: str, *, draft: bool
    ) -> JsonObject:
        """Raise an error that must not be copied into reports.

        Raises:
            ValueError: Always, with a secret-like message fixture.
        """
        del scenario_id, draft
        self.called = True
        msg = "upstream failed with token raw-token-secret-value"
        raise ValueError(msg)


class FlexibleBlueprintTransport:
    """Fake transport that accepts any scenario id."""

    def __init__(self, payload: JsonObject) -> None:
        """Store the fake API response payload and seen IDs."""
        self.payload = payload
        self.scenario_ids: list[str] = []

    def get_scenario_blueprint(
        self, scenario_id: str, *, draft: bool
    ) -> JsonObject:
        """Return a documented blueprint payload without constraining scenario.

        IDs.
        """
        assert not (draft is not True), f"Unexpected draft flag: {draft}"
        self.scenario_ids.append(scenario_id)
        return self.payload


def test_documented_blueprint_designer_messages_normalize_to_findings() -> None:
    """Documented blueprint designer messages become structured findings."""
    findings = normalize_linter_findings(
        payload=documented_blueprint_response(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert len(findings) == 1, (
        f"Expected one normalized linter finding: {findings}"
    )
    finding = findings[0].to_json()
    expected_subset = {
        "node_id": "2 ",
        "module_slug": "json:ParseJSON ",
        "severity": "warning ",
        "source_system": "make_designer",
        "source_prefix": MAKE_DESIGNER_WARNING_PREFIX,
        "message": "A transformer should not be the last module in the route.",
        "category": "last",
        "field_path": None,
        "source_ref": "make-api:/api/v2/scenarios/112/blueprint?draft=true",
        "captured_at_utc": FIXED_CAPTURED_AT,
        "adr_anchor": (
            "001066#repo.make-linter.documented-designer-message-signal"
        ),
    }
    mismatches = {
        key: finding.get(key)
        for key, expected_value in expected_subset.items()
        if finding.get(key) != expected_value
    }
    assert not (mismatches), (
        f"Designer message normalization drifted: {finding}"
    )
    assert str(finding.get("finding_id")).startswith("designer-message:"), (
        f"Designer message finding id is not stable: {finding}"
    )
    assert len(str(finding.get("fingerprint"))) == SHA256_HEX_LENGTH, (
        f"Designer message fingerprint is not a SHA-256 hex digest: {finding}"
    )


def test_designer_messages_normalize_as_warnings_705966e4() -> None:
    """Designer probe messages remain warnings in local diagnostic streams."""
    source = documented_blueprint_response()
    first_designer_message(source)["severity"] = "error"

    findings = normalize_linter_findings(
        payload=source,
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert findings[0].severity == "warning", (
        f"Designer probe severities must stay warnings: {findings[0]}"
    )


def test_designer_text_messages_normalize_to_findings() -> None:
    """Designer probe text fields are equivalent to message fields."""
    source = documented_blueprint_response()
    message = first_designer_message(source)
    message["text"] = message.pop("message")

    findings = normalize_linter_findings(
        payload=source,
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert len(findings) == 1, (
        f"Designer text message was not normalized: {findings}"
    )
    assert (
        findings[0].message
        == "A transformer should not be the last module in the route."
    ), f"Designer text message changed during normalization: {findings[0]}"


def test_designer_message_path_alias_normalizes_field_path() -> None:
    """Designer probe path aliases remain field-scoped evidence."""
    source = documented_blueprint_response()
    message = first_designer_message(source)
    message["path"] = "mapper.email"

    findings = normalize_linter_findings(
        payload=source,
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert findings[0].field_path == "mapper.email", (
        f"Designer path alias was not preserved as field evidence: "
        f"{findings[0]}"
    )


def test_root_designer_messages_normalize_to_findings() -> None:
    """Designer-message normalization includes blueprint-level warnings."""
    source = documented_blueprint_response()
    response = cast("JsonObject", source["response"])
    blueprint = cast("JsonObject", response["blueprint"])
    blueprint["flow"] = []
    blueprint["metadata"] = {
        "designer": {
            "messages": [
                {
                    "category": "scenario ",
                    "severity": "warning ",
                    "message": "Scenario-level designer warning.",
                }
            ]
        }
    }

    findings = normalize_linter_findings(
        payload=source,
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert len(findings) == 1, (
        f"Expected one root designer-message finding: {findings}"
    )
    finding = findings[0]
    assert not (finding.node_id is not None), (
        f"Root designer findings must not invent node identity: {finding}"
    )
    assert not (finding.module_slug is not None), (
        f"Root designer findings must not invent node identity: {finding}"
    )
    assert finding.category == "scenario", (
        f"Root designer message drifted: {finding}"
    )
    assert finding.message == "Scenario-level designer warning.", (
        f"Root designer message drifted: {finding}"
    )


def test_designer_message_fingerprint_is_stable_across_captures() -> None:
    """Repeated captures of the same designer warning keep one fact identity."""
    first = normalize_linter_findings(
        payload=documented_blueprint_response(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )
    second = normalize_linter_findings(
        payload=documented_blueprint_response(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc="2026-05-01T00:00:00Z",
    )

    assert len(first) == 1, (
        f"Expected one finding per capture: {first}, {second}"
    )
    assert len(second) == 1, (
        f"Expected one finding per capture: {first}, {second}"
    )
    assert first[0].finding_id == second[0].finding_id, (
        "Designer-message finding IDs must be stable across repeated captures."
    )
    assert first[0].fingerprint == second[0].fingerprint, (
        "Designer-message fingerprints must exclude capture timestamps."
    )
    assert first[0].captured_at_utc != second[0].captured_at_utc, (
        "Capture timestamps must remain metadata outside the fact fingerprint."
    )


def test_designer_message_normalization_requires_capture_timestamp_string() -> (
    None
):
    """Designer warning captures require explicit string timestamp metadata."""
    with pytest.raises(ValueError, match="captured_at_utc"):
        _ = normalize_linter_findings(
            payload=documented_blueprint_response(),
            source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
            captured_at_utc=cast("str", {"at": FIXED_CAPTURED_AT}),
        )


def test_designer_message_normalization_requires_source_ref_string() -> None:
    """Designer warning captures require explicit string source references."""
    with pytest.raises(ValueError, match="source_ref"):
        _ = normalize_linter_findings(
            payload=documented_blueprint_response(),
            source_ref=cast("str", {"source": "make-api"}),
            captured_at_utc=FIXED_CAPTURED_AT,
        )


def test_designer_message_normalization_does_not_coerce_malformed_shapes() -> (
    None
):
    """Malformed designer evidence fields do not become stringified facts."""
    source = documented_blueprint_response()
    response = cast("JsonObject", source["response"])
    blueprint = cast("JsonObject", response["blueprint"])
    flow = cast("list[object]", blueprint["flow"])
    node = cast("JsonObject", flow[0])
    node["id"] = True
    node["module"] = ["json:ParseJSON"]
    metadata = cast("JsonObject", node["metadata"])
    designer = cast("JsonObject", metadata["designer"])
    designer["messages"] = [
        {
            "category": "ignored",
            "message": {"text": "Do not stringify me."},
        },
        {
            "category": ["last"],
            "field": {"path": "mapper.url"},
            "message": "Keep the real warning.",
        },
    ]

    findings = normalize_linter_findings(
        payload=source,
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert len(findings) == 1, (
        f"Only string designer messages should normalize to findings: "
        f"{findings}"
    )
    finding = findings[0]
    assert finding.message == "Keep the real warning.", (
        f"String designer warning was not preserved: {finding}"
    )
    assert not (finding.node_id is not None), (
        f"Malformed node identity fields must not be string-coerced: {finding}"
    )
    assert not (finding.module_slug is not None), (
        f"Malformed node identity fields must not be string-coerced: {finding}"
    )
    assert not (finding.category is not None), (
        f"Malformed descriptor fields must not be string-coerced: {finding}"
    )
    assert not (finding.field_path is not None), (
        f"Malformed descriptor fields must not be string-coerced: {finding}"
    )


def test_nested_tool_designer_messages_normalize_to_findings() -> None:
    """Designer-message normalization follows tool flows inside nodes."""
    findings = normalize_linter_findings(
        payload=blueprint_response_with_tool_message(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert tuple(finding.node_id for finding in findings) == ("7",), (
        f"Nested tool designer message was not normalized: {findings}"
    )
    finding = findings[0].to_json()
    assert finding.get("module_slug") == "gateway:WebhookRespond", (
        f"Nested tool module slug drifted: {finding}"
    )
    assert (
        finding.get("message") == "Tool output is not returned to the caller."
    ), f"Nested tool designer message drifted: {finding}"


def test_error_handler_designer_messages_normalize_to_findings() -> None:
    """Designer-message normalization follows error-handler modules."""
    findings = normalize_linter_findings(
        payload=blueprint_response_with_error_handler_message(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert tuple(finding.node_id for finding in findings) == ("9",), (
        f"Error-handler designer message was not normalized: {findings}"
    )
    finding = findings[0].to_json()
    assert finding.get("module_slug") == "builtin:Break", (
        f"Error-handler module slug drifted: {finding}"
    )
    assert finding.get("message") == "Error handler route needs completion.", (
        f"Error-handler designer message drifted: {finding}"
    )


def test_linter_probe_requires_authorization_before_transport_call() -> None:
    """Unapproved probes fail before any HTTP-like transport is called."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(PermissionError, match="operator_approved=true"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=False,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="discover_linter_api",
            ),
            scenario_id="112",
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
        )

    assert not (transport.called), (
        "Unauthorized linter probes must not call the transport."
    )


def test_linter_probe_rejects_secret_like_credential_references() -> None:
    """Authorization stores credential references, not raw token material."""
    for credential_ref in (
        "raw-token-material ",
        "Bearer raw-token-material ",
        "Authorization: Bearer raw-token-material",
    ):
        with pytest.raises(PermissionError, match="non-secret reference"):
            _ = probe_linter_findings(
                transport=FakeBlueprintTransport(
                    documented_blueprint_response()
                ),
                authorization=MakeLinterProbeAuthorization(
                    operator_approved=True,
                    approved_by="test-operator",
                    credential_ref=credential_ref,
                    purpose="discover_linter_api",
                ),
                scenario_id="112",
                draft=True,
                captured_at_utc=FIXED_CAPTURED_AT,
            )


def test_linter_probe_requires_credential_reference() -> None:
    """Authorization must name a credential reference, not just approval.

    text.
    """
    with pytest.raises(PermissionError, match="requires credential_ref"):
        _ = probe_linter_findings(
            transport=FakeBlueprintTransport(documented_blueprint_response()),
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref=" ",
                purpose="discover_linter_api",
            ),
            scenario_id="112",
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
        )


def test_linter_probe_rejects_malformed_authorization_strings() -> None:
    """Authorization string fields must not be coerced from arbitrary JSON.

    shapes.
    """
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(PermissionError, match="requires approved_by"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by=cast("str", {"operator": "test"}),
                credential_ref="make-api-token:test",
                purpose="discover_linter_api",
            ),
            scenario_id="112",
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
        )

    with pytest.raises(PermissionError, match="requires credential_ref"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref=cast("str", ["make-api-token:test"]),
                purpose="discover_linter_api",
            ),
            scenario_id="112",
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
        )

    assert not (transport.called), (
        "Malformed linter authorization must fail before transport calls."
    )


def test_linter_probe_rejects_malformed_authorization_control_fields() -> None:
    """Authorization control fields must be exact JSON shapes."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(PermissionError, match="operator_approved=true"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=cast("bool", "true"),
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="discover_linter_api",
            ),
            scenario_id="112",
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
        )

    with pytest.raises(PermissionError, match="purpose must be"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose=cast("str", ["collect_designer_messages"]),
            ),
            scenario_id="112",
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
        )

    assert not (transport.called), (
        "Malformed linter control fields must fail before transport calls."
    )


def test_authorized_linter_probe_uses_fake_transport_only() -> None:
    """Authorized probes can normalize fake transport payloads without live.

    Make.

    access.
    """
    transport = FakeBlueprintTransport(documented_blueprint_response())
    findings = probe_linter_findings(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=True,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="discover_linter_api",
        ),
        scenario_id="112",
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert transport.called, (
        "Authorized linter probe did not call the injected fake transport."
    )
    assert len(findings) == 1, (
        f"Authorized linter probe did not normalize findings: {findings}"
    )


def test_linter_probe_rejects_malformed_scenario_id_before_transport() -> None:
    """Single-scenario probes do not coerce malformed scenario identifiers."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(ValueError, match="scenario_id"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="discover_linter_api",
            ),
            scenario_id=cast("str", ["112"]),
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
        )

    assert not (transport.called), (
        "Malformed scenario IDs must fail before transport calls."
    )


def test_linter_probe_rejects_malformed_draft_flag_before_transport() -> None:
    """Single-scenario probes do not coerce draft selection."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(TypeError, match="boolean draft"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="discover_linter_api",
            ),
            scenario_id="112",
            draft=cast("bool", "false"),
            captured_at_utc=FIXED_CAPTURED_AT,
        )

    assert not (transport.called), (
        "Malformed draft flags must fail before transport calls."
    )


def test_linter_probe_rejects_malformed_capture_62f510be() -> None:
    """Single-scenario probes validate capture metadata before transport.

    calls.
    """
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(ValueError, match="captured_at_utc"):
        _ = probe_linter_findings(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="discover_linter_api",
            ),
            scenario_id="112",
            draft=True,
            captured_at_utc=cast("str", ["2026-04-30T00:00:00Z"]),
        )

    assert not (transport.called), (
        "Malformed capture timestamps must fail before single transport calls."
    )


def test_designer_message_batch_writes_ignored_raw_manifest(
    tmp_path: Path,
) -> None:
    """Authorized read-only batches preserve raw designer messages as ingest.

    data.
    """
    transport = FakeBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        MakeDesignerMessageBatchRequest(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="collect_designer_messages",
            ),
            scenario_ids=("112",),
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
            repo_root=tmp_path,
        )
    )

    assert report.status == "ok", (
        f"Designer-message batch did not collect normalized findings: {report}"
    )
    assert report.finding_count == 1, (
        f"Designer-message batch did not collect normalized findings: {report}"
    )
    assert report.raw_dir == MAKE_DESIGNER_MESSAGE_RAW_DIR.as_posix(), (
        f"Designer-message batch used the wrong raw dir: {report}"
    )
    manifest_path = tmp_path / report.manifest_path
    assert manifest_path.is_file(), (
        f"Designer-message manifest was not written: {report}"
    )
    record = report.records[0]
    raw_payload = cast(
        "JsonObject", json.loads((tmp_path / record.relative_path).read_text())
    )
    normalized = cast(
        "list[JsonObject]", raw_payload.get("normalized_findings")
    )
    assert normalized[0].get("source_prefix") == MAKE_DESIGNER_WARNING_PREFIX, (
        f"Raw ingest payload lost designer warning prefix: {raw_payload}"
    )
    assert not (
        "src/languages/make/data/designer-messages/raw/"
        not in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    ), "Raw designer-message ingest files must stay ignored by Git."


def test_designer_message_batch_skips_unauthorized_transport_calls(
    tmp_path: Path,
) -> None:
    """Unauthorized batches report skipped live work without touching.

    transport.
    """
    transport = FakeBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=False,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=("112",),
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
        repo_root=tmp_path,
    )

    assert report.status == "unauthorized", (
        f"Unauthorized batch did not report authorization status: {report}"
    )
    assert report.unauthorized_count == 1, (
        f"Unauthorized batch did not report authorization status: {report}"
    )
    assert not (transport.called), (
        "Unauthorized designer-message batches must not call the transport."
    )


def test_designer_message_batch_checks_authorization_before_payload_shapes(
    tmp_path: Path,
) -> None:
    """Unauthorized batches return authorization status before validating.

    payload.

    metadata.
    """
    transport = FakeBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=False,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=("112",),
        draft=cast("bool", "false"),
        captured_at_utc=cast("str", ["2026-04-30T00:00:00Z"]),
        repo_root=tmp_path,
    )

    assert report.status == "unauthorized", (
        f"Unauthorized batch should not validate payload metadata first: "
        f"{report}"
    )
    assert report.unauthorized_count == 1, (
        f"Unauthorized batch should not validate payload metadata first: "
        f"{report}"
    )
    assert not (transport.called), (
        "Unauthorized malformed batches must not call the transport."
    )


def test_designer_message_batch_checks_authorization_before_raw_path_resolution(
    tmp_path: Path,
) -> None:
    """Unauthorized batches do not resolve or create raw ingest paths first."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=False,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=("112",),
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
        repo_root=tmp_path,
        raw_dir=Path("..") / "outside",
    )

    assert report.status == "unauthorized", (
        f"Unauthorized batch should report authorization first: {report}"
    )
    assert report.unauthorized_count == 1, (
        f"Unauthorized batch should report authorization first: {report}"
    )
    assert not (transport.called), (
        "Unauthorized batches with invalid paths must not call the transport."
    )
    assert not ((tmp_path / MAKE_DESIGNER_MESSAGE_RAW_DIR).exists()), (
        "Unauthorized batches must not create raw ingest directories."
    )


def test_designer_message_batch_skips_malformed_scenario_ids(
    tmp_path: Path,
) -> None:
    """Batch collection skips malformed scenario IDs without transport calls.

    for.

    them.
    """
    transport = FakeBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=True,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=("", cast("str", ["112"]), "112"),
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
        repo_root=tmp_path,
    )

    assert report.status == "ok", (
        f"Malformed scenario IDs were not skipped correctly: {report}"
    )
    assert report.collected_count == 1, (
        f"Malformed scenario IDs were not skipped correctly: {report}"
    )
    assert report.skipped_count == MALFORMED_SCENARIO_SKIP_COUNT, (
        f"Malformed scenario IDs were not skipped correctly: {report}"
    )
    assert transport.called, (
        "Valid scenario ID was not collected after malformed entries."
    )


def test_designer_message_batch_reports_all_malformed_scenario_ids_as_skipped(
    tmp_path: Path,
) -> None:
    """Batches with no valid scenario IDs do not create raw ingest artifacts."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=True,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=("", cast("str", ["112"])),
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
        repo_root=tmp_path,
    )

    assert report.status == "skipped", (
        f"All-malformed scenario IDs should be reported as skipped: {report}"
    )
    assert report.skipped_count == MALFORMED_SCENARIO_SKIP_COUNT, (
        f"All-malformed scenario IDs should be reported as skipped: {report}"
    )
    assert report.collected_count == 0, (
        f"Skipped designer-message batches must not report findings: {report}"
    )
    assert report.finding_count == 0, (
        f"Skipped designer-message batches must not report findings: {report}"
    )
    assert not (transport.called), (
        "All-malformed scenario batches must not call the transport."
    )
    assert not ((tmp_path / MAKE_DESIGNER_MESSAGE_RAW_DIR).exists()), (
        "All-malformed scenario batches must not create raw ingest directories."
    )


def test_designer_message_batch_uses_collision_resistant_raw_paths(
    tmp_path: Path,
) -> None:
    """Distinct scenario IDs that sanitize alike must not overwrite raw.

    records.
    """
    transport = FlexibleBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=True,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=("a/b", "ab"),
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
        repo_root=tmp_path,
    )

    record_paths = tuple(record.relative_path for record in report.records)
    assert report.status == "ok", (
        f"Collision fixture should collect two records: {report}"
    )
    assert report.collected_count == COLLISION_RECORD_COUNT, (
        f"Collision fixture should collect two records: {report}"
    )
    assert len(set(record_paths)) == COLLISION_RECORD_COUNT, (
        f"Raw designer-message records must not collide: {record_paths}"
    )
    for relative_path in record_paths:
        assert (tmp_path / relative_path).is_file(), (
            f"Raw designer-message record was not written: {relative_path}"
        )
    first_payload = cast(
        "JsonObject", json.loads((tmp_path / record_paths[0]).read_text())
    )
    assert (
        first_payload.get("source_ref")
        == "make-api:/api/v2/scenarios/a%2Fb/blueprint?draft=true"
    ), f"Scenario IDs must be encoded inside source refs: {first_payload}"
    assert transport.scenario_ids == ["a/b", "ab"], (
        f"Transport did not receive both scenario IDs: {transport.scenario_ids}"
    )


def test_designer_message_batch_bounds_raw_filename_tokens(
    tmp_path: Path,
) -> None:
    """Long scenario IDs keep bounded raw ingest filenames."""
    long_scenario_id = "scenario-" + ("x" * 260)
    transport = FlexibleBlueprintTransport(documented_blueprint_response())

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=True,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=(long_scenario_id,),
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
        repo_root=tmp_path,
    )

    raw_filename = (tmp_path / report.records[0].relative_path).name
    assert not (len(raw_filename) > MAX_RAW_DESIGNER_MESSAGE_FILENAME_LENGTH), (
        f"Raw designer-message filename should stay bounded: {raw_filename}"
    )
    assert raw_filename.endswith("-draft.json"), (
        f"Raw designer-message filename lost draft suffix: {raw_filename}"
    )
    assert transport.scenario_ids == [long_scenario_id], (
        f"Transport did not receive the original scenario ID: "
        f"{transport.scenario_ids}"
    )


def test_designer_message_batch_rejects_empty_scenario_id_batch(
    tmp_path: Path,
) -> None:
    """Authorized batches require at least one explicit scenario ID."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(ValueError, match="at least one scenario_id"):
        _ = collect_designer_message_batch(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="collect_designer_messages",
            ),
            scenario_ids=(),
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
            repo_root=tmp_path,
        )

    assert not (transport.called), (
        "Empty designer-message batches must fail before transport calls."
    )
    assert not ((tmp_path / MAKE_DESIGNER_MESSAGE_RAW_DIR).exists()), (
        "Empty designer-message batches must not create raw ingest directories."
    )


def test_designer_message_batch_rejects_non_tuple_scenario_id_batch(
    tmp_path: Path,
) -> None:
    """Authorized batches do not iterate malformed scenario-id containers."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(TypeError, match="tuple scenario_ids"):
        _ = collect_designer_message_batch(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="collect_designer_messages",
            ),
            scenario_ids=cast("tuple[str, ...]", "112"),
            draft=True,
            captured_at_utc=FIXED_CAPTURED_AT,
            repo_root=tmp_path,
        )

    assert not (transport.called), (
        "Malformed designer-message batch containers must fail before "
        "transport "
        "calls."
    )
    assert not ((tmp_path / MAKE_DESIGNER_MESSAGE_RAW_DIR).exists()), (
        "Malformed designer-message batches must not create raw ingest "
        "directories."
    )


def test_designer_message_batch_rejects_malformed_draft_flag(
    tmp_path: Path,
) -> None:
    """Batch collection requires an exact boolean draft selector."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(TypeError, match="boolean draft"):
        _ = collect_designer_message_batch(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="collect_designer_messages",
            ),
            scenario_ids=("112",),
            draft=cast("bool", "false"),
            captured_at_utc=FIXED_CAPTURED_AT,
            repo_root=tmp_path,
        )

    assert not (transport.called), (
        "Malformed batch draft flags must fail before transport calls."
    )


def test_designer_message_batch_rejects_malformed_capture_timestamp(
    tmp_path: Path,
) -> None:
    """Batch collection requires exact string capture metadata."""
    transport = FakeBlueprintTransport(documented_blueprint_response())

    with pytest.raises(ValueError, match="captured_at_utc"):
        _ = collect_designer_message_batch(
            transport=transport,
            authorization=MakeLinterProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-api-token:test",
                purpose="collect_designer_messages",
            ),
            scenario_ids=("112",),
            draft=True,
            captured_at_utc=cast("str", ["2026-04-30T00:00:00Z"]),
            repo_root=tmp_path,
        )

    assert not (transport.called), (
        "Malformed capture timestamps must fail before transport calls."
    )


def test_designer_message_batch_redacts_transport_failure_messages(
    tmp_path: Path,
) -> None:
    """Batch reports preserve failure type without leaking raw transport.

    details.
    """
    transport = SecretFailingBlueprintTransport()

    report = collect_designer_message_batch(
        transport=transport,
        authorization=MakeLinterProbeAuthorization(
            operator_approved=True,
            approved_by="test-operator",
            credential_ref="make-api-token:test",
            purpose="collect_designer_messages",
        ),
        scenario_ids=("112",),
        draft=True,
        captured_at_utc=FIXED_CAPTURED_AT,
        repo_root=tmp_path,
    )

    assert report.status == "failed", (
        f"Transport failure did not produce a failed report: {report}"
    )
    assert report.failed_count == 1, (
        f"Transport failure did not produce a failed report: {report}"
    )
    assert report.failures == ("112: ValueError",), (
        f"Transport failure details must stay bounded: {report.failures}"
    )
    assert "raw-token-secret-value" not in json.dumps(
        report.to_json(), sort_keys=True
    ), f"Transport failure leaked secret-like text: {report}"
    assert transport.called, (
        "Authorized failing batch did not call the injected transport."
    )


def test_designer_message_findings_export_reviewable_sql() -> None:
    """Normalized designer findings can be promoted through reviewed SQL.

    snapshots.
    """
    findings = normalize_linter_findings(
        payload=documented_blueprint_response(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    sql = designer_message_findings_to_sql(
        findings=findings,
        review_status="reviewed",
        valid_from=FIXED_CAPTURED_AT,
    )

    assert not (
        "INSERT OR REPLACE INTO designer_message_evidence" not in sql
    ), f"Designer-message SQL promotion target drifted: {sql}"
    assert not ("'reviewed'" not in sql), (
        f"Designer-message SQL must preserve review and source kind: {sql}"
    )
    assert not ("'designer_message'" not in sql), (
        f"Designer-message SQL must preserve review and source kind: {sql}"
    )


def test_designer_message_sql_export_requires_reviewed_temporal_metadata() -> (
    None
):
    """Designer-message SQL export only writes reviewed temporal evidence.

    rows.
    """
    findings = normalize_linter_findings(
        payload=documented_blueprint_response(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    with pytest.raises(ValueError, match="review_status='reviewed'"):
        _ = designer_message_findings_to_sql(
            findings=findings,
            review_status="needs_review",
            valid_from=FIXED_CAPTURED_AT,
        )

    with pytest.raises(ValueError, match="valid_from"):
        _ = designer_message_findings_to_sql(
            findings=findings,
            review_status="reviewed",
            valid_from=cast("str", {"at": FIXED_CAPTURED_AT}),
        )


def test_designer_message_sql_export_rejects_non_warning_findings() -> None:
    """Designer-message SQL export cannot emit local error-channel evidence."""
    finding = MakeLinterFinding(
        finding_id="designer-message:error",
        node_id="2",
        module_slug="json:ParseJSON",
        severity="error",
        message="This must not become designer evidence.",
        category="mapping",
        field_path="parameters.url",
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
        fingerprint="1" * 64,
    )

    with pytest.raises(ValueError, match="warning severity"):
        _ = designer_message_findings_to_sql(
            findings=(finding,),
            review_status="reviewed",
            valid_from=FIXED_CAPTURED_AT,
        )


def test_designer_message_sql_export_rejects_malformed_optional_fields() -> (
    None
):
    """Designer-message SQL export does not stringify malformed optional.

    fields.
    """
    finding = MakeLinterFinding(
        finding_id="designer-message:malformed-optional",
        node_id=cast("str | None", {"id": 2}),
        module_slug=cast("str | None", ["json:ParseJSON"]),
        severity="warning",
        message="This must not stringify malformed optional fields.",
        category=cast("str | None", {"category": "mapping"}),
        field_path=cast("str | None", ["parameters.url"]),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
        fingerprint="2" * 64,
    )

    with pytest.raises(TypeError, match="node_id"):
        _ = designer_message_findings_to_sql(
            findings=(finding,),
            review_status="reviewed",
            valid_from=FIXED_CAPTURED_AT,
        )


def test_designer_message_sql_export_nulls_blank_optional_fields() -> None:
    """Designer-message SQL export treats blank optional fields as absent.

    evidence.
    """
    finding = MakeLinterFinding(
        finding_id="designer-message:blank-optional",
        node_id=" ",
        module_slug="\t",
        severity="warning",
        message="Blank optional evidence should be omitted.",
        category="",
        field_path="\n",
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
        fingerprint="3" * SHA256_HEX_LENGTH,
    )

    sql = designer_message_findings_to_sql(
        findings=(finding,),
        review_status="reviewed",
        valid_from=FIXED_CAPTURED_AT,
    )

    assert "' '" not in sql, (
        f"Blank optional designer evidence must not be emitted: {sql}"
    )
    assert "'\\t'" not in sql, (
        f"Blank optional designer evidence must not be emitted: {sql}"
    )
    assert "''" not in sql, (
        f"Blank optional designer evidence must not be emitted: {sql}"
    )
    assert sql.count("NULL") == BLANK_OPTIONAL_SQL_NULL_COUNT, (
        f"Blank optional designer evidence should become NULL values: {sql}"
    )


def test_designer_message_ids_preserve_scenario_source_identity() -> None:
    """Identical designer messages from different scenarios stay distinct."""
    first = normalize_linter_findings(
        payload=documented_blueprint_response(),
        source_ref="make-api:/api/v2/scenarios/112/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )
    second = normalize_linter_findings(
        payload=documented_blueprint_response(),
        source_ref="make-api:/api/v2/scenarios/113/blueprint?draft=true",
        captured_at_utc=FIXED_CAPTURED_AT,
    )

    assert len(first) == 1, (
        f"Expected one finding per scenario: {first}, {second}"
    )
    assert len(second) == 1, (
        f"Expected one finding per scenario: {first}, {second}"
    )
    assert first[0].finding_id != second[0].finding_id, (
        "Designer-message finding IDs must include scenario source identity."
    )

    sql = designer_message_findings_to_sql(
        findings=(first[0], second[0]),
        review_status="reviewed",
        valid_from=FIXED_CAPTURED_AT,
    )

    assert (
        sql.count("INSERT OR REPLACE INTO designer_message_evidence")
        == MULTI_FINDING_SQL_INSERT_COUNT
    ), f"Both scenario findings must be exportable without collapse: {sql}"
    assert not ("scenarios/112" not in sql), (
        f"Designer-message SQL must preserve both source refs: {sql}"
    )
    assert not ("scenarios/113" not in sql), (
        f"Designer-message SQL must preserve both source refs: {sql}"
    )


def test_probe_status_and_report_reject_browser_scraping() -> None:
    """The go/no-go report keeps browser scraping rejected and offline.

    default.
    """
    status = build_linter_probe_status()
    _assert_linter_probe_status(status)
    _assert_linter_probe_report()


def _assert_linter_probe_status(status: JsonObject) -> None:
    assert status.get("report_path") == MAKE_LINTER_REPORT_PATH, (
        f"Linter probe status points at the wrong report: {status}"
    )
    assert status.get("browser_scraping") == "rejected", (
        f"Linter probe must reject browser scraping: {status}"
    )
    assert (
        status.get("standalone_validate_endpoint")
        == "not_found_in_documented_api_or_local_specs"
    ), f"Standalone validate endpoint status drifted: {status}"
    assert not (status.get("offline_validation_default") is not True), (
        f"Offline validation must remain default: {status}"
    )
    assert (
        status.get("designer_warning_prefix") == MAKE_DESIGNER_WARNING_PREFIX
    ), f"Status must expose designer warning prefix: {status}"
    assert status.get("local_error_prefix") == MAKE_AST_ERROR_PREFIX, (
        f"Status must expose local error prefix: {status}"
    )


def _assert_linter_probe_report() -> None:
    report_path = REPO_ROOT / MAKE_LINTER_REPORT_PATH
    loaded_report = cast(
        "object", json.loads(report_path.read_text(encoding="utf-8"))
    )
    assert isinstance(loaded_report, dict), (
        f"Linter probe report must be a JSON object: {loaded_report}"
    )
    report = cast("JsonObject", loaded_report)
    assert (
        report.get("status")
        == "conditional_go_for_documented_designer_messages"
    ), f"Unexpected linter probe report status: {report}"
    browser_scraping = report.get("browser_scraping")
    assert isinstance(browser_scraping, dict), (
        f"Report must include browser scraping status: {report}"
    )
    browser_scraping_payload = cast("JsonObject", browser_scraping)
    assert browser_scraping_payload.get("status") == "rejected", (
        f"Report must reject browser scraping: {report}"
    )
    rejected = report.get("rejected_candidates")
    assert isinstance(rejected, list), (
        f"Report must record rejected endpoint candidates: {report}"
    )
    assert rejected, (
        f"Report must record rejected endpoint candidates: {report}"
    )


def documented_blueprint_response() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "code": "OK",
        "response": {
            "blueprint": {
                "name": "Empty integration",
                "flow": [
                    {
                        "id": 2,
                        "module": "json:ParseJSON",
                        "version": 1,
                        "metadata": {
                            "designer": {
                                "x": -46,
                                "y": 47,
                                "messages": [
                                    {
                                        "category": "last ",
                                        "severity": "warning",
                                        "message": (
                                            "A transformer should not be the "
                                            "last module "
                                            "in the route."
                                        ),
                                    }
                                ],
                            }
                        },
                    }
                ],
            }
        },
    }


def blueprint_response_with_tool_message() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "response": {
            "blueprint": {
                "flow": [
                    {
                        "id": 1,
                        "module": "ai-agent:RunAgent",
                        "tools": [
                            {
                                "flow": [
                                    {
                                        "id": 7,
                                        "module": "gateway:WebhookRespond",
                                        "metadata": {
                                            "designer": {
                                                "messages": [
                                                    {
                                                        "severity": "warning",
                                                        "message": (
                                                            "Tool output is "
                                                            "not "
                                                            "returned "
                                                            "to the caller."
                                                        ),
                                                    }
                                                ]
                                            }
                                        },
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        }
    }


def blueprint_response_with_error_handler_message() -> JsonObject:
    """Return a compact blueprint fixture with an error-handler designer.

    message.
    """
    return {
        "response": {
            "blueprint": {
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "on_error": [
                            {
                                "id": 9,
                                "module": "builtin:Break",
                                "metadata": {
                                    "designer": {
                                        "messages": [
                                            {
                                                "severity": "warning ",
                                                "message": (
                                                    "Error handler route "
                                                    "needs completion."
                                                ),
                                            }
                                        ]
                                    }
                                },
                            }
                        ],
                    }
                ]
            }
        }
    }


def first_designer_message(payload: JsonObject) -> JsonObject:
    """Return the first designer message object from the compact fixture."""
    response = cast("JsonObject", payload["response"])
    blueprint = cast("JsonObject", response["blueprint"])
    flow = cast("list[object]", blueprint["flow"])
    node = cast("JsonObject", flow[0])
    metadata = cast("JsonObject", node["metadata"])
    designer = cast("JsonObject", metadata["designer"])
    messages = cast("list[object]", designer["messages"])
    return cast("JsonObject", messages[0])
