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

"""Plan deterministic Make blueprint designer coordinates.

Boundary contract:
- Owns: deterministic coordinate planning for parsed blueprint AST nodes.
- Must not: mutate payloads, analyze existing transitions, or render blueprints.
- Allows: traversal-shaped layout plans with configurable spacing.
- Split when: branch, route, or tool layout policy needs separate ownership.
- Merge when: another planner produces the same layout plan identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.ast.layout_models import (
    BlueprintLayoutPlan,
    BlueprintNodeLayout,
    BlueprintNoteLayout,
)

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject, MakeAstNode, MakeAstRoot

DEFAULT_COLUMN_SPACING: Final = 300
DEFAULT_ROW_SPACING: Final = 1850
DEFAULT_NOTE_OFFSET_X: Final = 120
DEFAULT_NOTE_OFFSET_Y: Final = 220
DEFAULT_NOTE_STACK_OFFSET_Y: Final = 180


class _LayoutContext:
    __slots__ = ("column_spacing", "layouts", "row_spacing")

    column_spacing: int
    row_spacing: int
    layouts: list[BlueprintNodeLayout]

    def __init__(
        self,
        *,
        column_spacing: int,
        row_spacing: int,
        layouts: list[BlueprintNodeLayout],
    ) -> None:
        """Create mutable layout planning state."""
        self.column_spacing = column_spacing
        self.row_spacing = row_spacing
        self.layouts = layouts


def plan_blueprint_layout(
    root: MakeAstRoot,
    *,
    column_spacing: int = DEFAULT_COLUMN_SPACING,
    row_spacing: int = DEFAULT_ROW_SPACING,
) -> BlueprintLayoutPlan:
    """Return a deterministic layout plan for one parsed blueprint."""
    layouts: list[BlueprintNodeLayout] = []
    context = _LayoutContext(
        column_spacing=column_spacing,
        row_spacing=row_spacing,
        layouts=layouts,
    )
    _ = _append_flow_layouts(
        nodes=root.flow,
        start_depth=0,
        lane=0,
        next_lane=1,
        context=context,
    )
    return BlueprintLayoutPlan(
        column_spacing=column_spacing,
        row_spacing=row_spacing,
        layouts=tuple(layouts),
        notes=_note_layouts(root=root, layouts=tuple(layouts), context=context),
    )


def _append_flow_layouts(
    *,
    nodes: tuple[MakeAstNode, ...],
    start_depth: int,
    lane: int,
    next_lane: int,
    context: _LayoutContext,
) -> int:
    """Append layouts for one linear flow and its nested route-like children.

    Returns:
        The updated layout state for the linear flow and route children.
    """
    current_lane = next_lane
    for offset, node in enumerate(nodes):
        depth = start_depth + offset
        context.layouts.append(_node_layout(node, depth, lane, context))
        for child_flow in _child_flows(node):
            current_lane = _append_flow_layouts(
                nodes=child_flow,
                start_depth=depth + 1,
                lane=current_lane,
                next_lane=current_lane + 1,
                context=context,
            )
    return current_lane


def _node_layout(
    node: MakeAstNode,
    depth: int,
    lane: int,
    context: _LayoutContext,
) -> BlueprintNodeLayout:
    """Return one node layout."""
    return BlueprintNodeLayout(
        node_id=node.node_id,
        module_token=node.module_token,
        depth=depth,
        lane=lane,
        x=depth * context.column_spacing,
        y=lane * context.row_spacing,
        source_path=node.source_trace.path,
    )


def _child_flows(node: MakeAstNode) -> tuple[tuple[MakeAstNode, ...], ...]:
    """Return non-empty child flows in AST traversal order."""
    route_flows = tuple(
        route.flow
        for route in (*node.routes, *node.branches, *node.tools)
        if route.flow
    )
    if not node.error_handlers:
        return route_flows
    return (*route_flows, node.error_handlers)


def _note_layouts(
    *,
    root: MakeAstRoot,
    layouts: tuple[BlueprintNodeLayout, ...],
    context: _LayoutContext,
) -> tuple[BlueprintNoteLayout, ...]:
    """Return deterministic note positions away from module coordinates."""
    notes = root.scenario.metadata.get("notes")
    if not isinstance(notes, list):
        return ()

    by_node_id = {layout.node_id: layout for layout in layouts}
    fallback_lane = max((layout.lane for layout in layouts), default=0) + 1
    anchored_counts: dict[str, int] = {}
    planned: list[BlueprintNoteLayout] = []
    for index, raw_note in enumerate(cast("list[object]", notes)):
        if not _is_json_object(raw_note):
            continue
        module_ids = _note_module_ids(raw_note)
        anchor = _first_existing_anchor(module_ids, by_node_id)
        if anchor is None:
            planned.append(
                _fallback_note_layout(
                    index=index,
                    module_ids=module_ids,
                    fallback_lane=fallback_lane + len(planned),
                    context=context,
                )
            )
            continue
        stack_index = anchored_counts.get(anchor.node_id, 0)
        anchored_counts[anchor.node_id] = stack_index + 1
        planned.append(
            BlueprintNoteLayout(
                note_index=index,
                module_ids=module_ids,
                x=anchor.x + DEFAULT_NOTE_OFFSET_X,
                y=anchor.y
                + DEFAULT_NOTE_OFFSET_Y
                + (stack_index * DEFAULT_NOTE_STACK_OFFSET_Y),
                source_path=("metadata", "notes", index),
            )
        )
    return tuple(planned)


def _fallback_note_layout(
    *,
    index: int,
    module_ids: tuple[str, ...],
    fallback_lane: int,
    context: _LayoutContext,
) -> BlueprintNoteLayout:
    return BlueprintNoteLayout(
        note_index=index,
        module_ids=module_ids,
        x=0,
        y=fallback_lane * context.row_spacing,
        source_path=("metadata", "notes", index),
    )


def _first_existing_anchor(
    module_ids: tuple[str, ...],
    layouts_by_node_id: dict[str, BlueprintNodeLayout],
) -> BlueprintNodeLayout | None:
    for module_id in module_ids:
        layout = layouts_by_node_id.get(module_id)
        if layout is not None:
            return layout
    return None


def _note_module_ids(note: JsonObject) -> tuple[str, ...]:
    module_ids = note.get("moduleIds")
    if not isinstance(module_ids, list):
        return ()
    normalized: list[str] = []
    for item in cast("list[object]", module_ids):
        text = _note_module_id_text(item)
        if text is not None:
            normalized.append(text)
    return tuple(normalized)


def _note_module_id_text(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    text = str(value).strip()
    return text or None


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
