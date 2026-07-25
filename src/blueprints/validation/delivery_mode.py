# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001046#repo.blueprint-validation.validator-policy
# - 001061#repo.delivery.client-ready-handoff-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Classify the achieved delivery mode for a validated blueprint.

Boundary contract:
- Owns: delivery-mode classification from an existing validation report.
- Must not: create findings, inspect AST nodes, or build handoff manifests.
- Allows: deterministic severity and code-prefix interpretation.
- Split when: delivery modes gain separate policy, scoring, or explanation
  rules.
- Merge when: another classifier returns the same delivery modes identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from blueprints.validation.models import BlueprintValidationReport

type BlueprintDeliveryMode = Literal[
    "invalid",
    "visual_skeleton",
    "import_safe_functional",
    "deploy_ready",
]

IMPORT_BLOCKING_PREFIXES = ("module.", "mapping.", "ast.", "router.")
SEMANTIC_BLOCKING_PREFIXES = ("semantic.", "ai_agent.", "output_contract.")
BINDING_BLOCKING_PREFIXES = ("handoff.",)


def achieved_blueprint_delivery_mode(
    report: BlueprintValidationReport,
) -> BlueprintDeliveryMode:
    """Return the strongest supported delivery mode.

    Returns:
        Delivery mode inferred from blueprints.validation evidence.
    """
    if _has_error_with_prefix(report, IMPORT_BLOCKING_PREFIXES):
        return "invalid"
    if _has_error_with_prefix(report, SEMANTIC_BLOCKING_PREFIXES):
        return "visual_skeleton"
    if _has_error_with_prefix(report, BINDING_BLOCKING_PREFIXES):
        return "import_safe_functional"
    if any(finding.severity == "error" for finding in report.findings):
        return "visual_skeleton"
    if report.findings:
        return "import_safe_functional"
    return "deploy_ready"


def _has_error_with_prefix(
    report: BlueprintValidationReport,
    prefixes: tuple[str, ...],
) -> bool:
    """Return whether a blocking finding has one of the given code prefixes."""
    return any(
        finding.severity == "error" and finding.code.startswith(prefixes)
        for finding in report.findings
    )
