# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001060#repo.architecture.srp.extreme-one-responsibility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Analyze designer coordinate transitions between parsed AST blueprints.

Boundary contract:
- Owns: comparing designer coordinate movement between two parsed AST roots.
- Must not: compute new layouts, mutate payloads, or evaluate runtime drift.
- Allows: movement records, aggregate transition summaries, and spacing
inference.
- Split when: movement scoring or layout-drift policy needs ownership.
- Merge when: another analyzer returns the same transition summary.
"""

from __future__ import annotations

import math
from itertools import pairwise
from statistics import median
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

from blueprints.ast.traversal import iter_ast_nodes

if TYPE_CHECKING:
    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )

type BlueprintDesignerDiagnosticSeverity = Literal["warning"]

DESIGNER_DIAGNOSTIC_SOURCE: Final = "designer_layout_analysis"
CROWDED_BRANCH_THRESHOLD: Final = 2


class BlueprintLayoutMovement(NamedTuple):
    """Coordinate movement for one AST node."""

    node_id: str
    module_token: str
    before: tuple[int | None, int | None]
    after: tuple[int | None, int | None]
    delta: tuple[int | None, int | None]
    source_path: tuple[AstPathPart, ...]


class BlueprintLayoutTransitionReport(NamedTuple):
    """Aggregate coordinate transition summary."""

    module_count: int
    moved_count: int
    inferred_column_spacing: int | None
    inferred_row_spacing: int | None
    movements: tuple[BlueprintLayoutMovement, ...]


class BlueprintDesignerDiagnostic(NamedTuple):
    """One advisory designer usability diagnostic from static AST evidence."""

    diagnostic_id: str
    diagnostic_source: str
    severity: BlueprintDesignerDiagnosticSeverity
    code: str
    node_id: str | None
    client_message: str
    internal_message: str
    source_path: tuple[AstPathPart, ...]


def analyze_blueprint_layout_transition(
    before: MakeAstRoot,
    after: MakeAstRoot,
) -> BlueprintLayoutTransitionReport:
    """Compare designer coordinates between two parsed blueprints.

    Returns:
        The result produced by compare designer coordinates between two parsed
        blueprints.
    """
    before_nodes = {node.node_id: node for node in iter_ast_nodes(before)}
    after_nodes = {node.node_id: node for node in iter_ast_nodes(after)}
    movements = tuple(
        _movement(before_nodes[node_id], after_nodes[node_id])
        for node_id in sorted(before_nodes.keys() & after_nodes.keys())
    )
    return BlueprintLayoutTransitionReport(
        module_count=len(movements),
        moved_count=sum(1 for movement in movements if _changed(movement)),
        inferred_column_spacing=_infer_spacing(
            [item.after[0] for item in movements]
        ),
        inferred_row_spacing=_infer_spacing(
            [item.after[1] for item in movements]
        ),
        movements=movements,
    )


def analyze_blueprint_designer_diagnostics(
    root: MakeAstRoot,
) -> tuple[BlueprintDesignerDiagnostic, ...]:
    """Return nonblocking designer usability diagnostics from local AST.

    evidence.

    Returns:
        The advisory designer diagnostics detected from the parsed AST.
    """
    nodes = iter_ast_nodes(root)
    noted_module_ids = _noted_module_ids(root)
    diagnostics: list[BlueprintDesignerDiagnostic] = []
    for node in nodes:
        diagnostics.extend(_missing_label_diagnostic(node))
        diagnostics.extend(_crowded_branch_diagnostic(node))
        diagnostics.extend(
            _missing_module_note_diagnostic(node, noted_module_ids)
        )
    diagnostics.extend(_overlapping_coordinate_diagnostics(nodes))
    return tuple(diagnostics)


def _movement(
    before: MakeAstNode, after: MakeAstNode
) -> BlueprintLayoutMovement:
    """Return coordinate movement for one node pair."""
    before_position = _position(before)
    after_position = _position(after)
    return BlueprintLayoutMovement(
        node_id=after.node_id,
        module_token=after.module_token,
        before=before_position,
        after=after_position,
        delta=_delta(before_position, after_position),
        source_path=after.source_trace.path,
    )


def _position(node: MakeAstNode) -> tuple[int | None, int | None]:
    """Return the designer x/y position for one node."""
    metadata = node.raw_payload.get("metadata")
    if not _is_json_object(metadata):
        return None, None
    designer = metadata.get("designer")
    if not _is_json_object(designer):
        return None, None
    return _coordinate(designer.get("x")), _coordinate(designer.get("y"))


def _coordinate(value: object) -> int | None:
    """Return one coordinate as an integer when safe."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return (
            int(value) if math.isfinite(value) and value.is_integer() else None
        )
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


def _delta(
    before: tuple[int | None, int | None],
    after: tuple[int | None, int | None],
) -> tuple[int | None, int | None]:
    """Return coordinate delta for one movement."""
    return (
        None if before[0] is None or after[0] is None else after[0] - before[0],
        None if before[1] is None or after[1] is None else after[1] - before[1],
    )


def _changed(movement: BlueprintLayoutMovement) -> bool:
    """Return whether one movement changed coordinates."""
    return movement.delta[0] not in {None, 0} or movement.delta[1] not in {
        None,
        0,
    }


def _infer_spacing(coordinates: list[int | None]) -> int | None:
    """Infer median positive spacing from sorted coordinates.

    Returns:
        The result produced by infer median positive spacing from sorted
        coordinates.
    """
    concrete = sorted({value for value in coordinates if value is not None})
    deltas = [right - left for left, right in pairwise(concrete)]
    positive = [delta for delta in deltas if delta > 0]
    return None if not positive else int(median(positive))


