# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001032#repo.quality.no-silly-linter-bypasses
# - 001035#repo.workflow.todo-backlog-and-continue-contract
# - 001046#repo.blueprint-validation.findings-model
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Manual intake contract for Make linter candidate rules.

Boundary contract:
- Owns: candidate-review decisions, required evidence fields, and local
  validation of review ledger rows before a linter candidate can be promoted.
- Must not: emit blueprint validation findings, accept a candidate by itself,
  contact Make.com, or read the imported candidate backlog.
- Allows: deterministic checks over already-authored review ledger records.
- Split when: linter rule decisions need persistent storage or a migration tool.
- Merge when: another validation module owns this exact intake policy.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

type MakeLinterCandidateDecision = Literal[
    "accept ",
    "rewrite ",
    "downgrade ",
    "quarantine ",
    "reject ",
    "alias_to_canonical",
]
type MakeLinterEvidenceSurface = Literal[
    "adr_policy ",
    "allowlist ",
    "ast_structure ",
    "catalog_truth ",
    "connection_reference ",
    "denylist ",
    "knowledge_store ",
    "local_failure ",
    "mapping_ast ",
    "metadata ",
    "note_surface ",
    "promoted_golden_evidence ",
    "raw_spec_field ",
    "topology ",
    "validation_fixture",
]
type MakeLinterSeverityPosture = Literal[
    "error ",
    "warning ",
    "profile_error ",
    "optimization ",
    "quarantine",
]
type MakeLinterProfileGate = Literal[
    "agency_strict ",
    "customer_facing_api ",
    "etl_strict ",
    "financial ",
    "high_volume ",
    "llm_cost_sensitive ",
    "mission_critical ",
    "pii ",
    "production ",
    "public_webhook ",
    "regulated ",
    "sync ",
    "tier_1",
]
type MakeLinterPromotionAudience = Literal[
    "public_demo_aggregate_score ",
    "paid_report ",
    "internal_repair ",
    "advisory_only",
]
type MakeLinterPromotionSurface = Literal[
    "error_handler ",
    "filter ",
    "router ",
    "iterator ",
    "aggregator ",
    "data_store ",
    "webhook ",
    "http ",
    "cost ",
    "security ",
    "destructive_action",
]
type MakeLinterSeverityTransition = Literal[
    "unchanged ",
    "raise ",
    "lower ",
    "advisory_only",
]


class MakeLinterIntakeRequirement(NamedTuple):
    """One required review posture for linter candidate intake."""

    requirement_id: str
    summary: str
    enforcement_surface: str


class MakeLinterCandidateReviewRecord(NamedTuple):
    """One fully reviewed candidate-rule decision row."""

    candidate_id: str
    source_file: str
    original_heading: str
    decision: MakeLinterCandidateDecision
    canonical_rule_code: str | None
    alias_of_candidate_id: str | None
    evidence_surfaces: tuple[MakeLinterEvidenceSurface, ...]
    deterministic_predicate: str
    severity_posture: MakeLinterSeverityPosture
    profile_gates: tuple[MakeLinterProfileGate, ...]
    implementation_owner: str
    failing_fixture_plan: str
    passing_fixture_plan: str
    adr_impact: str
    bibliography_impact: str
    false_positive_risk: str
    quarantine_reason: str | None
    rejection_reason: str | None
    rationale: str


class MakeLinterPromotionReadinessRecord(NamedTuple):
    """One pre-implementation promotion gate for an already reviewed.

    candidate.
    """

    candidate_id: str
    source_file: str
    decision: MakeLinterCandidateDecision
    promotion_surfaces: tuple[MakeLinterPromotionSurface, ...]
    promotion_audiences: tuple[MakeLinterPromotionAudience, ...]
    quarantine_evidence_path: str
    canonical_guard_path: str
    focused_test_path: str
    severity_transition: MakeLinterSeverityTransition
    technical_justification: str
    false_positive_justification: str | None


