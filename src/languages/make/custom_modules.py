# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# - 001069#repo.make-source-material.legal-use-boundary
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Customer-safe Make custom module and custom tool intake records.

Boundary contract:
- Owns: sanitized, local-only custom module intake facts and promotion policy.
- Must not: store raw customer payloads, credentials, account IDs, or private
examples.
- Allows: provenance records, pass-through decisions, and local custom tool
specs.
- Split when: persisted engagement storage or live Make custom-app APIs are
introduced.
- Merge when: the raw-spec compiler owns the same customer-safe intake boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypedDict, cast

from catalog.fallback.results import (
    SOURCE_LABEL_CLIENT_BUSINESS_CUSTOM_MODULE,
    SOURCE_LABEL_PRIVATE_THIRD_PARTY_OR_CUSTOMER_PRIVATE_MODULE,
    SOURCE_LABEL_PUBLIC_API_CONNECTOR_CANDIDATE,
    catalog_source_rank,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

type CustomModuleClassification = Literal[
    "public_api_connector_candidate ",
    "client_business_custom_module ",
    "private_third_party_or_customer_private_module",
]
type CustomModuleDeletionStatus = Literal[
    "not_applicable_public_source ",
    "raw_deleted_after_sanitization ",
    "raw_not_accepted",
]
type CustomModuleRetentionBehavior = Literal[
    "sanitized_public_candidate_only ",
    "engagement_local_sanitized_facts_only ",
    "pass_through_only",
]
type CustomModuleRedactionStatus = Literal[
    "sanitized_functional_facts_only ",
    "pass_through_metadata_only",
]
type CustomModuleRetentionScope = Literal[
    "shared_catalog_candidate ",
    "engagement_local ",
    "pass_through_only",
]
type CustomToolSpecStatus = Literal["ready", "pass_through_only"]
type JsonObject = dict[str, object]

CUSTOM_MODULE_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    (
        "public_api_connector_candidate ",
        "client_business_custom_module ",
        "private_third_party_or_customer_private_module",
    )
)
CUSTOM_MODULE_SOURCE_LABELS: Final[dict[CustomModuleClassification, str]] = {
    "public_api_connector_candidate": (
        SOURCE_LABEL_PUBLIC_API_CONNECTOR_CANDIDATE
    ),
    "client_business_custom_module": SOURCE_LABEL_CLIENT_BUSINESS_CUSTOM_MODULE,
    "private_third_party_or_customer_private_module": (
        SOURCE_LABEL_PRIVATE_THIRD_PARTY_OR_CUSTOMER_PRIVATE_MODULE
    ),
}
CUSTOM_MODULE_SHARED_CATALOG_CLASSIFICATION: Final = (
    "public_api_connector_candidate"
)
CUSTOM_MODULE_LOCAL_ONLY_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    (
        "client_business_custom_module ",
        "private_third_party_or_customer_private_module",
    )
)
CUSTOM_MODULE_RAW_INTAKE_PATH: Final = (
    "src/languages/make/client_raw_module_specs/"
)
CUSTOM_MODULE_SANITIZED_INTAKE_RELATIVE_PATH: Final = (
    "src/languages/make/client_raw_module_specs/sanitized/custom_modules.json"
)
CUSTOM_MODULE_STORAGE_SCHEMA_VERSION: Final = 1
CUSTOM_MODULE_STORAGE_KIND: Final = "make_custom_module_sanitized_intake"
CUSTOM_MODULE_SANITIZER_VERSION: Final = "custom-module-sanitizer-v1"
SAFE_IDENTIFIER_PATTERN: Final = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$"
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
        "private payload ",
        "secret ",
        "token",
    )
)
PRIVATE_EXAMPLE_MARKERS: Final = frozenset(("@", "http://", "https://"))


class CustomModuleIntakeError(ValueError):
    """Raised when custom module intake would cross the safe evidence.

    boundary.
    """


class CustomModuleAuthorization(NamedTuple):
    """Authorization metadata required before sanitized custom module facts are.

    accepted.
    """

    authorized: bool
    authorization_ref: str
    shared_catalog_promotion_approved: bool = False
    delete_after_processing: bool = True


class CustomModuleIntakeRequest(NamedTuple):
    """One custom module intake request before sanitization."""

    classification: CustomModuleClassification
    app_slug: str
    app_version: str
    internal_name: str
    display_name: str
    field_names: tuple[str, ...]
    authorization: CustomModuleAuthorization
    evidence_refs: tuple[str, ...]


