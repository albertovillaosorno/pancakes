# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for sellable customer-safe custom tools and reusable records.

Boundary contract:
- Owns: custom-tool product contracts, customer deliverables, and reusable
registry tests.
- Must not: use real customer payloads, credentials, live providers, or
generated cache roots.
- Allows: synthetic custom-tool requests and sanitized internal registry
assertions.
- Split when: generated custom-tool code or engagement storage gets separate
implementation.
- Merge when: custom module intake tests own the same sellable product contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from languages.make.custom_tool_products import (
    CUSTOM_TOOL_ARTIFACT_KINDS,
    CUSTOM_TOOL_DELIVERY_MANIFEST_NAME,
    CUSTOM_TOOL_REGISTRY_RELATIVE_PATH,
    CustomToolArtifactKind,
    CustomToolDeliveryPackageRequest,
    CustomToolGuidance,
    CustomToolProductError,
    CustomToolProductRequest,
    CustomToolProductWorkflowReport,
    build_custom_tool_delivery_package,
    create_custom_tool_product_contracts,
    custom_tool_delivery_manifest_as_dict,
    custom_tool_reusable_registry_path,
    load_custom_tool_reusable_registry_records,
    store_custom_tool_reusable_registry_records,
    write_custom_tool_delivery_package,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("artifact_kind", "deliverable_name"),
    [
        ("endpoint", "lead-router.openapi.json"),
        ("script", "lead-router.py"),
        ("api_wrapper", "ticket-wrapper.ts"),
        ("make_custom_app", "ticket-custom-app.zip"),
        ("make_custom_module", "route-lead.blueprint.json"),
        ("serverless_function", "route-lead-worker.ts"),
        ("parser", "invoice-parser.py"),
        ("data_cleaning_tool", "normalize-rows.py"),
    ],
)
def test_custom_tool_product_contract_accepts_all_sellable_artifact_kinds(
    artifact_kind: CustomToolArtifactKind,
    deliverable_name: str,
    tmp_path: Path,
) -> None:
    """Every supported custom-tool kind produces a deliverable and reusable.

    pattern.
    """
    report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind=artifact_kind,
                deliverable_name=deliverable_name,
            ),
        ),
        registry_storage_path=custom_tool_reusable_registry_path(tmp_path),
    )
    contract = report.contracts[0]
    reusable_record = report.reusable_registry_records[0]

    assert set(CUSTOM_TOOL_ARTIFACT_KINDS) == {
        "endpoint",
        "script",
        "api_wrapper",
        "make_custom_app",
        "make_custom_module",
        "serverless_function",
        "parser",
        "data_cleaning_tool",
    }
    assert contract.product_kind == "custom_tool_add_on"
    assert contract.artifact_kind == artifact_kind
    assert contract.customer_deliverable_name == deliverable_name
    assert contract.customer_receives_artifact is True
    assert contract.customer_delivery_boundary == (
        "customer_receives_code_or_integration_artifact"
    )
    assert contract.reusable_registry_required is True
    assert reusable_record.artifact_kind == artifact_kind
    assert reusable_record.reusable_scope == "internal_reusable_pattern"
    assert reusable_record.raw_payload_retained is False
    assert reusable_record.customer_secret_retained is False
    assert reusable_record.customer_private_payload_retained is False
    assert report.customer_deliverables == 1
    assert report.internal_reusable_records == 1
    assert report.provider_api_call is False
    assert report.live_make_called is False
    assert report.credentials_required is False


def test_custom_tool_reusable_registry_writes_only_sanitized_internal_records(
    tmp_path: Path,
) -> None:
    """Internal reusable custom-tool storage omits customer secrets and private.

    payloads.
    """
    storage_path = custom_tool_reusable_registry_path(tmp_path)
    report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="serverless_function",
                deliverable_name="route-lead-worker.ts",
            ),
        ),
        registry_storage_path=storage_path,
    )
    payload = _json_object_from_path(storage_path)
    stored_record = _object_list(payload, "records")[0]
    loaded_records = load_custom_tool_reusable_registry_records(storage_path)

    assert report.storage_report is not None
    assert (
        report.storage_report.relative_path
        == CUSTOM_TOOL_REGISTRY_RELATIVE_PATH
    )
    assert report.storage_report.record_count == 1
    assert report.storage_report.raw_payloads_written is False
    assert report.storage_report.customer_secrets_written is False
    assert report.storage_report.customer_private_payloads_written is False
    assert payload["raw_payloads_retained"] is False
    assert payload["customer_secrets_retained"] is False
    assert payload["customer_private_payloads_retained"] is False
    assert stored_record["registry_kind"] == "custom_tool_reusable_registry"
    assert stored_record["reusable_scope"] == "internal_reusable_pattern"
    assert stored_record["sanitized_input_fields"] == ["lead_status", "region"]
    assert stored_record["sanitized_output_fields"] == ["routing_decision"]
    assert stored_record["raw_payload_retained"] is False
    assert stored_record["customer_secret_retained"] is False
    assert stored_record["customer_private_payload_retained"] is False
    assert "source_hash" in stored_record
    assert "raw_payload" not in stored_record
    assert loaded_records == report.reusable_registry_records


