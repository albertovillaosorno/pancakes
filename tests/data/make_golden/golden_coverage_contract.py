# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000005#repo.tests.pytest.required-invocation
# - 001035#repo.workflow.todo-backlog-and-continue-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Contract tests for Golden coverage ledger health checks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

from golden.coverage import CoverageHealth, check_golden_coverage

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

type CoverageLedgerEntryPayload = dict[str, object]

DEFAULT_SCENARIO = "data/agent.blueprint.json"
PUBLIC_FIXTURE_BOUNDARY: Final = (
    "Do not promote template-specific business logic"
)
PUBLIC_PRIORITY_FIXTURE_COUNT: Final = 30
PUBLIC_TOP100_FIXTURE_COUNT: Final = 100
PUBLIC_FIXTURE_COUNT: Final = (
    PUBLIC_PRIORITY_FIXTURE_COUNT + PUBLIC_TOP100_FIXTURE_COUNT
)


def test_golden_coverage_health_accepts_valid_fixture(tmp_path: Path) -> None:
    """Valid ledger entries and scenario files produce an OK health report."""
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    _write_coverage(golden_root, [_entry()])

    report = check_golden_coverage(golden_root)

    assert report.ok, str(report.findings)
    assert report.entries[0].file == DEFAULT_SCENARIO, str(report.entries)


def test_repository_golden_coverage_uses_current_make_language_data_root() -> (
    None
):
    """The tracked Make Golden corpus lives under the current language data.

    root.
    """
    root = repo_root()
    golden_root = root / "src" / "languages" / "make" / "data" / "golden"
    old_root = root / "src" / "ast" / "data" / "golden" / "make"

    assert golden_root.is_dir(), (
        f"Current Make Golden root is missing: {golden_root}"
    )
    assert not old_root.exists(), (
        f"Legacy Make Golden root must stay retired: {old_root}"
    )

    report = check_golden_coverage(golden_root)

    assert report.ok, str(report.findings)
    assert len(report.entries) == PUBLIC_FIXTURE_COUNT, (
        f"Unexpected public fixture count: {report.entries}"
    )
    assert (
        sum(entry.completed for entry in report.entries) == PUBLIC_FIXTURE_COUNT
    ), (
        "Reviewed public source fixtures must carry completed manual-analysis "
        "evidence."
    )
    assert all(entry.manual_analysis is not None for entry in report.entries), (
        f"Reviewed public source fixtures lost manual analysis evidence: "
        f"{report.entries}"
    )


def test_repository_golden_coverage_is_public_fixture_evidence_only() -> None:
    """Public Golden entries are fixture evidence, not catalog completeness.

    claims.
    """
    golden_root = repo_root() / "src" / "languages" / "make" / "data" / "golden"
    report = check_golden_coverage(golden_root)

    assert report.ok, str(report.findings)
    priority_entries = tuple(
        entry
        for entry in report.entries
        if entry.file.startswith("data/public/priority/")
    )
    top_entries = tuple(
        entry
        for entry in report.entries
        if entry.file.startswith("data/public/top100/")
    )

    assert len(priority_entries) == PUBLIC_PRIORITY_FIXTURE_COUNT, (
        f"Priority fixture count drifted: {priority_entries}"
    )
    assert len(top_entries) == PUBLIC_TOP100_FIXTURE_COUNT, (
        f"Top-100 fixture count drifted: {top_entries}"
    )
    for entry in report.entries:
        assert entry.file.startswith("data/public/"), (
            f"Non-public fixture entered corpus: {entry}"
        )
        assert any(
            PUBLIC_FIXTURE_BOUNDARY in item
            for item in entry.additional_information
        ), f"Golden entry must carry anti-overclaim boundary text: {entry}"


def test_completed_true_requires_manual_analysis_evidence(
    tmp_path: Path,
) -> None:
    """Completed Golden entries must include manual analysis evidence."""
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    _write_coverage(
        golden_root, [_entry(completed=True, include_manual_analysis=False)]
    )

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.completed_manual_analysis_missing")


def test_completed_true_requires_logic_candidate_review(tmp_path: Path) -> None:
    """Manual completion evidence must explicitly cover logic-candidate.

    review.
    """
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    entry = _entry(completed=True)
    manual_analysis = entry.get("manual_analysis")
    assert isinstance(manual_analysis, dict), (
        f"Manual analysis fixture drifted: {entry}"
    )
    del manual_analysis["logic_candidate_review"]
    _write_coverage(golden_root, [entry])

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.completed_manual_analysis_missing")


