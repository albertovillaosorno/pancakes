# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for customer-safe Make custom module intake.

Boundary contract:
- Owns: custom module source classification, provenance, and custom tool spec
behavior.
- Must not: store raw customer payloads, credentials, account IDs, or provider
state.
- Allows: sanitized custom module facts and pass-through decisions.
- Split when: engagement storage gets a persistent repository boundary.
- Merge when: raw-spec compiler tests own the same custom source policy.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from catalog.fallback.results import (
    SOURCE_LABEL_CLIENT_BUSINESS_CUSTOM_MODULE,
    SOURCE_LABEL_PRIVATE_THIRD_PARTY_OR_CUSTOMER_PRIVATE_MODULE,
    SOURCE_LABEL_PUBLIC_API_CONNECTOR_CANDIDATE,
    catalog_source_rank,
)
from languages.make import custom_modules
from languages.make.custom_modules import (
    CustomModuleAuthorization,
    CustomModuleIntakeError,
    CustomModuleIntakeRequest,
    build_custom_module_intake_record,
    build_customer_safe_custom_tool_spec,
    create_customer_safe_custom_tool_specs,
    custom_module_intake_storage_path,
    custom_module_pass_through_report,
    load_custom_module_intake_records,
    store_custom_module_intake_record,
    store_custom_module_intake_records,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

REPO_ROOT = repo_root()


def test_public_api_connector_candidate_requires_explicit_promotion() -> None:
    """Public candidates can become shared catalog candidates only with.

    explicit.

    approval.
    """
    record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="public_api_connector_candidate",
            app_slug="acme-public",
            app_version="1.0",
            internal_name="CreateTicket",
            display_name="Create ticket",
            field_names=("summary", "priority"),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="public-openapi-reference",
                shared_catalog_promotion_approved=True,
            ),
            evidence_refs=("public-openapi-reference",),
        ),
    )

    assert record.source_label == SOURCE_LABEL_PUBLIC_API_CONNECTOR_CANDIDATE
    assert record.source_rank == catalog_source_rank(
        SOURCE_LABEL_PUBLIC_API_CONNECTOR_CANDIDATE
    )
    assert record.shared_catalog_eligible is True
    assert record.raw_payload_retained is False
    assert record.deletion_status == "not_applicable_public_source"
    report = custom_module_pass_through_report(
        module_token=record.module_token,
        intake_record=record,
    )
    assert report["status"] == "catalog_candidate", (
        f"Public promotion was blocked: {report}"
    )


def test_client_business_custom_module_stays_engagement_local() -> None:
    """Client business modules keep sanitized facts without becoming reusable.

    catalog truth.
    """
    record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="client_business_custom_module",
            app_slug="client-ops",
            app_version="2026.05",
            internal_name="RouteLead",
            display_name="Route lead",
            field_names=("lead_status", "region"),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="engagement-approval-42",
                shared_catalog_promotion_approved=True,
            ),
            evidence_refs=(
                "engagement-approval-42",
                "sanitized-field-inventory",
            ),
        ),
    )
    spec = build_customer_safe_custom_tool_spec(
        intake_record=record,
        tool_name="RouteLead",
        description="Route one sanitized lead record.",
    )

    assert record.source_label == SOURCE_LABEL_CLIENT_BUSINESS_CUSTOM_MODULE
    assert record.source_rank == catalog_source_rank(
        SOURCE_LABEL_CLIENT_BUSINESS_CUSTOM_MODULE
    )
    assert record.shared_catalog_eligible is False
    assert record.raw_payload_retained is False
    assert record.deletion_status == "raw_deleted_after_sanitization"
    assert spec["status"] == "ready"
    assert spec["scope"] == "engagement_local"
    assert spec["provider_api_call"] is False
    assert spec["live_make_called"] is False
    assert spec["credentials_required"] is False


