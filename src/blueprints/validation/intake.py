# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.blueprint-root-contract
# - 001046#repo.blueprint-validation.validator-policy
# - 001074#repo.make-source-material.source-type-risk-matrix
# - 001075#repo.client-blueprint-intake.shape-secret-identifier-gates
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Preflight customer Make blueprint intake before local analysis.

Boundary contract:
- Owns: local preflight decisions for customer-supplied Make blueprint exports.
- Must not: run catalog validation, generate reports, call services, or persist
files.
- Allows: JSON shape checks, source hashing, secret and identifier screening,
and release gates.
- Split when: hosted upload processing or report redaction gains independent
state.
- Merge when: another module owns the same customer blueprint intake manifest.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast

from blueprints.ast.parser import normalize_json_object

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog.models import JsonObject

type ClientBlueprintArtifactType = Literal["make_blueprint_json"]
type ClientBlueprintSourceType = Literal["client_exported_scenario_json"]
type ClientBlueprintIntakeMethod = Literal[
    "email_attachment", "offline_handoff"
]
type ClientBlueprintIntakeDecision = Literal[
    "accepted_for_local_analysis",
    "manual_review_required",
    "rejected",
]
type ClientBlueprintFindingSeverity = Literal["error", "manual_review"]
type ClientBlueprintFindingClass = Literal[
    "authorization",
    "artifact_type",
    "shape",
    "size",
    "secret",
    "personal_identifier",
    "processor_boundary",
]
type ClientBlueprintShapeStatus = Literal["passed", "blocked"]
type ClientBlueprintSecretStatus = Literal["passed", "blocked"]
type ClientBlueprintPersonalDataStatus = Literal[
    "passed", "manual_review_required"
]
type ClientBlueprintRedactionStatus = Literal[
    "not_required",
    "required",
    "redacted",
    "blocked",
]
type ClientBlueprintDeletionStatus = Literal[
    "not_started",
    "completed",
    "not_applicable",
]
type ClientBlueprintEvidenceCoverageStatus = Literal["complete", "incomplete"]
type ClientBlueprintTruncationReason = Literal["not_truncated"]
type ClientBlueprintPublicBackendExposure = Literal["forbidden"]
type ClientBlueprintLocalAnalysisBoundary = Literal[
    "operator_workstation_local_only"
]

MAX_CLIENT_BLUEPRINT_BYTES: Final = 2_000_000
CLIENT_BLUEPRINT_EXTENSION: Final = ".blueprint.json"
CLIENT_BLUEPRINT_SOURCE_TYPE: Final[ClientBlueprintSourceType] = (
    "client_exported_scenario_json"
)
CLIENT_BLUEPRINT_ARTIFACT_TYPE: Final[ClientBlueprintArtifactType] = (
    "make_blueprint_json"
)
LOCAL_ANALYSIS_BOUNDARY: Final[ClientBlueprintLocalAnalysisBoundary] = (
    "operator_workstation_local_only"
)
PUBLIC_BACKEND_EXPOSURE: Final[ClientBlueprintPublicBackendExposure] = (
    "forbidden"
)
REQUIRED_ROOT_FLOW_KEY: Final = "flow"
REQUIRED_ROOT_NAME_KEY: Final = "name"
FORBIDDEN_LIVE_ARTIFACT_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    (
        "bundle",
        "bundles",
        "execution",
        "executions",
        "history",
        "log",
        "logs",
        "payload",
        "payloads",
    )
)
SECRET_KEY_FRAGMENTS: Final[tuple[str, ...]] = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "client_secret",
    "cookie",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
    "x-api-key",
)
SECRET_VALUE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "secret.authorization_header",
        re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    ),
    ("secret.private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "secret.jwt_like",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        ),
    ),
    (
        "secret.url_query",
        re.compile(
            r"(?i)[?&](?:api[_-]?key|access[_-]?token|token|secret|password)="
        ),
    ),
    ("secret.sk_prefix", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
)
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)


