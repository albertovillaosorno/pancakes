# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for Schoenwald SRE launch business rules in Pancakes backend.

Boundary contract:
- Owns: deterministic launch, entitlement, referral, refund, and release-record
tests.
- Must not: call payment providers, Make.com, or customer account systems.
- Allows: redacted metadata decisions that must match public-web promises.
- Split when: provider adapters get separately approved integration tests.
"""

from __future__ import annotations

import pytest
from blueprints.validation.sre_launch_contract import (
    SreChangeRequestScope,
    SreMaintenanceEntitlementInput,
    SreReferralRewardInput,
    SreRefundPolicyInput,
    SreReleaseCertificateLookupRequest,
    SreReleaseCertificateRecord,
    assert_release_certificate_record_safe,
    classify_change_request,
    evaluate_maintenance_entitlements,
    referral_reward_decision,
    refund_policy_decision,
    release_certificate_lookup_policy,
    release_certificate_lookup_response,
    unsafe_release_status_for_test,
)


def test_maintenance_entitlements_match_public_web_contract() -> None:
    """Maintenance exposes one scenario slot, one standard change, and a.

    3-period Pro Change.
    """
    entitlements = evaluate_maintenance_entitlements(
        SreMaintenanceEntitlementInput(
            subscription_active=True,
            consecutive_paid_periods=3,
            included_standard_change_available=True,
            paid_extra_standard_changes=2,
        )
    )

    assert entitlements.scenario_slots == 1
    assert entitlements.included_standard_changes_per_period == 1
    assert entitlements.included_standard_change_available is True
    assert entitlements.unused_standard_changes_roll_over is False
    assert entitlements.pro_change_available is True
    assert entitlements.pro_change_paid_period_cadence == 3
    assert entitlements.pro_changes_stack is False
    assert entitlements.custom_tools_require_separate_order is True
    assert entitlements.additional_scenarios_require_separate_order is True
    assert entitlements.major_changes_require_separate_order is True


def test_change_classification_routes_out_of_e65b9360() -> None:
    """Only bounded same-purpose baseline changes can consume included.

    maintenance.
    """
    entitlements = evaluate_maintenance_entitlements(
        SreMaintenanceEntitlementInput(
            subscription_active=True,
            consecutive_paid_periods=1,
            included_standard_change_available=True,
            paid_extra_standard_changes=0,
        )
    )

    assert (
        classify_change_request(
            entitlements=entitlements,
            scope=SreChangeRequestScope(
                same_trigger_and_business_purpose=True,
                inside_accepted_app_provider_dependency_family=True,
                introduces_new_custom_tool=False,
                introduces_additional_scenario=False,
                major_architecture_replacement=False,
                high_risk_provider_approval_required=False,
            ),
        )
        == "included_standard_change"
    )
    assert (
        classify_change_request(
            entitlements=entitlements,
            scope=SreChangeRequestScope(
                same_trigger_and_business_purpose=True,
                inside_accepted_app_provider_dependency_family=True,
                introduces_new_custom_tool=True,
                introduces_additional_scenario=False,
                major_architecture_replacement=False,
                high_risk_provider_approval_required=False,
            ),
        )
        == "requires_custom_tool_order"
    )
    assert (
        classify_change_request(
            entitlements=entitlements,
            scope=SreChangeRequestScope(
                same_trigger_and_business_purpose=True,
                inside_accepted_app_provider_dependency_family=True,
                introduces_new_custom_tool=False,
                introduces_additional_scenario=True,
                major_architecture_replacement=False,
                high_risk_provider_approval_required=False,
            ),
        )
        == "requires_additional_scenario_order"
    )
    assert (
        classify_change_request(
            entitlements=entitlements,
            scope=SreChangeRequestScope(
                same_trigger_and_business_purpose=False,
                inside_accepted_app_provider_dependency_family=True,
                introduces_new_custom_tool=False,
                introduces_additional_scenario=False,
                major_architecture_replacement=False,
                high_risk_provider_approval_required=False,
            ),
        )
        == "requires_major_change_order"
    )


def test_refund_policy_revokes_paid_access_for_refunds_and_chargebacks() -> (
    None
):
    """Refund and chargeback state cannot leave backend paid access active."""
    assert (
        refund_policy_decision(
            SreRefundPolicyInput(
                gross_payment_cents=10_000,
                delivered_customer_package=True,
                customer_review_started=True,
                schoenwald_fault=False,
                duplicate_charge=False,
                refund_or_chargeback_recorded=True,
            )
        ).paid_access_revoked
        is True
    )

    duplicate = refund_policy_decision(
        SreRefundPolicyInput(
            gross_payment_cents=10_000,
            delivered_customer_package=False,
            customer_review_started=False,
            schoenwald_fault=False,
            duplicate_charge=True,
            refund_or_chargeback_recorded=False,
        )
    )
    assert duplicate.eligible is True
    assert duplicate.refund_cents == 10_000
    assert duplicate.paid_access_revoked is True


def test_referral_rewards_use_retained_net_revenue_and_first_three_months() -> (
    None
):
    """Referral rewards exclude non-retained revenue and stop recurring credit.

    after month three.
    """
    decision = referral_reward_decision(
        SreReferralRewardInput(
            gross_first_payment_cents=10_000,
            taxes_cents=1_500,
            discount_cents=1_000,
            refunded_cents=0,
            chargeback_cents=0,
            fraudulent_payment_cents=0,
            reversed_payment_cents=0,
            provider_adjustment_cents=500,
            retained_subscription_net_revenue_by_month_cents=(
                7_000,
                7_000,
                7_000,
                7_000,
            ),
            holdback_cleared=True,
            identity_verification_completed=True,
            launch_window_purchase=True,
            payout_threshold_met=True,
            tax_form_collected=True,
            use_future_initial_reward_reduction=False,
        )
    )

    assert decision.earned is True
    assert decision.eligible_net_first_payment_revenue_cents == 7_000
    assert decision.initial_reward_percent == 90
    assert decision.initial_reward_cents == 6_300
    assert decision.recurring_reward_percent == 25
    assert decision.recurring_reward_months_counted == 3
    assert decision.recurring_reward_cents == 5_250
    assert decision.reward_cents == 11_550


def test_referral_rewards_cancel_before_payout_f2a8c5a2() -> None:
    """Unpaid referral rewards cancel when retained revenue is reversed."""
    decision = referral_reward_decision(
        SreReferralRewardInput(
            gross_first_payment_cents=10_000,
            taxes_cents=0,
            discount_cents=0,
            refunded_cents=1,
            chargeback_cents=0,
            fraudulent_payment_cents=0,
            reversed_payment_cents=0,
            provider_adjustment_cents=0,
            retained_subscription_net_revenue_by_month_cents=(10_000,),
            holdback_cleared=True,
            identity_verification_completed=True,
            launch_window_purchase=False,
            payout_threshold_met=True,
            tax_form_collected=True,
            use_future_initial_reward_reduction=True,
        )
    )

    assert decision.cancellation_triggered is True
    assert decision.earned is False
    assert decision.initial_reward_percent == 25
    assert decision.reward_cents == 0


def test_release_certificate_lookup_is_backend_verified_and_minimal() -> None:
    """Release records are not certification claims and expose only safe status.

    fields.
    """
    record = release_record()
    assert_release_certificate_record_safe(record)

    assert release_certificate_lookup_policy() == {
        "backend_verification_required": True,
        "public_lookup_active": False,
        "certification_claim_allowed": False,
        "exposed_lookup_fields": [
            "status",
            "release_baseline",
            "package_family",
            "support_or_subscription_status",
        ],
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
    assert release_certificate_lookup_response(
        record=record,
        request=SreReleaseCertificateLookupRequest(
            backend_verified=False,
            certificate_uuid=record.certificate_uuid,
            customer_or_package_reference=record.customer_or_package_reference,
        ),
    ) == {"matched": False}
    assert release_certificate_lookup_response(
        record=record,
        request=SreReleaseCertificateLookupRequest(
            backend_verified=True,
            certificate_uuid=record.certificate_uuid,
            customer_or_package_reference=record.customer_or_package_reference,
        ),
    ) == {
        "matched": True,
        "package_family": "Scenario Repair",
        "release_baseline": "baseline-2026-06",
        "status": "active",
        "support_or_subscription_status": "active subscription",
    }


def test_release_certificate_records_reject_private_194f3fc7() -> None:
    """Malformed release records fail closed before lookup can return a.

    match.
    """
    with pytest.raises(ValueError, match="manifest_summary"):
        assert_release_certificate_record_safe(
            release_record(manifest_summary="contains private blueprint JSON")
        )
    with pytest.raises(
        ValueError, match="Unsupported release certificate status"
    ):
        assert_release_certificate_record_safe(
            release_record(status=unsafe_release_status_for_test("draft"))
        )


def release_record(
    *,
    manifest_summary: str = "Customer-safe release package manifest summary",
    status: str = "active",
) -> SreReleaseCertificateRecord:
    """Return one safe release record fixture."""
    return SreReleaseCertificateRecord(
        certificate_uuid="123e4567-e89b-42d3-a456-426614174000",
        customer_or_package_reference="PKG-2026-001",
        customer_safe_package_id="SRE-2026-001",
        package_family="Scenario Repair",
        package_name="Scheduling Repair Package",
        release_version="v1.0.0",
        status=unsafe_release_status_for_test(status),
        support_or_subscription_status="active subscription",
        supported_baseline="baseline-2026-06",
        manifest_summary=manifest_summary,
        fingerprint_sha256="a" * 64,
    )
