# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000005#repo.tests.pytest.required-invocation
# - 001035#repo.workflow.todo-backlog-and-continue-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Contract tests for the Golden coverage terminal summary."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from golden.coverage_summary import main

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

type CoverageLedgerEntryPayload = dict[str, object]

DEFAULT_SCENARIO = "data/agent.blueprint.json"


def test_golden_coverage_summary_prints_counts_for_valid_fixture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid health state prints total, true, and false counts."""
    golden_root = tmp_path / "golden"
    _write_scenario(golden_root, DEFAULT_SCENARIO)
    _write_coverage(golden_root, [_entry(completed=True)])

    exit_code = main(("--root", str(golden_root)))
    output = capsys.readouterr().out

    assert exit_code == 0, output
    _expect_output(output, "health: ok")
    _expect_output(output, "total entries: 1")
    _expect_output(output, "completed: true entries: 1")
    _expect_output(output, "completed: false entries: 0")


def test_golden_coverage_summary_exits_nonzero_for_invalid_health(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Invalid health state returns one and names the finding."""
    golden_root = tmp_path / "golden"
    _write_coverage(golden_root, [_entry()])

    exit_code = main(("--root", str(golden_root)))
    output = capsys.readouterr().out

    assert exit_code == 1, output
    _expect_output(output, "health: failed")
    _expect_output(output, "findings:")
    _expect_output(output, "coverage.scenario_file_missing")


def _entry(*, completed: bool = False) -> CoverageLedgerEntryPayload:
    entry: CoverageLedgerEntryPayload = {
        "title": "Agent",
        "description": "Example scenario.",
        "additional_information": ["Fixture owned by this test."],
        "file": DEFAULT_SCENARIO,
        "completed": completed,
    }
    if completed:
        entry["manual_analysis"] = {
            "reviewed_by": "local-test-operator",
            "reviewed_at": "2026-05-08T00:00:00Z",
            "parity_verdict": "accepted_as_generated",
            "privacy_verdict": "private labels removed or absent",
            "logic_candidate_review": "No missing reusable logic was found.",
            "golden_tool_evidence": [
                "python -m golden.coverage_summary --root <fixture>",
            ],
        }
    return entry


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


def _expect_output(output: str, expected: str) -> None:
    assert not (expected not in output), output