class ClientBlueprintIntakeFinding(NamedTuple):
    """One preflight finding before local customer blueprint analysis."""

    code: str
    severity: ClientBlueprintFindingSeverity
    finding_class: ClientBlueprintFindingClass
    json_pointer: str
    message: str


class ClientBlueprintIntakeRequest(NamedTuple):
    """Required request metadata and source text for one intake preflight."""

    file_name: str
    source_text: str
    intake_method: ClientBlueprintIntakeMethod
    received_surface: str
    customer_authorization_ref: str
    processor_boundary: str


class ClientBlueprintIntakeManifest(NamedTuple):
    """Required intake manifest for one customer blueprint source."""

    decision: ClientBlueprintIntakeDecision
    file_name: str
    accepted_artifact_type: ClientBlueprintArtifactType
    artifact_source_type: ClientBlueprintSourceType
    intake_method: ClientBlueprintIntakeMethod
    received_surface: str
    customer_authorization_ref: str
    processor_boundary: str
    local_analysis_boundary: ClientBlueprintLocalAnalysisBoundary
    public_backend_exposure: ClientBlueprintPublicBackendExposure
    source_sha256: str
    size_bytes: int
    max_size_bytes: int
    is_truncated: bool
    truncation_reason: ClientBlueprintTruncationReason
    shape_status: ClientBlueprintShapeStatus
    secret_status: ClientBlueprintSecretStatus
    personal_data_status: ClientBlueprintPersonalDataStatus
    redaction_status: ClientBlueprintRedactionStatus
    redaction_reason: str
    deletion_status: ClientBlueprintDeletionStatus
    deletion_reason: str
    evidence_coverage_status: ClientBlueprintEvidenceCoverageStatus
    external_model_processing_allowed: bool
    findings: tuple[ClientBlueprintIntakeFinding, ...]


CLIENT_BLUEPRINT_REQUIRED_MANIFEST_FIELDS: Final[tuple[str, ...]] = (
    ClientBlueprintIntakeManifest._fields
)


def validate_client_blueprint_intake(
    request: ClientBlueprintIntakeRequest,
) -> ClientBlueprintIntakeManifest:
    """Return a fail-closed preflight manifest for one customer blueprint.

    export.
    """
    encoded_source = request.source_text.encode("utf-8")
    findings: list[ClientBlueprintIntakeFinding] = []
    findings.extend(
        _metadata_findings(
            file_name=request.file_name,
            source_size=len(encoded_source),
            received_surface=request.received_surface,
            customer_authorization_ref=request.customer_authorization_ref,
            processor_boundary=request.processor_boundary,
        )
    )
    payload = _load_json_object(request.source_text, findings)
    if payload is not None:
        findings.extend(_shape_findings(payload))
        findings.extend(_source_material_findings(payload))

    has_error = any(finding.severity == "error" for finding in findings)
    has_manual_review = any(
        finding.severity == "manual_review" for finding in findings
    )
    decision = _intake_decision(
        has_error=has_error, has_manual_review=has_manual_review
    )
    secret_status: ClientBlueprintSecretStatus = (
        "blocked"
        if any(finding.finding_class == "secret" for finding in findings)
        else "passed"
    )
    personal_data_status: ClientBlueprintPersonalDataStatus = (
        "manual_review_required"
        if any(
            finding.finding_class == "personal_identifier"
            for finding in findings
        )
        else "passed"
    )
    shape_status: ClientBlueprintShapeStatus = (
        "blocked"
        if any(
            finding.finding_class in {"artifact_type", "shape", "size"}
            for finding in findings
        )
        else "passed"
    )
    redaction_status = _redaction_status(
        credential_gate_status=secret_status,
        personal_data_status=personal_data_status,
    )
    return ClientBlueprintIntakeManifest(
        decision=decision,
        file_name=request.file_name,
        accepted_artifact_type=CLIENT_BLUEPRINT_ARTIFACT_TYPE,
        artifact_source_type=CLIENT_BLUEPRINT_SOURCE_TYPE,
        intake_method=request.intake_method,
        received_surface=request.received_surface,
        customer_authorization_ref=request.customer_authorization_ref,
        processor_boundary=request.processor_boundary,
        local_analysis_boundary=LOCAL_ANALYSIS_BOUNDARY,
        public_backend_exposure=PUBLIC_BACKEND_EXPOSURE,
        source_sha256=hashlib.sha256(encoded_source).hexdigest(),
        size_bytes=len(encoded_source),
        max_size_bytes=MAX_CLIENT_BLUEPRINT_BYTES,
        is_truncated=False,
        truncation_reason="not_truncated",
        shape_status=shape_status,
        secret_status=secret_status,
        personal_data_status=personal_data_status,
        redaction_status=redaction_status,
        redaction_reason=_redaction_reason(
            credential_gate_status=secret_status,
            personal_data_status=personal_data_status,
        ),
        deletion_status="not_started",
        deletion_reason="raw_source_received_for_local_preflight",
        evidence_coverage_status=_evidence_coverage_status(
            received_surface=request.received_surface,
            customer_authorization_ref=request.customer_authorization_ref,
            processor_boundary=request.processor_boundary,
        ),
        external_model_processing_allowed=False,
        findings=tuple(findings),
    )


