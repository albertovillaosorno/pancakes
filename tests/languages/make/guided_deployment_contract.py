# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for guided Make deployment prerequisites and safety flags.

Boundary contract:
- Owns: tests for customer prerequisite gates before guided Make deployment.
- Must not: call Make.com, read credentials, or depend on live customer
  accounts.
- Allows: deterministic policy assertions over redacted prerequisite state.
- Split when: live onboarding sessions receive their own integration tests.
"""

from __future__ import annotations

from languages.make.guided_deployment import (
    GuidedMakeDeploymentPrerequisites,
    evaluate_guided_make_deployment,
    guided_make_deployment_policy,
)


def test_policy_defaults_to_blocked_and_no_secret_collection() -> None:
    """Static policy blocks deployment until prerequisites are confirmed."""
    policy = guided_make_deployment_policy()

    assert policy.status == "blocked_missing_customer_prerequisites"
    assert policy.provider_api_call_allowed_after_operator_approval is False
    assert policy.live_make_called_by_default is False
    assert policy.temporary_make_api_token_storage_allowed is False
    assert policy.public_form_secret_collection_allowed is False
    assert policy.scenario_activation_allowed_before_customer_review is False
    assert policy.connection_check_scenario_must_be_deleted is True
    assert policy.deployment_order == (
        "data_structures",
        "data_stores",
        "webhooks",
        "custom_apps_if_any",
        "inactive_scenario",
    )


def test_readiness_requires_all_customer_prerequisites() -> None:
    """Missing prerequisite state blocks operator apply."""
    readiness = evaluate_guided_make_deployment(
        GuidedMakeDeploymentPrerequisites(
            make_paid_plan_confirmed=False,
            workspace_permissions_confirmed=False,
            required_app_subscriptions_confirmed=False,
            provider_accounts_confirmed=False,
            runtime_values_confirmed=False,
            minimum_token_scopes_confirmed=False,
            connection_check_verified=False,
            connection_check_deleted=False,
            keep_scenario_inactive_until_customer_review=False,
        )
    )

    assert readiness.status == "blocked_missing_customer_prerequisites"
    assert readiness.blockers == (
        "make_paid_plan_not_confirmed",
        "workspace_permissions_not_confirmed",
        "required_app_subscriptions_not_confirmed",
        "provider_accounts_not_confirmed",
        "runtime_values_not_confirmed",
        "minimum_token_scopes_not_confirmed",
        "connection_check_not_verified",
        "connection_check_not_deleted",
        "scenario_activation_requested_before_customer_review",
    )
    assert readiness.provider_api_call_allowed_after_operator_approval is False


def test_blocks_public_secrets_and_token_storage() -> None:
    """Public forms and backend artifacts must never request secrets."""
    readiness = evaluate_guided_make_deployment(
        GuidedMakeDeploymentPrerequisites(
            make_paid_plan_confirmed=True,
            workspace_permissions_confirmed=True,
            required_app_subscriptions_confirmed=True,
            provider_accounts_confirmed=True,
            runtime_values_confirmed=True,
            minimum_token_scopes_confirmed=True,
            connection_check_verified=True,
            connection_check_deleted=True,
            keep_scenario_inactive_until_customer_review=True,
            public_form_secret_collection_requested=True,
            temporary_make_api_token_storage_requested=True,
        )
    )

    assert readiness.status == "blocked_missing_customer_prerequisites"
    assert readiness.blockers == (
        "public_form_secret_collection_requested",
        "temporary_make_api_token_storage_requested",
    )
    assert readiness.temporary_make_api_token_storage_allowed is False
    assert readiness.public_form_secret_collection_allowed is False


def test_allows_operator_apply_after_prerequisites() -> None:
    """A ready result still waits for customer review."""
    readiness = evaluate_guided_make_deployment(
        GuidedMakeDeploymentPrerequisites(
            make_paid_plan_confirmed=True,
            workspace_permissions_confirmed=True,
            required_app_subscriptions_confirmed=True,
            provider_accounts_confirmed=True,
            runtime_values_confirmed=True,
            minimum_token_scopes_confirmed=True,
            connection_check_verified=True,
            connection_check_deleted=True,
            keep_scenario_inactive_until_customer_review=True,
        )
    )

    assert readiness.status == "ready_for_guided_make_deployment"
    assert readiness.blockers == ()
    assert readiness.provider_api_call_allowed_after_operator_approval is True
    assert readiness.live_make_called_by_default is False
    assert readiness.scenario_activation_allowed_before_customer_review is False
