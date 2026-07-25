# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001049#repo.blueprint-repair.offline-action-contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Explicit offline blueprint repair action.

Boundary contract:
- Owns: composing validation, diagnostics, and placeholders into one outcome.
- Must not: mutate the blueprint, call live services, or apply repairs.
- Allows: offline orchestration over typed AST and catalog inputs.
- Split when: repair application or live staging becomes an explicit workflow.
- Merge when: another offline entrypoint returns this exact outcome unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from blueprints.repair.diagnostics import propose_repair_candidates
from blueprints.repair.outcome import (
    BlueprintRepairOutcome,
    BlueprintRepairStatus,
)
from blueprints.validation import (
    build_handoff_placeholder_manifest,
    validate_blueprint,
)

if TYPE_CHECKING:
    from catalog.knowledge import KnowledgeStoreQuery
    from catalog.models import CatalogSnapshot

    from blueprints.ast.models import MakeAstRoot
    from blueprints.validation import BlueprintValidationReport


def repair_blueprint_offline(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    knowledge: KnowledgeStoreQuery | None = None,
) -> BlueprintRepairOutcome:
    """Return an explicit offline repair outcome without mutation."""
    validation_report = validate_blueprint(
        root=root, catalog=catalog, knowledge=knowledge
    )
    diagnostics = propose_repair_candidates(validation_report)
    placeholders = build_handoff_placeholder_manifest(
        root=root, catalog=catalog
    )
    return BlueprintRepairOutcome(
        status=_status(validation_report),
        validation_report=validation_report,
        diagnostics=diagnostics,
        handoff_placeholders=placeholders,
    )


def _status(report: BlueprintValidationReport) -> BlueprintRepairStatus:
    """Return the offline repair status from blueprints.validation severity."""
    if any(finding.severity == "error" for finding in report.findings):
        return "rejected_with_reasons"
    if report.findings:
        return "accepted_as_generated"
    return "not_applicable"