def mark_client_blueprint_source_deleted(
    manifest: ClientBlueprintIntakeManifest,
    *,
    deletion_evidence_ref: str,
) -> ClientBlueprintIntakeManifest:
    """Return a manifest copy that records source deletion evidence.

    Raises:
        ValueError: If the deletion evidence reference is blank.
    """
    normalized_ref = deletion_evidence_ref.strip()
    if not normalized_ref:
        message = "Deletion evidence reference is required."
        raise ValueError(message)
    return manifest._replace(
        deletion_status="completed",
        deletion_reason=normalized_ref,
    )


def client_blueprint_report_release_errors(
    manifest: ClientBlueprintIntakeManifest,
) -> tuple[str, ...]:
    """Return fail-fast reasons that block releasing a report for one intake."""
    return tuple(
        error
        for error, blocked in (
            (
                "client_blueprint_intake_not_accepted",
                _intake_is_not_accepted(manifest),
            ),
            (
                "client_blueprint_shape_not_approved",
                not _is_gate_passed(manifest.shape_status),
            ),
            (
                "client_blueprint_secret_gate_blocked",
                not _is_gate_passed(manifest.secret_status),
            ),
            (
                "client_blueprint_personal_data_requires_review",
                not _is_gate_passed(manifest.personal_data_status),
            ),
            (
                "client_blueprint_redaction_not_resolved",
                not _redaction_is_resolved(manifest.redaction_status),
            ),
            (
                "client_blueprint_source_deletion_not_completed",
                manifest.deletion_status != "completed",
            ),
            (
                "client_blueprint_evidence_coverage_incomplete",
                manifest.evidence_coverage_status != "complete",
            ),
            (
                "client_blueprint_source_truncation_not_allowed",
                _is_source_truncated(manifest),
            ),
            (
                "client_blueprint_external_model_processing_forbidden",
                manifest.external_model_processing_allowed,
            ),
            (
                "client_blueprint_public_backend_forbidden",
                manifest.public_backend_exposure != "forbidden",
            ),
        )
        if blocked
    )


