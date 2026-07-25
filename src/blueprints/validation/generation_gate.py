# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# - 001045#repo.make-ast.module-resolution-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001066#repo.make-linter.secondary-linter-advisory-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Pre-render gate that blocks unsafe blueprint generation.

Boundary contract:
- Owns: converting validation errors into pre-render generation blockers.
- Must not: render blueprints, repair findings, or query live upstream services.
- Allows: offline validation composition and client-safe blocker explanations.
- Split when: blocker families need independent policy or evidence rules.
- Merge when: another gate returns the same blocker result from
blueprints.validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple

from catalog.knowledge import secondary_linter_result_from_validation_findings

from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.handoff_manifest import (
    HandoffBlockerSummary,
    build_handoff_blocker_manifest,
)
from blueprints.validation.models import (
    BlueprintGenerationBlocker,
    BlueprintGenerationGateReport,
    BlueprintValidationFinding,
)
from blueprints.validation.validator import validate_blueprint

if TYPE_CHECKING:
    from catalog.knowledge import KnowledgeStoreQuery
    from catalog.models import CatalogSnapshot

    from blueprints.ast.models import MakeAstRoot
    from blueprints.validation.models import BlueprintValidationReport

type BlueprintHandoffGateMode = Literal["strict", "draft"]
type BlueprintHandoffGateStatus = Literal["allowed", "blocked"]

UNSUPPORTED_MODULE_EVIDENCE: Final[tuple[str, ...]] = (
    "Make app raw spec ",
    "Make module schema ",
    "validated catalog record ",
    "catalog refresh access or exported spec",
)
VALIDATION_FAILURE_EVIDENCE: Final[tuple[str, ...]] = (
    "validated Make catalog record ",
    "complete required module mappings ",
    "passing blueprint validation report",
)


class BlueprintHandoffGateReport(NamedTuple):
    """Strict or draft handoff readiness result for one blueprint."""

    mode: BlueprintHandoffGateMode
    status: BlueprintHandoffGateStatus
    importable: bool
    validation_report: BlueprintValidationReport
    blockers: tuple[HandoffBlockerSummary, ...]
    generation_gate: BlueprintGenerationGateReport
    operator_message: str


def guard_blueprint_for_render(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    knowledge: KnowledgeStoreQuery | None = None,
) -> BlueprintGenerationGateReport:
    """Return whether a generated or assembled blueprint may be rendered."""
    validation_report = validate_blueprint(
        root=root, catalog=catalog, knowledge=knowledge
    )
    module_tokens_by_node = {
        node.node_id: node.module_token
        for node in iter_ast_nodes(root)
        if node.module_token
    }
    error_findings = validation_report.blocking_findings()
    blockers = tuple(
        _blocker_from_finding(
            finding=finding,
            module_tokens_by_node=module_tokens_by_node,
            error_index=error_index,
        )
        for error_index, finding in enumerate(error_findings, start=1)
    )
    status = "blocked" if blockers else "allowed"
    return BlueprintGenerationGateReport(
        status=status,
        validation_report=validation_report,
        blockers=blockers,
        secondary_linter=secondary_linter_result_from_validation_findings(
            validation_report.findings
        ),
    )


def guard_blueprint_for_handoff(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    mode: BlueprintHandoffGateMode = "strict",
    knowledge: KnowledgeStoreQuery | None = None,
) -> BlueprintHandoffGateReport:
    """Return whether a blueprint may be presented as handoff-importable.

    Raises:
        ValueError: If the handoff gate mode is unsupported.
    """
    if mode not in {"strict", "draft"}:
        message = f"Unsupported Make handoff gate mode: {mode!r}"
        raise ValueError(message)
    generation_gate = guard_blueprint_for_render(
        root=root,
        catalog=catalog,
        knowledge=knowledge,
    )
    blockers = build_handoff_blocker_manifest(
        report=generation_gate.validation_report
    )
    status: BlueprintHandoffGateStatus = (
        "blocked" if mode == "strict" and blockers else "allowed"
    )
    importable = (
        mode == "strict" and status == "allowed" and generation_gate.can_render
    )
    return BlueprintHandoffGateReport(
        mode=mode,
        status=status,
        importable=importable,
        validation_report=generation_gate.validation_report,
        blockers=blockers,
        generation_gate=generation_gate,
        operator_message=_handoff_operator_message(
            mode=mode,
            status=status,
            blockers=blockers,
        ),
    )


def _blocker_from_finding(
    *,
    finding: BlueprintValidationFinding,
    module_tokens_by_node: dict[str, str],
    error_index: int,
) -> BlueprintGenerationBlocker:
    """Convert one validation error into a generation blocker.

    Returns:
        The result produced by convert one validation error into a generation
        blocker.
    """
    requested_module = (
        module_tokens_by_node.get(finding.node_id)
        if finding.node_id is not None
        else None
    )
    if finding.code == "module.unresolved":
        return _unsupported_module_blocker(
            finding=finding,
            requested_module=requested_module,
            error_index=error_index,
        )
    return _validation_failure_blocker(
        finding=finding,
        requested_module=requested_module,
        error_index=error_index,
    )


def _unsupported_module_blocker(
    *,
    finding: BlueprintValidationFinding,
    requested_module: str | None,
    error_index: int,
) -> BlueprintGenerationBlocker:
    """Return a proposal-friendly blocker for an unknown module request."""
    return BlueprintGenerationBlocker(
        blocker_id=f"blocker:unsupported-module:{finding.node_id or 'root'}:{error_index}",
        code="generation.unsupported_module",
        node_id=finding.node_id,
        requested_module=requested_module,
        client_explanation=(
            "The requested Make module is not in the validated catalog. "
            "Add or refresh the Make app/module spec before a blueprint can be "
            "produced."
        ),
        internal_detail=finding.internal_message,
        needed_evidence=UNSUPPORTED_MODULE_EVIDENCE,
    )


def _validation_failure_blocker(
    *,
    finding: BlueprintValidationFinding,
    requested_module: str | None,
    error_index: int,
) -> BlueprintGenerationBlocker:
    """Return a blocker for a non-module validation failure."""
    return BlueprintGenerationBlocker(
        blocker_id=f"blocker:validation:{finding.code}:{finding.node_id or 'root'}:{error_index}",
        code="generation.validation_failed",
        node_id=finding.node_id,
        requested_module=requested_module,
        client_explanation=(
            "The blueprint request needs additional validated details "
            "before it "
            "can be rendered."
        ),
        internal_detail=finding.internal_message,
        needed_evidence=VALIDATION_FAILURE_EVIDENCE,
    )


def _handoff_operator_message(
    *,
    mode: BlueprintHandoffGateMode,
    status: BlueprintHandoffGateStatus,
    blockers: tuple[HandoffBlockerSummary, ...],
) -> str:
    """Return concise operator guidance for the first handoff gate outcome."""
    if blockers:
        first = blockers[0]
        prefix = (
            "Strict handoff is blocked"
            if status == "blocked"
            else "Draft handoff is allowed for review but is not importable"
        )
        return (
            f"{prefix}; fix {first.code} at {first.json_pointer} "
            f"with suggested owner {first.suggested_owner} first."
        )
    if mode == "draft":
        return "Draft handoff is allowed for review but is not importable."
    return "Strict handoff passed offline importability checks."
