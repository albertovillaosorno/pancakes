# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001055#repo.mcp.required-tool-surface
# - 001061#repo.delivery.client-ready-handoff-contract
# - 001075#repo.client-blueprint-intake.shape-secret-identifier-gates
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Guided Make deployment contract shared by local upload tooling.

Boundary contract:
- Owns: customer prerequisite gates and safe guided Make deployment policy.
- Must not: call Make.com, store tokens, collect secrets, or activate scenarios.
- Allows: deterministic readiness checks and public-safe deployment-order
metadata.
- Split when: hosted onboarding sessions own their own authenticated request
state.
- Merge when: another Make module duplicates guided deployment prerequisite
policy.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

type GuidedMakeDeploymentBlocker = Literal[
    "make_paid_plan_not_confirmed",
    "workspace_permissions_not_confirmed",
    "required_app_subscriptions_not_confirmed",
    "provider_accounts_not_confirmed",
    "runtime_values_not_confirmed",
    "minimum_token_scopes_not_confirmed",
    "connection_check_not_verified",
    "connection_check_not_deleted",
    "scenario_activation_requested_before_customer_review",
    "public_form_secret_collection_requested",
    "temporary_make_api_token_storage_requested",
]
type GuidedMakeDeploymentStatus = Literal[
    "ready_for_guided_make_deployment",
    "blocked_missing_customer_prerequisites",
]
type GuidedMakeDeploymentStep = Literal[
    "data_structures",
    "data_stores",
    "webhooks",
    "custom_apps_if_any",
    "inactive_scenario",
]
type JsonObject = dict[str, object]

GUIDED_MAKE_DEPLOYMENT_ORDER: Final[tuple[GuidedMakeDeploymentStep, ...]] = (
    "data_structures",
    "data_stores",
    "webhooks",
    "custom_apps_if_any",
    "inactive_scenario",
)


class GuidedMakeDeploymentPrerequisites(NamedTuple):
    """Customer-owned prerequisites before guided Make deployment can.

    proceed.
    """

    make_paid_plan_confirmed: bool
    workspace_permissions_confirmed: bool
    required_app_subscriptions_confirmed: bool
    provider_accounts_confirmed: bool
    runtime_values_confirmed: bool
    minimum_token_scopes_confirmed: bool
    connection_check_verified: bool
    connection_check_deleted: bool
    keep_scenario_inactive_until_customer_review: bool
    public_form_secret_collection_requested: bool = False
    temporary_make_api_token_storage_requested: bool = False


class GuidedMakeDeploymentReadiness(NamedTuple):
    """Fail-closed guided deployment readiness result."""

    status: GuidedMakeDeploymentStatus
    blockers: tuple[GuidedMakeDeploymentBlocker, ...]
    deployment_order: tuple[GuidedMakeDeploymentStep, ...]
    provider_api_call_allowed_after_operator_approval: bool
    live_make_called_by_default: bool
    temporary_make_api_token_storage_allowed: bool
    public_form_secret_collection_allowed: bool
    connection_check_scenario_required_when_connections_uncertain: bool
    connection_check_scenario_must_be_deleted: bool
    scenario_activation_allowed_before_customer_review: bool


def guided_make_deployment_policy() -> GuidedMakeDeploymentReadiness:
    """Return the static safe policy before customer-specific prerequisites are.

    known.
    """
    return GuidedMakeDeploymentReadiness(
        status="blocked_missing_customer_prerequisites",
        blockers=(
            "make_paid_plan_not_confirmed",
            "workspace_permissions_not_confirmed",
            "required_app_subscriptions_not_confirmed",
            "provider_accounts_not_confirmed",
            "runtime_values_not_confirmed",
            "minimum_token_scopes_not_confirmed",
            "connection_check_not_verified",
            "connection_check_not_deleted",
        ),
        deployment_order=GUIDED_MAKE_DEPLOYMENT_ORDER,
        provider_api_call_allowed_after_operator_approval=False,
        live_make_called_by_default=False,
        temporary_make_api_token_storage_allowed=False,
        public_form_secret_collection_allowed=False,
        connection_check_scenario_required_when_connections_uncertain=True,
        connection_check_scenario_must_be_deleted=True,
        scenario_activation_allowed_before_customer_review=False,
    )