def test_completed_true_accepts_manual_analysis_with_tool_evidence(
    tmp_path: Path,
) -> None:
    """Manual completion evidence can cite local Golden tool assistance."""
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    _write_coverage(golden_root, [_entry(completed=True)])

    report = check_golden_coverage(golden_root)

    assert report.ok, str(report.findings)
    manual_analysis = report.entries[0].manual_analysis
    assert manual_analysis is not None, (
        f"Completed entry lost manual analysis: {report.entries[0]}"
    )
    assert manual_analysis.logic_candidate_review, (
        f"Logic-candidate review must be explicit: {manual_analysis}"
    )
    assert manual_analysis.golden_tool_evidence, (
        f"Golden tool evidence must be explicit: {manual_analysis}"
    )


def test_golden_coverage_health_reports_missing_scenario_file(
    tmp_path: Path,
) -> None:
    """Ledger entries that point at absent files fail loudly."""
    golden_root = tmp_path / "golden"
    _write_coverage(golden_root, [_entry()])

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.scenario_file_missing")


def test_golden_coverage_health_reports_extra_scenario_file(
    tmp_path: Path,
) -> None:
    """Scenario JSON files without ledger entries are rejected."""
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    _write_scenario(golden_root, "data/unlisted.blueprint.json")
    _write_coverage(golden_root, [_entry()])

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.scenario_file_extra")


def test_golden_coverage_health_reports_duplicate_ledger_file(
    tmp_path: Path,
) -> None:
    """Duplicate file references in the ledger are rejected."""
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    _write_coverage(golden_root, [_entry(), _entry(title="Duplicate Agent")])

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.ledger_file_duplicate")


def test_golden_coverage_health_reports_non_standard_coverage_json(
    tmp_path: Path,
) -> None:
    """Non-standard JSON constants in coverage.json are rejected."""
    golden_root = tmp_path / "golden"
    golden_root.mkdir(parents=True)
    _ = (golden_root / "coverage.json").write_text("[NaN]", encoding="utf-8")

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.invalid_json")


def test_golden_coverage_health_reports_invalid_completed_field(
    tmp_path: Path,
) -> None:
    """The completion flag must be an explicit JSON boolean."""
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    entry = _entry()
    entry["completed"] = "false"
    _write_coverage(golden_root, [entry])

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.ledger_field_invalid")


def test_golden_coverage_health_reports_path_traversal(tmp_path: Path) -> None:
    """Ledger paths must stay under data/ and cannot traverse upward."""
    golden_root = tmp_path / "golden"
    _write_coverage(golden_root, [_entry(file="../secret.json")])

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.file_path_invalid")


def test_golden_coverage_health_reports_invalid_scenario_json(
    tmp_path: Path,
) -> None:
    """Scenario files must also be strict JSON documents."""
    golden_root = tmp_path / "golden"
    scenario_path = golden_root / DEFAULT_SCENARIO
    scenario_path.parent.mkdir(parents=True)
    _ = scenario_path.write_text('{"name": Infinity}', encoding="utf-8")
    _write_coverage(golden_root, [_entry()])

    report = check_golden_coverage(golden_root)

    _assert_finding(report, "coverage.scenario_json_invalid")


def _entry(
    *,
    title: str = "Agent",
    file: str = DEFAULT_SCENARIO,
    completed: bool = False,
    include_manual_analysis: bool = True,
) -> CoverageLedgerEntryPayload:
    entry: CoverageLedgerEntryPayload = {
        "title": title,
        "description": "Example scenario.",
        "additional_information": ["Fixture owned by this test."],
        "file": file,
        "completed": completed,
    }
    if completed and include_manual_analysis:
        entry["manual_analysis"] = _manual_analysis()
    return entry


def _manual_analysis() -> CoverageLedgerEntryPayload:
    return {
        "reviewed_by": "local-test-operator ",
        "reviewed_at": "2026-05-08T00:00:00Z ",
        "parity_verdict": "accepted_as_generated ",
        "privacy_verdict": "private labels removed or absent ",
        "logic_candidate_review": (
            "No missing reusable logic candidates were found."
        ),
        "golden_tool_evidence": [
            "python -m golden.coverage_summary --root <fixture>",
            "compare_golden_blueprint_texts semantic_parity=True",
        ],
    }


def _write_coverage(
    golden_root: Path, entries: list[CoverageLedgerEntryPayload]
) -> None:
    golden_root.mkdir(parents=True, exist_ok=True)
    _ = (golden_root / "coverage.json").write_text(
        json.dumps(entries, indent=2),
        encoding="utf-8",
    )


def _write_scenario(golden_root: Path, relative_path: str) -> None:
    scenario_path = golden_root / relative_path
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    _ = scenario_path.write_text(
        json.dumps({"name": relative_path}), encoding="utf-8"
    )


def _assert_finding(report: CoverageHealth, expected_code: str) -> None:
    codes = {finding.code for finding in report.findings}
    assert not (expected_code not in codes), str(report.findings)
