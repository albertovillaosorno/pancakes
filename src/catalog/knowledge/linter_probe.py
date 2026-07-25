# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001066#repo.make-linter.api-probe-authorized-only
# - 001066#repo.make-linter.documented-designer-message-signal
# - 001066#repo.make-linter.evidence-normalization
# - 001066#repo.make-linter.raw-designer-message-ingestion
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make linter API probe models, raw evidence, and normalization helpers.

Boundary contract:
- Owns: authorization checks, fake-transport boundary, raw designer-message
  ingest files, and finding normalization.
- Must not: implement HTTP clients, contact Make.com, or mutate SQLite.
- Allows: documented blueprint response parsing and structured probe reports.
- Split when: real Make HTTP adapters or reviewed SQL promotion become active.
- Merge when: live_probe owns this exact linter probe boundary.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, Protocol, cast
from urllib.parse import quote

from languages.make.raw_specs.paths import (
    relative_to_repo,
    resolve_repo_relative_path,
    safe_path_token,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from languages.make.raw_specs.models import JsonObject

MAKE_LINTER_ADR_ANCHOR = (
    "001066#repo.make-linter.documented-designer-message-signal"
)
MAKE_LINTER_REPORT_PATH = (
    "src/blueprints/validation/data/linter/probes/api_probe_report.json"
)
MAKE_BLUEPRINT_ENDPOINT = "/api/v2/scenarios/{scenarioId}/blueprint"
MAKE_DESIGNER_MESSAGE_RAW_DIR: Final[Path] = Path(
    "src/languages/make/data/designer-messages/raw"
)
MAKE_DESIGNER_MESSAGE_MANIFEST_NAME: Final = "manifest.json"
MAKE_DESIGNER_MESSAGE_SOURCE_KIND: Final = "designer_message"
MAKE_DESIGNER_WARNING_PREFIX: Final = "MAKE-DESIGNER-WARN"
MAKE_AST_ERROR_PREFIX: Final = "MAKE-AST-ERROR"
MAKE_AST_WARNING_PREFIX: Final = "MAKE-AST-WARN"
MAKE_SECONDARY_LINTER_SOURCE: Final = "make_linter_api_designer_messages"
MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT: Final = 0.25
MAX_CREDENTIAL_REF_LENGTH = 120
MAX_RAW_SCENARIO_TOKEN_LENGTH = 80
CHILD_FLOW_CONTAINER_KEYS: Final[tuple[str, ...]] = (
    "routes ",
    "branches ",
    "tools",
)
ERROR_FLOW_CONTAINER_KEYS: Final[tuple[str, ...]] = ("onerror", "on_error")
SECONDARY_LINTER_WARNING_KEYS: Final[tuple[str, ...]] = (
    "finding_id ",
    "code ",
    "node_id ",
    "module_slug ",
    "message ",
    "category ",
    "field_path ",
    "source_ref ",
    "captured_at_utc ",
    "fingerprint ",
    "internal_message",
)
LINTER_PROBE_PURPOSES: Final[frozenset[str]] = frozenset(
    ("collect_designer_messages", "discover_linter_api")
)
SECRET_CREDENTIAL_PREFIXES: Final[tuple[str, ...]] = (
    "authorization:",
    "authorization=",
    "bearer ",
    "pat_",
    "raw-token ",
    "sk-",
    "mk_",
    "token ",
)

type MakeSecondaryLinterStatus = Literal[
    "secondary_linter_unavailable ",
    "secondary_linter_passed ",
    "secondary_linter_warning",
]


class MakeLinterBlueprintTransport(Protocol):
    """Transport boundary for an operator-approved blueprint message probe."""

    def get_scenario_blueprint(
        self, scenario_id: str, *, draft: bool
    ) -> JsonObject:
        """Return a documented Make scenario blueprint response."""
        ...


class MakeLinterProbeAuthorization(NamedTuple):
    """Reviewed operator authorization for one Make linter API probe."""

    operator_approved: bool
    approved_by: str
    credential_ref: str
    purpose: str


class MakeDesignerMessageBatchRequest(NamedTuple):
    """Request for one read-only designer-message evidence collection batch."""

    transport: MakeLinterBlueprintTransport
    authorization: MakeLinterProbeAuthorization
    scenario_ids: tuple[str, ...]
    draft: bool
    captured_at_utc: str
    repo_root: Path
    raw_dir: Path = MAKE_DESIGNER_MESSAGE_RAW_DIR


class MakeLinterFinding(NamedTuple):
    """One normalized Make designer-message finding."""

    finding_id: str
    node_id: str | None
    module_slug: str | None
    severity: str
    message: str
    category: str | None
    field_path: str | None
    source_ref: str
    captured_at_utc: str
    fingerprint: str

    def to_json(self) -> JsonObject:
        """Return a credential-free JSON representation."""
        return {
            "finding_id": self.finding_id,
            "node_id": self.node_id,
            "module_slug": self.module_slug,
            "severity": self.severity,
            "source_system": "make_designer",
            "source_prefix": MAKE_DESIGNER_WARNING_PREFIX,
            "message": self.message,
            "category": self.category,
            "field_path": self.field_path,
            "source_ref": self.source_ref,
            "captured_at_utc": self.captured_at_utc,
            "fingerprint": self.fingerprint,
            "adr_anchor": MAKE_LINTER_ADR_ANCHOR,
        }


class MakeSecondaryLinterReport(NamedTuple):
    """Low-weight Make linter evidence that cannot replace offline.

    validation.
    """

    status: MakeSecondaryLinterStatus
    source: str
    warnings: tuple[JsonObject, ...]
    confidence_weight: float

    def to_json(self) -> JsonObject:
        """Return a credential-free JSON representation."""
        return {
            "status": self.status,
            "source": self.source,
            "warnings": [dict(warning) for warning in self.warnings],
            "confidence_weight": self.confidence_weight,
        }


class MakeDesignerMessageRawRecord(NamedTuple):
    """One raw designer-message ingest record written under the ignored raw.

    dir.
    """

    scenario_id: str
    draft: bool
    relative_path: str
    sha256: str
    finding_count: int
    captured_at_utc: str

    def to_json(self) -> JsonObject:
        """Return the manifest representation for this raw record."""
        return {
            "scenario_id": self.scenario_id,
            "draft": self.draft,
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "finding_count": self.finding_count,
            "captured_at_utc": self.captured_at_utc,
        }


class MakeDesignerMessageBatchReport(NamedTuple):
    """Summary for one read-only designer-message evidence collection batch."""

    status: str
    raw_dir: str
    manifest_path: str
    collected_count: int
    skipped_count: int
    failed_count: int
    unauthorized_count: int
    finding_count: int
    records: tuple[MakeDesignerMessageRawRecord, ...]
    failures: tuple[str, ...] = ()

    def to_json(self) -> JsonObject:
        """Return a machine-readable batch report."""
        return {
            "status": self.status,
            "raw_dir": self.raw_dir,
            "manifest_path": self.manifest_path,
            "collected_count": self.collected_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "unauthorized_count": self.unauthorized_count,
            "finding_count": self.finding_count,
            "records": [record.to_json() for record in self.records],
            "failures": list(self.failures),
        }


class DesignerMessageCollectionReport(NamedTuple):
    """Collected raw designer-message records and bounded failure metadata."""

    records: tuple[MakeDesignerMessageRawRecord, ...]
    failures: tuple[str, ...]
    skipped_count: int


class LinterFindingIdentity(NamedTuple):
    """Stable identity inputs for one normalized Make linter finding."""

    node_id: str | None
    module_slug: str | None
    message: str
    category: str | None
    field_path: str | None
    source_ref: str


def probe_linter_findings(
    *,
    transport: MakeLinterBlueprintTransport,
    authorization: MakeLinterProbeAuthorization,
    scenario_id: str,
    draft: bool,
    captured_at_utc: str,
) -> tuple[MakeLinterFinding, ...]:
    """Collect normalized findings through an injected, authorized transport.

    Returns:
        Normalized Make linter findings.
    """
    _require_authorization(authorization)
    normalized_scenario_id = _required_scenario_id(scenario_id)
    normalized_draft = _required_bool(draft, "draft")
    normalized_captured_at_utc = _required_string(
        captured_at_utc, "captured_at_utc"
    )
    payload = transport.get_scenario_blueprint(
        normalized_scenario_id, draft=normalized_draft
    )
    source_ref = _blueprint_source_ref(
        scenario_id=normalized_scenario_id, draft=normalized_draft
    )
    return normalize_linter_findings(
        payload=payload,
        source_ref=source_ref,
        captured_at_utc=normalized_captured_at_utc,
    )


def collect_designer_message_batch(
    request: MakeDesignerMessageBatchRequest | None = None,
    **legacy_arguments: object,
) -> MakeDesignerMessageBatchReport:
    """Collect raw designer-message evidence through an injected transport.

    Returns:
        The batch collection report.
    """
    request = _designer_message_batch_request(request, legacy_arguments)
    authorization_error = _authorization_error(request.authorization)
    if authorization_error is not None:
        return _unauthorized_batch_report(
            raw_dir=request.raw_dir,
            scenario_ids=request.scenario_ids,
            authorization_error=authorization_error,
        )

    resolved_raw_dir = resolve_repo_relative_path(
        request.repo_root, request.raw_dir
    )
    manifest_path = resolved_raw_dir / MAKE_DESIGNER_MESSAGE_MANIFEST_NAME
    normalized_scenario_ids = _required_scenario_id_batch(request.scenario_ids)
    normalized_draft = _required_bool(request.draft, "draft")
    normalized_captured_at_utc = _required_string(
        request.captured_at_utc, "captured_at_utc"
    )
    collection = _collect_designer_message_records(
        request=request,
        resolved_raw_dir=resolved_raw_dir,
        scenario_ids=normalized_scenario_ids,
        draft=normalized_draft,
        captured_at_utc=normalized_captured_at_utc,
    )
    report = MakeDesignerMessageBatchReport(
        status=_batch_status(
            records=collection.records,
            failures=collection.failures,
            skipped_count=collection.skipped_count,
        ),
        raw_dir=relative_to_repo(request.repo_root, resolved_raw_dir),
        manifest_path=relative_to_repo(request.repo_root, manifest_path),
        collected_count=len(collection.records),
        skipped_count=collection.skipped_count,
        failed_count=len(collection.failures),
        unauthorized_count=0,
        finding_count=sum(
            record.finding_count for record in collection.records
        ),
        records=collection.records,
        failures=collection.failures,
    )
    if collection.records:
        _write_batch_manifest(
            manifest_path=manifest_path,
            report=report,
            captured_at_utc=normalized_captured_at_utc,
        )
    return report


def _designer_message_batch_request(
    request: MakeDesignerMessageBatchRequest | None,
    legacy_arguments: Mapping[str, object],
) -> MakeDesignerMessageBatchRequest:
    if request is not None:
        if legacy_arguments:
            message = (
                "Pass either MakeDesignerMessageBatchRequest or legacy keyword "
                "arguments."
            )
            raise TypeError(message)
        return request
    return MakeDesignerMessageBatchRequest(
        transport=cast(
            "MakeLinterBlueprintTransport",
            _required_legacy_argument(legacy_arguments, "transport"),
        ),
        authorization=cast(
            "MakeLinterProbeAuthorization",
            _required_legacy_argument(legacy_arguments, "authorization"),
        ),
        scenario_ids=cast(
            "tuple[str, ...]",
            _required_legacy_argument(legacy_arguments, "scenario_ids"),
        ),
        draft=cast(
            "bool", _required_legacy_argument(legacy_arguments, "draft")
        ),
        captured_at_utc=cast(
            "str",
            _required_legacy_argument(legacy_arguments, "captured_at_utc"),
        ),
        repo_root=cast(
            "Path", _required_legacy_argument(legacy_arguments, "repo_root")
        ),
        raw_dir=cast(
            "Path",
            legacy_arguments.get("raw_dir", MAKE_DESIGNER_MESSAGE_RAW_DIR),
        ),
    )


def _required_legacy_argument(
    arguments: Mapping[str, object], key: str
) -> object:
    if key in arguments:
        return arguments[key]
    message = f"Missing designer-message batch argument: {key}"
    raise TypeError(message)


def _collect_designer_message_records(
    *,
    request: MakeDesignerMessageBatchRequest,
    resolved_raw_dir: Path,
    scenario_ids: tuple[object, ...],
    draft: bool,
    captured_at_utc: str,
) -> DesignerMessageCollectionReport:
    records: list[MakeDesignerMessageRawRecord] = []
    failures: list[str] = []
    skipped_count = 0
    for scenario_id in scenario_ids:
        normalized_scenario_id = _optional_scenario_id(scenario_id)
        if normalized_scenario_id is None:
            skipped_count += 1
            continue
        try:
            payload = request.transport.get_scenario_blueprint(
                normalized_scenario_id,
                draft=draft,
            )
        except (OSError, TypeError, ValueError) as exc:
            failures.append(
                _transport_failure_message(normalized_scenario_id, exc)
            )
            continue
        source_ref = _blueprint_source_ref(
            scenario_id=normalized_scenario_id,
            draft=draft,
        )
        findings = normalize_linter_findings(
            payload=payload,
            source_ref=source_ref,
            captured_at_utc=captured_at_utc,
        )
        record_payload: JsonObject = {
            "schema_version": 1,
            "scenario_id": normalized_scenario_id,
            "draft": draft,
            "source_ref": source_ref,
            "captured_at_utc": captured_at_utc,
            "payload": payload,
            "normalized_findings": [finding.to_json() for finding in findings],
        }
        payload_bytes = _canonical_json_bytes(record_payload)
        record_path = resolved_raw_dir / _raw_evidence_filename(
            scenario_id=normalized_scenario_id,
            draft=draft,
        )
        resolved_raw_dir.mkdir(parents=True, exist_ok=True)
        _ = record_path.write_bytes(payload_bytes)
        records.append(
            MakeDesignerMessageRawRecord(
                scenario_id=normalized_scenario_id,
                draft=draft,
                relative_path=relative_to_repo(request.repo_root, record_path),
                sha256=hashlib.sha256(payload_bytes).hexdigest(),
                finding_count=len(findings),
                captured_at_utc=captured_at_utc,
            )
        )
    return DesignerMessageCollectionReport(
        records=tuple(records),
        failures=tuple(failures),
        skipped_count=skipped_count,
    )


def _unauthorized_batch_report(
    *,
    raw_dir: Path,
    scenario_ids: object,
    authorization_error: str,
) -> MakeDesignerMessageBatchReport:
    safe_raw_dir = _safe_report_raw_dir(raw_dir)
    return MakeDesignerMessageBatchReport(
        status="unauthorized",
        raw_dir=safe_raw_dir.as_posix(),
        manifest_path=(
            safe_raw_dir / MAKE_DESIGNER_MESSAGE_MANIFEST_NAME
        ).as_posix(),
        collected_count=0,
        skipped_count=0,
        failed_count=0,
        unauthorized_count=_unauthorized_scenario_count(scenario_ids),
        finding_count=0,
        records=(),
        failures=(authorization_error,),
    )


def _safe_report_raw_dir(raw_dir: Path) -> Path:
    if raw_dir.is_absolute() or ".." in raw_dir.parts:
        return MAKE_DESIGNER_MESSAGE_RAW_DIR
    return raw_dir


def _unauthorized_scenario_count(scenario_ids: object) -> int:
    if not isinstance(scenario_ids, tuple):
        return 0
    return len(cast("tuple[object, ...]", scenario_ids))


def normalize_linter_findings(
    *,
    payload: JsonObject,
    source_ref: str,
    captured_at_utc: str,
) -> tuple[MakeLinterFinding, ...]:
    """Normalize Make blueprint designer messages into structured findings.

    Returns:
        Normalized Make linter findings.
    """
    normalized_source_ref = _required_string(source_ref, "source_ref")
    normalized_captured_at_utc = _required_string(
        captured_at_utc, "captured_at_utc"
    )
    blueprint = _blueprint_payload(payload)
    findings: list[MakeLinterFinding] = []
    findings.extend(
        _findings_from_designer_messages(
            messages=_designer_messages(blueprint),
            node_id=None,
            module_slug=None,
            source_ref=normalized_source_ref,
            captured_at_utc=normalized_captured_at_utc,
        )
    )
    for node in _flow_nodes(blueprint.get("flow")):
        findings.extend(
            _findings_from_designer_messages(
                messages=_designer_messages(node),
                node_id=_node_id_text(node.get("id")),
                module_slug=_optional_string(node.get("module")),
                source_ref=normalized_source_ref,
                captured_at_utc=normalized_captured_at_utc,
            )
        )
    return tuple(findings)


def secondary_linter_unavailable() -> MakeSecondaryLinterReport:
    """Return the computed result for the caller."""
    return MakeSecondaryLinterReport(
        status="secondary_linter_unavailable",
        source=MAKE_SECONDARY_LINTER_SOURCE,
        warnings=(),
        confidence_weight=0.0,
    )


def secondary_linter_result_from_findings(
    findings: tuple[MakeLinterFinding, ...],
) -> MakeSecondaryLinterReport:
    """Return a secondary linter result from an available Make API probe."""
    warnings = tuple(
        _secondary_warning_from_linter_finding(finding) for finding in findings
    )
    return _secondary_linter_available(warnings)


def secondary_linter_result_from_validation_findings(
    findings: tuple[object, ...],
) -> MakeSecondaryLinterReport:
    """Return secondary linter evidence from reviewed validation findings."""
    warnings = tuple(
        _secondary_warning_from_validation_finding(finding)
        for finding in findings
        if _is_designer_validation_warning(finding)
    )
    if not warnings:
        return secondary_linter_unavailable()
    return _secondary_linter_available(warnings)


def secondary_linter_result_from_warning_payloads(
    findings: tuple[Mapping[str, object], ...],
) -> MakeSecondaryLinterReport:
    """Return the computed result for the caller."""
    warnings = tuple(
        _secondary_warning_from_payload(finding)
        for finding in findings
        if _is_designer_warning_payload(finding)
    )
    if not warnings:
        return secondary_linter_unavailable()
    return _secondary_linter_available(warnings)


def _secondary_linter_available(
    warnings: tuple[JsonObject, ...],
) -> MakeSecondaryLinterReport:
    status: MakeSecondaryLinterStatus = (
        "secondary_linter_warning" if warnings else "secondary_linter_passed"
    )
    return MakeSecondaryLinterReport(
        status=status,
        source=MAKE_SECONDARY_LINTER_SOURCE,
        warnings=warnings,
        confidence_weight=MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT,
    )


def _secondary_warning_from_linter_finding(
    finding: MakeLinterFinding,
) -> JsonObject:
    warning = finding.to_json()
    warning["severity"] = "warning"
    warning["source_system"] = "make_designer"
    warning["source_prefix"] = MAKE_DESIGNER_WARNING_PREFIX
    return warning


def _secondary_warning_from_validation_finding(finding: object) -> JsonObject:
    return {
        "finding_id": _optional_string(getattr(finding, "finding_id", None)),
        "code": _optional_string(getattr(finding, "code", None))
        or "make_designer.warning",
        "node_id": _optional_string(getattr(finding, "node_id", None)),
        "severity": "warning ",
        "source_system": "make_designer",
        "source_prefix": MAKE_DESIGNER_WARNING_PREFIX,
        "message": _optional_string(getattr(finding, "client_message", None))
        or "",
        "internal_message": _optional_string(
            getattr(finding, "internal_message", None)
        ),
        "adr_anchor": MAKE_LINTER_ADR_ANCHOR,
    }


def _secondary_warning_from_payload(
    payload: Mapping[str, object],
) -> JsonObject:
    warning: JsonObject = {
        "severity": "warning ",
        "source_system": "make_designer",
        "source_prefix": MAKE_DESIGNER_WARNING_PREFIX,
        "adr_anchor": MAKE_LINTER_ADR_ANCHOR,
    }
    for key in SECONDARY_LINTER_WARNING_KEYS:
        value = payload.get(key)
        if _is_secondary_warning_value(value):
            warning[key] = value
    if "message" not in warning:
        warning["message"] = ""
    return warning


def _is_designer_validation_warning(finding: object) -> bool:
    code: object = getattr(finding, "code", None)
    severity: object = getattr(finding, "severity", None)
    return code == "make_designer.warning" and severity == "warning"


def _is_designer_warning_payload(payload: Mapping[str, object]) -> bool:
    return (
        payload.get("severity") == "warning"
        and payload.get("source_system") == "make_designer"
        and payload.get("source_prefix") == MAKE_DESIGNER_WARNING_PREFIX
    )


def _is_secondary_warning_value(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _findings_from_designer_messages(
    *,
    messages: tuple[JsonObject, ...],
    node_id: str | None,
    module_slug: str | None,
    source_ref: str,
    captured_at_utc: str,
) -> tuple[MakeLinterFinding, ...]:
    findings: list[MakeLinterFinding] = []
    for message_payload in messages:
        message = _designer_message_text(message_payload)
        if message is None:
            continue
        category = _optional_string(message_payload.get("category"))
        field_path = _designer_message_field_path(message_payload)
        identity = LinterFindingIdentity(
            node_id=node_id,
            module_slug=module_slug,
            message=message,
            category=category,
            field_path=field_path,
            source_ref=source_ref,
        )
        findings.append(
            MakeLinterFinding(
                finding_id=_finding_id(identity),
                node_id=node_id,
                module_slug=module_slug,
                severity="warning",
                message=message,
                category=category,
                field_path=field_path,
                source_ref=source_ref,
                captured_at_utc=captured_at_utc,
                fingerprint=_finding_fingerprint(identity),
            )
        )
    return tuple(findings)


def build_linter_probe_status() -> JsonObject:
    """Return the current go/no-go status for Make linter API probing."""
    return {
        "status": "conditional_go_for_documented_designer_messages",
        "report_path": MAKE_LINTER_REPORT_PATH,
        "accepted_signal": "documented scenario blueprint designer messages ",
        "standalone_validate_endpoint": (
            "not_found_in_documented_api_or_local_specs "
        ),
        "browser_scraping": "rejected",
        "offline_validation_default": True,
        "raw_designer_message_dir": MAKE_DESIGNER_MESSAGE_RAW_DIR.as_posix(),
        "designer_warning_prefix": MAKE_DESIGNER_WARNING_PREFIX,
        "local_error_prefix": MAKE_AST_ERROR_PREFIX,
        "secondary_linter_source": MAKE_SECONDARY_LINTER_SOURCE,
        "secondary_linter_confidence_weight": (
            MAKE_SECONDARY_LINTER_CONFIDENCE_WEIGHT
        ),
        "secondary_linter_absent_status": "secondary_linter_unavailable",
    }


def designer_message_findings_to_sql(
    *,
    findings: tuple[MakeLinterFinding, ...],
    review_status: str,
    valid_from: str,
) -> str:
    """Return deterministic SQL for reviewed designer-message evidence.

    Returns:
        A SQL fragment suitable for review before committing to tracked
        snapshots.
    """
    normalized_review_status = _required_review_status(review_status)
    normalized_valid_from = _required_string(valid_from, "valid_from")
    lines = [
        (
            "-- Reviewed Make designer-message evidence. Generated rows "
            "require "
            "review."
        ),
        "BEGIN TRANSACTION;",
    ]
    ordered_findings = tuple(sorted(findings, key=lambda item: item.finding_id))
    lines.extend(
        _designer_message_insert_sql(
            finding, normalized_review_status, normalized_valid_from
        )
        for finding in ordered_findings
    )
    lines.extend(("COMMIT;", ""))
    return "\n".join(lines)


def _blueprint_payload(payload: JsonObject) -> JsonObject:
    response = payload.get("response")
    if isinstance(response, dict):
        blueprint = cast("Mapping[str, object]", response).get("blueprint")
        if isinstance(blueprint, dict):
            return cast("JsonObject", blueprint)
    blueprint = payload.get("blueprint")
    if isinstance(blueprint, dict):
        return cast("JsonObject", blueprint)
    return payload


def _flow_nodes(value: object) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        return ()
    nodes: list[JsonObject] = []
    for item in cast("list[object]", value):
        if isinstance(item, dict):
            node = cast("JsonObject", item)
            nodes.append(node)
            nodes.extend(_flow_nodes(node.get("flow")))
            for container_key in CHILD_FLOW_CONTAINER_KEYS:
                container = node.get(container_key)
                if isinstance(container, list):
                    nodes.extend(
                        _child_flow_nodes(cast("list[object]", container))
                    )
            for container_key in ERROR_FLOW_CONTAINER_KEYS:
                container = node.get(container_key)
                if isinstance(container, dict):
                    nodes.extend(
                        _error_flow_nodes((cast("object", container),))
                    )
                elif isinstance(container, list):
                    nodes.extend(
                        _error_flow_nodes(
                            tuple(cast("list[object]", container))
                        )
                    )
    return tuple(nodes)


def _child_flow_nodes(container: list[object]) -> tuple[JsonObject, ...]:
    nodes: list[JsonObject] = []
    for child in container:
        if isinstance(child, dict):
            nodes.extend(
                _flow_nodes(cast("Mapping[str, object]", child).get("flow"))
            )
    return tuple(nodes)


def _error_flow_nodes(container: tuple[object, ...]) -> tuple[JsonObject, ...]:
    nodes: list[JsonObject] = []
    for child in container:
        if not isinstance(child, dict):
            continue
        child_map = cast("JsonObject", child)
        if "flow" in child_map and "module" not in child_map:
            nodes.extend(_flow_nodes(child_map.get("flow")))
            continue
        nodes.extend(_flow_nodes([child_map]))
    return tuple(nodes)


def _designer_messages(node: JsonObject) -> tuple[JsonObject, ...]:
    metadata = node.get("metadata")
    if not isinstance(metadata, dict):
        return ()
    designer = cast("Mapping[str, object]", metadata).get("designer")
    if not isinstance(designer, dict):
        return ()
    messages = cast("Mapping[str, object]", designer).get("messages")
    if not isinstance(messages, list):
        return ()
    return tuple(
        cast("JsonObject", item)
        for item in cast("list[object]", messages)
        if isinstance(item, dict)
    )


def _designer_message_text(message_payload: JsonObject) -> str | None:
    for key in ("message", "text"):
        text = _optional_string(message_payload.get(key))
        if text is not None:
            return text
    return None


def _designer_message_field_path(message_payload: JsonObject) -> str | None:
    for key in ("field", "fieldPath", "path"):
        field_path = _optional_string(message_payload.get(key))
        if field_path is not None:
            return field_path
    return None


def _blueprint_source_ref(*, scenario_id: str, draft: bool) -> str:
    draft_value = "true" if draft else "false"
    encoded_scenario_id = quote(scenario_id, safe="")
    endpoint = MAKE_BLUEPRINT_ENDPOINT.format(scenarioId=encoded_scenario_id)
    return f"make-api:{endpoint}?draft={draft_value}"


def _require_authorization(authorization: MakeLinterProbeAuthorization) -> None:
    authorization_error = _authorization_error(authorization)
    if authorization_error is not None:
        raise PermissionError(authorization_error)


def _authorization_error(
    authorization: MakeLinterProbeAuthorization,
) -> str | None:
    if authorization.operator_approved is not True:
        return "Make linter API probe requires operator_approved=true."
    purpose = _optional_string(authorization.purpose)
    if purpose not in LINTER_PROBE_PURPOSES:
        return (
            "Make linter API probe purpose must be collect_designer_messages "
            "or discover_linter_api."
        )
    approved_by = _optional_string(authorization.approved_by)
    if approved_by is None:
        return "Make linter API probe requires approved_by."
    credential_ref = _optional_string(authorization.credential_ref)
    if credential_ref is None:
        return "Make linter API probe requires credential_ref."
    if _looks_like_secret(credential_ref):
        return "credential_ref must be a non-secret reference, not a raw token."
    return None


def _looks_like_secret(value: str) -> bool:
    lowered = " ".join(value.casefold().strip().split())
    return (
        lowered.startswith(SECRET_CREDENTIAL_PREFIXES)
        or len(value) > MAX_CREDENTIAL_REF_LENGTH
    )


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _required_string(value: object, name: str) -> str:
    text = _optional_string(value)
    if text is None:
        message = f"Make linter API probe requires non-empty string {name}."
        raise ValueError(message)
    return text


def _required_review_status(value: object) -> str:
    review_status = _required_string(value, "review_status")
    if review_status != "reviewed":
        message = (
            "Designer-message SQL promotion requires review_status='reviewed'."
        )
        raise ValueError(message)
    return review_status


def _optional_scenario_id(value: object) -> str | None:
    return _optional_string(value)


def _required_scenario_id(value: object) -> str:
    scenario_id = _optional_scenario_id(value)
    if scenario_id is None:
        message = (
            "Make linter API probe requires a non-empty string scenario_id."
        )
        raise ValueError(message)
    return scenario_id


def _required_scenario_id_batch(value: object) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        message = "Make linter API probe requires tuple scenario_ids."
        raise TypeError(message)
    if not value:
        message = "Make linter API probe requires at least one scenario_id."
        raise ValueError(message)
    return cast("tuple[object, ...]", value)


def _required_bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    message = f"Make linter API probe requires boolean {name}."
    raise TypeError(message)


def _node_id_text(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return str(value)
    return _optional_string(value)


def _finding_id(identity: LinterFindingIdentity) -> str:
    suffix = hashlib.sha256(
        _canonical_json_bytes(
            {
                "node_id": identity.node_id,
                "module_slug": identity.module_slug,
                "message": identity.message,
                "category": identity.category,
                "field_path": identity.field_path,
                "source_ref": identity.source_ref,
            }
        )
    ).hexdigest()[:16]
    return f"designer-message:{suffix}"


def _finding_fingerprint(identity: LinterFindingIdentity) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(
            {
                "node_id": identity.node_id,
                "module_slug": identity.module_slug,
                "message": identity.message,
                "category": identity.category,
                "field_path": identity.field_path,
                "source_ref": identity.source_ref,
            }
        )
    ).hexdigest()


def _raw_evidence_filename(*, scenario_id: str, draft: bool) -> str:
    draft_token = "draft" if draft else "published"
    scenario_token = safe_path_token(scenario_id)[
        :MAX_RAW_SCENARIO_TOKEN_LENGTH
    ]
    scenario_fingerprint = hashlib.sha256(
        scenario_id.encode("utf-8")
    ).hexdigest()[:12]
    return (
        f"scenario-{scenario_token}-{scenario_fingerprint}-{draft_token}.json"
    )


def _batch_status(
    *,
    records: tuple[MakeDesignerMessageRawRecord, ...],
    failures: tuple[str, ...],
    skipped_count: int,
) -> str:
    if failures and records:
        return "partial"
    if failures:
        return "failed"
    if skipped_count and not records:
        return "skipped"
    return "ok"


def _transport_failure_message(scenario_id: str, exc: BaseException) -> str:
    return f"{scenario_id}: {type(exc).__name__}"


def _write_batch_manifest(
    *,
    manifest_path: Path,
    report: MakeDesignerMessageBatchReport,
    captured_at_utc: str,
) -> None:
    manifest_payload: JsonObject = {
        "schema_version": 1,
        "generated_at_utc": captured_at_utc,
        "raw_dir": report.raw_dir,
        "record_count": report.collected_count,
        "finding_count": report.finding_count,
        "records": [record.to_json() for record in report.records],
    }
    _ = manifest_path.write_bytes(_canonical_json_bytes(manifest_payload))


def _designer_message_insert_sql(
    finding: MakeLinterFinding,
    review_status: str,
    valid_from: str,
) -> str:
    _validate_designer_message_sql_finding(finding)
    node_id = _optional_sql_text(finding.node_id, "node_id")
    module_slug = _optional_sql_text(finding.module_slug, "module_slug")
    category = _optional_sql_text(finding.category, "category")
    field_path = _optional_sql_text(finding.field_path, "field_path")
    values = (
        finding.finding_id,
        node_id,
        module_slug,
        finding.severity,
        finding.message,
        category,
        field_path,
        review_status,
        MAKE_DESIGNER_MESSAGE_SOURCE_KIND,
        finding.source_ref,
        valid_from,
        None,
        finding.fingerprint,
        MAKE_LINTER_ADR_ANCHOR,
    )
    prefix = (
        "INSERT OR REPLACE INTO designer_message_evidence ("
        "finding_id, node_id, module_slug, severity, message, category, "
        "field_path, "
        "review_status, source_kind, source_ref, valid_from, valid_to, "
        "fingerprint, "
        "adr_anchor"
        ") VALUES ("
    )
    value_sql = ", ".join(_sql_literal(value) for value in values)
    return prefix + value_sql + ");"


def _validate_designer_message_sql_finding(finding: MakeLinterFinding) -> None:
    _ = _required_string(finding.finding_id, "finding_id")
    _ = _required_string(finding.message, "message")
    _ = _required_string(finding.source_ref, "source_ref")
    _ = _required_string(finding.fingerprint, "fingerprint")
    if finding.severity != "warning":
        message = "Designer-message SQL promotion requires warning severity."
        raise ValueError(message)


def _sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _optional_sql_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        message = (
            f"Designer-message SQL promotion requires string or null {name}."
        )
        raise TypeError(message)
    return value.strip() or None


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