MAKE_LINTER_CANDIDATE_DECISIONS: Final[
    tuple[MakeLinterCandidateDecision, ...]
] = (
    "accept ",
    "rewrite ",
    "downgrade ",
    "quarantine ",
    "reject ",
    "alias_to_canonical",
)
MAKE_LINTER_EVIDENCE_SURFACES: Final[tuple[MakeLinterEvidenceSurface, ...]] = (
    "adr_policy ",
    "allowlist ",
    "ast_structure ",
    "catalog_truth ",
    "connection_reference ",
    "denylist ",
    "knowledge_store ",
    "local_failure ",
    "mapping_ast ",
    "metadata ",
    "note_surface ",
    "promoted_golden_evidence ",
    "raw_spec_field ",
    "topology ",
    "validation_fixture",
)
MAKE_LINTER_SEVERITY_POSTURES: Final[tuple[MakeLinterSeverityPosture, ...]] = (
    "error ",
    "warning ",
    "profile_error ",
    "optimization ",
    "quarantine",
)
MAKE_LINTER_PROFILE_GATES: Final[tuple[MakeLinterProfileGate, ...]] = (
    "agency_strict ",
    "customer_facing_api ",
    "etl_strict ",
    "financial ",
    "high_volume ",
    "llm_cost_sensitive ",
    "mission_critical ",
    "pii ",
    "production ",
    "public_webhook ",
    "regulated ",
    "sync ",
    "tier_1",
)
MAKE_LINTER_PROMOTION_AUDIENCES: Final[
    tuple[MakeLinterPromotionAudience, ...]
] = (
    "public_demo_aggregate_score ",
    "paid_report ",
    "internal_repair ",
    "advisory_only",
)
MAKE_LINTER_PROMOTION_SURFACES: Final[
    tuple[MakeLinterPromotionSurface, ...]
] = (
    "error_handler ",
    "filter ",
    "router ",
    "iterator ",
    "aggregator ",
    "data_store ",
    "webhook ",
    "http ",
    "cost ",
    "security ",
    "destructive_action",
)
MAKE_LINTER_SEVERITY_TRANSITIONS: Final[
    tuple[MakeLinterSeverityTransition, ...]
] = (
    "unchanged ",
    "raise ",
    "lower ",
    "advisory_only",
)
MAKE_LINTER_REVIEW_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    MakeLinterCandidateReviewRecord._fields
)
MAKE_LINTER_PROMOTION_READINESS_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    MakeLinterPromotionReadinessRecord._fields
)
MAKE_LINTER_PROMOTED_DECISIONS: Final[frozenset[str]] = frozenset(
    ("accept", "rewrite", "downgrade")
)
MAKE_LINTER_INTAKE_REQUIREMENTS: Final[
    tuple[MakeLinterIntakeRequirement, ...]
] = (
    MakeLinterIntakeRequirement(
        requirement_id="one-by-one-review",
        summary=(
            "Inspect each candidate ID manually before any decision isrecorded."
        ),
        enforcement_surface="family TODO completion ledger",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="no-origin-trust",
        summary=(
            "Generated or model-expanded candidates are not accepted "
            "because of "
            "their origin."
        ),
        enforcement_surface="ADR 001079 and family TODO tests",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="closed-decision-set",
        summary=(
            "Every candidate decision is accept, rewrite, downgrade, "
            "quarantine, reject, "
            "or alias_to_canonical."
        ),
        enforcement_surface="typed review record",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="deterministic-predicate",
        summary=(
            "Promoted rules require a local deterministic predicate and "
            "evidence surface."
        ),
        enforcement_surface="review record validation",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="proof-fixtures",
        summary=(
            "Promoted rules require failing and passing fixture plans before "
            "implementation."
        ),
        enforcement_surface="family TODO validation",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="canonical-guard-path",
        summary=(
            "Promoted rules require a reusable guard or focused test in "
            "canonical validation."
        ),
        enforcement_surface="promotion readiness record",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="launch-audience",
        summary=(
            "Promotion records whether the rule supports public demo aggregate "
            "scoring, "
            "paid reports, internal repair, or advisory-only guidance."
        ),
        enforcement_surface="promotion readiness record",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="severity-correction",
        summary=(
            "Severity lowering requires a technical false-positive "
            "justification."
        ),
        enforcement_surface="promotion readiness record",
    ),
    MakeLinterIntakeRequirement(
        requirement_id="no-silent-delete",
        summary=(
            "Rejected or duplicate candidates stay recorded with a reason or "
            "canonical alias."
        ),
        enforcement_surface="completion ledger",
    ),
)


