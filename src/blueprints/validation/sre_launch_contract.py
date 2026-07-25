# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001061#repo.delivery.client-ready-handoff-contract
# - 001075#repo.client-blueprint-intake.shape-secret-identifier-gates
# - 001077#repo.client-safe-audit-report.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Schoenwald SRE launch contract mirrored from the public web promise.

Boundary contract:
- Owns: deterministic backend launch promises for maintenance,
  refunds, referrals, and release record lookup safety.
- Must not: process payments, call providers, expose customer records,
  or claim certification.
- Allows: fail-closed decisions over redacted order, subscription,
  and release metadata.
- Split when: a live billing adapter or release ledger becomes separate.
- Merge when: another slice duplicates the same public decisions.
"""

from __future__ import annotations

import re
from typing import Final, Literal, NamedTuple, cast

type SreChangeClassification = Literal[
    "included_standard_change",
    "paid_extra_standard_change",
    "requires_extra_standard_change_order",
    "requires_major_change_order",
    "requires_additional_scenario_order",
    "requires_custom_tool_order",
]
type SreReleaseCertificateStatus = Literal[
    "active", "expired", "revoked", "superseded"
]
type JsonObject = dict[str, object]

PRO_CHANGE_PAID_PERIOD_CADENCE: Final = 3
RELEASE_CERTIFICATE_STATUSES: Final[frozenset[str]] = frozenset(
    ("active", "expired", "revoked", "superseded")
)
RELEASE_CERTIFICATE_LOOKUP_FIELDS: Final = (
    "status",
    "release_baseline",
    "package_family",
    "support_or_subscription_status",
)
FORBIDDEN_PUBLIC_TEXT_PATTERN_TEXT: Final = r"@|\b(?:api[_-]?key|ast|bearer|blueprint json|client[_-]?secret|internal graph|linter logic|password|private prompt|prompt|raw provider payload|runtime value|scoring|secret|token)\b"
FORBIDDEN_PUBLIC_TEXT_PATTERN: Final = re.compile(
    FORBIDDEN_PUBLIC_TEXT_PATTERN_TEXT, re.IGNORECASE
)
SAFE_REFERENCE_PATTERN: Final = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,80}$")
SHA256_PATTERN: Final = re.compile(r"^[a-f0-9]{64}$")
UUID_PATTERN: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
VERSION_PATTERN: Final = re.compile(r"^v[0-9]+(?:\.[0-9]+){0,2}$")


class SreMaintenanceEntitlementInput(NamedTuple):
    """Inputs from accepted order/subscription state."""

    subscription_active: bool
    consecutive_paid_periods: int
    included_standard_change_available: bool
    paid_extra_standard_changes: int
    scenario_slots: int = 1
    accepted_order_allows_pro_change_stacking: bool = False


class SreMaintenanceEntitlementState(NamedTuple):
    """Customer-visible maintenance entitlement contract."""

    subscription_active: bool
    scenario_slots: int
    included_standard_changes_per_period: int
    included_standard_change_available: bool
    unused_standard_changes_roll_over: bool
    paid_extra_standard_changes: int
    pro_change_available: bool
    pro_change_paid_period_cadence: int
    pro_changes_stack: bool
    custom_tools_require_separate_order: bool
    additional_scenarios_require_separate_order: bool
    major_changes_require_separate_order: bool


class SreChangeRequestScope(NamedTuple):
    """One requested service change classified against the accepted baseline."""

    same_trigger_and_business_purpose: bool
    inside_accepted_app_provider_dependency_family: bool
    introduces_new_custom_tool: bool
    introduces_additional_scenario: bool
    major_architecture_replacement: bool
    high_risk_provider_approval_required: bool


class SreRefundPolicyInput(NamedTuple):
    """Redacted payment/refund facts after provider review."""

    gross_payment_cents: int
    delivered_customer_package: bool
    customer_review_started: bool
    schoenwald_fault: bool
    duplicate_charge: bool
    refund_or_chargeback_recorded: bool


class SreRefundDecision(NamedTuple):
    """Fail-closed refund/access decision."""

    eligible: bool
    refund_cents: int
    paid_access_revoked: bool
    reason: str


class SreReferralRewardInput(NamedTuple):
    """Referral reward facts already stripped of private provider payloads."""

    gross_first_payment_cents: int
    taxes_cents: int
    discount_cents: int
    refunded_cents: int
    chargeback_cents: int
    fraudulent_payment_cents: int
    reversed_payment_cents: int
    provider_adjustment_cents: int
    retained_subscription_net_revenue_by_month_cents: tuple[int, ...]
    holdback_cleared: bool
    identity_verification_completed: bool
    launch_window_purchase: bool
    payout_threshold_met: bool
    tax_form_collected: bool
    use_future_initial_reward_reduction: bool


class SreReferralRewardDecision(NamedTuple):
    """Referral reward decision over retained eligible net revenue."""

    earned: bool
    cancellation_triggered: bool
    eligible_net_first_payment_revenue_cents: int
    initial_reward_percent: int
    initial_reward_cents: int
    recurring_reward_percent: int
    recurring_reward_months_counted: int
    recurring_reward_cents: int
    reward_cents: int


class SreReleaseCertificateRecord(NamedTuple):
    """Release record metadata safe enough for minimal lookup responses."""

    certificate_uuid: str
    customer_or_package_reference: str
    customer_safe_package_id: str
    package_family: str
    package_name: str
    release_version: str
    status: SreReleaseCertificateStatus
    support_or_subscription_status: str
    supported_baseline: str
    manifest_summary: str
    fingerprint_sha256: str | None


class SreReleaseCertificateLookupRequest(NamedTuple):
    """Lookup request after backend identity/package verification."""

    backend_verified: bool
    certificate_uuid: str
    customer_or_package_reference: str


def evaluate_maintenance_entitlements(
    source: SreMaintenanceEntitlementInput,
) -> SreMaintenanceEntitlementState:
    """Return the maintenance contract for one subscription mirror."""
    _require_non_negative(
        source.consecutive_paid_periods, "consecutive_paid_periods"
    )
    _require_non_negative(
        source.paid_extra_standard_changes, "paid_extra_standard_changes"
    )
    _require_positive(source.scenario_slots, "scenario_slots")
    return SreMaintenanceEntitlementState(
        subscription_active=source.subscription_active,
        scenario_slots=source.scenario_slots,
        included_standard_changes_per_period=1,
        included_standard_change_available=(
            source.subscription_active
            and source.included_standard_change_available
        ),
        unused_standard_changes_roll_over=False,
        paid_extra_standard_changes=source.paid_extra_standard_changes,
        pro_change_available=(
            source.subscription_active
            and source.consecutive_paid_periods
            >= PRO_CHANGE_PAID_PERIOD_CADENCE
        ),
        pro_change_paid_period_cadence=PRO_CHANGE_PAID_PERIOD_CADENCE,
        pro_changes_stack=source.accepted_order_allows_pro_change_stacking,
        custom_tools_require_separate_order=True,
        additional_scenarios_require_separate_order=True,
        major_changes_require_separate_order=True,
    )


def classify_change_request(
    *,
    entitlements: SreMaintenanceEntitlementState,
    scope: SreChangeRequestScope,
) -> SreChangeClassification:
    """Classify one requested change against the public maintenance promise.

    Returns:
        The order or entitlement path that owns the requested change.
    """
    result: SreChangeClassification
    if scope.introduces_additional_scenario:
        result = "requires_additional_scenario_order"
    elif scope.introduces_new_custom_tool:
        result = "requires_custom_tool_order"
    elif (
        scope.major_architecture_replacement
        or scope.high_risk_provider_approval_required
        or not scope.same_trigger_and_business_purpose
        or not scope.inside_accepted_app_provider_dependency_family
    ):
        result = "requires_major_change_order"
    elif not entitlements.subscription_active:
        result = "requires_extra_standard_change_order"
    elif entitlements.included_standard_change_available:
        result = "included_standard_change"
    elif entitlements.paid_extra_standard_changes > 0:
        result = "paid_extra_standard_change"
    else:
        result = "requires_extra_standard_change_order"
    return result


def refund_policy_decision(source: SreRefundPolicyInput) -> SreRefundDecision:
    """Return conservative refund/access decisions."""
    _require_non_negative(source.gross_payment_cents, "gross_payment_cents")
    if source.refund_or_chargeback_recorded:
        return SreRefundDecision(
            eligible=True,
            refund_cents=0,
            paid_access_revoked=True,
            reason="provider_refund_or_chargeback_recorded",
        )
    if source.duplicate_charge or source.schoenwald_fault:
        return SreRefundDecision(
            eligible=True,
            refund_cents=source.gross_payment_cents,
            paid_access_revoked=True,
            reason="duplicate_charge_or_schoenwald_fault",
        )
    if source.delivered_customer_package or source.customer_review_started:
        return SreRefundDecision(
            eligible=False,
            refund_cents=0,
            paid_access_revoked=False,
            reason="delivery_or_customer_review_started",
        )
    return SreRefundDecision(
        eligible=False,
        refund_cents=0,
        paid_access_revoked=False,
        reason="no_refund_trigger",
    )


def referral_reward_decision(
    source: SreReferralRewardInput,
) -> SreReferralRewardDecision:
    """Return referral rewards from retained eligible net revenue only."""
    _require_referral_amounts_non_negative(source)
    cancellation_triggered = any(
        amount > 0
        for amount in (
            source.refunded_cents,
            source.chargeback_cents,
            source.fraudulent_payment_cents,
            source.reversed_payment_cents,
        )
    )
    eligible_net = max(
        0,
        source.gross_first_payment_cents
        - source.taxes_cents
        - source.discount_cents
        - source.refunded_cents
        - source.chargeback_cents
        - source.fraudulent_payment_cents
        - source.reversed_payment_cents
        - source.provider_adjustment_cents,
    )
    initial_percent = _initial_referral_percent(source)
    earned = (
        not cancellation_triggered
        and source.holdback_cleared
        and source.identity_verification_completed
        and source.payout_threshold_met
        and source.tax_form_collected
        and eligible_net > 0
    )
    initial_reward = eligible_net * initial_percent // 100 if earned else 0
    recurring_nets = source.retained_subscription_net_revenue_by_month_cents[:3]
    recurring_reward = sum(recurring_nets) * 25 // 100 if earned else 0
    return SreReferralRewardDecision(
        earned=earned,
        cancellation_triggered=cancellation_triggered,
        eligible_net_first_payment_revenue_cents=eligible_net,
        initial_reward_percent=initial_percent,
        initial_reward_cents=initial_reward,
        recurring_reward_percent=25,
        recurring_reward_months_counted=len(recurring_nets) if earned else 0,
        recurring_reward_cents=recurring_reward,
        reward_cents=initial_reward + recurring_reward,
    )


def assert_release_certificate_record_safe(
    record: SreReleaseCertificateRecord,
) -> None:
    """Raise when a release record exposes private or unsupported status.

    Raises:
        ValueError: If release metadata is unsafe, malformed, or unsupported.
    """
    _assert_uuid(record.certificate_uuid)
    _assert_safe_reference(
        record.customer_or_package_reference, "customer_or_package_reference"
    )
    _assert_safe_reference(
        record.customer_safe_package_id, "customer_safe_package_id"
    )
    _assert_safe_text(record.package_family, "package_family")
    _assert_safe_text(record.package_name, "package_name")
    _assert_version(record.release_version)
    if record.status not in RELEASE_CERTIFICATE_STATUSES:
        message = f"Unsupported release certificate status: {record.status}"
        raise ValueError(message)
    _assert_safe_text(
        record.support_or_subscription_status, "support_or_subscription_status"
    )
    _assert_safe_text(record.supported_baseline, "supported_baseline")
    _assert_safe_text(record.manifest_summary, "manifest_summary")
    if record.fingerprint_sha256 is not None and not SHA256_PATTERN.fullmatch(
        record.fingerprint_sha256
    ):
        message = (
            "Release certificate fingerprint must be lowercase sha256 text."
        )
        raise ValueError(message)


def release_certificate_lookup_response(
    *,
    record: SreReleaseCertificateRecord,
    request: SreReleaseCertificateLookupRequest,
) -> JsonObject:
    """Return a minimal public lookup response after verification."""
    assert_release_certificate_record_safe(record)
    _assert_uuid(request.certificate_uuid)
    _assert_safe_reference(
        request.customer_or_package_reference, "customer_or_package_reference"
    )
    if (
        not request.backend_verified
        or request.certificate_uuid != record.certificate_uuid
        or request.customer_or_package_reference
        != record.customer_or_package_reference
    ):
        return {"matched": False}
    return {
        "matched": True,
        "package_family": record.package_family,
        "release_baseline": record.supported_baseline,
        "status": record.status,
        "support_or_subscription_status": record.support_or_subscription_status,
    }


def release_certificate_lookup_policy() -> JsonObject:
    """Return the backend lookup surface allowed by the public contract."""
    return {
        "backend_verification_required": True,
        "public_lookup_active": False,
        "certification_claim_allowed": False,
        "exposed_lookup_fields": list(RELEASE_CERTIFICATE_LOOKUP_FIELDS),
        "private_fields_forbidden": [
            "customer_name",
            "private_blueprint_json",
            "runtime_values",
            "secrets",
            "internal_ast",
            "internal_graph",
            "prompts",
            "linter_logic",
            "scoring",
        ],
    }


def _initial_referral_percent(source: SreReferralRewardInput) -> int:
    if source.use_future_initial_reward_reduction:
        return 25
    return 90 if source.launch_window_purchase else 50


def _require_referral_amounts_non_negative(
    source: SreReferralRewardInput,
) -> None:
    for field_name, value in (
        ("gross_first_payment_cents", source.gross_first_payment_cents),
        ("taxes_cents", source.taxes_cents),
        ("discount_cents", source.discount_cents),
        ("refunded_cents", source.refunded_cents),
        ("chargeback_cents", source.chargeback_cents),
        ("fraudulent_payment_cents", source.fraudulent_payment_cents),
        ("reversed_payment_cents", source.reversed_payment_cents),
        ("provider_adjustment_cents", source.provider_adjustment_cents),
    ):
        _require_non_negative(value, field_name)
    for index, value in enumerate(
        source.retained_subscription_net_revenue_by_month_cents
    ):
        _require_non_negative(
            value, f"retained_subscription_net_revenue_by_month_cents[{index}]"
        )


def _require_positive(value: int, field_name: str) -> None:
    if value <= 0:
        message = f"{field_name} must be positive."
        raise ValueError(message)


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        message = f"{field_name} must be non-negative."
        raise ValueError(message)


def _assert_uuid(value: str) -> None:
    if not UUID_PATTERN.fullmatch(value):
        message = f"Invalid release certificate UUID: {value}"
        raise ValueError(message)


def _assert_version(value: str) -> None:
    if not VERSION_PATTERN.fullmatch(value):
        message = f"Invalid release version: {value}"
        raise ValueError(message)


def _assert_safe_reference(value: str, label: str) -> None:
    if not SAFE_REFERENCE_PATTERN.fullmatch(
        value
    ) or FORBIDDEN_PUBLIC_TEXT_PATTERN.search(value):
        message = f"Unsafe release certificate {label}."
        raise ValueError(message)


def _assert_safe_text(value: str, label: str) -> None:
    text = value.strip()
    if not text or FORBIDDEN_PUBLIC_TEXT_PATTERN.search(text):
        message = f"Unsafe release certificate {label}."
        raise ValueError(message)


def unsafe_release_status_for_test(value: str) -> SreReleaseCertificateStatus:
    """Return an intentionally unsafe status for runtime validation tests."""
    return cast("SreReleaseCertificateStatus", value)