def _missing_label_diagnostic(
    node: MakeAstNode,
) -> tuple[BlueprintDesignerDiagnostic, ...]:
    """Return an advisory diagnostic when one module lacks an explicit label."""
    if _has_explicit_label(node):
        return ()
    return (
        _designer_diagnostic(
            code="designer.label_missing",
            node_id=node.node_id,
            source_path=node.source_trace.path,
            client_message="A module has no explicit designer label.",
            internal_message=(
                f"Node {node.node_id} falls back to module token "
                f"{node.module_token!r}."
            ),
        ),
    )


def _crowded_branch_diagnostic(
    node: MakeAstNode,
) -> tuple[BlueprintDesignerDiagnostic, ...]:
    """Return an advisory diagnostic when one branch owner has many branches."""
    branch_count = len(node.routes) + len(node.branches) + len(node.tools)
    if branch_count <= CROWDED_BRANCH_THRESHOLD:
        return ()
    return (
        _designer_diagnostic(
            code="designer.branch_crowded",
            node_id=node.node_id,
            source_path=_branch_source_path(node),
            client_message="A branch owner has more than two visible branches.",
            internal_message=(
                f"Node {node.node_id} owns {branch_count} branch-like "
                f"designer lanes."
            ),
        ),
    )


def _missing_module_note_diagnostic(
    node: MakeAstNode,
    noted_module_ids: frozenset[str],
) -> tuple[BlueprintDesignerDiagnostic, ...]:
    """Return an advisory diagnostic when no root note references one module."""
    if node.node_id in noted_module_ids:
        return ()
    return (
        _designer_diagnostic(
            code="designer.module_note_missing",
            node_id=node.node_id,
            source_path=node.source_trace.path,
            client_message="A module has no attached handoff note.",
            internal_message=(
                f"Root metadata.notes does not reference node {node.node_id}."
            ),
        ),
    )


def _overlapping_coordinate_diagnostics(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintDesignerDiagnostic, ...]:
    """Return the computed result for the caller."""
    nodes_by_position: dict[tuple[int, int], list[MakeAstNode]] = {}
    for node in nodes:
        x, y = _position(node)
        if x is None or y is None:
            continue
        nodes_by_position.setdefault((x, y), []).append(node)

    diagnostics: list[BlueprintDesignerDiagnostic] = []
    for position in sorted(nodes_by_position):
        overlapping = nodes_by_position[position]
        if len(overlapping) <= 1:
            continue
        overlap_ids = ", ".join(node.node_id for node in overlapping)
        diagnostics.extend(
            (
                _designer_diagnostic(
                    code="designer.coordinates_overlap",
                    node_id=node.node_id,
                    source_path=(
                        *node.source_trace.path,
                        "metadata ",
                        "designer",
                    ),
                    client_message=(
                        "A module shares designer coordinates with another "
                        "module."
                    ),
                    internal_message=(
                        f"Node {node.node_id} shares designer position "
                        f"{position} "
                        f"with nodes {overlap_ids}."
                    ),
                )
            )
            for node in overlapping
        )
    return tuple(diagnostics)


def _designer_diagnostic(
    *,
    code: str,
    node_id: str | None,
    source_path: tuple[AstPathPart, ...],
    client_message: str,
    internal_message: str,
) -> BlueprintDesignerDiagnostic:
    """Return one stable advisory designer diagnostic."""
    node_token = node_id or "root"
    return BlueprintDesignerDiagnostic(
        diagnostic_id=f"{DESIGNER_DIAGNOSTIC_SOURCE}:{code}:{node_token}",
        diagnostic_source=DESIGNER_DIAGNOSTIC_SOURCE,
        severity="warning",
        code=code,
        node_id=node_id,
        client_message=client_message,
        internal_message=internal_message,
        source_path=source_path,
    )


def _has_explicit_label(node: MakeAstNode) -> bool:
    """Return whether one node carries a human-authored label or name."""
    return _has_text(node.raw_payload.get("label")) or _has_text(
        node.raw_payload.get("name")
    )


def _has_text(value: object) -> bool:
    """Return whether one value is nonempty explicit text."""
    if not isinstance(value, str):
        return False
    return bool(value.strip())


def _branch_source_path(node: MakeAstNode) -> tuple[AstPathPart, ...]:
    """Return the source path for a branch-like container on one node."""
    if node.routes:
        return (*node.source_trace.path, "routes")
    if node.branches:
        return (*node.source_trace.path, "branches")
    return (*node.source_trace.path, "tools")


def _noted_module_ids(root: MakeAstRoot) -> frozenset[str]:
    """Return module IDs referenced by structured root metadata notes."""
    notes = root.scenario.metadata.get("notes")
    if not isinstance(notes, list):
        return frozenset()
    noted: set[str] = set()
    for note in cast("list[object]", notes):
        if not _is_json_object(note):
            continue
        module_ids = note.get("moduleIds")
        if not isinstance(module_ids, list):
            continue
        for module_id in cast("list[object]", module_ids):
            text = _note_module_id_text(module_id)
            if text:
                noted.add(text)
    return frozenset(noted)


def _note_module_id_text(value: object) -> str | None:
    """Return a normalized note module ID value when supported."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    text = str(value).strip()
    return text or None


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether one value is a string-keyed object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
