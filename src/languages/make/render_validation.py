# Repository header: begin
# Provenance source mode: source_refs
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Compose Make blueprint export with offline source-gate validation.

Boundary contract:
- Owns: Make adapter render-and-validate orchestration over source gates and
  output JSON parse.
- Must not: implement generic AST semantics, mutate live services, or persist
  artifacts.
- Allows: draft/strict Make export composition and typed diagnostics over
  rendered JSON.
- Split when: MCP, handoff, or bundle persistence need caller-specific
  workflows.
- Merge when: another Make adapter module owns the same render-and-validate
  operation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal, NamedTuple

from blueprints.ast.artifacts import classify_blueprint_artifact_phase
from blueprints.ast.parser import parse_make_ast_json_text
from blueprints.ast.phase_gates import (
    PHASE_RENDER,
    BlueprintPhaseDiagnostic,
    BlueprintPhaseGateReport,
    phase_gate_from_validation_report,
)

from languages.make.blueprint_export import (
    MakeBlueprintRenderMode,
    MakeBlueprintRenderReport,
    render_make_blueprint_payload,
)

if TYPE_CHECKING:
    from blueprints.ast.artifacts import BlueprintArtifactPhase
    from blueprints.ast.models import JsonObject, MakeAstRoot
    from blueprints.validation.models import (
        BlueprintGenerationGateReport,
        BlueprintValidationReport,
    )
    from catalog.knowledge import KnowledgeStoreQuery
    from catalog.models import CatalogSnapshot

type MakeBlueprintRenderValidationMode = Literal["strict", "draft"]


class MakeBlueprintRenderValidationReport(NamedTuple):
    """Rendered Make blueprint payload plus validation diagnostics."""

    mode: MakeBlueprintRenderValidationMode
    rendered_payload: JsonObject
    artifact_phase: BlueprintArtifactPhase
    importable: bool
    render_result: MakeBlueprintRenderReport
    generation_gate: BlueprintGenerationGateReport
    validation_report: BlueprintValidationReport
    phase_gates: tuple[BlueprintPhaseGateReport, ...]
    diagnostics: tuple[BlueprintPhaseDiagnostic, ...]


def render_and_validate_blueprint(
    *,
    root: MakeAstRoot,
    catalog: CatalogSnapshot,
    mode: MakeBlueprintRenderValidationMode = "strict",
    knowledge: KnowledgeStoreQuery | None = None,
) -> MakeBlueprintRenderValidationReport:
    """Render a Make blueprint payload after source validation.

    Returns:
        The rendered payload and validation outcome for the rendered artifact.

    Raises:
        ValueError: If the composition mode is unsupported.
    """
    if mode not in {"strict", "draft"}:
        message = f"Unsupported Make blueprint render validation mode: {mode!r}"
        raise ValueError(message)
    render_result = render_make_blueprint_payload(
        root=root,
        catalog=catalog,
        mode=_renderer_mode(mode),
        knowledge=knowledge,
    )
    _ = parse_make_ast_json_text(
        json.dumps(render_result.payload, sort_keys=True)
    )
    generation_gate = render_result.gate
    render_phase_gate = phase_gate_from_validation_report(
        phase=PHASE_RENDER,
        report=generation_gate.validation_report,
    )
    return MakeBlueprintRenderValidationReport(
        mode=mode,
        rendered_payload=render_result.payload,
        artifact_phase=classify_blueprint_artifact_phase(render_result.payload),
        importable=mode == "strict"
        and render_result.importable
        and generation_gate.can_render,
        render_result=render_result,
        generation_gate=generation_gate,
        validation_report=generation_gate.validation_report,
        phase_gates=(render_phase_gate,),
        diagnostics=render_phase_gate.diagnostics,
    )


def _renderer_mode(
    mode: MakeBlueprintRenderValidationMode,
) -> MakeBlueprintRenderMode:
    """Return the renderer mode matching one Make composition mode."""
    return "importable" if mode == "strict" else "draft"
