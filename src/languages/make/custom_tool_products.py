# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# - 001069#repo.make-source-material.legal-use-boundary
# - 001075#repo.client-blueprint-intake.shape-secret-identifier-gates
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Customer-safe custom tool product contracts and reusable registry records.

Boundary contract:
- Owns: sellable custom-tool add-on contracts and reusable sanitized pattern
storage.
- Must not: store customer secrets, raw/private payloads, credentials, or
provider state.
- Allows: customer deliverable promises and generalized internal custom-tool
patterns.
- Split when: custom-tool code generation or engagement storage needs its own
boundary.
- Merge when: custom module intake owns the same product and reusable registry
contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

type CustomToolArtifactKind = Literal[
    "endpoint ",
    "script ",
    "api_wrapper ",
    "make_custom_app ",
    "make_custom_module ",
    "serverless_function ",
    "parser ",
    "data_cleaning_tool",
]
type CustomToolProductKind = Literal["custom_tool_add_on"]
type CustomToolCustomerDeliveryBoundary = Literal[
    "customer_receives_code_or_integration_artifact"
]
type CustomToolReusableScope = Literal["internal_reusable_pattern"]
type CustomToolRegistryKind = Literal["custom_tool_reusable_registry"]
type CustomToolDeliveryPackageKind = Literal["custom_tool_delivery_package"]
type CustomToolGuidanceStatus = Literal[
    "included_with_evidence", "omitted_no_evidence"
]
type JsonObject = dict[str, object]

