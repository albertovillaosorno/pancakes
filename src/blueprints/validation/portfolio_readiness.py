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

"""Build offline portfolio readiness rows for Make project fixture assets.

Boundary contract:
- Owns: read-only portfolio readiness rows from fixture scenario.json files.
- Must not: mutate assets, render client reports, call live Make, or read
credentials.
- Allows: project discovery, offline validation composition, and compact matrix
rows.
- Split when: markdown rendering or release gates need independent ownership.
- Merge when: another reporting module returns the same matrix contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

from blueprints.ast import parse_make_ast_json_text
from blueprints.ast.artifacts import classify_blueprint_artifact_phase
from blueprints.ast.errors import MakeAstParseError
from blueprints.validation.delivery_coverage import (
    build_blueprint_delivery_coverage_from_report,
)
from blueprints.validation.generation_gate import guard_blueprint_for_handoff
from blueprints.validation.handoff_manifest import (
    build_handoff_placeholder_manifest,
    build_handoff_readiness_manifest,
    build_offline_handoff_evidence_sources,
)

if TYPE_CHECKING:
    from pathlib import Path

    from catalog.knowledge import KnowledgeStoreQuery
    from catalog.models import CatalogSnapshot

    from blueprints.ast.artifacts import BlueprintArtifactPhase
    from blueprints.ast.models import JsonObject
    from blueprints.validation.delivery_mode import BlueprintDeliveryMode

type PortfolioReadinessStatus = Literal[
    "blocked",
    "source_draft",
    "importable_candidate",
    "live_make_scenario",
]
type PortfolioEvidenceStatus = Literal[
    "offline_validation_only",
    "offline_parse_failed",
]
PROJECT_TEMPLATE_PART: Final = "templates"


class PortfolioReadinessRow(NamedTuple):
    """One portfolio asset readiness row from offline repository evidence."""

    project_id: str
    project_name: str
    relative_scenario_path: str
    artifact_phase: BlueprintArtifactPhase
    importability_status: PortfolioReadinessStatus
    delivery_mode: BlueprintDeliveryMode | str
    blocker_count: int
    warning_count: int
    placeholder_count: int
    evidence_status: PortfolioEvidenceStatus
    live_make_called: bool
    blocker_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    placeholder_keys: tuple[str, ...]
    client_ready_score: float


class PortfolioReadinessMatrix(NamedTuple):
    """Portfolio readiness matrix sorted by project ID and scenario path."""

    rows: tuple[PortfolioReadinessRow, ...]

    def row_for_project(self, project_id: str) -> PortfolioReadinessRow | None:
        """Return the first matrix row for one project ID when present."""
        for row in self.rows:
            if row.project_id == project_id:
                return row
        return None


def build_portfolio_readiness_matrix(
    *,
    projects_root: Path,
    catalog: CatalogSnapshot,
    knowledge: KnowledgeStoreQuery | None = None,
) -> PortfolioReadinessMatrix:
    """Return readiness rows for portfolio project scenario fixtures."""
    repo_root = _infer_repo_root(projects_root)
    rows = tuple(
        _readiness_row(
            scenario_path=scenario_path,
            projects_root=projects_root,
            repo_root=repo_root,
            catalog=catalog,
            knowledge=knowledge,
        )
        for scenario_path in _project_scenario_paths(projects_root)
    )
    return PortfolioReadinessMatrix(
        rows=tuple(
            sorted(
                rows,
                key=lambda row: (row.project_id, row.relative_scenario_path),
            )
        )
    )


def _readiness_row(
    *,
    scenario_path: Path,
    projects_root: Path,
    repo_root: Path,
    catalog: CatalogSnapshot,
    knowledge: KnowledgeStoreQuery | None,
) -> PortfolioReadinessRow:
    """Return one readiness row from a scenario asset."""
    project_id = _project_id(
        scenario_path=scenario_path, projects_root=projects_root
    )
    relative_path = _relative_path(path=scenario_path, repo_root=repo_root)
    try:
        payload = _read_json_object(scenario_path)
        root = parse_make_ast_json_text(
            json.dumps(payload, ensure_ascii=True, sort_keys=True)
        )
    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
        ValueError,
        MakeAstParseError,
    ) as exc:
        return _parse_failed_row(
            project_id=project_id,
            scenario_path=scenario_path,
            relative_path=relative_path,
            error=exc,
        )

    artifact_phase = classify_blueprint_artifact_phase(payload)
    strict_gate = guard_blueprint_for_handoff(
        root=root,
        catalog=catalog,
        knowledge=knowledge,
    )
    report = strict_gate.validation_report
    placeholders = build_handoff_placeholder_manifest(
        root=root, catalog=catalog
    )
    coverage = build_blueprint_delivery_coverage_from_report(
        report=report,
        catalog=catalog,
        placeholders=placeholders,
    )
    manifest = build_handoff_readiness_manifest(
        report=report,
        placeholders=placeholders,
        importable=strict_gate.importable,
        live_make_called=False,
        evidence_sources=build_offline_handoff_evidence_sources(),
    )
    return PortfolioReadinessRow(
        project_id=project_id,
        project_name=root.scenario.name,
        relative_scenario_path=relative_path,
        artifact_phase=artifact_phase,
        importability_status=_readiness_status(
            strict_importable=strict_gate.importable
        ),
        delivery_mode=coverage.delivery_mode,
        blocker_count=len(manifest.blockers),
        warning_count=len(manifest.warnings),
        placeholder_count=len(manifest.placeholders),
        evidence_status="offline_validation_only",
        live_make_called=manifest.live_make_called,
        blocker_codes=tuple(blocker.code for blocker in manifest.blockers),
        warning_codes=tuple(warning.code for warning in manifest.warnings),
        placeholder_keys=tuple(
            placeholder.key for placeholder in manifest.placeholders
        ),
        client_ready_score=coverage.client_ready_score,
    )


def _parse_failed_row(
    *,
    project_id: str,
    scenario_path: Path,
    relative_path: str,
    error: Exception,
) -> PortfolioReadinessRow:
    """Return a blocked row when a project scenario cannot be parsed."""
    return PortfolioReadinessRow(
        project_id=project_id,
        project_name=scenario_path.parent.name,
        relative_scenario_path=relative_path,
        artifact_phase="source_draft",
        importability_status="blocked",
        delivery_mode="source_draft",
        blocker_count=1,
        warning_count=0,
        placeholder_count=0,
        evidence_status="offline_parse_failed",
        live_make_called=False,
        blocker_codes=(
            f"portfolio.scenario_parse_failed:{type(error).__name__}",
        ),
        warning_codes=(),
        placeholder_keys=(),
        client_ready_score=0.0,
    )


def _project_scenario_paths(projects_root: Path) -> tuple[Path, ...]:
    """Return the computed result for the caller."""
    return tuple(
        sorted(
            path
            for path in projects_root.rglob("scenario.json")
            if path.is_file()
            and not _has_template_part(path.relative_to(projects_root))
        )
    )


def _has_template_part(relative_path: Path) -> bool:
    """Return if one project-relative path is a template or private helper."""
    return any(
        part == PROJECT_TEMPLATE_PART or part.startswith("_")
        for part in relative_path.parts
    )


def _read_json_object(path: Path) -> JsonObject:
    """Return one scenario JSON object.

    Raises:
        TypeError: If the scenario JSON root is not an object.
    """

    def reject_non_standard_constant(raw_value: str) -> object:
        message = (
            f"Portfolio scenario uses non-standard JSON constant {raw_value}:"
            f"{path}"
        )
        raise ValueError(message)

    payload = cast(
        "object",
        json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=reject_non_standard_constant,
        ),
    )
    if not _is_json_object(payload):
        message = (
            f"Portfolio project scenario must contain a JSON object: {path}"
        )
        raise TypeError(message)
    return payload


def _readiness_status(*, strict_importable: bool) -> PortfolioReadinessStatus:
    """Return the matrix importability status from strict handoff evidence."""
    if strict_importable:
        return "importable_candidate"
    return "blocked"


def _project_id(*, scenario_path: Path, projects_root: Path) -> str:
    """Return the project ID implied by a scenario path."""
    try:
        relative = scenario_path.relative_to(projects_root)
    except ValueError:
        return scenario_path.parent.name
    return relative.parts[0] if relative.parts else scenario_path.parent.name


def _relative_path(*, path: Path, repo_root: Path) -> str:
    """Return one deterministic repository-relative path when possible."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _infer_repo_root(projects_root: Path) -> Path:
    """Return the repository root implied by projects."""
    return projects_root.parent


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether one value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