class CustomModuleIntakeRecord(NamedTuple):
    """One sanitized Make custom module intake record."""

    classification: CustomModuleClassification
    module_token: str
    catalog_module_id: str
    app_slug: str
    app_version: str
    internal_name: str
    display_name: str
    sanitized_field_names: tuple[str, ...]
    source_label: str
    source_rank: int
    authorization_ref: str
    retention_behavior: CustomModuleRetentionBehavior
    deletion_status: CustomModuleDeletionStatus
    raw_payload_retained: bool
    shared_catalog_eligible: bool
    provenance: tuple[str, ...]
    pass_through_reason: str | None
    redaction_status: CustomModuleRedactionStatus
    sanitizer_version: str
    source_hash: str
    retention_scope: CustomModuleRetentionScope


class CustomModuleStorageReport(NamedTuple):
    """Summary of one sanitized custom module storage write."""

    relative_path: str
    record_count: int
    raw_payloads_written: bool
    shared_catalog_records: int
    engagement_local_records: int
    pass_through_records: int


class CustomToolCreatorWorkflowReport(NamedTuple):
    """Summary of one local customer-safe custom tool creator run."""

    specs: tuple[CustomToolSpec, ...]
    pass_through_reports: tuple[dict[str, object], ...]
    storage_report: CustomModuleStorageReport | None
    provider_api_call: bool
    live_make_called: bool
    credentials_required: bool
    shared_catalog_promotions: int
    engagement_local_specs: int
    pass_through_specs: int


class CustomToolSpec(TypedDict):
    """JSON-ready local custom tool spec derived from sanitized custom module.

    evidence.
    """

    status: CustomToolSpecStatus
    tool_name: str
    description: str
    module_token: str
    catalog_module_id: str | None
    scope: str
    source_label: str
    source_rank: int
    shared_catalog_eligible: bool
    fields: tuple[str, ...]
    provider_api_call: bool
    live_make_called: bool
    credentials_required: bool
    pass_through_reason: str | None


def build_custom_module_intake_record(
    request: CustomModuleIntakeRequest,
) -> CustomModuleIntakeRecord:
    """Return a sanitized custom module intake record.

    Returns:
        The sanitized custom module intake record.

    Raises:
        CustomModuleIntakeError: If evidence is unauthorized or unsafe to
        retain.
    """
    _require_classification(request.classification)
    if not request.authorization.authorized:
        message = "Custom module evidence requires explicit authorization."
        raise CustomModuleIntakeError(message)
    authorization_ref = _safe_text(
        request.authorization.authorization_ref,
        field_name="authorization_ref",
    )
    safe_app_slug = _safe_identifier(request.app_slug, field_name="app_slug")
    safe_app_version = _safe_identifier(
        request.app_version, field_name="app_version"
    )
    safe_internal_name = _safe_identifier(
        request.internal_name, field_name="internal_name"
    )
    safe_display_name = _safe_text(
        request.display_name, field_name="display_name"
    )
    safe_fields = _safe_field_names(request.field_names)
    provenance = _safe_provenance(request.evidence_refs)
    source_label = CUSTOM_MODULE_SOURCE_LABELS[request.classification]
    shared_catalog_eligible = (
        request.classification == CUSTOM_MODULE_SHARED_CATALOG_CLASSIFICATION
        and request.authorization.shared_catalog_promotion_approved
    )
    pass_through_reason = (
        None
        if shared_catalog_eligible
        or request.classification == "client_business_custom_module"
        else "private_custom_module_evidence_is_not_reusable_catalog_truth"
    )
    source_hash = _source_hash(
        {
            "classification": request.classification,
            "app_slug": safe_app_slug,
            "app_version": safe_app_version,
            "internal_name": safe_internal_name,
            "display_name": safe_display_name,
            "sanitized_field_names": list(safe_fields),
            "authorization_ref": authorization_ref,
            "provenance": list(provenance),
            "sanitizer_version": CUSTOM_MODULE_SANITIZER_VERSION,
        }
    )
    return CustomModuleIntakeRecord(
        classification=request.classification,
        module_token=f"{safe_app_slug}:{safe_internal_name}",
        catalog_module_id=(
            f"module:{safe_app_slug}:{safe_app_version}:custom:{safe_internal_name}"
        ),
        app_slug=safe_app_slug,
        app_version=safe_app_version,
        internal_name=safe_internal_name,
        display_name=safe_display_name,
        sanitized_field_names=safe_fields,
        source_label=source_label,
        source_rank=catalog_source_rank(source_label),
        authorization_ref=authorization_ref,
        retention_behavior=_retention_behavior(request.classification),
        deletion_status=_deletion_status(
            classification=request.classification,
            delete_after_processing=request.authorization.delete_after_processing,
        ),
        raw_payload_retained=False,
        shared_catalog_eligible=shared_catalog_eligible,
        provenance=provenance,
        pass_through_reason=pass_through_reason,
        redaction_status=_redaction_status(request.classification),
        sanitizer_version=CUSTOM_MODULE_SANITIZER_VERSION,
        source_hash=source_hash,
        retention_scope=_retention_scope(
            classification=request.classification,
            shared_catalog_eligible=shared_catalog_eligible,
        ),
    )


