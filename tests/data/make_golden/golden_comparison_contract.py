# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000005#repo.tests.pytest.required-invocation
# - 001035#repo.workflow.todo-backlog-and-continue-contract
# - 001068#repo.operator-commands.command-registry
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Contract tests for deterministic Golden blueprint comparison."""

from __future__ import annotations

from pathlib import Path

from golden.comparison import (
    GoldenComparisonReport,
    GoldenEvidenceGap,
    compare_golden_blueprint_texts,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "comparison"
REFERENCE_FIXTURE = "reference_router.json"


def test_golden_comparison_accepts_semantically_equal_fixture() -> None:
    """Identical Golden and generated payloads allow completion."""
    report = _compare(REFERENCE_FIXTURE)

    _require_completion_allowed(report)
    assert report.semantic_parity, (
        f"Expected semantic parity: {report.as_dict()}"
    )


def test_golden_comparison_ignores_formatting_only_json_differences() -> None:
    """JSON key order and whitespace are not semantic differences."""
    report = _compare("formatting_equivalent_router.json")

    _require_completion_allowed(report)
    assert report.semantic_parity, (
        f"Formatting-only fixture should be semantic parity: {report.as_dict()}"
    )


def test_golden_comparison_rejects_missing_module() -> None:
    """Missing generated modules block Golden completion."""
    report = _compare("missing_module_router.json")

    _require_completion_blocked(report, "semantic_difference")
    removed_nodes = report.comparison.as_dict().get("removed_nodes")
    assert removed_nodes, (
        f"Missing module fixture did not report removed nodes: "
        f"{report.as_dict()}"
    )


def test_golden_comparison_reports_changed_mapping_path() -> None:
    """Changed mappings fail comparison with a deterministic JSON path."""
    report = _compare("changed_mapping_router.json")

    _require_completion_blocked(report, "semantic_difference")
    assert any(
        "mapper" in finding.path
        for finding in report.comparison.semantic_findings
    ), f"Changed mapping fixture missed mapper path: {report.as_dict()}"


def test_golden_comparison_classifies_layout_separately() -> None:
    """Designer layout changes do not become semantic differences."""
    report = _compare("layout_shift_router.json")

    _require_completion_allowed(report)
    assert report.semantic_parity, (
        f"Layout-only fixture should preserve semantic parity: "
        f"{report.as_dict()}"
    )
    assert not (report.layout_parity), (
        f"Layout-only fixture should report layout drift: {report.as_dict()}"
    )
    assert report.comparison.layout_findings, (
        f"Layout-only fixture should expose layout findings: {report.as_dict()}"
    )


def test_golden_comparison_blocks_unresolved_evidence_gap() -> None:
    """Explicit evidence gaps block Golden completion even when semantics.

    match.
    """
    report = _compare(
        REFERENCE_FIXTURE,
        evidence_gaps=(
            GoldenEvidenceGap(
                code="golden.evidence.unresolved_output_contract",
                message="Output contract evidence is missing for this fixture.",
                path="$.flow[0]",
            ),
        ),
    )

    _require_completion_blocked(report, "evidence_gap")
    assert report.semantic_parity, (
        f"Evidence-only blocker should preserve semantic parity: "
        f"{report.as_dict()}"
    )


def _compare(
    generated_fixture: str,
    *,
    evidence_gaps: tuple[GoldenEvidenceGap, ...] = (),
) -> GoldenComparisonReport:
    return compare_golden_blueprint_texts(
        reference_text=_fixture_text(REFERENCE_FIXTURE),
        generated_text=_fixture_text(generated_fixture),
        label=generated_fixture,
        evidence_gaps=evidence_gaps,
    )


def _fixture_text(filename: str) -> str:
    return (FIXTURE_ROOT / filename).read_text(encoding="utf-8")


def _require_completion_allowed(report: GoldenComparisonReport) -> None:
    assert report.completion_allowed, (
        f"Expected Golden completion to be allowed: {report.as_dict()}"
    )


def _require_completion_blocked(
    report: GoldenComparisonReport, blocker: str
) -> None:
    assert not (report.completion_allowed), (
        f"Expected Golden completion to be blocked: {report.as_dict()}"
    )
    assert not (blocker not in report.completion_blockers), (
        f"Missing blocker {blocker}: {report.as_dict()}"
    )
