# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001061#repo.delivery.client-ready-handoff-contract
# - 001077#repo.client-safe-audit-report.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Client-safe audit report contract projection from validated blueprint.

evidence.

Boundary contract:
- Owns: deterministic JSON and operator-preview report fields from handoff
evidence.
- Must not: render customer PDFs, read raw customer source, or call live
services.
- Allows: claim guards, relative output paths, and deferred PDF profile
metadata.
- Split when: PDF rendering, report styling, or external delivery gets approved.
- Merge when: another module projects the same report contract from the same
evidence.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, cast
from urllib.parse import urlsplit

from blueprints.validation.network_hosts import host_ip_candidates

if TYPE_CHECKING:
    from blueprints.validation.delivery_coverage import (
        BlueprintDeliveryCoverage,
    )
    from blueprints.validation.delivery_mode import BlueprintDeliveryMode
    from blueprints.validation.handoff_manifest import (
        BlueprintHandoffReadinessManifest,
        HandoffImportabilityStatus,
    )

type ClientSafeReportAudience = Literal["operator_review", "customer_safe"]
type ClientSafeReportPdfStatus = Literal["deferred"]

PRIVATE_OUTPUT_MARKERS: Final = (
    "c:/users/",
    "\\users\\",
    "schoenwald ",
    "repos/",
    "repos/proprietary ",
    "commands/",
    "commands\\",
    "src/",
    "tests/",
    "tools/",
    "tools\\",
    "docs/adr ",
    "docs\\adr ",
    "private adr ",
    "schoenwald.skills ",
    "candidate id ",
    "candidate_id ",
    "corpus count ",
    "corpus_count ",
    "deterministic predicate ",
    "predicate:",
    "exploit recipe ",
    "step-by-step exploit ",
    "mcp internals ",
    "mcp server ",
    "src/mcp ",
    "mcp/oauth",
    ".env ",
    "oauth ",
    "raw-spec ",
    "raw-specs ",
    "raw specs ",
    "raw_spec ",
    "raw source ",
    "source evidence ",
    "source-evidence ",
    "evidence pipeline ",
    "rule corpus ",
    "rule-corpus ",
    "make-source ",
    "make source ",
    "token ",
    "secret ",
    "password ",
    "webhook url",
)
UNSUPPORTED_CLAIM_MARKERS: Final = (
    "pdf/a ",
    "pades ",
    "tamper evidence ",
    "certified by make ",
    "make.com certified ",
    "guaranteed ",
    "zero failure ",
    "legal advice ",
    "legal sufficiency ",
    "legally sufficient ",
    "certifies compliance ",
    "certify compliance ",
    "certified compliant ",
    "compliance certified ",
    "compliance guarantee ",
    "audit complete ",
    "audit completion ",
    "auditor approved ",
    "attestation ready ",
    "soc 2 ready ",
    "pci dss compliant ",
    "gdpr compliant ",
    "iso 27001 certified ",
    "iso/iec 27001 certified ",
    "compliant with pci dss ",
    "meets pci dss ",
    "passes pci dss",
)
INTERNAL_RULE_ID_PATTERN: Final = re.compile(
    r"\b(?:IDM|OBS|STM|TME|ZDT)-\d{3}\b"
)
LOCAL_HOST_ENDPOINT_PATTERN_TEXT: Final = (
    r"\b(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d{2,5})?\b"
)
LOCAL_DOTLOCAL_ENDPOINT_PATTERN_TEXT: Final = (
    r"|\b[a-z0-9.-]+\.local(?::\d{2,5})?\b"
)
LOCAL_ENDPOINT_PATTERN: Final = re.compile(
    f"{LOCAL_HOST_ENDPOINT_PATTERN_TEXT}{LOCAL_DOTLOCAL_ENDPOINT_PATTERN_TEXT}",
    re.IGNORECASE,
)
STATIC_HTTP_URL_PATTERN: Final = re.compile(
    r"\bhttps?://[^\s<>'\"`]+", re.IGNORECASE
)
REQUIRED_DISCLOSURES: Final = (
    "Static offline analysis only; live Make execution is not implied.",
    (
        "Evidence is limited to parsed blueprint, validation, handoff, and "
        "coverage "
        "artifacts."
    ),
    (
        "Customer PDF delivery, archival conformance, and advanced "
        "signatures are "
        "deferred profiles."
    ),
)


