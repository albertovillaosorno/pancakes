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

"""Contract tests for the offline Golden batch runner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from golden.batch import GoldenCandidate, run_golden_batch

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from golden.coverage import CoverageEntry

type CoverageLedgerEntryPayload = dict[str, object]

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "comparison"
REFERENCE_TEXT = (FIXTURE_ROOT / "reference_router.json").read_text(
    encoding="utf-8"
)
CHANGED_MAPPING_TEXT = (FIXTURE_ROOT / "changed_mapping_router.json").read_text(
    encoding="utf-8"
)


class StaticCandidateProvider:
    """Return local fixture candidates without live service access."""

    def __init__(self, candidates: dict[str, str]) -> None:
        """Store candidate text by coverage entry title."""
        self.candidates = candidates
        self.requested_titles: list[str] = []

    def candidate_for(self, entry: CoverageEntry) -> GoldenCandidate:
        """Return the candidate fixture for one entry."""
        self.requested_titles.append(entry.title)
        return GoldenCandidate(blueprint_text=self.candidates[entry.title])


def test_golden_batch_processes_all_safe_incomplete_entries(
    tmp_path: Path,
) -> None:
    """Two safe incomplete entries both complete in one local batch."""
    golden_root = _golden_root(tmp_path)
    _write_golden_entry(golden_root, "First Agent", "data/first.blueprint.json")
    _write_golden_entry(
        golden_root, "Second Agent", "data/second.blueprint.json"
    )
    _write_coverage(
        golden_root,
        [
            _coverage_entry("First Agent", "data/first.blueprint.json"),
            _coverage_entry("Second Agent", "data/second.blueprint.json"),
        ],
    )
    provider = StaticCandidateProvider(
        {
            "First Agent": REFERENCE_TEXT,
            "Second Agent": REFERENCE_TEXT,
        }
    )

    report = run_golden_batch(
        repo_root=repo_root(),
        golden_root=golden_root,
        candidate_provider=provider,
    )

    assert report.processed_titles == ("First Agent", "Second Agent"), (
        f"Batch did not process both safe entries: {report}"
    )
    assert not (report.stopped_title is not None), (
        f"Batch should not have stopped early: {report}"
    )
    assert provider.requested_titles == ["First Agent", "Second Agent"], (
        f"Provider call order drifted: {provider.requested_titles}"
    )


def test_golden_batch_stops_on_deterministic_mismatch(tmp_path: Path) -> None:
    """The first semantic mismatch stops the batch with diagnostics."""
    golden_root = _golden_root(tmp_path)
    _write_golden_entry(golden_root, "Safe Agent", "data/safe.blueprint.json")
    _write_golden_entry(
        golden_root, "Mismatch Agent", "data/mismatch.blueprint.json"
    )
    _write_coverage(
        golden_root,
        [
            _coverage_entry("Safe Agent", "data/safe.blueprint.json"),
            _coverage_entry("Mismatch Agent", "data/mismatch.blueprint.json"),
        ],
    )
    provider = StaticCandidateProvider(
        {
            "Safe Agent": REFERENCE_TEXT,
            "Mismatch Agent": CHANGED_MAPPING_TEXT,
        }
    )

    report = run_golden_batch(
        repo_root=repo_root(),
        golden_root=golden_root,
        candidate_provider=provider,
    )

    assert report.processed_titles == ("Safe Agent",), (
        f"Batch should process only the safe entry first: {report}"
    )
    assert report.stopped_title == "Mismatch Agent", (
        f"Batch stopped on the wrong entry: {report}"
    )
    assert report.stop_reason == "semantic_difference", (
        f"Batch did not expose the semantic stop reason: {report}"
    )


def test_golden_batch_refuses_ledger_file_disagreement(tmp_path: Path) -> None:
    """Coverage health failures prevent any reconstruction provider call."""
    golden_root = _golden_root(tmp_path)
    _write_coverage(
        golden_root,
        [_coverage_entry("Missing Agent", "data/missing.blueprint.json")],
    )
    provider = StaticCandidateProvider({"Missing Agent": REFERENCE_TEXT})

    report = run_golden_batch(
        repo_root=repo_root(),
        golden_root=golden_root,
        candidate_provider=provider,
    )

    assert not (report.started), (
        f"Batch should refuse unhealthy coverage: {report}"
    )
    assert report.stop_reason == "coverage_health_failed", (
        f"Unexpected coverage stop reason: {report}"
    )
    if provider.requested_titles:
        message = (
            f"Provider called after ledger drift: {provider.requested_titles}"
        )
        assert not (provider.requested_titles), message


def _golden_root(tmp_path: Path) -> Path:
    return tmp_path / "golden"


def _write_golden_entry(
    golden_root: Path, _title: str, relative_path: str
) -> None:
    scenario_path = golden_root / relative_path
    scenario_path.parent.mkdir(parents=True, exist_ok=True)
    _ = scenario_path.write_text(REFERENCE_TEXT, encoding="utf-8")


def _coverage_entry(
    title: str, relative_path: str
) -> CoverageLedgerEntryPayload:
    return {
        "title": title,
        "description": "Synthetic Golden batch fixture.",
        "additional_information": ["Local test fixture."],
        "file": relative_path,
        "completed": False,
    }


def _write_coverage(
    golden_root: Path, entries: list[CoverageLedgerEntryPayload]
) -> None:
    golden_root.mkdir(parents=True, exist_ok=True)
    _ = (golden_root / "coverage.json").write_text(
        json.dumps(entries, indent=2),
        encoding="utf-8",
    )