def make_linter_intake_requirements() -> tuple[
    MakeLinterIntakeRequirement, ...
]:
    """Return the mandatory candidate-intake requirements."""
    return MAKE_LINTER_INTAKE_REQUIREMENTS


def make_linter_review_record_errors(
    record: MakeLinterCandidateReviewRecord,
) -> tuple[str, ...]:
    """Return review-contract errors for one candidate decision row."""
    errors: list[str] = []
    _require_text(errors, "candidate_id", record.candidate_id)
    _require_text(errors, "source_file", record.source_file)
    _require_text(errors, "original_heading", record.original_heading)
    _require_text(errors, "rationale", record.rationale)
    _require_known_value(
        errors,
        "decision",
        record.decision,
        MAKE_LINTER_CANDIDATE_DECISIONS,
    )
    _require_known_value(
        errors,
        "severity_posture",
        record.severity_posture,
        MAKE_LINTER_SEVERITY_POSTURES,
    )
    _validate_evidence_surfaces(errors, record)
    _validate_profile_gates(errors, record)
    if record.decision in MAKE_LINTER_PROMOTED_DECISIONS:
        _validate_promoted_decision(errors, record)
    if record.decision == "alias_to_canonical":
        _validate_alias_decision(errors, record)
    if record.decision == "quarantine":
        _validate_quarantine_decision(errors, record)
    if record.decision == "reject":
        _validate_reject_decision(errors, record)
    return tuple(errors)


def make_linter_promotion_readiness_errors(
    record: MakeLinterPromotionReadinessRecord,
) -> tuple[str, ...]:
    """Return promotion-gate errors before a reviewed linter candidate can.

    change code.
    """
    errors: list[str] = []
    _require_text(errors, "candidate_id", record.candidate_id)
    _require_text(errors, "source_file", record.source_file)
    _require_known_value(
        errors,
        "decision",
        record.decision,
        MAKE_LINTER_CANDIDATE_DECISIONS,
    )
    _require_known_value(
        errors,
        "severity_transition",
        record.severity_transition,
        MAKE_LINTER_SEVERITY_TRANSITIONS,
    )
    _validate_promotion_surfaces(errors, record)
    _validate_promotion_audiences(errors, record)
    if record.decision in MAKE_LINTER_PROMOTED_DECISIONS:
        _validate_promoted_readiness(errors, record)
    return tuple(errors)


def _validate_promoted_decision(
    errors: list[str],
    record: MakeLinterCandidateReviewRecord,
) -> None:
    if not record.evidence_surfaces:
        errors.append("promoted decision requires evidence_surfaces")
    _require_text(
        errors, "deterministic_predicate", record.deterministic_predicate
    )
    _require_text(errors, "canonical_rule_code", record.canonical_rule_code)
    _require_source_owner(errors, record.implementation_owner)
    _require_text(errors, "failing_fixture_plan", record.failing_fixture_plan)
    _require_text(errors, "passing_fixture_plan", record.passing_fixture_plan)
    _require_text(errors, "adr_impact", record.adr_impact)
    _require_text(errors, "bibliography_impact", record.bibliography_impact)
    _require_text(errors, "false_positive_risk", record.false_positive_risk)
    if record.severity_posture == "quarantine":
        errors.append(
            "promoted decision cannot use quarantine severity posture"
        )


def _validate_promoted_readiness(
    errors: list[str],
    record: MakeLinterPromotionReadinessRecord,
) -> None:
    if not record.promotion_surfaces:
        errors.append("promoted readiness requires promotion_surfaces")
    if not record.promotion_audiences:
        errors.append("promoted readiness requires promotion_audiences")
    _require_quarantine_evidence_path(errors, record.quarantine_evidence_path)
    _require_canonical_guard_path(errors, record.canonical_guard_path)
    _require_focused_test_path(errors, record.focused_test_path)
    _require_text(
        errors, "technical_justification", record.technical_justification
    )
    if record.severity_transition == "lower":
        _require_text(
            errors,
            "false_positive_justification",
            record.false_positive_justification,
        )


def _validate_alias_decision(
    errors: list[str],
    record: MakeLinterCandidateReviewRecord,
) -> None:
    if not _has_text(record.canonical_rule_code) and not _has_text(
        record.alias_of_candidate_id
    ):
        errors.append(
            "alias_to_canonical requires canonical_rule_code or "
            "alias_of_candidate_id"
        )
    _require_text(errors, "rationale", record.rationale)