def test_custom_module_intake_storage_writes_only_sanitized_metadata(
    tmp_path: Path,
) -> None:
    """Sanitized intake storage writes metadata without raw customer.

    payloads.
    """
    record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="client_business_custom_module",
            app_slug="client-ops",
            app_version="2026.05",
            internal_name="RouteLead",
            display_name="Route lead",
            field_names=("lead_status", "region"),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="engagement-approval-42",
            ),
            evidence_refs=("sanitized-field-inventory",),
        ),
    )

    report = store_custom_module_intake_record(
        repo_root=tmp_path, intake_record=record
    )
    storage_path = custom_module_intake_storage_path(tmp_path)
    payload = _json_object_from_path(storage_path)
    stored_records = _object_list(payload, "records")
    stored_record = stored_records[0]

    assert report.raw_payloads_written is False
    assert report.relative_path == (
        "src/languages/make/client_raw_module_specs/sanitized/custom_modules.json"
    )
    assert report.record_count == 1
    assert report.engagement_local_records == 1
    assert payload["raw_payloads_retained"] is False
    assert stored_record["classification"] == "client_business_custom_module"
    assert stored_record["sanitized_field_names"] == ["lead_status", "region"]
    assert (
        stored_record["redaction_status"] == "sanitized_functional_facts_only"
    )
    assert stored_record["deletion_status"] == "raw_deleted_after_sanitization"
    assert stored_record["raw_payload_retained"] is False
    assert stored_record["retention_scope"] == "engagement_local"
    assert "source_hash" in stored_record
    assert "raw_payload" not in stored_record


def test_custom_module_intake_storage_rejects_raw_retention_state(
    tmp_path: Path,
) -> None:
    """Persistent custom module storage refuses records that retain raw.

    payloads.
    """
    record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="client_business_custom_module",
            app_slug="client-ops",
            app_version="2026.05",
            internal_name="RouteLead",
            display_name="Route lead",
            field_names=("lead_status",),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="engagement-approval-42",
            ),
            evidence_refs=("sanitized-field-inventory",),
        ),
    )
    unsafe_record = record._replace(raw_payload_retained=True)

    with pytest.raises(
        CustomModuleIntakeError, match="Raw custom module payloads"
    ):
        _ = store_custom_module_intake_record(
            repo_root=tmp_path, intake_record=unsafe_record
        )