class ClientSafeAuditReport(NamedTuple):
    """Deterministic customer-safe report contract derived from validated.

    evidence.
    """

    report_id: str
    source_label: str
    audience: ClientSafeReportAudience
    output_relative_path: str
    importability_status: HandoffImportabilityStatus
    delivery_mode: BlueprintDeliveryMode
    live_make_called: bool
    blocker_count: int
    warning_count: int
    handoff_placeholder_count: int
    client_ready_score: float
    evidence_source_ids: tuple[str, ...]
    disclosures: tuple[str, ...]
    pdf_status: ClientSafeReportPdfStatus
    customer_pdf_enabled: bool
    is_truncated: bool
    truncation_reason: str


def build_client_safe_audit_report(
    *,
    report_id: str,
    source_label: str,
    manifest: BlueprintHandoffReadinessManifest,
    coverage: BlueprintDeliveryCoverage,
    audience: ClientSafeReportAudience = "operator_review",
) -> ClientSafeAuditReport:
    """Return a deterministic report contract from already-reviewed evidence."""
    normalized_report_id = _normalize_report_id(report_id)
    return ClientSafeAuditReport(
        report_id=normalized_report_id,
        source_label=source_label,
        audience=audience,
        output_relative_path=f"reports/client-safe/{normalized_report_id}.json",
        importability_status=manifest.importability_status,
        delivery_mode=coverage.delivery_mode,
        live_make_called=manifest.live_make_called,
        blocker_count=len(manifest.blockers),
        warning_count=len(manifest.warnings),
        handoff_placeholder_count=coverage.handoff_placeholder_count,
        client_ready_score=coverage.client_ready_score,
        evidence_source_ids=tuple(
            source.source_id for source in manifest.evidence_sources
        ),
        disclosures=REQUIRED_DISCLOSURES,
        pdf_status="deferred",
        customer_pdf_enabled=False,
        is_truncated=False,
        truncation_reason="not_truncated",
    )


def client_safe_audit_report_as_dict(
    report: ClientSafeAuditReport,
) -> dict[str, object]:
    """Return one JSON-ready report contract mapping."""
    return {
        "report_id": report.report_id,
        "source_label": report.source_label,
        "audience": report.audience,
        "output_relative_path": report.output_relative_path,
        "importability_status": report.importability_status,
        "delivery_mode": report.delivery_mode,
        "live_make_called": report.live_make_called,
        "blocker_count": report.blocker_count,
        "warning_count": report.warning_count,
        "handoff_placeholder_count": report.handoff_placeholder_count,
        "client_ready_score": report.client_ready_score,
        "evidence_source_ids": list(report.evidence_source_ids),
        "disclosures": list(report.disclosures),
        "pdf_status": report.pdf_status,
        "customer_pdf_enabled": report.customer_pdf_enabled,
        "is_truncated": report.is_truncated,
        "truncation_reason": report.truncation_reason,
    }


def client_safe_audit_report_guard_errors(
    report: ClientSafeAuditReport,
) -> tuple[str, ...]:
    """Return release blockers for a customer-facing report projection."""
    errors: list[str] = []
    if report.blocker_count:
        errors.append("handoff_blockers_present")
    if report.live_make_called:
        errors.append("live_make_claim_requires_separate_evidence")
    if report.customer_pdf_enabled or report.pdf_status != "deferred":
        errors.append("pdf_profile_not_approved")
    if report.is_truncated or report.truncation_reason != "not_truncated":
        errors.append("truncated_report_requires_manual_review")
    if _unsafe_relative_path(report.output_relative_path):
        errors.append("unsafe_output_path")

    text_values = tuple(_report_text_values(report))
    if any(
        _contains_marker(value, PRIVATE_OUTPUT_MARKERS) for value in text_values
    ):
        errors.append("private_or_raw_source_marker_present")
    if any(INTERNAL_RULE_ID_PATTERN.search(value) for value in text_values):
        errors.append("internal_rule_marker_present")
    if any(_contains_local_endpoint_marker(value) for value in text_values):
        errors.append("local_endpoint_marker_present")
    if any(
        _contains_marker(value, UNSUPPORTED_CLAIM_MARKERS)
        for value in text_values
    ):
        errors.append("unsupported_claim_marker_present")
    return tuple(dict.fromkeys(errors))


