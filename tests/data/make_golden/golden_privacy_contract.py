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

"""Contract tests for Golden privacy-aware parity filtering."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from golden.comparison import compare_golden_blueprint_texts

if TYPE_CHECKING:
    from golden.comparison import GoldenComparisonReport

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "comparison"
REFERENCE_ACCOUNT_LABEL = "privacy_reference_account_label.json"


def test_privacy_filter_allows_safe_nonfunctional_label_removal() -> None:
    """Safe removal of nonfunctional private account labels can pass parity."""
    report = _privacy_compare(
        reference_fixture=REFERENCE_ACCOUNT_LABEL,
        generated_fixture="privacy_generated_safe_removed.json",
    )

    assert report.completion_allowed, (
        f"Safe private label removal should pass: {report.as_dict()}"
    )
    assert any(
        finding.severity == "info" for finding in report.privacy_findings
    ), f"Privacy info finding missing: {report.as_dict()}"


def test_privacy_filter_rejects_preserved_private_label() -> None:
    """Generated output must not preserve nonfunctional private account.

    labels.
    """
    report = _privacy_compare(
        reference_fixture=REFERENCE_ACCOUNT_LABEL,
        generated_fixture="privacy_generated_preserved_private.json",
    )

    assert not (report.completion_allowed), (
        f"Preserved private label should fail critically: {report.as_dict()}"
    )
    assert not ("privacy_critical" not in report.completion_blockers), (
        f"Privacy critical blocker missing: {report.as_dict()}"
    )
    messages = tuple(finding.message for finding in report.privacy_findings)
    assert any(
        "preserved a nonfunctional private/account label" in item
        for item in messages
    ), f"Generated-output failure message drifted: {messages}"


def test_privacy_filter_does_not_silently_remove_behavior_required_value() -> (
    None
):
    """Behavior-required private-like values remain semantic blockers."""
    report = _privacy_compare(
        reference_fixture="privacy_reference_behavior_required.json",
        generated_fixture="privacy_generated_behavior_removed.json",
    )

    assert not (report.completion_allowed), (
        f"Behavior-required value removal should be blocked: {report.as_dict()}"
    )
    assert not ("semantic_difference" not in report.completion_blockers), (
        f"Behavior removal must remain a semantic difference: "
        f"{report.as_dict()}"
    )
    assert not ("privacy_error" not in report.completion_blockers), (
        f"Behavior-required privacy review blocker missing: {report.as_dict()}"
    )


def test_privacy_filter_does_not_modify_raw_reference_fixture() -> None:
    """Raw Golden-style reference files remain untouched by privacy.

    comparison.
    """
    fixture_path = FIXTURE_ROOT / REFERENCE_ACCOUNT_LABEL
    before = fixture_path.read_text(encoding="utf-8")

    _ = _privacy_compare(
        reference_fixture=REFERENCE_ACCOUNT_LABEL,
        generated_fixture="privacy_generated_safe_removed.json",
    )

    after = fixture_path.read_text(encoding="utf-8")
    assert after == before, (
        "Privacy filter modified the raw Golden reference fixture."
    )


def _privacy_compare(
    *,
    reference_fixture: str,
    generated_fixture: str,
) -> GoldenComparisonReport:
    return compare_golden_blueprint_texts(
        reference_text=_fixture_text(reference_fixture),
        generated_text=_fixture_text(generated_fixture),
        label=generated_fixture,
        enable_privacy_filter=True,
    )


def _fixture_text(filename: str) -> str:
    return (FIXTURE_ROOT / filename).read_text(encoding="utf-8")