def custom_module_intake_storage_path(repo_root: Path) -> Path:
    """Return the local sanitized custom module intake storage path."""
    return repo_root / CUSTOM_MODULE_SANITIZED_INTAKE_RELATIVE_PATH


def store_custom_module_intake_record(
    *,
    repo_root: Path,
    intake_record: CustomModuleIntakeRecord,
) -> CustomModuleStorageReport:
    """Store one sanitized custom module record in the approved local intake.

    path.

    Returns:
        The write summary.
    """
    return store_custom_module_intake_records(
        storage_path=custom_module_intake_storage_path(repo_root),
        intake_records=(intake_record,),
        relative_path=CUSTOM_MODULE_SANITIZED_INTAKE_RELATIVE_PATH,
    )


def store_custom_module_intake_records(
    *,
    storage_path: Path,
    intake_records: tuple[CustomModuleIntakeRecord, ...],
    relative_path: str | None = None,
) -> CustomModuleStorageReport:
    """Store sanitized custom module records without retaining raw payload.

    material.

    Returns:
        The write summary.

    Raises:
        CustomModuleIntakeError: If a record would retain raw payload material.
        OSError: If the storage payload cannot be fully written.
    """
    if not intake_records:
        message = (
            "Custom module storage requires at least one sanitized intake "
            "record."
        )
        raise CustomModuleIntakeError(message)
    _reject_linked_storage_path(storage_path)
    existing_records = (
        load_custom_module_intake_records(storage_path)
        if storage_path.exists()
        else ()
    )
    merged_records = _merge_custom_module_records(
        existing_records=existing_records,
        intake_records=intake_records,
    )
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_linked_storage_path(storage_path)
    payload = _storage_payload(merged_records)
    payload_bytes = _canonical_json_bytes(payload)
    written_bytes = storage_path.write_bytes(payload_bytes)
    if written_bytes != len(payload_bytes):
        message = (
            f"Could not write full custom module storage payload to"
            f"{storage_path}."
        )
        raise OSError(message)
    return _storage_report(
        relative_path=relative_path or storage_path.as_posix(),
        records=merged_records,
    )


def load_custom_module_intake_records(
    storage_path: Path,
) -> tuple[CustomModuleIntakeRecord, ...]:
    """Load sanitized custom module intake records from disk.

    Returns:
        The sanitized custom module intake records.

    Raises:
        CustomModuleIntakeError: If storage declares retained raw payloads.
        ValueError: If storage metadata is unsupported.
    """
    payload = _load_json_object(storage_path)
    schema_version = _required_int(payload, "schema_version")
    if schema_version != CUSTOM_MODULE_STORAGE_SCHEMA_VERSION:
        message = (
            f"Unsupported custom module storage schema version:{schema_version}"
        )
        raise ValueError(message)
    kind = _required_text(payload, "kind")
    if kind != CUSTOM_MODULE_STORAGE_KIND:
        message = f"Unsupported custom module storage kind: {kind}"
        raise ValueError(message)
    if _required_bool(payload, "raw_payloads_retained"):
        message = "Custom module storage must not retain raw payloads."
        raise CustomModuleIntakeError(message)
    return tuple(
        _record_from_payload(record)
        for record in _object_sequence(payload, "records")
    )