def render_operator_report_preview(report: ClientSafeAuditReport) -> str:
    """Return deterministic operator Markdown after report guard checks pass.

    Raises:
        ValueError: If report fields are not safe enough to preview.
    """
    errors = client_safe_audit_report_guard_errors(report)
    if errors:
        message = f"Client-safe audit report guard failed: {', '.join(errors)}"
        raise ValueError(message)

    disclosures = "\n".join(
        f"- {disclosure}" for disclosure in report.disclosures
    )
    evidence_ids = ", ".join(report.evidence_source_ids)
    return (
        "# Operator Audit Report Preview\n\n "
        "This preview is generated from the reviewed JSON report contract.\n\n"
        f"- Report ID: `{report.report_id}`\n"
        f"- Source: `{report.source_label}`\n"
        f"- Delivery mode: `{report.delivery_mode}`\n"
        f"- Importability: `{report.importability_status}`\n"
        f"- Client-ready score: `{report.client_ready_score}`\n"
        f"- Evidence: `{evidence_ids}`\n"
        f"- Output contract: `{report.output_relative_path}`\n"
        f"- PDF status: `{report.pdf_status}`\n\n"
        "## Disclosures\n\n"
        f"{disclosures}\n"
    )


def _normalize_report_id(report_id: str) -> str:
    token = "-".join(part for part in report_id.casefold().split() if part)
    normalized = "".join(
        character if character.isalnum() or character == "-" else "-"
        for character in token
    )
    compact = "-".join(part for part in normalized.split("-") if part)
    if not compact:
        message = "Report ID must contain at least one alphanumeric character."
        raise ValueError(message)
    return compact


def _unsafe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    return (
        normalized.startswith(("/", "../"))
        or ":" in normalized
        or any(part == ".." for part in normalized.split("/"))
    )


def _contains_local_endpoint_marker(value: str) -> bool:
    """Return the computed result for the caller."""
    return LOCAL_ENDPOINT_PATTERN.search(
        value
    ) is not None or _contains_local_http_url(value)


def _contains_local_http_url(value: str) -> bool:
    """Return whether report text contains a URL with local host evidence."""
    for match in STATIC_HTTP_URL_PATTERN.finditer(value):
        url_text = match.group(0).rstrip(".,);]}")
        parts = urlsplit(url_text)
        host = parts.hostname
        if host is not None and _local_endpoint_host(host):
            return True
    return False


def _local_endpoint_host(host: str) -> bool:
    """Return whether one URL host names localhost-style endpoint evidence."""
    normalized = host.casefold().strip("[]").rstrip(".")
    if normalized == "localhost" or normalized.endswith(".local"):
        return True
    return any(
        candidate.is_loopback or candidate.is_unspecified
        for candidate in host_ip_candidates(normalized)
    )


def _report_text_values(report: ClientSafeAuditReport) -> tuple[str, ...]:
    payload = client_safe_audit_report_as_dict(report)
    values: list[str] = []
    for value in payload.values():
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            items = cast("list[object]", value)
            values.extend(item for item in items if isinstance(item, str))
        elif isinstance(value, bool | int | float):
            continue
        else:
            values.append(str(value))
    return tuple(values)


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    normalized = value.casefold().replace("\\", "/")
    return any(
        marker.casefold().replace("\\", "/") in normalized for marker in markers
    )