def client_blueprint_intake_manifest_as_dict(
    manifest: ClientBlueprintIntakeManifest,
) -> JsonObject:
    """Return a JSON-ready intake manifest with every required field present."""
    return {
        "decision": manifest.decision,
        "file_name": manifest.file_name,
        "accepted_artifact_type": manifest.accepted_artifact_type,
        "artifact_source_type": manifest.artifact_source_type,
        "intake_method": manifest.intake_method,
        "received_surface": manifest.received_surface,
        "customer_authorization_ref": manifest.customer_authorization_ref,
        "processor_boundary": manifest.processor_boundary,
        "local_analysis_boundary": manifest.local_analysis_boundary,
        "public_backend_exposure": manifest.public_backend_exposure,
        "source_sha256": manifest.source_sha256,
        "size_bytes": manifest.size_bytes,
        "max_size_bytes": manifest.max_size_bytes,
        "is_truncated": manifest.is_truncated,
        "truncation_reason": manifest.truncation_reason,
        "shape_status": manifest.shape_status,
        "secret_status": manifest.secret_status,
        "personal_data_status": manifest.personal_data_status,
        "redaction_status": manifest.redaction_status,
        "redaction_reason": manifest.redaction_reason,
        "deletion_status": manifest.deletion_status,
        "deletion_reason": manifest.deletion_reason,
        "evidence_coverage_status": manifest.evidence_coverage_status,
        "external_model_processing_allowed": (
            manifest.external_model_processing_allowed
        ),
        "findings": [
            {
                "code": finding.code,
                "severity": finding.severity,
                "finding_class": finding.finding_class,
                "json_pointer": finding.json_pointer,
                "message": finding.message,
            }
            for finding in manifest.findings
        ],
    }


def _metadata_findings(
    *,
    file_name: str,
    source_size: int,
    received_surface: str,
    customer_authorization_ref: str,
    processor_boundary: str,
) -> tuple[ClientBlueprintIntakeFinding, ...]:
    """Return findings from intake metadata only."""
    findings: list[ClientBlueprintIntakeFinding] = []
    if not file_name.strip() or "/" in file_name or "\\" in file_name:
        findings.append(
            _finding(
                code="intake.file_name.invalid",
                severity="error",
                finding_class="artifact_type",
                json_pointer="$file_name",
                message="Client blueprint intake requires a plain file name.",
            )
        )
    if not file_name.casefold().endswith(CLIENT_BLUEPRINT_EXTENSION):
        findings.append(
            _finding(
                code="intake.file_name.not_blueprint_json",
                severity="error",
                finding_class="artifact_type",
                json_pointer="$file_name",
                message="Only Make .blueprint.json exports are accepted.",
            )
        )
    if source_size <= 0:
        findings.append(
            _finding(
                code="intake.source.empty",
                severity="error",
                finding_class="size",
                json_pointer="$source",
                message="Client blueprint source cannot be empty.",
            )
        )
    if source_size > MAX_CLIENT_BLUEPRINT_BYTES:
        findings.append(
            _finding(
                code="intake.source.too_large",
                severity="error",
                finding_class="size",
                json_pointer="$source",
                message=(
                    "Client blueprint source exceeds the approved intake size."
                ),
            )
        )
    if not received_surface.strip():
        findings.append(
            _finding(
                code="intake.received_surface.missing",
                severity="error",
                finding_class="processor_boundary",
                json_pointer="$received_surface",
                message="Email or offline handoff surface must be named.",
            )
        )
    if not customer_authorization_ref.strip():
        findings.append(
            _finding(
                code="intake.authorization.missing",
                severity="error",
                finding_class="authorization",
                json_pointer="$customer_authorization_ref",
                message=(
                    "Customer authorization reference is required before"
                    "analysis."
                ),
            )
        )
    if not processor_boundary.strip():
        findings.append(
            _finding(
                code="intake.processor_boundary.missing",
                severity="error",
                finding_class="processor_boundary",
                json_pointer="$processor_boundary",
                message="Processor and retention boundary must be explicit.",
            )
        )
    return tuple(findings)


