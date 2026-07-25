# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - docs/adr/public-demo-aggregate-score-boundary-policy.md
# - 001046#repo.blueprint-validation.validator-policy
# - 001064#repo.make-knowledge.course-promoted-rules
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Static scenario rule-surface taxonomy for Make blueprint review.

Boundary contract:
- Owns: scenario-surface metadata, evidence gates, and customer/internal
boundaries.
- Must not: emit findings, contact Make.com, depend on live scenarios, or reveal
linter internals.
- Allows: deterministic lookup of rule-surface posture for downstream
documentation gates.
- Split when: a surface becomes executable validation behavior.
- Merge when: linter taxonomy fully owns this customer/internal surface map.
"""

from __future__ import annotations

from typing import Final, Literal, NamedTuple

type ScenarioRuleSurfaceId = Literal[
    "aggregator ",
    "data_store ",
    "data_structure ",
    "error_handler ",
    "filter ",
    "http ",
    "human_audit ",
    "iterator ",
    "json_parse ",
    "make_ai ",
    "operation_volume_optimization ",
    "router ",
    "webhook",
]
type ScenarioRuleSignalDomain = Literal[
    "data_contract ",
    "handoff ",
    "human_review ",
    "operations ",
    "reliability ",
    "security",
]
type ScenarioRuleEvidenceGate = Literal[
    "local_ast_allowed ",
    "promoted_knowledge_required ",
    "make_live_parity_required_for_customer_visual_claims ",
    "operator_policy_required",
]
type ScenarioRuleOutputPosture = Literal[
    "blocking_capable ",
    "advisory_only ",
    "optimization_only",
]


class ScenarioRuleSurface(NamedTuple):
    """One static Make scenario rule surface."""

    surface_id: ScenarioRuleSurfaceId
    title: str
    customer_visible_summary: str
    internal_linter_boundary: str
    signal_domains: tuple[ScenarioRuleSignalDomain, ...]
    evidence_gate: ScenarioRuleEvidenceGate
    output_posture: ScenarioRuleOutputPosture
    canonical_rule_family_ids: tuple[str, ...]


SCENARIO_RULE_SURFACES: Final[tuple[ScenarioRuleSurface, ...]] = (
    ScenarioRuleSurface(
        surface_id="filter",
        title="Filter predicates and labels",
        customer_visible_summary=(
            "Explains why a bundle passes, drops, or enters a route."
        ),
        internal_linter_boundary=(
            "Keep predicate mechanics, rule codes, and source paths in "
            "internal "
            "diagnostics."
        ),
        signal_domains=("reliability", "handoff"),
        evidence_gate="make_live_parity_required_for_customer_visual_claims",
        output_posture="blocking_capable",
        canonical_rule_family_ids=("route_branch_topology",),
    ),
    ScenarioRuleSurface(
        surface_id="router",
        title="Router branch topology",
        customer_visible_summary=(
            "Explains branch purpose, exclusivity, and fallback behavior."
        ),
        internal_linter_boundary=(
            "Keep topology proof paths and route traversal mechanics in "
            "internal diagnostics."
        ),
        signal_domains=("reliability", "handoff"),
        evidence_gate="local_ast_allowed",
        output_posture="blocking_capable",
        canonical_rule_family_ids=("route_branch_topology",),
    ),
    ScenarioRuleSurface(
        surface_id="error_handler",
        title="Error-handler recovery routes",
        customer_visible_summary=(
            "Explains handled failure classes and recovery posture."
        ),
        internal_linter_boundary=(
            "Do not expose handler-detection predicates, exact finding IDs, or "
            "repair recipes."
        ),
        signal_domains=("reliability", "handoff"),
        evidence_gate="make_live_parity_required_for_customer_visual_claims",
        output_posture="blocking_capable",
        canonical_rule_family_ids=("error_handling_reliability",),
    ),
    ScenarioRuleSurface(
        surface_id="data_store",
        title="Data store state mutation",
        customer_visible_summary=(
            "Explains keying, retention, recovery, and side effects."
        ),
        internal_linter_boundary=(
            "Keep transaction heuristics and sensitive storage predicates in "
            "internal diagnostics."
        ),
        signal_domains=("reliability", "security", "data_contract"),
        evidence_gate="promoted_knowledge_required",
        output_posture="advisory_only",
        canonical_rule_family_ids=("transaction_safety",),
    ),
    ScenarioRuleSurface(
        surface_id="data_structure",
        title="Data structure contracts",
        customer_visible_summary=(
            "Explains expected records, fields, and shape assumptions."
        ),
        internal_linter_boundary=(
            "Keep catalog resolution, placeholder, and field-inference "
            "mechanics internal."
        ),
        signal_domains=("data_contract", "handoff"),
        evidence_gate="promoted_knowledge_required",
        output_posture="blocking_capable",
        canonical_rule_family_ids=(
            "catalog_resolution ",
            "mapping_reference_contracts",
        ),
    ),
    ScenarioRuleSurface(
        surface_id="iterator",
        title="Iterator fan-out",
        customer_visible_summary=(
            "Explains how array fan-out can multiply work."
        ),
        internal_linter_boundary=(
            "Do not expose operation-estimator formulas or internal threshold "
            "constants."
        ),
        signal_domains=("operations",),
        evidence_gate="local_ast_allowed",
        output_posture="optimization_only",
        canonical_rule_family_ids=("operation_volume_optimization",),
    ),
    ScenarioRuleSurface(
        surface_id="aggregator",
        title="Aggregator bundling",
        customer_visible_summary=(
            "Explains bundle strategy and volume assumptions."
        ),
        internal_linter_boundary=(
            "Do not expose advisory thresholds, matching heuristics, or graph "
            "traversal paths."
        ),
        signal_domains=("operations",),
        evidence_gate="promoted_knowledge_required",
        output_posture="optimization_only",
        canonical_rule_family_ids=("operation_volume_optimization",),
    ),
    ScenarioRuleSurface(
        surface_id="webhook",
        title="Webhook ingress and response safety",
        customer_visible_summary=(
            "Explains ingress guardrails, payload shape, and response flow."
        ),
        internal_linter_boundary=(
            "Keep local security predicates and rule IDs out of "
            "customer-facing "
            "artifacts."
        ),
        signal_domains=("reliability", "security", "data_contract"),
        evidence_gate="promoted_knowledge_required",
        output_posture="advisory_only",
        canonical_rule_family_ids=(
            "semantic_runtime_contracts ",
            "webhook_http_security",
        ),
    ),
    ScenarioRuleSurface(
        surface_id="http",
        title="HTTP request and response safety",
        customer_visible_summary=(
            "Explains transport, timeout, retry, and response assumptions."
        ),
        internal_linter_boundary=(
            "Keep URL parsing, sensitive-field detection, and exact rule "
            "mechanics internal."
        ),
        signal_domains=("reliability", "security", "data_contract"),
        evidence_gate="local_ast_allowed",
        output_posture="blocking_capable",
        canonical_rule_family_ids=(
            "http_url_security ",
            "webhook_http_security",
        ),
    ),
    ScenarioRuleSurface(
        surface_id="json_parse",
        title="JSON parsing contracts",
        customer_visible_summary=(
            "Explains required input and expected schema evidence."
        ),
        internal_linter_boundary=(
            "Do not expose parser probes, internal fixture names, or exact "
            "detection paths."
        ),
        signal_domains=("data_contract", "reliability"),
        evidence_gate="promoted_knowledge_required",
        output_posture="advisory_only",
        canonical_rule_family_ids=("webhook_http_security",),
    ),
    ScenarioRuleSurface(
        surface_id="make_ai",
        title="Make AI and agent modules",
        customer_visible_summary=(
            "Explains objective, tool contract, fallback, and review needs."
        ),
        internal_linter_boundary=(
            "Keep prompt probes, internal policy checks, and model-scoring "
            "logic private."
        ),
        signal_domains=("human_review", "security", "data_contract"),
        evidence_gate="local_ast_allowed",
        output_posture="advisory_only",
        canonical_rule_family_ids=("ai_agent_contracts",),
    ),
    ScenarioRuleSurface(
        surface_id="human_audit",
        title="Human audit and release governance",
        customer_visible_summary=(
            "Explains ownership, change reason, rollback, and review posture."
        ),
        internal_linter_boundary=(
            "Keep release-gate predicates, operator notes, and internal audit "
            "rows private."
        ),
        signal_domains=("handoff", "human_review", "reliability"),
        evidence_gate="operator_policy_required",
        output_posture="advisory_only",
        canonical_rule_family_ids=(
            "scenario_release_governance ",
            "designer_layout_handoff",
        ),
    ),
    ScenarioRuleSurface(
        surface_id="operation_volume_optimization",
        title="Operation volume optimization",
        customer_visible_summary=(
            "Explains cost and throughput risk without claiming runtime truth."
        ),
        internal_linter_boundary=(
            "Do not reveal formulas, thresholds, exact node paths, or scoring "
            "internals."
        ),
        signal_domains=("operations",),
        evidence_gate="local_ast_allowed",
        output_posture="optimization_only",
        canonical_rule_family_ids=("operation_volume_optimization",),
    ),
)

SCENARIO_RULE_SURFACE_IDS: Final[frozenset[str]] = frozenset(
    surface.surface_id for surface in SCENARIO_RULE_SURFACES
)
_SCENARIO_RULE_SURFACE_BY_ID: Final[dict[str, ScenarioRuleSurface]] = {
    surface.surface_id: surface for surface in SCENARIO_RULE_SURFACES
}


def scenario_rule_surfaces() -> tuple[ScenarioRuleSurface, ...]:
    """Return scenario rule surfaces in deterministic review order."""
    return SCENARIO_RULE_SURFACES


def scenario_rule_surface_ids() -> tuple[str, ...]:
    """Return scenario rule surface identifiers."""
    return tuple(sorted(SCENARIO_RULE_SURFACE_IDS))


def scenario_rule_surface_by_id(surface_id: str) -> ScenarioRuleSurface:
    """Return one scenario rule surface by identifier.

    Raises:
        ValueError: If the surface ID is not part of the taxonomy.
    """
    surface = _SCENARIO_RULE_SURFACE_BY_ID.get(surface_id)
    if surface is None:
        msg = f"Unsupported scenario rule surface: {surface_id!r}"
        raise ValueError(msg)
    return surface
