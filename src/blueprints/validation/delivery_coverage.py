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

"""Summarize client-ready delivery coverage from blueprints.validation evidence.

Boundary contract:
- Owns: compact client-ready coverage summaries for one blueprint and catalog.
- Must not: own validation rules, placeholder policy, or rendering decisions.
- Allows: composing validation, handoff counts, delivery mode, and score data.
- Split when: score policy or regression policy needs independent ownership.
- Merge when: another coverage file computes the same summary identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from blueprints.validation.delivery_mode import (
    BlueprintDeliveryMode,
    achieved_blueprint_delivery_mode,
)
from blueprints.validation.handoff_manifest import (
    HandoffPlaceholder,
    build_handoff_placeholder_manifest,
)
from blueprints.validation.validator import validate_blueprint

if TYPE_CHECKING:
    from catalog.knowledge import KnowledgeStoreQuery
    from catalog.models import CatalogSnapshot

    from blueprints.ast.models import MakeAstRoot
    from blueprints.validation.models import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )


class BlueprintDeliveryCoverage(NamedTuple):
    """Compact delivery coverage summary for one blueprint."""

    catalog_fingerprint: str
    delivery_mode: BlueprintDeliveryMode
    error_count: int
    warning_count: int
    optimization_count: int
    explanation_count: int
    handoff_placeholder_count: int
    client_ready_score: float


def build_blueprint_delivery_coverage(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    knowledge: KnowledgeStoreQuery | None = None,
) -> BlueprintDeliveryCoverage:
    """Return a deterministic client-ready coverage summary."""
    report = validate_blueprint(root=root, catalog=catalog, knowledge=knowledge)
    placeholders = build_handoff_placeholder_manifest(
        root=root, catalog=catalog
    )
    return build_blueprint_delivery_coverage_from_report(
        report=report,
        catalog=catalog,
        placeholders=placeholders,
    )


def build_blueprint_delivery_coverage_from_report(
    *,
    report: BlueprintValidationReport,
    catalog: CatalogSnapshot,
    placeholders: tuple[HandoffPlaceholder, ...],
) -> BlueprintDeliveryCoverage:
    """Return delivery coverage from an existing validation and handoff pass."""
    error_count = _severity_count(report.findings, "error")
    warning_count = _severity_count(report.findings, "warning")
    optimization_count = _severity_count(report.findings, "optimization")
    explanation_count = _severity_count(report.findings, "explanation")
    return BlueprintDeliveryCoverage(
        catalog_fingerprint=catalog.fingerprint,
        delivery_mode=achieved_blueprint_delivery_mode(report),
        error_count=error_count,
        warning_count=warning_count,
        optimization_count=optimization_count,
        explanation_count=explanation_count,
        handoff_placeholder_count=len(placeholders),
        client_ready_score=_score(
            errors=error_count,
            warnings=warning_count,
            placeholders=len(placeholders),
        ),
    )


def coverage_regressed(
    *,
    baseline: BlueprintDeliveryCoverage,
    current: BlueprintDeliveryCoverage,
) -> bool:
    """Return whether delivery coverage became worse."""
    return current.client_ready_score < baseline.client_ready_score


def _severity_count(
    findings: tuple[BlueprintValidationFinding, ...], severity: str
) -> int:
    """Return number of findings with a given severity attribute."""
    return sum(1 for finding in findings if finding.severity == severity)


def _score(*, errors: int, warnings: int, placeholders: int) -> float:
    """Return a bounded client-ready score."""
    penalty = (errors * 40) + (warnings * 10) + (placeholders * 5)
    return max(0.0, round((100 - penalty) / 100, 3))
