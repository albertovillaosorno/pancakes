# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for public demo aggregate score output.

Boundary contract:
- Owns: tests for aggregate-only public demo score behavior.
- Must not: test hosted upload, email delivery, exact findings, or remediation
copy.
- Allows: synthetic validation reports and aggregate output assertions.
- Split when: hosted demo intake is approved.
"""

from __future__ import annotations

import pytest
from blueprints.optimization.advisory import BlueprintOptimizationAdvice
from blueprints.validation import (
    PUBLIC_DEMO_AGGREGATE_SCORE_FIELDS,
    BlueprintFindingSeverity,
    BlueprintValidationFinding,
    BlueprintValidationReport,
    blocked_public_demo_aggregate_score,
    build_public_demo_aggregate_score,
    public_demo_aggregate_score_as_dict,
)


def test_public_demo_score_exposes_only_aggregate_fields() -> None:
    """Public demo output omits exact findings, rules, fixes, paths, and.

    messages.
    """
    report = validation_report(
        findings=(
            finding("secret-leak", "error", code="security.secret"),
            finding("timeout-risk", "warning", code="webhook.timeout"),
            finding("handoff-note", "explanation", code="handoff.note"),
            finding(
                "operations-review",
                "optimization",
                code="operation.volume_review",
            ),
        )
    )
    score = build_public_demo_aggregate_score(
        validation_report=report,
        optimization_advice=(optimization_advice(),),
    )

    payload = public_demo_aggregate_score_as_dict(score)

    assert tuple(payload) == PUBLIC_DEMO_AGGREGATE_SCORE_FIELDS, (
        f"Public demo fields drifted: {payload}"
    )
    assert payload == {
        "format_status": "accepted",
        "error_count": 1,
        "warning_count": 1,
        "info_count": 1,
        "total_quality_score": 48,
        "risk_band": "high",
        "operations_score": 62,
    }
    forbidden_fragments = (
        "secret-leak",
        "security.secret",
        "timeout-risk",
        "webhook.timeout",
        "client message",
        "internal message",
        "fix",
        "source_path",
    )
    rendered_payload = repr(payload)
    for fragment in forbidden_fragments:
        assert fragment not in rendered_payload, (
            f"Public demo payload leaked private detail {fragment!r}: {payload}"
        )


def test_public_demo_score_blocks_unknown_formats_without_parser_detail() -> (
    None
):
    """Rejected demo input returns a closed score without parser diagnostics."""
    score = blocked_public_demo_aggregate_score(format_status="unknown_format")

    assert public_demo_aggregate_score_as_dict(score) == {
        "format_status": "unknown_format",
        "error_count": 0,
        "warning_count": 0,
        "info_count": 0,
        "total_quality_score": 0,
        "risk_band": "blocked",
        "operations_score": 0,
    }


def test_public_demo_score_rejects_accepted_without_validation_report() -> None:
    """Accepted scores must come from local validation artifacts."""
    with pytest.raises(ValueError, match="validation report"):
        _ = blocked_public_demo_aggregate_score(format_status="accepted")


def test_public_demo_score_is_monotonic_for_blocking_errors() -> None:
    """More blocking errors cannot improve total quality or risk."""
    one_error = build_public_demo_aggregate_score(
        validation_report=validation_report(
            findings=(finding("first", "error", code="module.unresolved"),)
        )
    )
    two_errors = build_public_demo_aggregate_score(
        validation_report=validation_report(
            findings=(
                finding("first", "error", code="module.unresolved"),
                finding("second", "error", code="route.invalid"),
            )
        )
    )

    assert two_errors.total_quality_score < one_error.total_quality_score, (
        f"More errors should lower quality: {one_error}, {two_errors}"
    )
    assert one_error.risk_band == "high"
    assert two_errors.risk_band == "high"


def test_public_demo_score_marks_many_operations_signals_medium_risk() -> None:
    """Operation-heavy accepted blueprints get lower operations score and.

    medium.

    risk.
    """
    report = validation_report(
        findings=(
            finding(
                "operation-volume",
                "optimization",
                code="operation.volume_review",
            ),
            finding("pagination", "optimization", code="pagination.required"),
            finding("schedule", "warning", code="schedule.sub_minute_interval"),
        )
    )
    score = build_public_demo_aggregate_score(
        validation_report=report,
        optimization_advice=(optimization_advice(), optimization_advice()),
    )

    assert score.risk_band == "medium"
    assert score.operations_score == 32
    assert score.total_quality_score == 80


def validation_report(
    *,
    findings: tuple[BlueprintValidationFinding, ...] = (),
) -> BlueprintValidationReport:
    """Return a synthetic validation report."""
    return BlueprintValidationReport(
        catalog_fingerprint="catalog:test", findings=findings
    )


def finding(
    finding_id: str,
    severity: BlueprintFindingSeverity,
    *,
    code: str,
) -> BlueprintValidationFinding:
    """Return a synthetic validation finding with private detail populated."""
    return BlueprintValidationFinding(
        finding_id=finding_id,
        severity=severity,
        code=code,
        node_id="module-1",
        client_message="client message with exact detail",
        internal_message="internal message with fix instructions",
        catalog_module_id="module:test",
        source_path=("flow", 0, "module"),
    )


def optimization_advice() -> BlueprintOptimizationAdvice:
    """Return synthetic optimization advice with private detail populated."""
    return BlueprintOptimizationAdvice(
        advice_id="optimization-advice",
        hint_code="optimization.webhook_response_timeout_risk",
        severity="optimization",
        node_id="module-2",
        client_message="client optimization detail",
        internal_message="internal optimization rule detail",
        adr_anchor="repo.public-demo-aggregate-score.aggregate-only-output",
    )