def create_customer_safe_custom_tool_specs(
    *,
    intake_requests: tuple[CustomModuleIntakeRequest, ...],
    unknown_module_tokens: tuple[str, ...] = (),
    storage_path: Path | None = None,
) -> CustomToolCreatorWorkflowReport:
    """Create local custom tool specs from sanitized, authorized custom module.

    evidence.

    Returns:
        The local workflow report.
    """
    records = tuple(
        build_custom_module_intake_record(request)
        for request in intake_requests
    )
    specs = tuple(
        build_customer_safe_custom_tool_spec(
            intake_record=record,
            tool_name=record.internal_name,
            description=_custom_tool_description(record),
        )
        for record in records
    )
    pass_through_reports = _custom_tool_pass_through_reports(
        records=records,
        unknown_module_tokens=unknown_module_tokens,
    )
    storage_report = (
        store_custom_module_intake_records(
            storage_path=storage_path,
            intake_records=records,
        )
        if storage_path is not None and records
        else None
    )
    return CustomToolCreatorWorkflowReport(
        specs=specs,
        pass_through_reports=pass_through_reports,
        storage_report=storage_report,
        provider_api_call=False,
        live_make_called=False,
        credentials_required=False,
        shared_catalog_promotions=sum(
            1 for spec in specs if spec["scope"] == "shared_catalog_candidate"
        ),
        engagement_local_specs=sum(
            1 for spec in specs if spec["scope"] == "engagement_local"
        ),
        pass_through_specs=sum(
            1 for spec in specs if spec["status"] == "pass_through_only"
        ),
    )


def custom_module_pass_through_report(
    *,
    module_token: str,
    intake_record: CustomModuleIntakeRecord | None = None,
) -> dict[str, object]:
    """Return a JSON-ready pass-through or promotion report for one custom.

    module.
    """
    safe_module_token = _safe_module_token(module_token)
    if intake_record is None:
        return {
            "status": "pass_through_only",
            "module_token": safe_module_token,
            "source_label": None,
            "source_rank": None,
            "shared_catalog_eligible": False,
            "reason": "custom_module_evidence_missing",
        }
    if intake_record.shared_catalog_eligible:
        return {
            "status": "catalog_candidate",
            "module_token": safe_module_token,
            "catalog_module_id": intake_record.catalog_module_id,
            "source_label": intake_record.source_label,
            "source_rank": intake_record.source_rank,
            "shared_catalog_eligible": True,
            "reason": None,
        }
    return {
        "status": "pass_through_only",
        "module_token": safe_module_token,
        "catalog_module_id": intake_record.catalog_module_id,
        "source_label": intake_record.source_label,
        "source_rank": intake_record.source_rank,
        "shared_catalog_eligible": False,
        "reason": intake_record.pass_through_reason
        or "custom_module_is_engagement_local_only",
    }


def build_customer_safe_custom_tool_spec(
    *,
    intake_record: CustomModuleIntakeRecord,
    tool_name: str,
    description: str,
) -> CustomToolSpec:
    """Build a local-only custom tool spec from sanitized custom module.

    evidence.

    Returns:
        A JSON-ready local custom tool spec.
    """
    safe_tool_name = _safe_identifier(tool_name, field_name="tool_name")
    safe_description = _safe_text(description, field_name="description")
    if (
        intake_record.classification
        == "private_third_party_or_customer_private_module"
    ):
        return {
            "status": "pass_through_only",
            "tool_name": safe_tool_name,
            "description": safe_description,
            "module_token": intake_record.module_token,
            "catalog_module_id": None,
            "scope": "pass_through_only",
            "source_label": intake_record.source_label,
            "source_rank": intake_record.source_rank,
            "shared_catalog_eligible": False,
            "fields": (),
            "provider_api_call": False,
            "live_make_called": False,
            "credentials_required": False,
            "pass_through_reason": intake_record.pass_through_reason,
        }
    return {
        "status": "ready",
        "tool_name": safe_tool_name,
        "description": safe_description,
        "module_token": intake_record.module_token,
        "catalog_module_id": intake_record.catalog_module_id,
        "scope": (
            "shared_catalog_candidate"
            if intake_record.shared_catalog_eligible
            else "engagement_local"
        ),
        "source_label": intake_record.source_label,
        "source_rank": intake_record.source_rank,
        "shared_catalog_eligible": intake_record.shared_catalog_eligible,
        "fields": intake_record.sanitized_field_names,
        "provider_api_call": False,
        "live_make_called": False,
        "credentials_required": False,
        "pass_through_reason": None,
    }