def test_custom_tool_registry_merges_reusable_1303283d(
    tmp_path: Path,
) -> None:
    """Reusable registry storage deduplicates by sanitized reusable pattern.

    identity.
    """
    storage_path = custom_tool_reusable_registry_path(tmp_path)
    first_report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="parser",
                deliverable_name="invoice-parser.py",
                pattern_summary=(
                    "Parse normalized invoice rows into routing fields."
                ),
            ),
        ),
        registry_storage_path=storage_path,
    )
    second_report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="parser",
                deliverable_name="invoice-parser.py",
                pattern_summary=(
                    "Parse normalized invoice rows into routing fields."
                ),
            ),
            _product_request(
                artifact_kind="data_cleaning_tool",
                deliverable_name="normalize-rows.py",
                pattern_summary=(
                    "Normalize tabular rows before automation routing."
                ),
            ),
        ),
        registry_storage_path=storage_path,
    )
    loaded_records = load_custom_tool_reusable_registry_records(storage_path)

    assert len(first_report.reusable_registry_records) == 1
    assert second_report.storage_report is not None
    assert second_report.storage_report.record_count == 2
    assert len(loaded_records) == 2
    assert {record.artifact_kind for record in loaded_records} == {
        "parser",
        "data_cleaning_tool",
    }


def test_custom_tool_product_contract_rejects_eb80dd7f() -> None:
    """Reusable custom-tool records cannot retain secrets or private payload.

    descriptions.
    """
    with pytest.raises(CustomToolProductError, match="secret-like"):
        _ = create_custom_tool_product_contracts(
            product_requests=(
                _product_request(
                    artifact_kind="api_wrapper",
                    deliverable_name="ticket-wrapper.ts",
                    input_fields=("api_key",),
                ),
            ),
        )

    with pytest.raises(CustomToolProductError, match="private payload"):
        _ = create_custom_tool_product_contracts(
            product_requests=(
                _product_request(
                    artifact_kind="endpoint",
                    deliverable_name="lead-router.openapi.json",
                    pattern_summary="Reuse the raw payload routing strategy.",
                ),
            ),
        )


def test_custom_tool_registry_rejects_retained_customer_material(
    tmp_path: Path,
) -> None:
    """Persistent registry storage refuses records marked as retaining customer.

    material.
    """
    report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="script",
                deliverable_name="lead-router.py",
            ),
        ),
    )
    unsafe_record = report.reusable_registry_records[0]._replace(
        raw_payload_retained=True
    )

    with pytest.raises(CustomToolProductError, match="cannot retain"):
        _ = store_custom_tool_reusable_registry_records(
            storage_path=custom_tool_reusable_registry_path(tmp_path),
            registry_records=(unsafe_record,),
        )


def test_custom_tool_delivery_package_requires_complete_customer_handoff(
    tmp_path: Path,
) -> None:
    """A custom tool is complete only with artifact, tests, instructions, and.

    validation.
    """
    product_report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="serverless_function",
                deliverable_name="route-lead-worker.ts",
            ),
        ),
    )
    delivery_request = _delivery_request(product_report=product_report)
    package_root = tmp_path / "customer-delivery-package"

    write_report = write_custom_tool_delivery_package(
        package_root=package_root,
        request=delivery_request,
    )
    package = write_report.delivery_package

    assert package.source_artifact_present is True
    assert package.tests_present is True
    assert package.integration_instructions_present is True
    assert package.secrets_template_present is True
    assert package.local_validation_present is True
    assert package.delivery_package_present is True
    assert package.internal_registry_metadata_included is False
    assert write_report.files_written == (
        "route-lead-worker.ts",
        "tests/route-lead-worker.test.ts",
        "integration-instructions.md",
        "secrets-template.env.example",
        "local-validation.md",
        "delivery-manifest.json",
    )
    assert (package_root / "route-lead-worker.ts").is_file()
    assert (package_root / "tests" / "route-lead-worker.test.ts").is_file()
    assert (package_root / "secrets-template.env.example").read_text(
        encoding="utf-8",
    ) == "SERVICE_API_KEY=<provide-value>\n"
    assert write_report.internal_registry_metadata_included is False
    assert write_report.raw_payloads_written is False
    assert write_report.customer_secrets_written is False
    assert write_report.customer_private_payloads_written is False