CUSTOM_TOOL_ARTIFACT_KINDS: Final[frozenset[str]] = frozenset(
    (
        "endpoint ",
        "script ",
        "api_wrapper ",
        "make_custom_app ",
        "make_custom_module ",
        "serverless_function ",
        "parser ",
        "data_cleaning_tool",
    )
)
CUSTOM_TOOL_PRODUCT_KIND: Final[CustomToolProductKind] = "custom_tool_add_on"
CUSTOM_TOOL_DELIVERY_BOUNDARY: Final[CustomToolCustomerDeliveryBoundary] = (
    "customer_receives_code_or_integration_artifact"
)
CUSTOM_TOOL_REUSABLE_SCOPE: Final[CustomToolReusableScope] = (
    "internal_reusable_pattern"
)
CUSTOM_TOOL_REGISTRY_KIND: Final[CustomToolRegistryKind] = (
    "custom_tool_reusable_registry"
)
CUSTOM_TOOL_DELIVERY_PACKAGE_KIND: Final[CustomToolDeliveryPackageKind] = (
    "custom_tool_delivery_package"
)
CUSTOM_TOOL_REGISTRY_SCHEMA_VERSION: Final = 1
CUSTOM_TOOL_REGISTRY_STORAGE_KIND: Final = (
    "custom_tool_reusable_registry_storage"
)
CUSTOM_TOOL_SANITIZER_VERSION: Final = "custom-tool-product-sanitizer-v1"
CUSTOM_TOOL_REGISTRY_RELATIVE_PATH: Final = (
    "src/languages/make/custom_tool_registry/sanitized/custom_tools.json"
)
CUSTOM_TOOL_DELIVERY_MANIFEST_NAME: Final = "delivery-manifest.json"
CUSTOM_TOOL_INTEGRATION_INSTRUCTIONS_NAME: Final = "integration-instructions.md"
CUSTOM_TOOL_LOCAL_VALIDATION_NAME: Final = "local-validation.md"
CUSTOM_TOOL_SECRETS_TEMPLATE_NAME: Final = "secrets-template.env.example"
SAFE_IDENTIFIER_PATTERN: Final = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$"
)
SAFE_PLACEHOLDER_PATTERN: Final = re.compile(r"^[A-Z][A-Z0-9_]{2,95}$")
SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(
        r"(?i)[?&](?:api[_-]?key|access[_-]?token|token|secret|password)="
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
SECRET_TEXT_MARKERS: Final = frozenset(
    (
        "access_token ",
        "account_id ",
        "api_key ",
        "apikey ",
        "authorization ",
        "bearer ",
        "client_secret ",
        "credential ",
        "customer_id ",
        "password ",
        "private_key ",
        "refresh_token ",
        "secret ",
        "token ",
        "x-api-key",
    )
)
PRIVATE_PAYLOAD_MARKERS: Final = frozenset(
    (
        "customer payload ",
        "customer_payload ",
        "private payload ",
        "private_payload ",
        "raw payload ",
        "raw_payload",
    )
)
PRIVATE_EXAMPLE_MARKERS: Final = frozenset(("@", "http://", "https://"))


class CustomToolProductError(ValueError):
    """Raised when a custom-tool product contract crosses the safe boundary."""


class CustomToolProductRequest(NamedTuple):
    """One purchased custom-tool request before product and registry.

    sanitization.
    """

    artifact_kind: CustomToolArtifactKind
    tool_name: str
    customer_deliverable_name: str
    reusable_pattern_summary: str
    input_fields: tuple[str, ...]
    output_fields: tuple[str, ...]
    purchase_authorization_ref: str
    evidence_refs: tuple[str, ...]


class CustomToolProductContract(NamedTuple):
    """Customer-facing custom-tool add-on contract."""

    product_kind: CustomToolProductKind
    artifact_kind: CustomToolArtifactKind
    tool_name: str
    customer_deliverable_name: str
    customer_receives_artifact: bool
    customer_delivery_boundary: CustomToolCustomerDeliveryBoundary
    purchase_authorization_ref: str
    input_fields: tuple[str, ...]
    output_fields: tuple[str, ...]
    reusable_registry_required: bool
    private_payloads_reusable: bool
    customer_secrets_reusable: bool
    provider_api_call: bool
    live_make_called: bool
    credentials_required: bool
    evidence_refs: tuple[str, ...]


class CustomToolReusableRegistryRecord(NamedTuple):
    """Sanitized internal reusable custom-tool pattern record."""

    registry_kind: CustomToolRegistryKind
    artifact_kind: CustomToolArtifactKind
    pattern_id: str
    tool_name: str
    reusable_pattern_summary: str
    sanitized_input_fields: tuple[str, ...]
    sanitized_output_fields: tuple[str, ...]
    reusable_scope: CustomToolReusableScope
    source_refs: tuple[str, ...]
    source_hash: str
    sanitizer_version: str
    raw_payload_retained: bool
    customer_secret_retained: bool
    customer_private_payload_retained: bool


class CustomToolRegistryStorageReport(NamedTuple):
    """Summary of one sanitized custom-tool reusable registry write."""

    relative_path: str
    record_count: int
    raw_payloads_written: bool
    customer_secrets_written: bool
    customer_private_payloads_written: bool
    reusable_scope: CustomToolReusableScope


class CustomToolProductWorkflowReport(NamedTuple):
    """Summary of one local customer-safe custom-tool product workflow."""

    contracts: tuple[CustomToolProductContract, ...]
    reusable_registry_records: tuple[CustomToolReusableRegistryRecord, ...]
    storage_report: CustomToolRegistryStorageReport | None
    customer_deliverables: int
    internal_reusable_records: int
    provider_api_call: bool
    live_make_called: bool
    credentials_required: bool


class CustomToolGuidance(NamedTuple):
    """Optional custom-tool operational guidance supported by evidence."""

    guidance_text: str
    evidence_ref: str


class CustomToolDeliveryPackageRequest(NamedTuple):
    """One customer custom-tool delivery package request."""

    product_contract: CustomToolProductContract
    reusable_registry_record: CustomToolReusableRegistryRecord
    source_artifact_name: str
    source_artifact_text: str
    test_artifact_name: str
    test_artifact_text: str
    integration_instructions: str
    secret_placeholders: tuple[str, ...]
    local_validation_command: str
    rate_limit_guidance: CustomToolGuidance | None = None
    scope_guidance: CustomToolGuidance | None = None
    telemetry_guidance: CustomToolGuidance | None = None


class CustomToolDeliveryPackage(NamedTuple):
    """Validated customer-facing custom-tool delivery package manifest."""

    package_kind: CustomToolDeliveryPackageKind
    tool_name: str
    artifact_kind: CustomToolArtifactKind
    customer_deliverable_name: str
    source_artifact_name: str
    test_artifact_name: str
    integration_instructions_name: str
    secrets_template_name: str
    local_validation_name: str
    manifest_name: str
    customer_files: tuple[str, ...]
    source_artifact_present: bool
    tests_present: bool
    integration_instructions_present: bool
    secrets_template_present: bool
    local_validation_present: bool
    delivery_package_present: bool
    internal_registry_metadata_included: bool
    rate_limit_guidance_status: CustomToolGuidanceStatus
    rate_limit_guidance: str | None
    rate_limit_evidence_ref: str | None
    scope_guidance_status: CustomToolGuidanceStatus
    scope_guidance: str | None
    scope_evidence_ref: str | None
    telemetry_guidance_status: CustomToolGuidanceStatus
    telemetry_guidance: str | None
    telemetry_evidence_ref: str | None
    raw_payload_retained: bool
    customer_secret_retained: bool
    customer_private_payload_retained: bool


class CustomToolDeliveryPackageWriteReport(NamedTuple):
    """Summary of one customer custom-tool delivery package write."""

    package_root: str
    delivery_package: CustomToolDeliveryPackage
    files_written: tuple[str, ...]
    manifest_written: bool
    internal_registry_metadata_included: bool
    raw_payloads_written: bool
    customer_secrets_written: bool
    customer_private_payloads_written: bool


def build_custom_tool_product_contract(
    request: CustomToolProductRequest,
) -> CustomToolProductContract:
    """Return a customer-facing contract for one purchased custom-tool add-on.

    Returns:
        The customer-visible custom-tool add-on contract.
    """
    _require_artifact_kind(request.artifact_kind)
    safe_tool_name = _safe_identifier(request.tool_name, field_name="tool_name")
    safe_deliverable_name = _safe_identifier(
        request.customer_deliverable_name,
        field_name="customer_deliverable_name",
    )
    safe_purchase_ref = _safe_text(
        request.purchase_authorization_ref,
        field_name="purchase_authorization_ref",
    )
    safe_inputs = _safe_field_names(
        request.input_fields, field_name="input_fields"
    )
    safe_outputs = _safe_field_names(
        request.output_fields, field_name="output_fields"
    )
    safe_evidence = _safe_reference_tuple(
        request.evidence_refs, field_name="evidence_ref"
    )
    return CustomToolProductContract(
        product_kind=CUSTOM_TOOL_PRODUCT_KIND,
        artifact_kind=request.artifact_kind,
        tool_name=safe_tool_name,
        customer_deliverable_name=safe_deliverable_name,
        customer_receives_artifact=True,
        customer_delivery_boundary=CUSTOM_TOOL_DELIVERY_BOUNDARY,
        purchase_authorization_ref=safe_purchase_ref,
        input_fields=safe_inputs,
        output_fields=safe_outputs,
        reusable_registry_required=True,
        private_payloads_reusable=False,
        customer_secrets_reusable=False,
        provider_api_call=False,
        live_make_called=False,
        credentials_required=False,
        evidence_refs=safe_evidence,
    )


def build_custom_tool_reusable_registry_record(
    request: CustomToolProductRequest,
) -> CustomToolReusableRegistryRecord:
    """Return a sanitized internal reusable custom-tool pattern record.

    Returns:
        The reusable registry record.
    """
    contract = build_custom_tool_product_contract(request)
    safe_summary = _safe_text(
        request.reusable_pattern_summary,
        field_name="reusable_pattern_summary",
    )
    hash_payload: JsonObject = {
        "artifact_kind": contract.artifact_kind,
        "tool_name": contract.tool_name,
        "reusable_pattern_summary": safe_summary,
        "input_fields": list(contract.input_fields),
        "output_fields": list(contract.output_fields),
        "source_refs": list(contract.evidence_refs),
        "sanitizer_version": CUSTOM_TOOL_SANITIZER_VERSION,
    }
    source_hash = _source_hash(hash_payload)
    return CustomToolReusableRegistryRecord(
        registry_kind=CUSTOM_TOOL_REGISTRY_KIND,
        artifact_kind=contract.artifact_kind,
        pattern_id=f"custom-tool:{contract.artifact_kind}:{source_hash[:16]}",
        tool_name=contract.tool_name,
        reusable_pattern_summary=safe_summary,
        sanitized_input_fields=contract.input_fields,
        sanitized_output_fields=contract.output_fields,
        reusable_scope=CUSTOM_TOOL_REUSABLE_SCOPE,
        source_refs=contract.evidence_refs,
        source_hash=source_hash,
        sanitizer_version=CUSTOM_TOOL_SANITIZER_VERSION,
        raw_payload_retained=False,
        customer_secret_retained=False,
        customer_private_payload_retained=False,
    )


def create_custom_tool_product_contracts(
    *,
    product_requests: tuple[CustomToolProductRequest, ...],
    registry_storage_path: Path | None = None,
) -> CustomToolProductWorkflowReport:
    """Create local product contracts and internal reusable registry records.

    Returns:
        A local workflow report with no provider calls or credential
        requirements.

    Raises:
        CustomToolProductError: If no requests are provided or a request is
        unsafe.
    """
    if not product_requests:
        message = "Custom tool product workflow requires at least one request."
        raise CustomToolProductError(message)
    contracts = tuple(
        build_custom_tool_product_contract(request)
        for request in product_requests
    )
    registry_records = tuple(
        build_custom_tool_reusable_registry_record(request)
        for request in product_requests
    )
    storage_report = (
        store_custom_tool_reusable_registry_records(
            storage_path=registry_storage_path,
            registry_records=registry_records,
            relative_path=CUSTOM_TOOL_REGISTRY_RELATIVE_PATH,
        )
        if registry_storage_path is not None
        else None
    )
    return CustomToolProductWorkflowReport(
        contracts=contracts,
        reusable_registry_records=registry_records,
        storage_report=storage_report,
        customer_deliverables=sum(
            1 for contract in contracts if contract.customer_receives_artifact
        ),
        internal_reusable_records=len(registry_records),
        provider_api_call=False,
        live_make_called=False,
        credentials_required=False,
    )


def build_custom_tool_delivery_package(
    request: CustomToolDeliveryPackageRequest,
) -> CustomToolDeliveryPackage:
    """Return a validated customer custom-tool delivery package manifest.

    Returns:
        The customer-facing package manifest.

    Raises:
        CustomToolProductError: If the package request is incomplete or unsafe.
    """
    _require_delivery_contract_matches_registry(request)
    source_artifact_name = _safe_identifier(
        request.source_artifact_name,
        field_name="source_artifact_name",
    )
    if (
        source_artifact_name
        != request.product_contract.customer_deliverable_name
    ):
        message = (
            "Custom tool source artifact must match the purchased deliverable "
            "name."
        )
        raise CustomToolProductError(message)
    test_artifact_name = _safe_identifier(
        request.test_artifact_name,
        field_name="test_artifact_name",
    )
    _ = _safe_document_text(
        request.source_artifact_text, field_name="source_artifact_text"
    )
    _ = _safe_document_text(
        request.test_artifact_text, field_name="test_artifact_text"
    )
    integration_instructions = _safe_document_text(
        request.integration_instructions,
        field_name="integration_instructions",
    )
    local_validation_command = _safe_document_text(
        request.local_validation_command,
        field_name="local_validation_command",
    )
    secret_placeholders = _safe_secret_placeholders(request.secret_placeholders)
    rate_limit_guidance = _optional_guidance(request.rate_limit_guidance)
    scope_guidance = _optional_guidance(request.scope_guidance)
    telemetry_guidance = _optional_guidance(request.telemetry_guidance)
    customer_files = (
        source_artifact_name,
        f"tests/{test_artifact_name}",
        CUSTOM_TOOL_INTEGRATION_INSTRUCTIONS_NAME,
        CUSTOM_TOOL_SECRETS_TEMPLATE_NAME,
        CUSTOM_TOOL_LOCAL_VALIDATION_NAME,
        CUSTOM_TOOL_DELIVERY_MANIFEST_NAME,
    )
    return CustomToolDeliveryPackage(
        package_kind=CUSTOM_TOOL_DELIVERY_PACKAGE_KIND,
        tool_name=request.product_contract.tool_name,
        artifact_kind=request.product_contract.artifact_kind,
        customer_deliverable_name=request.product_contract.customer_deliverable_name,
        source_artifact_name=source_artifact_name,
        test_artifact_name=test_artifact_name,
        integration_instructions_name=CUSTOM_TOOL_INTEGRATION_INSTRUCTIONS_NAME,
        secrets_template_name=CUSTOM_TOOL_SECRETS_TEMPLATE_NAME,
        local_validation_name=CUSTOM_TOOL_LOCAL_VALIDATION_NAME,
        manifest_name=CUSTOM_TOOL_DELIVERY_MANIFEST_NAME,
        customer_files=customer_files,
        source_artifact_present=True,
        tests_present=True,
        integration_instructions_present=bool(integration_instructions),
        secrets_template_present=bool(secret_placeholders),
        local_validation_present=bool(local_validation_command),
        delivery_package_present=True,
        internal_registry_metadata_included=False,
        rate_limit_guidance_status=_guidance_status(rate_limit_guidance),
        rate_limit_guidance=_guidance_text(rate_limit_guidance),
        rate_limit_evidence_ref=_guidance_evidence_ref(rate_limit_guidance),
        scope_guidance_status=_guidance_status(scope_guidance),
        scope_guidance=_guidance_text(scope_guidance),
        scope_evidence_ref=_guidance_evidence_ref(scope_guidance),
        telemetry_guidance_status=_guidance_status(telemetry_guidance),
        telemetry_guidance=_guidance_text(telemetry_guidance),
        telemetry_evidence_ref=_guidance_evidence_ref(telemetry_guidance),
        raw_payload_retained=False,
        customer_secret_retained=False,
        customer_private_payload_retained=False,
    )


def write_custom_tool_delivery_package(
    *,
    package_root: Path,
    request: CustomToolDeliveryPackageRequest,
) -> CustomToolDeliveryPackageWriteReport:
    """Write one validated customer custom-tool delivery package.

    Returns:
        The package write summary.

    Raises:
        OSError: If a package file cannot be fully written.
    """
    _reject_linked_storage_path(package_root)
    delivery_package = build_custom_tool_delivery_package(request)
    package_root.mkdir(parents=True, exist_ok=True)
    _reject_linked_storage_path(package_root)
    file_payloads = _delivery_package_file_payloads(
        request=request,
        delivery_package=delivery_package,
    )
    files_written: list[str] = []
    for relative_path, payload in file_payloads:
        target_path = package_root / relative_path
        _reject_linked_storage_path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        _reject_linked_storage_path(target_path)
        payload_bytes = payload.encode("utf-8")
        written_bytes = target_path.write_bytes(payload_bytes)
        if written_bytes != len(payload_bytes):
            message = (
                f"Could not write full custom tool delivery file to"
                f"{target_path}."
            )
            raise OSError(message)
        files_written.append(relative_path)
    return CustomToolDeliveryPackageWriteReport(
        package_root=package_root.as_posix(),
        delivery_package=delivery_package,
        files_written=tuple(files_written),
        manifest_written=CUSTOM_TOOL_DELIVERY_MANIFEST_NAME in files_written,
        internal_registry_metadata_included=False,
        raw_payloads_written=False,
        customer_secrets_written=False,
        customer_private_payloads_written=False,
    )


def custom_tool_delivery_manifest_as_dict(
    delivery_package: CustomToolDeliveryPackage,
) -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "package_kind": delivery_package.package_kind,
        "tool_name": delivery_package.tool_name,
        "artifact_kind": delivery_package.artifact_kind,
        "customer_deliverable_name": delivery_package.customer_deliverable_name,
        "source_artifact_name": delivery_package.source_artifact_name,
        "test_artifact_name": delivery_package.test_artifact_name,
        "integration_instructions_name": (
            delivery_package.integration_instructions_name
        ),
        "secrets_template_name": delivery_package.secrets_template_name,
        "local_validation_name": delivery_package.local_validation_name,
        "manifest_name": delivery_package.manifest_name,
        "customer_files": list(delivery_package.customer_files),
        "source_artifact_present": delivery_package.source_artifact_present,
        "tests_present": delivery_package.tests_present,
        "integration_instructions_present": (
            delivery_package.integration_instructions_present
        ),
        "secrets_template_present": delivery_package.secrets_template_present,
        "local_validation_present": delivery_package.local_validation_present,
        "delivery_package_present": delivery_package.delivery_package_present,
        "internal_registry_metadata_included": (
            delivery_package.internal_registry_metadata_included
        ),
        "rate_limit_guidance_status": (
            delivery_package.rate_limit_guidance_status
        ),
        "rate_limit_guidance": delivery_package.rate_limit_guidance,
        "rate_limit_evidence_ref": delivery_package.rate_limit_evidence_ref,
        "scope_guidance_status": delivery_package.scope_guidance_status,
        "scope_guidance": delivery_package.scope_guidance,
        "scope_evidence_ref": delivery_package.scope_evidence_ref,
        "telemetry_guidance_status": delivery_package.telemetry_guidance_status,
        "telemetry_guidance": delivery_package.telemetry_guidance,
        "telemetry_evidence_ref": delivery_package.telemetry_evidence_ref,
        "raw_payload_retained": delivery_package.raw_payload_retained,
        "customer_secret_retained": delivery_package.customer_secret_retained,
        "customer_private_payload_retained": (
            delivery_package.customer_private_payload_retained
        ),
    }


