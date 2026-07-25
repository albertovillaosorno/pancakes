# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for Make linter candidate intake policy.

Boundary contract:
- Owns: typed candidate decision records and review-contract validation.
- Must not: implement candidate rules, read completed TODO archives, or inspect
  customer blueprints.
- Allows: synthetic review records that prove the intake gate is fail-closed.
- Split when: candidate decision persistence becomes a dedicated registry.
- Merge when: linter taxonomy tests own the same intake gate behavior.
"""

from __future__ import annotations

from blueprints.validation import (
    MAKE_LINTER_CANDIDATE_DECISIONS,
    MAKE_LINTER_PROMOTION_AUDIENCES,
    MAKE_LINTER_PROMOTION_READINESS_REQUIRED_FIELDS,
    MAKE_LINTER_PROMOTION_SURFACES,
    MAKE_LINTER_REVIEW_REQUIRED_FIELDS,
    MakeLinterCandidateReviewRecord,
    MakeLinterPromotionReadinessRecord,
    make_linter_intake_requirements,
    make_linter_promotion_readiness_errors,
    make_linter_review_record_errors,
)


def test_linter_intake_decisions_are_closed_and_manual() -> None:
    """The intake gate exposes only the reviewed decision vocabulary."""
    expected = (
        "accept",
        "rewrite",
        "downgrade",
        "quarantine",
        "reject",
        "alias_to_canonical",
    )

    assert expected == MAKE_LINTER_CANDIDATE_DECISIONS, (
        f"Linter candidate decisions drifted: {MAKE_LINTER_CANDIDATE_DECISIONS}"
    )

    requirements = {
        requirement.requirement_id: requirement
        for requirement in make_linter_intake_requirements()
    }
    for requirement_id in (
        "one-by-one-review",
        "no-origin-trust",
        "closed-decision-set",
        "deterministic-predicate",
        "proof-fixtures",
        "canonical-guard-path",
        "launch-audience",
        "severity-correction",
        "no-silent-delete",
    ):
        assert not (requirement_id not in requirements), (
            f"Mandatory intake requirement is missing: {requirement_id}"
        )


def test_linter_review_record_has_no_optional_field_defaults() -> None:
    """A review row states every truncation-prone decision field."""
    if MakeLinterCandidateReviewRecord._field_defaults:
        defaults = MakeLinterCandidateReviewRecord._field_defaults
        assert not (MakeLinterCandidateReviewRecord._field_defaults), (
            "Linter candidate review records must not have default fields: "
            f"{defaults}"
        )
    assert (
        MakeLinterCandidateReviewRecord._fields
        == MAKE_LINTER_REVIEW_REQUIRED_FIELDS
    ), "The exported required field list drifted from the review record shape."
    assert (
        MakeLinterPromotionReadinessRecord._fields
        == MAKE_LINTER_PROMOTION_READINESS_REQUIRED_FIELDS
    ), "The exported promotion readiness fields drifted from record shape."


def test_linter_promotion_surfaces_and_audiences_cover_launch() -> None:
    """Promotion readiness records name launch surfaces and outputs."""
    assert MAKE_LINTER_PROMOTION_SURFACES == (
        "error_handler",
        "filter",
        "router",
        "iterator",
        "aggregator",
        "data_store",
        "webhook",
        "http",
        "cost",
        "security",
        "destructive_action",
    )
    assert MAKE_LINTER_PROMOTION_AUDIENCES == (
        "public_demo_aggregate_score",
        "paid_report",
        "internal_repair",
        "advisory_only",
    )


def test_accepted_linter_candidate_requires_evidence() -> None:
    """A promoted rule needs evidence, owner, and proof fixtures."""
    record = _base_record()._replace(
        decision="accept",
        canonical_rule_code=None,
        evidence_surfaces=(),
        deterministic_predicate="",
        implementation_owner="docs/todo/queue/0016.md",
        failing_fixture_plan="",
        passing_fixture_plan="",
        false_positive_risk="",
    )

    errors = make_linter_review_record_errors(record)
    expected_errors = {
        "promoted decision requires evidence_surfaces",
        "deterministic_predicate is required",
        "canonical_rule_code is required",
        "implementation_owner must be a source path",
        "failing_fixture_plan is required",
        "passing_fixture_plan is required",
        "false_positive_risk is required",
    }
    assert expected_errors.issubset(set(errors)), (
        f"Promoted rule intake did not fail closed: {errors}"
    )


def test_valid_rewritten_linter_candidate_passes_intake_policy() -> None:
    """A fully reviewed rewritten candidate has no intake-policy errors."""
    record = _base_record()._replace(
        decision="rewrite",
        canonical_rule_code="http.parse_response_missing",
        evidence_surfaces=("ast_structure", "validation_fixture"),
        deterministic_predicate=(
            "HTTP requests that expect JSON must enable parse response."
        ),
        implementation_owner="src/blueprints/validation/validator.py",
        failing_fixture_plan=(
            "Fixture with JSON HTTP response and parse response disabled."
        ),
        passing_fixture_plan=(
            "Fixture with JSON HTTP response and parse response enabled."
        ),
        false_positive_risk=(
            "Keep warning severity because response semantics can be external."
        ),
    )

    errors = make_linter_review_record_errors(record)

    assert not (errors), (
        f"Valid rewritten candidate failed intake policy: {errors}"
    )


def test_promoted_linter_candidate_requires_quarantine() -> None:
    """A promoted rule needs quarantine evidence and test paths."""
    record = _promotion_record()._replace(
        canonical_guard_path="docs/manual-note.md",
        focused_test_path="src/blueprints/validation/validator.py",
        promotion_audiences=(),
        promotion_surfaces=(),
        quarantine_evidence_path="ai://unreviewed-observation",
        technical_justification="",
    )

    errors = make_linter_promotion_readiness_errors(record)

    expected_errors = {
        "promoted readiness requires promotion_surfaces",
        "promoted readiness requires promotion_audiences",
        (
            "quarantine_evidence_path must point at linter quarantine "
            "or decision data"
        ),
        "canonical_guard_path must be reachable from source or tests",
        "focused_test_path must be a test path",
        "technical_justification is required",
    }
    assert expected_errors.issubset(set(errors)), (
        f"Promotion readiness did not fail closed: {errors}"
    )


def test_promoted_linter_candidate_records_launch_audience() -> None:
    """A valid readiness row records launch use and severity changes."""
    record = _promotion_record()._replace(
        promotion_audiences=(
            "public_demo_aggregate_score",
            "paid_report",
            "internal_repair",
        ),
        promotion_surfaces=("webhook", "security", "cost"),
        severity_transition="lower",
        false_positive_justification=(
            "Webhook timeout risk is warning-grade unless runtime duration "
            "evidence is present."
        ),
    )

    errors = make_linter_promotion_readiness_errors(record)

    assert not errors, (
        f"Valid promotion readiness row failed intake policy: {errors}"
    )


def test_advisory_only_promotion_stays_separate() -> None:
    """Advisory-only guidance stays separate from active outputs."""
    mixed_audience_errors = make_linter_promotion_readiness_errors(
        _promotion_record()._replace(
            promotion_audiences=("advisory_only", "paid_report"),
        )
    )
    missing_severity_reason_errors = make_linter_promotion_readiness_errors(
        _promotion_record()._replace(
            false_positive_justification=None,
            severity_transition="lower",
        )
    )

    assert not (
        "advisory_only cannot be combined with active promotion audiences"
        not in mixed_audience_errors
    ), (
        "Advisory-only audience mixed with active outputs: "
        f"{mixed_audience_errors}"
    )
    assert not (
        "false_positive_justification is required"
        not in missing_severity_reason_errors
    ), (
        "Severity lowering did not require a false-positive justification: "
        f"{missing_severity_reason_errors}"
    )


def test_profile_error_linter_candidate_requires_profile_gate() -> None:
    """Profile-only errors must name the profile that makes the rule fatal."""
    record = _base_record()._replace(
        decision="accept",
        canonical_rule_code="webhook.security_signature_missing",
        evidence_surfaces=("ast_structure", "metadata", "validation_fixture"),
        deterministic_predicate=(
            "Public webhook profile requires signature verification metadata."
        ),
        severity_posture="profile_error",
        profile_gates=(),
        implementation_owner="src/blueprints/validation/validator.py",
        failing_fixture_plan=(
            "Public webhook fixture without signature metadata."
        ),
        passing_fixture_plan="Public webhook fixture with signature metadata.",
        false_positive_risk="Only fatal under public_webhook profile.",
    )

    errors = make_linter_review_record_errors(record)

    assert not ("profile_error requires profile_gates" not in errors), (
        f"Profile-gated error did not require a profile gate: {errors}"
    )


def test_terminal_decisions_need_successor_or_reason() -> None:
    """Non-promoted decisions preserve traceability."""
    alias_errors = make_linter_review_record_errors(
        _base_record()._replace(
            decision="alias_to_canonical",
            canonical_rule_code=None,
            alias_of_candidate_id=None,
        )
    )
    quarantine_errors = make_linter_review_record_errors(
        _base_record()._replace(
            decision="quarantine",
            severity_posture="warning",
            quarantine_reason=None,
        )
    )
    reject_errors = make_linter_review_record_errors(
        _base_record()._replace(
            decision="reject",
            rejection_reason=None,
        )
    )

    assert not (
        "alias_to_canonical requires canonical_rule_code "
        "or alias_of_candidate_id" not in alias_errors
    ), f"Alias decision did not require a canonical successor: {alias_errors}"
    if {
        "quarantine_reason is required",
        "quarantine decision requires quarantine severity posture",
    }.difference(quarantine_errors):
        message = (
            "Quarantine decision did not require a reason and posture: "
            f"{quarantine_errors}"
        )
        assert not (
            {
                "quarantine_reason is required",
                "quarantine decision requires quarantine severity posture",
            }.difference(quarantine_errors)
        ), message
    assert not ("rejection_reason is required" not in reject_errors), (
        f"Reject decision did not require a reason: {reject_errors}"
    )


def _base_record() -> MakeLinterCandidateReviewRecord:
    return MakeLinterCandidateReviewRecord(
        candidate_id="SEC-001",
        source_file="02_security_ingress_http.md",
        original_heading="SEC-001 - Example candidate",
        decision="rewrite",
        canonical_rule_code="semantic.trigger_position_invalid",
        alias_of_candidate_id=None,
        evidence_surfaces=("ast_structure",),
        deterministic_predicate="Top-level trigger-like modules must be first.",
        severity_posture="error",
        profile_gates=(),
        implementation_owner="src/blueprints/validation/validator.py",
        failing_fixture_plan="Fixture with trigger after a non-trigger module.",
        passing_fixture_plan=(
            "Fixture with trigger as the first top-level module."
        ),
        adr_impact="ADR 001079 already owns the intake gate.",
        bibliography_impact=(
            "No external source needed for this synthetic fixture."
        ),
        false_positive_risk=(
            "Uses deterministic module placement evidence only."
        ),
        quarantine_reason=None,
        rejection_reason=None,
        rationale=(
            "Manual review converted the source candidate into a "
            "deterministic decision."
        ),
    )


def _promotion_record() -> MakeLinterPromotionReadinessRecord:
    return MakeLinterPromotionReadinessRecord(
        candidate_id="SEC-001",
        source_file="src/blueprints/validation/data/linter/quarantine/security/secure-001.md",
        decision="rewrite",
        promotion_surfaces=("webhook", "security"),
        promotion_audiences=("paid_report", "internal_repair"),
        quarantine_evidence_path=(
            "src/blueprints/validation/data/linter/quarantine/security/secure-001.md"
        ),
        canonical_guard_path="src/blueprints/validation/validator.py",
        focused_test_path="tests/blueprints/validation/blueprint_validation_contract.py",
        severity_transition="unchanged",
        technical_justification=(
            "Local AST evidence and focused fixtures support the rule."
        ),
        false_positive_justification=None,
    )