def test_custom_module_intake_storage_rejects_linked_storage_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sanitized custom module storage must not follow linked output paths."""
    record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="client_business_custom_module",
            app_slug="client-ops",
            app_version="2026.05",
            internal_name="RouteLead",
            display_name="Route lead",
            field_names=("lead_status",),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="engagement-approval-42",
            ),
            evidence_refs=("sanitized-field-inventory",),
        ),
    )
    storage_path = custom_module_intake_storage_path(tmp_path)
    storage_path.parent.mkdir(parents=True)
    _ = storage_path.write_text("outside placeholder\n", encoding="utf-8")

    def fake_link_probe(path: Path) -> bool:
        return path == storage_path

    monkeypatch.setattr(
        custom_modules, "_path_is_filesystem_link", fake_link_probe
    )

    with pytest.raises(CustomModuleIntakeError, match="symlink or junction"):
        _ = store_custom_module_intake_records(
            storage_path=storage_path,
            intake_records=(record,),
        )
    assert storage_path.read_text(encoding="utf-8") == "outside placeholder\n"


def test_custom_module_storage_keeps_public_7deb6ab3(
    tmp_path: Path,
) -> None:
    """Shared candidates and customer-local modules remain separate storage.

    records.
    """
    public_record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="public_api_connector_candidate",
            app_slug="acme-public",
            app_version="1.0",
            internal_name="CreateTicket",
            display_name="Create ticket",
            field_names=("summary",),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="public-openapi-reference",
                shared_catalog_promotion_approved=True,
            ),
            evidence_refs=("public-openapi-reference",),
        ),
    )
    client_record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="client_business_custom_module",
            app_slug="acme-public",
            app_version="1.0",
            internal_name="CreateTicket",
            display_name="Create ticket",
            field_names=("customer_status",),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="engagement-approval-42",
                shared_catalog_promotion_approved=True,
            ),
            evidence_refs=("sanitized-field-inventory",),
        ),
    )

    storage_path = custom_module_intake_storage_path(tmp_path)
    report = store_custom_module_intake_records(
        storage_path=storage_path,
        intake_records=(public_record, client_record),
    )
    loaded_records = load_custom_module_intake_records(storage_path)
    classifications = {record.classification for record in loaded_records}
    client_records = [
        record
        for record in loaded_records
        if record.classification == "client_business_custom_module"
    ]

    assert report.shared_catalog_records == 1
    assert report.engagement_local_records == 1
    assert classifications == {
        "public_api_connector_candidate",
        "client_business_custom_module",
    }
    assert client_records[0].shared_catalog_eligible is False
    assert client_records[0].retention_scope == "engagement_local"


def test_custom_tool_creator_workflow_builds_local_specs_without_provider_calls(
    tmp_path: Path,
) -> None:
    """The custom tool creator workflow stays local and separates reusable.

    truth.
    """
    public_request = CustomModuleIntakeRequest(
        classification="public_api_connector_candidate",
        app_slug="acme-public",
        app_version="1.0",
        internal_name="CreateTicket",
        display_name="Create ticket",
        field_names=("summary",),
        authorization=CustomModuleAuthorization(
            authorized=True,
            authorization_ref="public-openapi-reference",
            shared_catalog_promotion_approved=True,
        ),
        evidence_refs=("public-openapi-reference",),
    )
    client_request = CustomModuleIntakeRequest(
        classification="client_business_custom_module",
        app_slug="client-ops",
        app_version="2026.05",
        internal_name="RouteLead",
        display_name="Route lead",
        field_names=("lead_status",),
        authorization=CustomModuleAuthorization(
            authorized=True,
            authorization_ref="engagement-approval-42",
            shared_catalog_promotion_approved=True,
        ),
        evidence_refs=("sanitized-field-inventory",),
    )
    private_request = CustomModuleIntakeRequest(
        classification="private_third_party_or_customer_private_module",
        app_slug="partner-private",
        app_version="1.0",
        internal_name="PrivateAction",
        display_name="Private action",
        field_names=("status",),
        authorization=CustomModuleAuthorization(
            authorized=True,
            authorization_ref="private-review-7",
        ),
        evidence_refs=("private-review-7",),
    )

    report = create_customer_safe_custom_tool_specs(
        intake_requests=(public_request, client_request, private_request),
        unknown_module_tokens=("unknown-custom:DoThing",),
        storage_path=custom_module_intake_storage_path(tmp_path),
    )
    scopes = {spec["module_token"]: spec["scope"] for spec in report.specs}
    pass_through_reasons = {
        item["module_token"]: item["reason"]
        for item in report.pass_through_reports
    }

    assert report.provider_api_call is False
    assert report.live_make_called is False
    assert report.credentials_required is False
    assert report.storage_report is not None
    assert report.storage_report.record_count == 3
    assert report.shared_catalog_promotions == 1
    assert report.engagement_local_specs == 1
    assert report.pass_through_specs == 1
    assert scopes == {
        "acme-public:CreateTicket": "shared_catalog_candidate",
        "client-ops:RouteLead": "engagement_local",
        "partner-private:PrivateAction": "pass_through_only",
    }
    assert pass_through_reasons["partner-private:PrivateAction"] == (
        "private_custom_module_evidence_is_not_reusable_catalog_truth"
    )
    assert (
        pass_through_reasons["unknown-custom:DoThing"]
        == "custom_module_evidence_missing"
    )


def test_custom_tool_creator_workflow_blocks_unauthorized_evidence() -> None:
    """The custom tool creator workflow requires explicit authorization."""
    with pytest.raises(
        CustomModuleIntakeError, match="requires explicit authorization"
    ):
        _ = create_customer_safe_custom_tool_specs(
            intake_requests=(
                CustomModuleIntakeRequest(
                    classification="client_business_custom_module",
                    app_slug="client-ops",
                    app_version="2026.05",
                    internal_name="RouteLead",
                    display_name="Route lead",
                    field_names=("lead_status",),
                    authorization=CustomModuleAuthorization(
                        authorized=False,
                        authorization_ref="engagement-approval-42",
                    ),
                    evidence_refs=("sanitized-field-inventory",),
                ),
            ),
        )


def test_private_third_party_custom_module_remains_pass_through_only() -> None:
    """Private third-party or customer-private modules are not converted into.

    tool specs.
    """
    record = build_custom_module_intake_record(
        CustomModuleIntakeRequest(
            classification="private_third_party_or_customer_private_module",
            app_slug="partner-private",
            app_version="1.0",
            internal_name="PrivateAction",
            display_name="Private action",
            field_names=("status",),
            authorization=CustomModuleAuthorization(
                authorized=True,
                authorization_ref="private-review-7",
                delete_after_processing=True,
            ),
            evidence_refs=("private-review-7",),
        ),
    )
    spec = build_customer_safe_custom_tool_spec(
        intake_record=record,
        tool_name="PrivateAction",
        description=(
            "Preserve unsupported private module as pass-through evidence."
        ),
    )

    assert (
        record.source_label
        == SOURCE_LABEL_PRIVATE_THIRD_PARTY_OR_CUSTOMER_PRIVATE_MODULE
    )
    assert record.shared_catalog_eligible is False
    assert record.retention_behavior == "pass_through_only"
    assert spec["status"] == "pass_through_only"
    assert spec["fields"] == ()
    assert spec["catalog_module_id"] is None


def test_custom_module_raw_intake_path_tracks_only_ignore_policy() -> None:
    """The raw intake path tracks only its Git ignore policy."""
    ignore_text = (
        REPO_ROOT
        / "src"
        / "languages"
        / "make"
        / "client_raw_module_specs"
        / ".gitignore"
    ).read_text(encoding="utf-8")

    assert ignore_text == "*\n!.gitignore\n"


def test_unknown_custom_module_without_evidence_is_pass_through() -> None:
    """Unknown custom modules remain visible instead of being deleted or.

    fabricated.
    """
    module_token = "unknown-custom:DoThing"
    report = custom_module_pass_through_report(module_token=module_token)

    assert report == {
        "status": "pass_through_only",
        "module_token": "unknown-custom:DoThing",
        "source_label": None,
        "source_rank": None,
        "shared_catalog_eligible": False,
        "reason": "custom_module_evidence_missing",
    }


def test_custom_module_intake_rejects_secret_or_account_specific_text() -> None:
    """Sanitized intake refuses credential and account-specific material."""
    with pytest.raises(CustomModuleIntakeError, match="secret-like"):
        _ = build_custom_module_intake_record(
            CustomModuleIntakeRequest(
                classification="client_business_custom_module",
                app_slug="client-ops",
                app_version="2026.05",
                internal_name="RouteLead",
                display_name="Route lead",
                field_names=("api_key",),
                authorization=CustomModuleAuthorization(
                    authorized=True,
                    authorization_ref="engagement-approval-42",
                ),
                evidence_refs=("engagement-approval-42",),
            ),
        )


def _json_object_from_path(path: Path) -> dict[str, object]:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return {
        str(key): value
        for key, value in cast("dict[object, object]", payload).items()
    }


def _object_list(
    payload: dict[str, object], key: str
) -> tuple[dict[str, object], ...]:
    value = payload.get(key)
    assert isinstance(value, list), f"{key} must be a list."
    records: list[dict[str, object]] = []
    for item in cast("list[object]", value):
        assert isinstance(item, dict), f"{key} must contain only JSON objects."
        records.append(
            {
                str(key): value
                for key, value in cast("dict[object, object]", item).items()
            }
        )
    return tuple(records)