def _custom_tool_description(record: CustomModuleIntakeRecord) -> str:
    return f"Local custom tool for {record.display_name}."


def _custom_tool_pass_through_reports(
    *,
    records: tuple[CustomModuleIntakeRecord, ...],
    unknown_module_tokens: tuple[str, ...],
) -> tuple[dict[str, object], ...]:
    record_reports = tuple(
        custom_module_pass_through_report(
            module_token=record.module_token,
            intake_record=record,
        )
        for record in records
        if record.pass_through_reason is not None
    )
    unknown_reports = tuple(
        custom_module_pass_through_report(module_token=module_token)
        for module_token in unknown_module_tokens
    )
    return (*record_reports, *unknown_reports)


def _require_classification(classification: CustomModuleClassification) -> None:
    if classification not in CUSTOM_MODULE_CLASSIFICATIONS:
        message = f"Unsupported custom module classification: {classification}"
        raise CustomModuleIntakeError(message)


def _retention_behavior(
    classification: CustomModuleClassification,
) -> CustomModuleRetentionBehavior:
    if classification == "public_api_connector_candidate":
        return "sanitized_public_candidate_only"
    if classification == "client_business_custom_module":
        return "engagement_local_sanitized_facts_only"
    return "pass_through_only"


def _deletion_status(
    *,
    classification: CustomModuleClassification,
    delete_after_processing: bool,
) -> CustomModuleDeletionStatus:
    if classification == "public_api_connector_candidate":
        return "not_applicable_public_source"
    if delete_after_processing:
        return "raw_deleted_after_sanitization"
    return "raw_not_accepted"


def _redaction_status(
    classification: CustomModuleClassification,
) -> CustomModuleRedactionStatus:
    if classification == "private_third_party_or_customer_private_module":
        return "pass_through_metadata_only"
    return "sanitized_functional_facts_only"


def _retention_scope(
    *,
    classification: CustomModuleClassification,
    shared_catalog_eligible: bool,
) -> CustomModuleRetentionScope:
    if classification == "private_third_party_or_customer_private_module":
        return "pass_through_only"
    if shared_catalog_eligible:
        return "shared_catalog_candidate"
    return "engagement_local"


def _merge_custom_module_records(
    *,
    existing_records: tuple[CustomModuleIntakeRecord, ...],
    intake_records: tuple[CustomModuleIntakeRecord, ...],
) -> tuple[CustomModuleIntakeRecord, ...]:
    merged: dict[tuple[str, str, str], CustomModuleIntakeRecord] = {}
    for record in (*existing_records, *intake_records):
        _require_storable_record(record)
        key = (
            record.classification,
            record.module_token,
            record.authorization_ref,
        )
        merged[key] = record
    return tuple(
        merged[key]
        for key in sorted(
            merged,
            key=lambda item: (item[0], item[1].casefold(), item[2].casefold()),
        )
    )


def _require_storable_record(record: CustomModuleIntakeRecord) -> None:
    if record.raw_payload_retained:
        message = (
            "Raw custom module payloads cannot be written to sanitized storage."
        )
        raise CustomModuleIntakeError(message)
    if record.sanitizer_version != CUSTOM_MODULE_SANITIZER_VERSION:
        message = (
            "Custom module storage received an unsupported sanitizer version."
        )
        raise CustomModuleIntakeError(message)
    if (
        record.classification != CUSTOM_MODULE_SHARED_CATALOG_CLASSIFICATION
        and record.shared_catalog_eligible
    ):
        message = (
            "Only public API connector candidates can enter shared catalog "
            "storage."
        )
        raise CustomModuleIntakeError(message)


def _storage_payload(
    records: tuple[CustomModuleIntakeRecord, ...],
) -> JsonObject:
    return {
        "schema_version": CUSTOM_MODULE_STORAGE_SCHEMA_VERSION,
        "kind": CUSTOM_MODULE_STORAGE_KIND,
        "raw_intake_path": CUSTOM_MODULE_RAW_INTAKE_PATH,
        "raw_payloads_retained": False,
        "sanitizer_version": CUSTOM_MODULE_SANITIZER_VERSION,
        "records": [_record_payload(record) for record in records],
    }