def _load_json_object(
    source_text: str,
    findings: list[ClientBlueprintIntakeFinding],
) -> JsonObject | None:
    """Return normalized source JSON or append a shape finding."""
    try:
        parsed = cast("object", json.loads(source_text))
    except json.JSONDecodeError:
        findings.append(
            _finding(
                code="intake.source.invalid_json",
                severity="error",
                finding_class="shape",
                json_pointer="$source",
                message="Client blueprint source must be valid JSON.",
            )
        )
        return None
    if not isinstance(parsed, dict):
        findings.append(
            _finding(
                code="intake.source.not_object",
                severity="error",
                finding_class="shape",
                json_pointer="$source",
                message="Client blueprint JSON must be an object.",
            )
        )
        return None
    try:
        return normalize_json_object(cast("Mapping[str, object]", parsed))
    except (TypeError, ValueError):
        findings.append(
            _finding(
                code="intake.source.unsupported_json_value",
                severity="error",
                finding_class="shape",
                json_pointer="$source",
                message="Client blueprint JSON contains unsupported values.",
            )
        )
        return None


def _shape_findings(
    payload: Mapping[str, object],
) -> tuple[ClientBlueprintIntakeFinding, ...]:
    """Return the computed result for the caller."""
    findings: list[ClientBlueprintIntakeFinding] = []
    if not isinstance(payload.get(REQUIRED_ROOT_NAME_KEY), str):
        findings.append(
            _finding(
                code="intake.shape.name_missing",
                severity="error",
                finding_class="shape",
                json_pointer="/name",
                message="Make blueprint JSON must include a scenario name.",
            )
        )
    if not isinstance(payload.get(REQUIRED_ROOT_FLOW_KEY), list):
        findings.append(
            _finding(
                code="intake.shape.flow_missing",
                severity="error",
                finding_class="shape",
                json_pointer="/flow",
                message="Make blueprint JSON must include a flow array.",
            )
        )
    findings.extend(
        _finding(
            code="intake.shape.live_artifact_key",
            severity="error",
            finding_class="shape",
            json_pointer=f"/{_escape_json_pointer_part(key)}",
            message=(
                "Execution logs, live payloads, and run history are outside"
                "intake scope."
            ),
        )
        for key in sorted(
            FORBIDDEN_LIVE_ARTIFACT_ROOT_KEYS.intersection(payload)
        )
    )
    return tuple(findings)


def _source_material_findings(
    payload: Mapping[str, object],
) -> tuple[ClientBlueprintIntakeFinding, ...]:
    """Return secret and personal-identifier findings from normalized JSON."""
    findings: list[ClientBlueprintIntakeFinding] = []
    _collect_source_material_findings(payload, (), findings)
    return tuple(findings)


def _collect_source_material_findings(
    value: object,
    path: tuple[str | int, ...],
    findings: list[ClientBlueprintIntakeFinding],
) -> None:
    """Append source-material findings while recursively walking JSON."""
    if isinstance(value, dict):
        for key, child in cast("JsonObject", value).items():
            key_path = (*path, key)
            normalized_key = _normalize_key(key)
            if any(
                fragment in normalized_key for fragment in SECRET_KEY_FRAGMENTS
            ):
                findings.append(
                    _finding(
                        code="intake.secret.key_detected",
                        severity="error",
                        finding_class="secret",
                        json_pointer=_json_pointer(key_path),
                        message=(
                            "Secret-like fields must be removed before intake."
                        ),
                    )
                )
            if EMAIL_PATTERN.search(key):
                findings.append(
                    _finding(
                        code="intake.personal_identifier.key_email",
                        severity="manual_review",
                        finding_class="personal_identifier",
                        json_pointer=_json_pointer(key_path),
                        message=(
                            "Email-like identifiers require redaction review"
                            "before reporting."
                        ),
                    )
                )
            _collect_source_material_findings(child, key_path, findings)
    elif isinstance(value, list):
        for index, child in enumerate(cast("list[object]", value)):
            _collect_source_material_findings(child, (*path, index), findings)
    elif isinstance(value, str):
        findings.extend(_string_findings(value, path))