def custom_tool_reusable_registry_path(repo_root: Path) -> Path:
    """Return the sanitized internal custom-tool reusable registry path."""
    return repo_root / CUSTOM_TOOL_REGISTRY_RELATIVE_PATH


def store_custom_tool_reusable_registry_records(
    *,
    storage_path: Path,
    registry_records: tuple[CustomToolReusableRegistryRecord, ...],
    relative_path: str | None = None,
) -> CustomToolRegistryStorageReport:
    """Store sanitized reusable custom-tool records without raw customer.

    material.

    Returns:
        The write summary.

    Raises:
        CustomToolProductError: If storage would retain raw customer material.
        OSError: If the storage payload cannot be fully written.
    """
    if not registry_records:
        message = (
            "Custom tool registry storage requires at least one reusablerecord."
        )
        raise CustomToolProductError(message)
    _reject_linked_storage_path(storage_path)
    existing_records = (
        load_custom_tool_reusable_registry_records(storage_path)
        if storage_path.exists()
        else ()
    )
    merged_records = _merge_registry_records(
        existing_records=existing_records,
        registry_records=registry_records,
    )
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_linked_storage_path(storage_path)
    payload = _registry_storage_payload(merged_records)
    payload_bytes = _canonical_json_bytes(payload)
    written_bytes = storage_path.write_bytes(payload_bytes)
    if written_bytes != len(payload_bytes):
        message = (
            f"Could not write full custom tool registry payload to"
            f"{storage_path}."
        )
        raise OSError(message)
    return _registry_storage_report(
        relative_path=relative_path or storage_path.as_posix(),
        records=merged_records,
    )


