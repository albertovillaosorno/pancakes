# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Client-safe audit report projection tests.

Boundary contract:
- Owns: JSON report contract, deferred PDF, private marker, and preview guard
tests.
- Must not: render PDFs, call Make.com, read customer files, or use live
credentials.
- Allows: synthetic manifest and coverage records built from public-safe test
values.
- Split when: PDF rendering or customer delivery gains a separate approved
boundary.
- Merge when: another test owns these exact report projection guarantees.
"""

from __future__ import annotations

import json

import pytest
from blueprints.validation.client_report import (
    ClientSafeAuditReport,
    build_client_safe_audit_report,
    client_safe_audit_report_as_dict,
    client_safe_audit_report_guard_errors,
    render_operator_report_preview,
)
from blueprints.validation.delivery_coverage import BlueprintDeliveryCoverage
from blueprints.validation.handoff_manifest import (
    BlueprintHandoffReadinessManifest,
    HandoffBlockerSummary,
    HandoffEvidenceSource,
)


def test_client_safe_report_contract_is_json_first_and_pdf_deferred() -> None:
    """The report contract is deterministic JSON and does not claim PDF.

    readiness.
    """
    report = _report()
    payload = client_safe_audit_report_as_dict(report)

    assert (
        payload["output_relative_path"]
        == "reports/client-safe/lead-routing-audit.json"
    ), f"Report output path drifted: {payload}"
    assert payload["pdf_status"] == "deferred", (
        f"PDF status must stay deferred: {payload}"
    )
    assert payload["customer_pdf_enabled"] is False, (
        f"Customer PDF output is not approved in Pancakes core: {payload}"
    )
    assert payload["is_truncated"] is False, (
        f"Report must expose truncation state: {payload}"
    )
    assert payload["truncation_reason"] == "not_truncated", (
        f"Report must expose truncation reason: {payload}"
    )
    _ = json.dumps(payload, sort_keys=True)

    preview = render_operator_report_preview(report)

    assert "reviewed JSON report contract" in preview, (
        f"Preview must identify JSON as the source of truth: {preview}"
    )
    assert "PDF/A" not in preview, (
        f"Preview must not claim archival PDF support: {preview}"
    )
    assert "C:/Users" not in preview, f"Preview leaked a local path: {preview}"


def test_client_safe_report_guard_blocks_4dd62232() -> None:
    """Private paths, raw-spec markers, and PDF enablement fail before.

    projection.
    """
    report = _report(
        source_label=(
            "C:/Users/example/source/schoenwald/repos/proprietary/pancakes/"
            "temp/raw-specs-json/token.json"
        ),
        customer_pdf_enabled=True,
    )

    errors = set(client_safe_audit_report_guard_errors(report))

    assert "private_or_raw_source_marker_present" in errors, (
        f"Private source markers were not blocked: {errors}"
    )
    assert "pdf_profile_not_approved" in errors, (
        f"PDF enablement must stay blocked in Pancakes core: {errors}"
    )


@pytest.mark.parametrize(
    "output_relative_path",
    [
        "../client-safe/lead-routing-audit.json ",
        "reports/client-safe/../lead-routing-audit.json ",
        "reports/client-safe/..",
        r"reports\client-safe\..",
    ],
)
def test_client_safe_report_guard_blocks_parent_directory_output_paths(
    output_relative_path: str,
) -> None:
    """Customer-safe report output paths must not contain parent-directory.

    segments.
    """
    report = _report(output_relative_path=output_relative_path)

    errors = set(client_safe_audit_report_guard_errors(report))

    assert "unsafe_output_path" in errors, (
        f"Parent-directory output path was not blocked: "
        f"{output_relative_path!r}, {errors}"
    )


@pytest.mark.parametrize(
    "internal_marker",
    [
        ("raw-spec",),
        ("raw specs",),
        ("raw_spec",),
        ("raw source",),
        ("source evidence",),
        ("evidence pipeline",),
        ("rule corpus",),
        ("Make-source evidence",),
    ],
)
def test_client_safe_report_guard_blocks_source_evidence_mechanics(
    internal_marker: str,
) -> None:
    """Public or client report fields cannot disclose internal evidence.

    mechanics.
    """
    report = _report(
        source_label=f"Customer report references {internal_marker}."
    )

    errors = set(client_safe_audit_report_guard_errors(report))

    assert "private_or_raw_source_marker_present" in errors, (
        f"Internal evidence marker was not blocked: {internal_marker!r}, "
        f"{errors}"
    )


def test_client_safe_report_guard_blocks_internal_rule_and_endpoint_leaks() -> (
    None
):
    """Internal rule IDs, local endpoints, and implementation paths fail before.

    preview.
    """
    report = _report(
        source_label=(
            "Candidate ID IDM-010 from corpus_count 130 used deterministic "
            "predicate "
            "logic in src/mcp/server.py at localhost:3000."
        ),
    )

    errors = set(client_safe_audit_report_guard_errors(report))

    assert "private_or_raw_source_marker_present" in errors, (
        f"Implementation leakage markers were not blocked: {errors}"
    )
    assert "internal_rule_marker_present" in errors, (
        f"Internal rule IDs were not blocked: {errors}"
    )
    assert "local_endpoint_marker_present" in errors, (
        f"Local endpoint markers were not blocked: {errors}"
    )


def test_client_safe_report_guard_blocks_obfuscated_local_endpoint_urls() -> (
    None
):
    """Public report fields cannot contain numeric loopback endpoint aliases."""
    report = _report(
        source_label="Customer report references http://2130706433:8787/internal/status."
    )

    errors = set(client_safe_audit_report_guard_errors(report))

    assert "local_endpoint_marker_present" in errors, (
        f"Obfuscated local endpoint marker was not blocked: {errors}"
    )


@pytest.mark.parametrize(
    "unsupported_claim",
    [
        "Pancakes certifies compliance for PCI DSS.",
        "Pancakes confirms the customer audit complete state.",
        "Pancakes says this blueprint is attestation ready for SOC 2.",
        "Pancakes gives legally sufficient GDPR compliant output.",
        "Pancakes says this customer is ISO/IEC 27001 certified.",
    ],
)
def test_client_safe_report_guard_blocks_cc3d3d40(
    unsupported_claim: str,
) -> None:
    """Customer-safe report fields cannot imply compliance, audit, or legal.

    outcomes.
    """
    report = _report(source_label=unsupported_claim)

    errors = set(client_safe_audit_report_guard_errors(report))

    assert "unsupported_claim_marker_present" in errors, (
        f"Unsupported standards claim was not blocked: "
        f"{unsupported_claim!r}, {errors}"
    )


def test_client_safe_report_preview_rejects_blocked_handoff_reports() -> None:
    """A report with handoff blockers cannot become generated customer-facing.

    copy.
    """
    report = _report(blocker_count=1)

    errors = client_safe_audit_report_guard_errors(report)

    assert errors == ("handoff_blockers_present",), (
        f"Blocked handoff report should fail only the blocker gate: {errors}"
    )
    with pytest.raises(ValueError, match="handoff_blockers_present"):
        _ = render_operator_report_preview(report)


def _report(
    *,
    source_label: str = "Synthetic lead routing blueprint",
    blocker_count: int = 0,
    customer_pdf_enabled: bool = False,
    output_relative_path: str | None = None,
) -> ClientSafeAuditReport:
    manifest = BlueprintHandoffReadinessManifest(
        importability_status="importable_candidate",
        live_make_called=False,
        blockers=tuple(_blocker(index) for index in range(blocker_count)),
        warnings=(),
        secondary_diagnostics=(),
        placeholders=(),
        evidence_sources=(
            HandoffEvidenceSource(
                source_id="ast.parse",
                label="AST parser",
                detail="Parsed a sanitized synthetic Make fixture.",
            ),
            HandoffEvidenceSource(
                source_id="validation.importability",
                label="Importability validation",
                detail="Validated with local catalog evidence.",
            ),
        ),
    )
    coverage = BlueprintDeliveryCoverage(
        catalog_fingerprint="catalog:fingerprint:synthetic",
        delivery_mode="deploy_ready",
        error_count=0,
        warning_count=0,
        optimization_count=0,
        explanation_count=0,
        handoff_placeholder_count=0,
        client_ready_score=1.0,
    )
    report = build_client_safe_audit_report(
        report_id="Lead Routing Audit",
        source_label=source_label,
        manifest=manifest,
        coverage=coverage,
        audience="operator_review",
    )
    if customer_pdf_enabled:
        report = report._replace(customer_pdf_enabled=True)
    if output_relative_path is not None:
        report = report._replace(output_relative_path=output_relative_path)
    return report


def _blocker(index: int) -> HandoffBlockerSummary:
    return HandoffBlockerSummary(
        code=f"semantic.synthetic_blocker_{index}",
        json_pointer="/flow/0",
        severity="error",
        suggested_owner="blueprint",
        message="Synthetic blocker for report guard tests.",
    )
