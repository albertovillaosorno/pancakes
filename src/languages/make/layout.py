# Repository header: begin
# Provenance source mode: source_refs
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Plan Make-native blueprint designer coordinates.

Boundary contract:
- Owns: Make-specific designer coordinate policy for exported blueprint JSON.
- Must not: mutate AST payloads, validate modules, or define generic layout
semantics.
- Allows: deterministic Make-like x/y plans from parsed AST route topology.
- Split when: notes or route layout need independent Make UI policy.
- Merge when: another Make layout planner produces the same coordinates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from blueprints.ast.layout_models import (
    BlueprintLayoutPlan,
    BlueprintNodeLayout,
    BlueprintNoteLayout,
)

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject, MakeAstNode, MakeAstRoot

MAKE_COLUMN_SPACING: Final = 300
MAKE_BRANCH_SPACING: Final = 300
MAKE_NOTE_OFFSET_X: Final = 120
MAKE_NOTE_OFFSET_Y: Final = 180
MAKE_NOTE_STACK_OFFSET_Y: Final = 160


class _LaneCursor:
    __slots__ = ("next_lane",)

    next_lane: int

    def __init__(self) -> None:
        """Create one mutable Make layout lane cursor."""
        self.next_lane = 0


def plan_make_blueprint_layout(root: MakeAstRoot) -> BlueprintLayoutPlan:
    """Return the computed result for the caller."""
    cursor = _LaneCursor()
    layouts, flow_y = _plan_flow(
        nodes=root.flow,
        start_depth=0,
        preferred_y=0,
        cursor=cursor,
    )
    # The top-level flow should align visually with the first router midpoint
    # when present.
    normalized = tuple(
        layout
        if _is_nested_layout(layout)
        else _replace_flow_y(layout=layout, flow_y=flow_y)
        for layout in layouts
    )
    return BlueprintLayoutPlan(
        column_spacing=MAKE_COLUMN_SPACING,
        row_spacing=MAKE_BRANCH_SPACING,
        layouts=normalized,
        notes=_note_layouts(root=root, layouts=normalized),
    )


def _plan_flow(
    *,
    nodes: tuple[MakeAstNode, ...],
    start_depth: int,
    preferred_y: int,
    cursor: _LaneCursor,
) -> tuple[tuple[BlueprintNodeLayout, ...], int]:
    layouts: list[BlueprintNodeLayout] = []
    branch_midpoints: list[int] = []
    for offset, node in enumerate(nodes):
        depth = start_depth + offset
        child_layouts, child_y = _plan_child_flows(
            node=node, depth=depth, cursor=cursor
        )
        node_y = child_y if child_y is not None else preferred_y
        if child_y is not None:
            branch_midpoints.append(child_y)
        layouts.append(_node_layout(node=node, depth=depth, y=node_y))
        layouts.extend(child_layouts)
    flow_y = _midpoint(branch_midpoints) if branch_midpoints else preferred_y
    return tuple(
        layout
        if _is_nested_layout(layout)
        else _replace_flow_y(layout=layout, flow_y=flow_y)
        for layout in layouts
    ), flow_y


def _plan_child_flows(
    *,
    node: MakeAstNode,
    depth: int,
    cursor: _LaneCursor,
) -> tuple[tuple[BlueprintNodeLayout, ...], int | None]:
    flows = tuple(
        route.flow
        for route in (*node.routes, *node.branches, *node.tools)
        if route.flow
    )
    if node.error_handlers:
        flows = (*flows, node.error_handlers)
    if not flows:
        return (), None
    child_layouts: list[BlueprintNodeLayout] = []
    child_ys: list[int] = []
    for flow in flows:
        child_y = cursor.next_lane * MAKE_BRANCH_SPACING
        cursor.next_lane += 1
        planned, planned_y = _plan_flow(
            nodes=flow,
            start_depth=depth + 1,
            preferred_y=child_y,
            cursor=cursor,
        )
        child_layouts.extend(planned)
        child_ys.append(planned_y)
    return tuple(child_layouts), _midpoint(child_ys)


def _node_layout(
    *, node: MakeAstNode, depth: int, y: int
) -> BlueprintNodeLayout:
    return BlueprintNodeLayout(
        node_id=node.node_id,
        module_token=node.module_token,
        depth=depth,
        lane=round(y / MAKE_BRANCH_SPACING),
        x=depth * MAKE_COLUMN_SPACING,
        y=y,
        source_path=node.source_trace.path,
    )


def _replace_flow_y(
    *, layout: BlueprintNodeLayout, flow_y: int
) -> BlueprintNodeLayout:
    return BlueprintNodeLayout(
        node_id=layout.node_id,
        module_token=layout.module_token,
        depth=layout.depth,
        lane=round(flow_y / MAKE_BRANCH_SPACING),
        x=layout.x,
        y=flow_y,
        source_path=layout.source_path,
    )


def _is_nested_layout(layout: BlueprintNodeLayout) -> bool:
    return (
        "routes" in layout.source_path
        or "branches" in layout.source_path
        or "tools" in layout.source_path
    )


def _midpoint(values: list[int]) -> int:
    if not values:
        return 0
    return round((min(values) + max(values)) / 2)


def _note_layouts(
    *,
    root: MakeAstRoot,
    layouts: tuple[BlueprintNodeLayout, ...],
) -> tuple[BlueprintNoteLayout, ...]:
    notes = root.scenario.metadata.get("notes")
    if not isinstance(notes, list):
        return ()
    by_node_id = {layout.node_id: layout for layout in layouts}
    planned: list[BlueprintNoteLayout] = []
    for index, raw_note in enumerate(cast("list[object]", notes)):
        if not isinstance(raw_note, dict):
            continue
        module_ids = _note_module_ids(cast("JsonObject", raw_note))
        anchor = next(
            (
                by_node_id[module_id]
                for module_id in module_ids
                if module_id in by_node_id
            ),
            None,
        )
        if anchor is None:
            continue
        stack_index = len(planned)
        planned.append(
            BlueprintNoteLayout(
                note_index=index,
                module_ids=module_ids,
                x=anchor.x + MAKE_NOTE_OFFSET_X,
                y=anchor.y
                + MAKE_NOTE_OFFSET_Y
                + (stack_index * MAKE_NOTE_STACK_OFFSET_Y),
                source_path=("metadata", "notes", index),
            )
        )
    return tuple(planned)


def _note_module_ids(note: JsonObject) -> tuple[str, ...]:
    raw_ids = note.get("moduleIds")
    if not isinstance(raw_ids, list):
        return ()
    module_ids: list[str] = []
    for raw_id in cast("list[object]", raw_ids):
        if isinstance(raw_id, bool):
            continue
        if isinstance(raw_id, int) and raw_id > 0:
            module_ids.append(str(raw_id))
        elif isinstance(raw_id, str) and raw_id.strip():
            module_ids.append(raw_id.strip())
    return tuple(module_ids)