def load_custom_tool_reusable_registry_records(
    storage_path: Path,
) -> tuple[CustomToolReusableRegistryRecord, ...]:
    """Load sanitized reusable custom-tool records from disk.

    Returns:
        The sanitized reusable custom-tool registry records.

    Raises:
        ValueError: If storage metadata is unsupported.
    """
    payload = _load_json_object(storage_path)
    schema_version = _required_int(payload, "schema_version")
    if schema_version != CUSTOM_TOOL_REGISTRY_SCHEMA_VERSION:
        message = (
            f"Unsupported custom tool registry schema version: {schema_version}"
        )
        raise ValueError(message)
    kind = _required_text(payload, "kind")
    if kind != CUSTOM_TOOL_REGISTRY_STORAGE_KIND:
        message = f"Unsupported custom tool registry storage kind: {kind}"
        raise ValueError(message)
    _require_registry_storage_flags(payload)
    return tuple(
        _registry_record_from_payload(record)
        for record in _object_sequence(payload)
    )


def _delivery_package_file_payloads(
    *,
    request: CustomToolDeliveryPackageRequest,
    delivery_package: CustomToolDeliveryPackage,
) -> tuple[tuple[str, str], ...]:
    manifest_text = json.dumps(
        custom_tool_delivery_manifest_as_dict(delivery_package),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    return (
        (
            delivery_package.source_artifact_name,
            request.source_artifact_text.strip() + "\n",
        ),
        (
            f"tests/{delivery_package.test_artifact_name}",
            request.test_artifact_text.strip() + "\n",
        ),
        (
            CUSTOM_TOOL_INTEGRATION_INSTRUCTIONS_NAME,
            request.integration_instructions.strip() + "\n",
        ),
        (
            CUSTOM_TOOL_SECRETS_TEMPLATE_NAME,
            _secrets_template_text(request.secret_placeholders),
        ),
        (
            CUSTOM_TOOL_LOCAL_VALIDATION_NAME,
            request.local_validation_command.strip() + "\n",
        ),
        (CUSTOM_TOOL_DELIVERY_MANIFEST_NAME, manifest_text + "\n"),
    )


def _secrets_template_text(secret_placeholders: tuple[str, ...]) -> str:
    placeholders = _safe_secret_placeholders(secret_placeholders)
    return "".join(
        f"{placeholder}=<provide-value>\n" for placeholder in placeholders
    )


def _require_delivery_contract_matches_registry(
    request: CustomToolDeliveryPackageRequest,
) -> None:
    contract = request.product_contract
    registry_record = request.reusable_registry_record
    if not contract.customer_receives_artifact:
        message = "Custom tool delivery requires a purchased customer artifact."
        raise CustomToolProductError(message)
    if contract.tool_name != registry_record.tool_name:
        message = (
            "Custom tool delivery contract and registry record names differ."
        )
        raise CustomToolProductError(message)
    if contract.artifact_kind != registry_record.artifact_kind:
        message = (
            "Custom tool delivery contract and registry record kinds differ."
        )
        raise CustomToolProductError(message)
    if (
        registry_record.customer_secret_retained
        or registry_record.customer_private_payload_retained
    ):
        message = "Custom tool delivery cannot package unsafe registry records."
        raise CustomToolProductError(message)


def _optional_guidance(
    guidance: CustomToolGuidance | None,
) -> CustomToolGuidance | None:
    if guidance is None:
        return None
    return CustomToolGuidance(
        guidance_text=_safe_document_text(
            guidance.guidance_text, field_name="guidance_text"
        ),
        evidence_ref=_safe_text(
            guidance.evidence_ref, field_name="guidance_evidence_ref"
        ),
    )


def _guidance_status(
    guidance: CustomToolGuidance | None,
) -> CustomToolGuidanceStatus:
    if guidance is None:
        return "omitted_no_evidence"
    return "included_with_evidence"


def _guidance_text(guidance: CustomToolGuidance | None) -> str | None:
    if guidance is None:
        return None
    return guidance.guidance_text


def _guidance_evidence_ref(guidance: CustomToolGuidance | None) -> str | None:
    if guidance is None:
        return None
    return guidance.evidence_ref


def _merge_registry_records(
    *,
    existing_records: tuple[CustomToolReusableRegistryRecord, ...],
    registry_records: tuple[CustomToolReusableRegistryRecord, ...],
) -> tuple[CustomToolReusableRegistryRecord, ...]:
    merged: dict[tuple[str, str], CustomToolReusableRegistryRecord] = {}
    for record in (*existing_records, *registry_records):
        _require_storable_registry_record(record)
        merged[record.artifact_kind, record.pattern_id] = record
    return tuple(
        merged[key]
        for key in sorted(
            merged,
            key=lambda item: (item[0], item[1].casefold()),
        )
    )


def _registry_storage_payload(
    records: tuple[CustomToolReusableRegistryRecord, ...],
) -> JsonObject:
    return {
        "schema_version": CUSTOM_TOOL_REGISTRY_SCHEMA_VERSION,
        "kind": CUSTOM_TOOL_REGISTRY_STORAGE_KIND,
        "raw_payloads_retained": False,
        "customer_secrets_retained": False,
        "customer_private_payloads_retained": False,
        "sanitizer_version": CUSTOM_TOOL_SANITIZER_VERSION,
        "records": [_registry_record_payload(record) for record in records],
    }


def _registry_record_payload(
    record: CustomToolReusableRegistryRecord,
) -> JsonObject:
    _require_storable_registry_record(record)
    return {
        "registry_kind": record.registry_kind,
        "artifact_kind": record.artifact_kind,
        "pattern_id": record.pattern_id,
        "tool_name": record.tool_name,
        "reusable_pattern_summary": record.reusable_pattern_summary,
        "sanitized_input_fields": list(record.sanitized_input_fields),
        "sanitized_output_fields": list(record.sanitized_output_fields),
        "reusable_scope": record.reusable_scope,
        "source_refs": list(record.source_refs),
        "source_hash": record.source_hash,
        "sanitizer_version": record.sanitizer_version,
        "raw_payload_retained": record.raw_payload_retained,
        "customer_secret_retained": record.customer_secret_retained,
        "customer_private_payload_retained": (
            record.customer_private_payload_retained
        ),
    }


def _registry_record_from_payload(
    payload: JsonObject,
) -> CustomToolReusableRegistryRecord:
    record = CustomToolReusableRegistryRecord(
        registry_kind=_registry_kind_from_payload(payload),
        artifact_kind=_artifact_kind_from_payload(payload),
        pattern_id=_required_text(payload, "pattern_id"),
        tool_name=_required_text(payload, "tool_name"),
        reusable_pattern_summary=_required_text(
            payload, "reusable_pattern_summary"
        ),
        sanitized_input_fields=_text_tuple(payload, "sanitized_input_fields"),
        sanitized_output_fields=_text_tuple(payload, "sanitized_output_fields"),
        reusable_scope=_reusable_scope_from_payload(payload),
        source_refs=_text_tuple(payload, "source_refs"),
        source_hash=_required_text(payload, "source_hash"),
        sanitizer_version=_required_text(payload, "sanitizer_version"),
        raw_payload_retained=_required_bool(payload, "raw_payload_retained"),
        customer_secret_retained=_required_bool(
            payload, "customer_secret_retained"
        ),
        customer_private_payload_retained=_required_bool(
            payload,
            "customer_private_payload_retained",
        ),
    )
    _require_storable_registry_record(record)
    return record


def _registry_storage_report(
    *,
    relative_path: str,
    records: tuple[CustomToolReusableRegistryRecord, ...],
) -> CustomToolRegistryStorageReport:
    return CustomToolRegistryStorageReport(
        relative_path=relative_path,
        record_count=len(records),
        raw_payloads_written=False,
        customer_secrets_written=False,
        customer_private_payloads_written=False,
        reusable_scope=CUSTOM_TOOL_REUSABLE_SCOPE,
    )


def _require_storable_registry_record(
    record: CustomToolReusableRegistryRecord,
) -> None:
    if record.registry_kind != CUSTOM_TOOL_REGISTRY_KIND:
        message = "Custom tool registry received an unsupported record kind."
        raise CustomToolProductError(message)
    _require_artifact_kind(record.artifact_kind)
    if record.reusable_scope != CUSTOM_TOOL_REUSABLE_SCOPE:
        message = (
            "Custom tool registry only accepts internal reusable patterns."
        )
        raise CustomToolProductError(message)
    if record.sanitizer_version != CUSTOM_TOOL_SANITIZER_VERSION:
        message = (
            "Custom tool registry received an unsupported sanitizer version."
        )
        raise CustomToolProductError(message)
    if (
        record.raw_payload_retained
        or record.customer_secret_retained
        or record.customer_private_payload_retained
    ):
        message = (
            "Custom tool registry cannot retain customer secrets or raw "
            "payloads."
        )
        raise CustomToolProductError(message)


def _require_registry_storage_flags(payload: JsonObject) -> None:
    if (
        _required_bool(payload, "raw_payloads_retained")
        or _required_bool(payload, "customer_secrets_retained")
        or _required_bool(payload, "customer_private_payloads_retained")
    ):
        message = (
            "Custom tool registry storage must not retain customer private "
            "material."
        )
        raise CustomToolProductError(message)


def _require_artifact_kind(artifact_kind: str) -> None:
    if artifact_kind not in CUSTOM_TOOL_ARTIFACT_KINDS:
        message = f"Unsupported custom tool artifact kind: {artifact_kind}"
        raise CustomToolProductError(message)


def _registry_kind_from_payload(payload: JsonObject) -> CustomToolRegistryKind:
    value = _required_text(payload, "registry_kind")
    if value != CUSTOM_TOOL_REGISTRY_KIND:
        message = f"Unsupported custom tool registry kind: {value}"
        raise CustomToolProductError(message)
    return value


def _artifact_kind_from_payload(payload: JsonObject) -> CustomToolArtifactKind:
    value = _required_text(payload, "artifact_kind")
    _require_artifact_kind(value)
    return cast("CustomToolArtifactKind", value)


def _reusable_scope_from_payload(
    payload: JsonObject,
) -> CustomToolReusableScope:
    value = _required_text(payload, "reusable_scope")
    if value != CUSTOM_TOOL_REUSABLE_SCOPE:
        message = f"Unsupported custom tool reusable scope: {value}"
        raise CustomToolProductError(message)
    return value


def _safe_field_names(
    field_names: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    if not field_names:
        message = f"{field_name} requires at least one sanitized field name."
        raise CustomToolProductError(message)
    return tuple(
        _safe_identifier(value, field_name=field_name) for value in field_names
    )


def _safe_reference_tuple(
    values: tuple[str, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    if not values:
        message = f"{field_name} requires at least one reference."
        raise CustomToolProductError(message)
    return tuple(_safe_text(value, field_name=field_name) for value in values)


def _safe_secret_placeholders(placeholders: tuple[str, ...]) -> tuple[str, ...]:
    if not placeholders:
        message = (
            "Custom tool delivery requires at least one secret placeholder."
        )
        raise CustomToolProductError(message)
    safe_placeholders: list[str] = []
    for placeholder in placeholders:
        text = placeholder.strip()
        if not SAFE_PLACEHOLDER_PATTERN.fullmatch(text):
            message = "Secret placeholders must be uppercase names, not values."
            raise CustomToolProductError(message)
        safe_placeholders.append(text)
    return tuple(safe_placeholders)


def _safe_identifier(value: str, *, field_name: str) -> str:
    text = _safe_text(value, field_name=field_name)
    if not SAFE_IDENTIFIER_PATTERN.fullmatch(text):
        message = f"{field_name} is not a safe custom tool identifier."
        raise CustomToolProductError(message)
    return text


def _safe_document_text(value: str, *, field_name: str) -> str:
    text = value.strip()
    if not text:
        message = f"{field_name} must not be empty."
        raise CustomToolProductError(message)
    normalized = text.casefold()
    if any(marker in normalized for marker in PRIVATE_PAYLOAD_MARKERS):
        message = f"{field_name} contains private payload text."
        raise CustomToolProductError(message)
    if any(pattern.search(text) for pattern in SECRET_VALUE_PATTERNS):
        message = f"{field_name} contains secret-like values."
        raise CustomToolProductError(message)
    if any(marker in text for marker in PRIVATE_EXAMPLE_MARKERS):
        message = f"{field_name} contains private example material."
        raise CustomToolProductError(message)
    return text


def _safe_text(value: str, *, field_name: str) -> str:
    text = value.strip()
    if not text:
        message = f"{field_name} must not be empty."
        raise CustomToolProductError(message)
    normalized = text.casefold()
    if any(marker in normalized for marker in SECRET_TEXT_MARKERS):
        message = f"{field_name} contains secret-like text."
        raise CustomToolProductError(message)
    if any(marker in normalized for marker in PRIVATE_PAYLOAD_MARKERS):
        message = f"{field_name} contains private payload text."
        raise CustomToolProductError(message)
    if any(marker in text for marker in PRIVATE_EXAMPLE_MARKERS):
        message = f"{field_name} contains private example material."
        raise CustomToolProductError(message)
    return text


def _source_hash(payload: JsonObject) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _canonical_json_bytes(payload: JsonObject) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _load_json_object(path: Path) -> JsonObject:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        message = f"{path} must contain a JSON object."
        raise TypeError(message)
    return {
        str(item_key): item_value
        for item_key, item_value in cast(
            "Mapping[object, object]", payload
        ).items()
    }


def _object_sequence(payload: JsonObject) -> tuple[JsonObject, ...]:
    value = payload.get("records")
    if not isinstance(value, list):
        message = "Custom tool registry records must be a list."
        raise TypeError(message)
    records: list[JsonObject] = []
    for item in cast("Sequence[object]", value):
        if not isinstance(item, dict):
            message = "Custom tool registry records must contain only objects."
            raise TypeError(message)
        records.append(
            {
                str(item_key): item_value
                for item_key, item_value in cast(
                    "Mapping[object, object]", item
                ).items()
            }
        )
    return tuple(records)


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Custom tool registry member {key!r} must be non-empty text."
        raise ValueError(message)
    return value


def _required_int(payload: JsonObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Custom tool registry member {key!r} must be an integer."
        raise TypeError(message)
    return value


def _required_bool(payload: JsonObject, key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        message = f"Custom tool registry member {key!r} must be a boolean."
        raise TypeError(message)
    return value


def _text_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Custom tool registry member {key!r} must be a text list."
        raise TypeError(message)
    items: list[str] = []
    for item in cast("Sequence[object]", value):
        if not isinstance(item, str) or not item.strip():
            message = (
                f"Custom tool registry member {key!r} must be a non-empty text "
                f"list."
            )
            raise ValueError(message)
        items.append(item)
    return tuple(items)


def _reject_linked_storage_path(path: Path) -> None:
    """Reject existing symlink or junction components before storage writes.

    Raises:
        CustomToolProductError: If the storage path crosses a filesystem link.
    """
    for candidate in _existing_storage_path_components(path):
        if _path_is_filesystem_link(candidate):
            message = (
                f"Custom tool registry storage path uses a symlink or junction:"
                f"{path}"
            )
            raise CustomToolProductError(message)


def _existing_storage_path_components(path: Path) -> tuple[Path, ...]:
    """Return existing path components that would be traversed by a write."""
    candidates: list[Path] = []
    current = path
    while True:
        if current.exists() or current.is_symlink():
            candidates.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return tuple(reversed(candidates))


def _path_is_filesystem_link(path: Path) -> bool:
    """Return whether one path is a symlink or Windows reparse-point link."""
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        mode = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return bool(
        getattr(mode, "st_file_attributes", 0)
        & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )
