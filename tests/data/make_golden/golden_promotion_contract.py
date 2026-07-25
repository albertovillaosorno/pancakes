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

"""Contract tests for Golden logic candidate promotion."""

from __future__ import annotations

from golden.promotion import (
    GoldenRulePromotionFindingCode,
    GoldenRulePromotionReport,
    GoldenRulePromotionRequest,
    evaluate_golden_rule_promotion,
)


def test_golden_promotion_accepts_evidenced_owned_candidate() -> None:
    """A promotion-ready candidate carries owner, evidence, tests, and ADR.

    path.
    """
    report = evaluate_golden_rule_promotion(_valid_promotion_request())

    assert report.promoted_rule_ready, str(report.findings)
    assert report.owner_path == "src/blueprints/validation/**/*", (
        f"Owner path drifted: {report.owner_path}"
    )


def test_golden_promotion_rejects_ownerless_candidate() -> None:
    """Promoted rules cannot enter the repository without an owner."""
    report = evaluate_golden_rule_promotion(
        _valid_promotion_request()._replace(owner=None)
    )

    _assert_finding(report, "golden.promotion.owner_missing")


def test_golden_promotion_rejects_evidence_free_candidate() -> None:
    """Promoted rules need validation and generalization evidence."""
    report = evaluate_golden_rule_promotion(
        _valid_promotion_request()._replace(
            repeated_pattern_evidence=(),
            authoritative_make_facts=(),
            validation_evidence=(),
        )
    )

    _assert_finding(report, "golden.promotion.generalization_evidence_missing")
    _assert_finding(report, "golden.promotion.validation_evidence_missing")


def test_golden_promotion_rejects_repeated_template_caefec10() -> None:
    """Repeated Golden template patterns are not enough to promote repository.

    logic.
    """
    report = evaluate_golden_rule_promotion(
        _valid_promotion_request()._replace(authoritative_make_facts=())
    )

    _assert_finding(report, "golden.promotion.generalization_evidence_missing")


def test_golden_promotion_rejects_output_gate_without_focused_tests() -> None:
    """A promoted rule needs focused tests before it can gate output."""
    report = evaluate_golden_rule_promotion(
        _valid_promotion_request()._replace(focused_test_paths=())
    )

    _assert_finding(report, "golden.promotion.focused_tests_missing")


def test_golden_promotion_requires_adr_update_for_policy_change() -> None:
    """Durable policy, severity, command, and architecture changes need ADR.

    evidence.
    """
    request = _valid_promotion_request()._replace(adr_update_path=None)
    report = evaluate_golden_rule_promotion(request)

    _assert_finding(report, "golden.promotion.adr_update_missing")


def test_golden_promotion_records_rejected_candidate_a8a4abdd() -> None:
    """Rejected candidates are recorded as local review evidence, not as.

    permanent.

    noise.
    """
    report = evaluate_golden_rule_promotion(
        _valid_promotion_request()._replace(
            disposition="reject",
            disposition_reason=(
                "One fixture-specific label, not reusable behavior."
            ),
            owner=None,
            affected_scenarios=(),
            repeated_pattern_evidence=(),
            validation_evidence=(),
            focused_test_paths=(),
            policy_impact="none",
            adr_update_path=None,
            gates_output=False,
        )
    )

    assert not (report.findings), str(report.findings)
    assert report.recorded_without_durable_noise, (
        f"Rejected candidate should be locally recordable: {report}"
    )
    assert not (report.promoted_rule_ready), (
        f"Rejected candidate must not be promotion-ready: {report}"
    )


def _valid_promotion_request() -> GoldenRulePromotionRequest:
    return GoldenRulePromotionRequest(
        candidate_id="golden.route-filter-labels",
        summary="Route filter labels must survive blueprint regeneration.",
        disposition="promote",
        disposition_reason=None,
        owner="validation",
        affected_scenarios=(
            "data/Lead Router.blueprint.json ",
            "data/Support Router.blueprint.json",
        ),
        repeated_pattern_evidence=(
            "Two Golden routers preserve route filters on regenerated output.",
            "Two Golden routers fail when route filter labels are dropped.",
        ),
        authoritative_make_facts=(
            (
                "Manual LLM review confirmed this is importable Make behavior, "
                "not template-specific logic."
            ),
        ),
        expected_behavior=(
            "Route filter labels remain semantic validation inputs."
        ),
        validation_evidence=(
            "compare_golden_blueprint_texts semantic_parity=True",
        ),
        focused_test_paths=(
            "tests/blueprints/validation/test_route_filter_labels.py",
        ),
        policy_impact="validation_severity",
        adr_update_path="docs/adr/blueprint-validator-policy.md",
        gates_output=True,
    )


def _assert_finding(
    report: GoldenRulePromotionReport,
    expected_code: GoldenRulePromotionFindingCode,
) -> None:
    codes = {finding.code for finding in report.findings}
    assert not (expected_code not in codes), str(report.findings)