def evaluate_guided_make_deployment(
    prerequisites: GuidedMakeDeploymentPrerequisites,
) -> GuidedMakeDeploymentReadiness:
    """Return guided Make deployment readiness from customer-owned.

    prerequisites.
    """
    blockers = _guided_deployment_blockers(prerequisites)
    return GuidedMakeDeploymentReadiness(
        status=(
            "blocked_missing_customer_prerequisites"
            if blockers
            else "ready_for_guided_make_deployment"
        ),
        blockers=blockers,
        deployment_order=GUIDED_MAKE_DEPLOYMENT_ORDER,
        provider_api_call_allowed_after_operator_approval=not blockers,
        live_make_called_by_default=False,
        temporary_make_api_token_storage_allowed=False,
        public_form_secret_collection_allowed=False,
        connection_check_scenario_required_when_connections_uncertain=True,
        connection_check_scenario_must_be_deleted=True,
        scenario_activation_allowed_before_customer_review=False,
    )


def guided_make_deployment_readiness_as_dict(
    readiness: GuidedMakeDeploymentReadiness,
) -> JsonObject:
    """Return JSON-ready guided Make deployment readiness metadata."""
    return {
        "status": readiness.status,
        "blockers": list(readiness.blockers),
        "deployment_order": list(readiness.deployment_order),
        "provider_api_call_allowed_after_operator_approval": (
            readiness.provider_api_call_allowed_after_operator_approval
        ),
        "live_make_called_by_default": readiness.live_make_called_by_default,
        "temporary_make_api_token_storage_allowed": (
            readiness.temporary_make_api_token_storage_allowed
        ),
        "public_form_secret_collection_allowed": (
            readiness.public_form_secret_collection_allowed
        ),
        "connection_check_scenario_required_when_connections_uncertain": (
            readiness.connection_check_scenario_required_when_connections_uncertain
        ),
        "connection_check_scenario_must_be_deleted": (
            readiness.connection_check_scenario_must_be_deleted
        ),
        "scenario_activation_allowed_before_customer_review": (
            readiness.scenario_activation_allowed_before_customer_review
        ),
    }


def guided_make_deployment_policy_as_dict() -> JsonObject:
    """Return JSON-ready static guided Make deployment policy metadata."""
    return guided_make_deployment_readiness_as_dict(
        guided_make_deployment_policy()
    )


def _guided_deployment_blockers(
    prerequisites: GuidedMakeDeploymentPrerequisites,
) -> tuple[GuidedMakeDeploymentBlocker, ...]:
    checks: tuple[tuple[bool, GuidedMakeDeploymentBlocker], ...] = (
        (
            not prerequisites.make_paid_plan_confirmed,
            "make_paid_plan_not_confirmed",
        ),
        (
            not prerequisites.workspace_permissions_confirmed,
            "workspace_permissions_not_confirmed",
        ),
        (
            not prerequisites.required_app_subscriptions_confirmed,
            "required_app_subscriptions_not_confirmed",
        ),
        (
            not prerequisites.provider_accounts_confirmed,
            "provider_accounts_not_confirmed",
        ),
        (
            not prerequisites.runtime_values_confirmed,
            "runtime_values_not_confirmed",
        ),
        (
            not prerequisites.minimum_token_scopes_confirmed,
            "minimum_token_scopes_not_confirmed",
        ),
        (
            not prerequisites.connection_check_verified,
            "connection_check_not_verified",
        ),
        (
            not prerequisites.connection_check_deleted,
            "connection_check_not_deleted",
        ),
        (
            not prerequisites.keep_scenario_inactive_until_customer_review,
            "scenario_activation_requested_before_customer_review",
        ),
        (
            prerequisites.public_form_secret_collection_requested,
            "public_form_secret_collection_requested",
        ),
        (
            prerequisites.temporary_make_api_token_storage_requested,
            "temporary_make_api_token_storage_requested",
        ),
    )
    return tuple(blocker for condition, blocker in checks if condition)