def _string_findings(
    value: str,
    path: tuple[str | int, ...],
) -> tuple[ClientBlueprintIntakeFinding, ...]:
    """Return string-value findings for secrets and direct identifiers."""
    findings: list[ClientBlueprintIntakeFinding] = []
    for code, pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(value):
            findings.append(
                _finding(
                    code=code,
                    severity="error",
                    finding_class="secret",
                    json_pointer=_json_pointer(path),
                    message="Secret-like values must be removed before intake.",
                )
            )
    if EMAIL_PATTERN.search(value):
        findings.append(
            _finding(
                code="intake.personal_identifier.email",
                severity="manual_review",
                finding_class="personal_identifier",
                json_pointer=_json_pointer(path),
                message=(
                    "Email-like identifiers require redaction review before"
                    "reporting."
                ),
            )
        )
    return tuple(findings)


def _intake_decision(
    *,
    has_error: bool,
    has_manual_review: bool,
) -> ClientBlueprintIntakeDecision:
    """Return the aggregate intake decision."""
    if has_error:
        return "rejected"
    if has_manual_review:
        return "manual_review_required"
    return "accepted_for_local_analysis"


def _redaction_status(
    *,
    credential_gate_status: ClientBlueprintSecretStatus,
    personal_data_status: ClientBlueprintPersonalDataStatus,
) -> ClientBlueprintRedactionStatus:
    """Return the manifest redaction status from source findings."""
    if _is_gate_blocked(credential_gate_status):
        return "blocked"
    if personal_data_status == "manual_review_required":
        return "required"
    return "not_required"


def _redaction_reason(
    *,
    credential_gate_status: ClientBlueprintSecretStatus,
    personal_data_status: ClientBlueprintPersonalDataStatus,
) -> str:
    """Return a stable redaction reason."""
    if _is_gate_blocked(credential_gate_status):
        return "secret_like_source_value_detected"
    if personal_data_status == "manual_review_required":
        return "personal_identifier_detected"
    return "no_sensitive_values_detected"


def _evidence_coverage_status(
    *,
    received_surface: str,
    customer_authorization_ref: str,
    processor_boundary: str,
) -> ClientBlueprintEvidenceCoverageStatus:
    """Return if required authorization and processor evidence is present."""
    if (
        received_surface.strip()
        and customer_authorization_ref.strip()
        and processor_boundary.strip()
    ):
        return "complete"
    return "incomplete"


def _intake_is_not_accepted(manifest: ClientBlueprintIntakeManifest) -> bool:
    """Return whether intake failed to reach accepted local-analysis status."""
    return manifest.decision != "accepted_for_local_analysis"


def _is_gate_passed(status: str) -> bool:
    """Return whether a gate status is clean enough for report release."""
    return status == "passed"


def _is_gate_blocked(status: str) -> bool:
    """Return whether a gate status blocks intake."""
    return status == "blocked"


def _redaction_is_resolved(status: ClientBlueprintRedactionStatus) -> bool:
    """Return whether redaction is resolved for report release."""
    return status in {"not_required", "redacted"}


def _is_source_truncated(manifest: ClientBlueprintIntakeManifest) -> bool:
    """Return whether source truncation blocks report release."""
    return (
        manifest.is_truncated or manifest.truncation_reason != "not_truncated"
    )


def _finding(
    *,
    code: str,
    severity: ClientBlueprintFindingSeverity,
    finding_class: ClientBlueprintFindingClass,
    json_pointer: str,
    message: str,
) -> ClientBlueprintIntakeFinding:
    """Return one intake finding."""
    return ClientBlueprintIntakeFinding(
        code=code,
        severity=severity,
        finding_class=finding_class,
        json_pointer=json_pointer,
        message=message,
    )


def _json_pointer(path: tuple[str | int, ...]) -> str:
    """Return a JSON pointer for a source path."""
    if not path:
        return "$"
    return "/" + "/".join(_escape_json_pointer_part(str(part)) for part in path)


def _escape_json_pointer_part(value: str) -> str:
    """Escape one JSON pointer path part.

    Returns:
        The escaped JSON pointer path part.
    """
    return value.replace("~", "~0").replace("/", "~1")


def _normalize_key(value: str) -> str:
    """Return a normalized key for source-material scanning."""
    return re.sub(r"[^a-z0-9_-]+", "", value.casefold())
