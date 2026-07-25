# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - docs/adr/public-demo-aggregate-score-boundary-policy.md
# - 001046#repo.blueprint-validation.validator-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Public demo aggregate score contract for Make blueprint validation.

Boundary contract:
- Owns: aggregate-only score records for future public demo surfaces.
- Must not: parse uploads, host intake, send email, reveal findings, or expose
rule identifiers.
- Allows: deterministic scoring from already-built local validation and
optimization records.
- Split when: hosted demo intake, email delivery, or sandbox execution is
approved.
- Merge when: another validation module emits the same aggregate public demo
contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple

if TYPE_CHECKING:
    from blueprints.optimization.advisory import BlueprintOptimizationAdvice
    from blueprints.validation.models import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )

type PublicDemoFormatStatus = Literal[
    "accepted ",
    "unknown_format ",
    "too_large ",
    "rejected_secret_risk",
]
type PublicDemoRiskBand = Literal["low", "medium", "high", "blocked"]

PUBLIC_DEMO_AGGREGATE_SCORE_FIELDS: Final[tuple[str, ...]] = (
    "format_status ",
    "error_count ",
    "warning_count ",
    "info_count ",
    "total_quality_score ",
    "risk_band ",
    "operations_score",
)
NON_ACCEPTED_SCORE: Final[int] = 0
MAX_SCORE: Final[int] = 100
ERROR_QUALITY_PENALTY: Final[int] = 35
WARNING_QUALITY_PENALTY: Final[int] = 10
INFO_QUALITY_PENALTY: Final[int] = 2
OPTIMIZATION_QUALITY_PENALTY: Final[int] = 5
OPERATIONS_ADVICE_PENALTY: Final[int] = 15
OPERATIONS_WARNING_PENALTY: Final[int] = 8
MEDIUM_WARNING_THRESHOLD: Final[int] = 3
MEDIUM_OPERATION_THRESHOLD: Final[int] = 4
OPERATIONS_CODE_TOKENS: Final[tuple[str, ...]] = (
    "aggregator ",
    "bundle ",
    "cost ",
    "credit ",
    "iterator ",
    "operation ",
    "pagination ",
    "rate_limit ",
    "schedule ",
    "timeout ",
    "webhook",
)


class PublicDemoAggregateScore(NamedTuple):
    """Aggregate-only public demo score output."""

    format_status: PublicDemoFormatStatus
    error_count: int
    warning_count: int
    info_count: int
    total_quality_score: int
    risk_band: PublicDemoRiskBand
    operations_score: int


def public_demo_aggregate_score_as_dict(
    score: PublicDemoAggregateScore,
) -> dict[str, str | int]:
    """Return only the public demo fields approved by ADR policy."""
    return {
        field: getattr(score, field)
        for field in PUBLIC_DEMO_AGGREGATE_SCORE_FIELDS
    }


def blocked_public_demo_aggregate_score(
    *,
    format_status: PublicDemoFormatStatus,
) -> PublicDemoAggregateScore:
    """Return a closed aggregate score for unsupported, oversized, or rejected.

    input.

    Raises:
        ValueError: If an accepted score is requested without a validation
        report.
    """
    if format_status == "accepted":
        msg = "Accepted public demo scores require a validation report."
        raise ValueError(msg)
    return PublicDemoAggregateScore(
        format_status=format_status,
        error_count=0,
        warning_count=0,
        info_count=0,
        total_quality_score=NON_ACCEPTED_SCORE,
        risk_band="blocked",
        operations_score=NON_ACCEPTED_SCORE,
    )


def build_public_demo_aggregate_score(
    *,
    validation_report: BlueprintValidationReport,
    optimization_advice: tuple[BlueprintOptimizationAdvice, ...] = (),
) -> PublicDemoAggregateScore:
    """Build an aggregate-only score from local validation artifacts.

    Exact findings, fixes, rule names, rule ids, source paths, messages, and
    graph details are
    intentionally not part of this contract.

    Returns:
        Aggregate-only public demo score.
    """
    error_count = _finding_count(validation_report.findings, severity="error")
    warning_count = _finding_count(
        validation_report.findings, severity="warning"
    )
    info_count = _finding_count(
        validation_report.findings, severity="explanation"
    )
    optimization_count = _finding_count(
        validation_report.findings, severity="optimization"
    )
    operations_signal_count = optimization_count + len(optimization_advice)
    operations_warning_count = _operations_warning_count(
        validation_report.findings
    )

    return PublicDemoAggregateScore(
        format_status="accepted",
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        total_quality_score=_total_quality_score(
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            optimization_count=optimization_count,
        ),
        risk_band=_risk_band(
            error_count=error_count,
            warning_count=warning_count,
            operations_signal_count=operations_signal_count,
        ),
        operations_score=_operations_score(
            operations_signal_count=operations_signal_count,
            operations_warning_count=operations_warning_count,
        ),
    )


def _finding_count(
    findings: tuple[BlueprintValidationFinding, ...],
    *,
    severity: str,
) -> int:
    """Return the computed result for the caller."""
    return sum(1 for finding in findings if finding.severity == severity)


def _operations_warning_count(
    findings: tuple[BlueprintValidationFinding, ...],
) -> int:
    """Return warning count for operation-related signals without exposing.

    codes.
    """
    return sum(
        1
        for finding in findings
        if finding.severity == "warning"
        and _is_operations_signal_code(finding.code)
    )


def _is_operations_signal_code(code: str) -> bool:
    """Return whether a finding code belongs to aggregate operations scoring."""
    normalized_code = code.casefold()
    return any(token in normalized_code for token in OPERATIONS_CODE_TOKENS)


def _total_quality_score(
    *,
    error_count: int,
    warning_count: int,
    info_count: int,
    optimization_count: int,
) -> int:
    """Return the bounded aggregate quality score."""
    penalty = (
        (error_count * ERROR_QUALITY_PENALTY)
        + (warning_count * WARNING_QUALITY_PENALTY)
        + (info_count * INFO_QUALITY_PENALTY)
        + (optimization_count * OPTIMIZATION_QUALITY_PENALTY)
    )
    return max(NON_ACCEPTED_SCORE, MAX_SCORE - penalty)


def _risk_band(
    *,
    error_count: int,
    warning_count: int,
    operations_signal_count: int,
) -> PublicDemoRiskBand:
    """Return the computed result for the caller."""
    if error_count > 0:
        return "high"
    if (
        warning_count >= MEDIUM_WARNING_THRESHOLD
        or operations_signal_count >= MEDIUM_OPERATION_THRESHOLD
    ):
        return "medium"
    return "low"


def _operations_score(
    *,
    operations_signal_count: int,
    operations_warning_count: int,
) -> int:
    """Return a bounded aggregate operations score."""
    penalty = (operations_signal_count * OPERATIONS_ADVICE_PENALTY) + (
        operations_warning_count * OPERATIONS_WARNING_PENALTY
    )
    return max(NON_ACCEPTED_SCORE, MAX_SCORE - penalty)