def test_custom_tool_delivery_guidance_is_included_only_with_evidence() -> None:
    """Rate limits, scopes, and telemetry are included only when evidence.

    exists.
    """
    product_report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="endpoint",
                deliverable_name="lead-router.openapi.json",
            ),
        ),
    )
    package = build_custom_tool_delivery_package(
        _delivery_request(
            product_report=product_report,
            rate_limit_guidance=CustomToolGuidance(
                guidance_text="Limit calls to documented retry budgets.",
                evidence_ref="vendor-limits-review-0001",
            ),
        )
    )

    assert package.rate_limit_guidance_status == "included_with_evidence"
    assert package.rate_limit_evidence_ref == "vendor-limits-review-0001"
    assert package.scope_guidance_status == "omitted_no_evidence"
    assert package.scope_guidance is None
    assert package.telemetry_guidance_status == "omitted_no_evidence"
    assert package.telemetry_guidance is None


def test_custom_tool_delivery_manifest_excludes_internal_registry_metadata(
    tmp_path: Path,
) -> None:
    """Customer packages must not include the internal reusable registry.

    record.
    """
    product_report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="script",
                deliverable_name="lead-router.py",
            ),
        ),
    )
    package_root = tmp_path / "customer-delivery-package"
    write_report = write_custom_tool_delivery_package(
        package_root=package_root,
        request=_delivery_request(product_report=product_report),
    )
    manifest_payload = _json_object_from_path(
        package_root / CUSTOM_TOOL_DELIVERY_MANIFEST_NAME
    )
    manifest_text = json.dumps(manifest_payload, sort_keys=True)
    manifest_from_contract = custom_tool_delivery_manifest_as_dict(
        write_report.delivery_package,
    )

    assert manifest_payload == manifest_from_contract
    assert manifest_payload["internal_registry_metadata_included"] is False
    assert "pattern_id" not in manifest_text
    assert "source_hash" not in manifest_text
    assert "reusable_pattern_summary" not in manifest_text
    assert not (package_root / "custom_tools.json").exists()


def test_custom_tool_delivery_rejects_missing_required_handoff_parts() -> None:
    """Delivery package validation fails closed when required handoff pieces.

    are.

    absent.
    """
    product_report = create_custom_tool_product_contracts(
        product_requests=(
            _product_request(
                artifact_kind="parser",
                deliverable_name="invoice-parser.py",
            ),
        ),
    )

    with pytest.raises(CustomToolProductError, match="source_artifact_text"):
        _ = build_custom_tool_delivery_package(
            _delivery_request(
                product_report=product_report, source_artifact_text=""
            )
        )

    with pytest.raises(CustomToolProductError, match="secret placeholder"):
        _ = build_custom_tool_delivery_package(
            _delivery_request(
                product_report=product_report, secret_placeholders=()
            )
        )


def _product_request(
    *,
    artifact_kind: CustomToolArtifactKind,
    deliverable_name: str,
    pattern_summary: str = "Route normalized lead fields into reusable work queues.",
    input_fields: tuple[str, ...] = ("lead_status", "region"),
) -> CustomToolProductRequest:
    """Return a synthetic purchased custom-tool request."""
    return CustomToolProductRequest(
        artifact_kind=artifact_kind,
        tool_name="RouteLead",
        customer_deliverable_name=deliverable_name,
        reusable_pattern_summary=pattern_summary,
        input_fields=input_fields,
        output_fields=("routing_decision",),
        purchase_authorization_ref="custom-tool-order-0001",
        evidence_refs=("sanitized-requirement-inventory",),
    )


def _delivery_request(
    *,
    product_report: CustomToolProductWorkflowReport,
    source_artifact_text: str = "export function routeLead() { return 'queued'; }",
    secret_placeholders: tuple[str, ...] = ("SERVICE_API_KEY",),
    rate_limit_guidance: CustomToolGuidance | None = None,
) -> CustomToolDeliveryPackageRequest:
    """Return a synthetic custom-tool delivery package request."""
    contract = product_report.contracts[0]
    registry_record = product_report.reusable_registry_records[0]
    artifact_base_name = contract.customer_deliverable_name.rsplit(".", 1)[0]

    return CustomToolDeliveryPackageRequest(
        product_contract=contract,
        reusable_registry_record=registry_record,
        source_artifact_name=contract.customer_deliverable_name,
        source_artifact_text=source_artifact_text,
        test_artifact_name=f"{artifact_base_name}.test.ts",
        test_artifact_text="test('routeLead', () => expect(true).toBe(true));",
        integration_instructions=(
            "Install the artifact and configure SERVICE_API_KEY."
        ),
        secret_placeholders=secret_placeholders,
        local_validation_command="npm test route-lead-worker.test.ts",
        rate_limit_guidance=rate_limit_guidance,
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