def _record_payload(record: CustomModuleIntakeRecord) -> JsonObject:
    _require_storable_record(record)
    return {
        "classification": record.classification,
        "module_token": record.module_token,
        "catalog_module_id": record.catalog_module_id,
        "app_slug": record.app_slug,
        "app_version": record.app_version,
        "internal_name": record.internal_name,
        "display_name": record.display_name,
        "sanitized_field_names": list(record.sanitized_field_names),
        "source_label": record.source_label,
        "source_rank": record.source_rank,
        "authorization_ref": record.authorization_ref,
        "retention_behavior": record.retention_behavior,
        "deletion_status": record.deletion_status,
        "raw_payload_retained": record.raw_payload_retained,
        "shared_catalog_eligible": record.shared_catalog_eligible,
        "provenance": list(record.provenance),
        "pass_through_reason": record.pass_through_reason,
        "redaction_status": record.redaction_status,
        "sanitizer_version": record.sanitizer_version,
        "source_hash": record.source_hash,
        "retention_scope": record.retention_scope,
    }


def _record_from_payload(payload: JsonObject) -> CustomModuleIntakeRecord:
    record = CustomModuleIntakeRecord(
        classification=_classification(payload),
        module_token=_required_text(payload, "module_token"),
        catalog_module_id=_required_text(payload, "catalog_module_id"),
        app_slug=_required_text(payload, "app_slug"),
        app_version=_required_text(payload, "app_version"),
        internal_name=_required_text(payload, "internal_name"),
        display_name=_required_text(payload, "display_name"),
        sanitized_field_names=_text_tuple(payload, "sanitized_field_names"),
        source_label=_required_text(payload, "source_label"),
        source_rank=_required_int(payload, "source_rank"),
        authorization_ref=_required_text(payload, "authorization_ref"),
        retention_behavior=_retention_behavior_from_payload(payload),
        deletion_status=_deletion_status_from_payload(payload),
        raw_payload_retained=_required_bool(payload, "raw_payload_retained"),
        shared_catalog_eligible=_required_bool(
            payload, "shared_catalog_eligible"
        ),
        provenance=_text_tuple(payload, "provenance"),
        pass_through_reason=_optional_text(payload, "pass_through_reason"),
        redaction_status=_redaction_status_from_payload(payload),
        sanitizer_version=_required_text(payload, "sanitizer_version"),
        source_hash=_required_text(payload, "source_hash"),
        retention_scope=_retention_scope_from_payload(payload),
    )
    _require_storable_record(record)
    return record


def _storage_report(
    *,
    relative_path: str,
    records: tuple[CustomModuleIntakeRecord, ...],
) -> CustomModuleStorageReport:
    shared_catalog_records = sum(
        1 for record in records if record.shared_catalog_eligible
    )
    engagement_local_records = sum(
        1 for record in records if record.retention_scope == "engagement_local"
    )
    pass_through_records = sum(
        1 for record in records if record.retention_scope == "pass_through_only"
    )
    return CustomModuleStorageReport(
        relative_path=relative_path,
        record_count=len(records),
        raw_payloads_written=False,
        shared_catalog_records=shared_catalog_records,
        engagement_local_records=engagement_local_records,
        pass_through_records=pass_through_records,
    )


def _canonical_json_bytes(payload: JsonObject) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _reject_linked_storage_path(path: Path) -> None:
    """Reject existing symlink or junction components before storage writes.

    Raises:
        CustomModuleIntakeError: If the storage path crosses a filesystem link.
    """
    for candidate in _existing_storage_path_components(path):
        if _path_is_filesystem_link(candidate):
            message = (
                f"Custom module storage path uses a symlink or junction: {path}"
            )
            raise CustomModuleIntakeError(message)


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


def _source_hash(payload: JsonObject) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


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


