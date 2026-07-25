# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001049#repo.error-handling.repair-diagnostics-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Phase-gate diagnostics for Make AST artifact transitions.

Boundary contract:
- Owns: naming artifact phases and formatting phase-gate diagnostics.
- Must not: implement validation rules, render blueprints, or repair artifacts.
- Allows: parser wrapping and conversion of validation reports into
  phase results.
- Split when: independent artifact life cycles need separate gate result
  families.
- Merge when: another AST module formats the same phase diagnostics.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final, Literal, NamedTuple

from blueprints.ast.errors import MakeAstParseError
from blueprints.ast.parser import parse_make_ast_json_text

if TYPE_CHECKING:
    from blueprints.ast.models import MakeAstRoot
    from blueprints.validation.models import BlueprintValidationReport

type BlueprintArtifactPhase = Literal["parse", "compile", "render", "handoff"]

PHASE_PARSE: Final[BlueprintArtifactPhase] = "parse"
PHASE_COMPILE: Final[BlueprintArtifactPhase] = "compile"
PHASE_RENDER: Final[BlueprintArtifactPhase] = "render"
PHASE_HANDOFF: Final[BlueprintArtifactPhase] = "handoff"


class BlueprintPhaseDiagnostic(NamedTuple):
    """One actionable diagnostic emitted by an artifact phase gate."""

    phase: BlueprintArtifactPhase
    code: str
    message: str
    blueprint_path: tuple[str | int, ...] = ()


class BlueprintPhaseGateReport(NamedTuple):
    """Result of checking one artifact phase transition."""

    phase: BlueprintArtifactPhase
    passed: bool
    diagnostics: tuple[BlueprintPhaseDiagnostic, ...] = ()


class BlueprintPhaseGateError(RuntimeError):
    """Raised when a phase gate blocks an artifact transition."""

    def __init__(
        self,
        *,
        phase: BlueprintArtifactPhase,
        diagnostics: tuple[BlueprintPhaseDiagnostic, ...],
    ) -> None:
        """Store phase-gate diagnostics on the raised error."""
        super().__init__(
            _phase_gate_message(phase=phase, diagnostics=diagnostics)
        )
        self.phase = phase
        self.diagnostics = diagnostics


def parse_blueprint_phase(
    source_text: str,
    *,
    blueprint_path: tuple[str | int, ...] = (),
) -> MakeAstRoot:
    """Parse source JSON or raise a phase-gate error with parser diagnostics.

    Returns:
        The parsed AST root.

    Raises:
        BlueprintPhaseGateError: If parsing fails before downstream phases
            can run.
    """
    try:
        return parse_make_ast_json_text(source_text)
    except MakeAstParseError as error:
        diagnostic = BlueprintPhaseDiagnostic(
            phase=PHASE_PARSE,
            code="phase.parse_error",
            message=str(error),
            blueprint_path=blueprint_path,
        )
        raise BlueprintPhaseGateError(
            phase=PHASE_PARSE,
            diagnostics=(diagnostic,),
        ) from error


def phase_gate_from_validation_report(
    *,
    phase: BlueprintArtifactPhase,
    report: BlueprintValidationReport,
) -> BlueprintPhaseGateReport:
    """Convert validation errors into one phase-gate result.

    Returns:
        The phase gate result derived from the main validator report.
    """
    diagnostics = tuple(
        BlueprintPhaseDiagnostic(
            phase=phase,
            code=finding.code,
            message=finding.client_message,
            blueprint_path=finding.source_path,
        )
        for finding in report.findings
        if finding.severity == "error"
    )
    return BlueprintPhaseGateReport(
        phase=phase,
        passed=not diagnostics,
        diagnostics=diagnostics,
    )


def format_blueprint_path(path: tuple[str | int, ...]) -> str:
    """Return a compact JSONPath-like location for a blueprint path."""
    if not path:
        return "$"
    parts = ["$"]
    for item in path:
        if isinstance(item, int):
            parts.append(f"[{item}]")
            continue
        if item.isidentifier():
            parts.append(f".{item}")
            continue
        parts.append(f"[{json.dumps(item, sort_keys=True)}]")
    return "".join(parts)


def _phase_gate_message(
    *,
    phase: BlueprintArtifactPhase,
    diagnostics: tuple[BlueprintPhaseDiagnostic, ...],
) -> str:
    """Return a concise phase-gate exception message."""
    if not diagnostics:
        return f"Blueprint {phase} phase failed without diagnostics."
    first = diagnostics[0]
    path = format_blueprint_path(first.blueprint_path)
    return f"Blueprint {phase} phase failed at {path}: {first.message}"