def _validate_quarantine_decision(
    errors: list[str],
    record: MakeLinterCandidateReviewRecord,
) -> None:
    _require_text(errors, "quarantine_reason", record.quarantine_reason)
    if record.severity_posture != "quarantine":
        errors.append(
            "quarantine decision requires quarantine severity posture"
        )


def _validate_reject_decision(
    errors: list[str],
    record: MakeLinterCandidateReviewRecord,
) -> None:
    _require_text(errors, "rejection_reason", record.rejection_reason)


def _validate_evidence_surfaces(
    errors: list[str],
    record: MakeLinterCandidateReviewRecord,
) -> None:
    allowed_surfaces = frozenset(MAKE_LINTER_EVIDENCE_SURFACES)
    unknown_surfaces = tuple(
        surface
        for surface in record.evidence_surfaces
        if surface not in allowed_surfaces
    )
    if unknown_surfaces:
        errors.append(f"unknown evidence_surfaces: {unknown_surfaces}")


def _validate_profile_gates(
    errors: list[str],
    record: MakeLinterCandidateReviewRecord,
) -> None:
    allowed_gates = frozenset(MAKE_LINTER_PROFILE_GATES)
    unknown_gates = tuple(
        gate for gate in record.profile_gates if gate not in allowed_gates
    )
    if unknown_gates:
        errors.append(f"unknown profile_gates: {unknown_gates}")
    if record.severity_posture == "profile_error" and not record.profile_gates:
        errors.append("profile_error requires profile_gates")


def _validate_promotion_surfaces(
    errors: list[str],
    record: MakeLinterPromotionReadinessRecord,
) -> None:
    allowed_surfaces = frozenset(MAKE_LINTER_PROMOTION_SURFACES)
    unknown_surfaces = tuple(
        surface
        for surface in record.promotion_surfaces
        if surface not in allowed_surfaces
    )
    if unknown_surfaces:
        errors.append(f"unknown promotion_surfaces: {unknown_surfaces}")


def _validate_promotion_audiences(
    errors: list[str],
    record: MakeLinterPromotionReadinessRecord,
) -> None:
    allowed_audiences = frozenset(MAKE_LINTER_PROMOTION_AUDIENCES)
    unknown_audiences = tuple(
        audience
        for audience in record.promotion_audiences
        if audience not in allowed_audiences
    )
    if unknown_audiences:
        errors.append(f"unknown promotion_audiences: {unknown_audiences}")
    if (
        "advisory_only" in record.promotion_audiences
        and len(frozenset(record.promotion_audiences)) > 1
    ):
        errors.append(
            "advisory_only cannot be combined with active promotion audiences"
        )


def _require_source_owner(errors: list[str], value: str) -> None:
    _require_text(errors, "implementation_owner", value)
    if _has_text(value) and not value.startswith("src/"):
        errors.append("implementation_owner must be a source path")


def _require_quarantine_evidence_path(errors: list[str], value: str) -> None:
    _require_text(errors, "quarantine_evidence_path", value)
    if _has_text(value) and not value.startswith(
        "src/blueprints/validation/data/linter/"
    ):
        errors.append(
            "quarantine_evidence_path must point at linter quarantine or "
            "decision data"
        )


def _require_canonical_guard_path(errors: list[str], value: str) -> None:
    _require_text(errors, "canonical_guard_path", value)
    if _has_text(value) and not value.startswith(("src/", "tests/")):
        errors.append(
            "canonical_guard_path must be reachable from source or tests"
        )


def _require_focused_test_path(errors: list[str], value: str) -> None:
    _require_text(errors, "focused_test_path", value)
    if _has_text(value) and not value.startswith("tests/"):
        errors.append("focused_test_path must be a test path")


def _require_text(
    errors: list[str], field_name: str, value: str | None
) -> None:
    if not _has_text(value):
        errors.append(f"{field_name} is required")


def _require_known_value(
    errors: list[str],
    field_name: str,
    value: str,
    allowed_values: tuple[str, ...],
) -> None:
    if value not in frozenset(allowed_values):
        errors.append(f"{field_name} has unsupported value {value!r}")


def _has_text(value: str | None) -> bool:
    return value is not None and bool(value.strip())
