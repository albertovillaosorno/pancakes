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

"""Contract tests for Golden mismatch triage discipline."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from golden.comparison import compare_golden_blueprint_texts
from golden.mismatch import triage_golden_mismatch

if TYPE_CHECKING:
    from golden.comparison import GoldenComparisonReport

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "comparison"


def test_golden_mismatch_routes_mapping_change_to_shared_owner() -> None:
    """Mapping mismatches route to shared compilation ownership."""
    triage = triage_golden_mismatch(_changed_mapping_report())
    owners = {decision.owner for decision in triage.decisions}

    assert not ("compilation" not in owners), (
        f"Mapping mismatch did not route to compilation: {triage}"
    )
    assert any(
        "src/blueprints" in decision.owner_path for decision in triage.decisions
    ), f"Shared owner path missing from triage: {triage}"


def test_golden_mismatch_rejects_scenario_specific_shortcut_by_default() -> (
    None
):
    """Scenario-specific patches are not the normal mismatch path."""
    triage = triage_golden_mismatch(_changed_mapping_report())

    assert not (triage.scenario_specific_patch_allowed), (
        f"Scenario-specific shortcut should be rejected: {triage}"
    )
    assert not (
        any(
            decision.owner == "proven_scenario_outlier"
            for decision in triage.decisions
        )
    ), f"Outlier owner should require explicit evidence: {triage}"


def test_golden_mismatch_allows_outlier_only_with_explicit_evidence() -> None:
    """Proven outlier handling must carry explicit evidence."""
    triage = triage_golden_mismatch(
        _changed_mapping_report(),
        outlier_evidence=(
            "Documented in docs/todo/pending/golden-outlier-example.md."
        ),
    )

    assert triage.scenario_specific_patch_allowed, (
        f"Outlier evidence should allow scenario-specific handling: {triage}"
    )
    assert triage.outlier_evidence is not None, (
        f"Outlier evidence was not preserved: {triage}"
    )
    assert any(
        decision.owner == "proven_scenario_outlier"
        for decision in triage.decisions
    ), f"Outlier owner decision missing: {triage}"


def _changed_mapping_report() -> GoldenComparisonReport:
    return compare_golden_blueprint_texts(
        reference_text=_fixture_text("reference_router.json"),
        generated_text=_fixture_text("changed_mapping_router.json"),
        label="changed-mapping",
    )


def _fixture_text(filename: str) -> str:
    return (FIXTURE_ROOT / filename).read_text(encoding="utf-8")