def _object_sequence(payload: JsonObject, key: str) -> tuple[JsonObject, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Custom module storage member {key!r} must be a list."
        raise TypeError(message)
    records: list[JsonObject] = []
    for item in cast("Sequence[object]", value):
        if not isinstance(item, dict):
            message = (
                f"Custom module storage member {key!r} must contain only "
                f"objects."
            )
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


def _classification(payload: JsonObject) -> CustomModuleClassification:
    value = _required_text(payload, "classification")
    if value not in CUSTOM_MODULE_CLASSIFICATIONS:
        message = f"Unsupported custom module classification: {value}"
        raise CustomModuleIntakeError(message)
    return cast("CustomModuleClassification", value)


def _retention_behavior_from_payload(
    payload: JsonObject,
) -> CustomModuleRetentionBehavior:
    value = _required_text(payload, "retention_behavior")
    if value not in {
        "sanitized_public_candidate_only ",
        "engagement_local_sanitized_facts_only ",
        "pass_through_only",
    }:
        message = f"Unsupported custom module retention behavior: {value}"
        raise CustomModuleIntakeError(message)
    return cast("CustomModuleRetentionBehavior", value)


def _deletion_status_from_payload(
    payload: JsonObject,
) -> CustomModuleDeletionStatus:
    value = _required_text(payload, "deletion_status")
    if value not in {
        "not_applicable_public_source ",
        "raw_deleted_after_sanitization ",
        "raw_not_accepted",
    }:
        message = f"Unsupported custom module deletion status: {value}"
        raise CustomModuleIntakeError(message)
    return cast("CustomModuleDeletionStatus", value)


def _redaction_status_from_payload(
    payload: JsonObject,
) -> CustomModuleRedactionStatus:
    value = _required_text(payload, "redaction_status")
    if value not in {
        "sanitized_functional_facts_only ",
        "pass_through_metadata_only",
    }:
        message = f"Unsupported custom module redaction status: {value}"
        raise CustomModuleIntakeError(message)
    return cast("CustomModuleRedactionStatus", value)


def _retention_scope_from_payload(
    payload: JsonObject,
) -> CustomModuleRetentionScope:
    value = _required_text(payload, "retention_scope")
    if value not in {
        "shared_catalog_candidate ",
        "engagement_local ",
        "pass_through_only",
    }:
        message = f"Unsupported custom module retention scope: {value}"
        raise CustomModuleIntakeError(message)
    return cast("CustomModuleRetentionScope", value)


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = (
            f"Custom module storage member {key!r} must be non-empty text."
        )
        raise ValueError(message)
    return value


def _optional_text(payload: JsonObject, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = (
            f"Custom module storage member {key!r} must be text when present."
        )
        raise TypeError(message)
    return value


def _required_int(payload: JsonObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Custom module storage member {key!r} must be an integer."
        raise TypeError(message)
    return value


def _required_bool(payload: JsonObject, key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        message = f"Custom module storage member {key!r} must be a boolean."
        raise TypeError(message)
    return value


def _text_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Custom module storage member {key!r} must be a text list."
        raise TypeError(message)
    items: list[str] = []
    for item in cast("Sequence[object]", value):
        if not isinstance(item, str) or not item.strip():
            message = (
                f"Custom module storage member {key!r} must be a non-empty "
                f"text "
                f"list."
            )
            raise ValueError(message)
        items.append(item)
    return tuple(items)


def _safe_field_names(field_names: tuple[str, ...]) -> tuple[str, ...]:
    if not field_names:
        message = "Custom module intake requires sanitized field names."
        raise CustomModuleIntakeError(message)
    return tuple(
        _safe_identifier(field_name, field_name="field_name")
        for field_name in field_names
    )


def _safe_provenance(evidence_refs: tuple[str, ...]) -> tuple[str, ...]:
    if not evidence_refs:
        message = "Custom module intake requires provenance references."
        raise CustomModuleIntakeError(message)
    return tuple(
        _safe_text(ref, field_name="evidence_ref") for ref in evidence_refs
    )


def _safe_identifier(value: str, *, field_name: str) -> str:
    text = _safe_text(value, field_name=field_name)
    if not SAFE_IDENTIFIER_PATTERN.fullmatch(text):
        message = f"{field_name} is not a safe custom module identifier."
        raise CustomModuleIntakeError(message)
    return text


def _safe_module_token(value: str) -> str:
    token = _safe_text(value, field_name="module_token")
    if ":" not in token:
        message = "module_token must preserve the Make app:module shape."
        raise CustomModuleIntakeError(message)
    return token


def _safe_text(value: str, *, field_name: str) -> str:
    text = value.strip()
    if not text:
        message = f"{field_name} must not be empty."
        raise CustomModuleIntakeError(message)
    normalized = text.casefold()
    if any(marker in normalized for marker in SECRET_TEXT_MARKERS):
        message = f"{field_name} contains secret-like or account-specific text."
        raise CustomModuleIntakeError(message)
    if any(marker in text for marker in PRIVATE_EXAMPLE_MARKERS):
        message = f"{field_name} contains private example material."
        raise CustomModuleIntakeError(message)
    return text
