# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for deterministic designer layout generation.

Boundary contract:
- Owns: tests for layout coordinate generation and payload application.
- Must not: test catalog resolution, live Make import, or validation gates.
- Allows: small sanitized blueprint fixtures and layout-preservation assertions.
- Split when: layout analysis or renderer importability needs separate
ownership.
- Merge when: another AST test duplicates this layout-generation boundary.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest
from blueprints.ast import (
    DEFAULT_COLUMN_SPACING,
    DEFAULT_ROW_SPACING,
    BlueprintLayoutPlan,
    BlueprintNodeLayout,
    JsonObject,
    apply_blueprint_layout,
    parse_make_ast,
    plan_blueprint_layout,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "importability"
)
ROUTER_TWO_BRANCHES_FIXTURE = FIXTURE_ROOT / "layout_router_two_branches.json"


def test_linear_flow_layout_uses_default_column_spacing() -> None:
    """Top-level linear nodes use the canonical default column spacing."""
    root = parse_make_ast(_linear_two_node_payload())

    plan = plan_blueprint_layout(root)

    assert plan.column_spacing == DEFAULT_COLUMN_SPACING, (
        f"Layout plan did not report default column spacing: {plan}"
    )
    assert tuple(
        (item.node_id, item.depth, item.lane, item.x, item.y)
        for item in plan.layouts
    ) == (("1", 0, 0, 0, 0), ("2", 1, 0, DEFAULT_COLUMN_SPACING, 0)), (
        f"Linear layout did not use deterministic default coordinates: "
        f"{plan.layouts}"
    )


def test_router_branch_layout_uses_default_row_spacing() -> None:
    """Router branch lanes use the canonical default row spacing."""
    root = parse_make_ast(_fixture_payload())

    plan = plan_blueprint_layout(root)

    assert plan.row_spacing == DEFAULT_ROW_SPACING, (
        f"Layout plan did not report default row spacing: {plan}"
    )
    assert tuple(
        (item.node_id, item.depth, item.lane, item.x, item.y)
        for item in plan.layouts
    ) == (
        ("1", 0, 0, 0, 0),
        ("2", 1, 1, DEFAULT_COLUMN_SPACING, DEFAULT_ROW_SPACING),
        ("3", 1, 2, DEFAULT_COLUMN_SPACING, DEFAULT_ROW_SPACING * 2),
        ("4", 2, 2, DEFAULT_COLUMN_SPACING * 2, DEFAULT_ROW_SPACING * 2),
    ), (
        f"Router branch layout did not use deterministic default lanes: "
        f"{plan.layouts}"
    )


def test_layout_generation_does_not_change_non_layout_fields() -> None:
    """Applying generated coordinates preserves routing, filters, parameters,.

    and mappers.
    """
    payload = _fixture_payload()
    original_payload = copy.deepcopy(payload)
    root = parse_make_ast(payload)

    rendered = apply_blueprint_layout(root, plan_blueprint_layout(root))

    assert payload == original_payload, (
        f"Layout application mutated the source payload: {payload}"
    )
    assert _without_designer_coordinates(
        rendered
    ) == _without_designer_coordinates(original_payload), (
        f"Layout application changed non-layout fields: {rendered}"
    )
    assert _route_flow_ids(rendered) == _route_flow_ids(original_payload), (
        f"Layout application changed route order: {rendered}"
    )


def test_layout_payload_error_names_invalid_path() -> None:
    """Invalid layout source paths fail with a deterministic path diagnostic."""
    root = parse_make_ast(_linear_two_node_payload())
    plan = BlueprintLayoutPlan(
        column_spacing=DEFAULT_COLUMN_SPACING,
        row_spacing=DEFAULT_ROW_SPACING,
        layouts=(
            BlueprintNodeLayout(
                node_id="missing",
                module_token=root.flow[1].module_token,
                depth=0,
                lane=0,
                x=0,
                y=0,
                source_path=("flow", 4),
            ),
        ),
        notes=(),
    )

    with pytest.raises(
        KeyError, match=r"Layout path does not resolve.*\('flow', 4\)"
    ):
        _ = apply_blueprint_layout(root, plan)


def _linear_two_node_payload() -> JsonObject:
    return {
        "name": "layout-linear-demo",
        "flow": [
            _node(
                node_id="1",
                module="webhooks:CustomWebhook",
                parameters={"hook": "demo-only"},
                mapper={"payload": "{{1.body}}"},
            ),
            _node(
                node_id="2",
                module="http:MakeRequest",
                parameters={"url": "https://example.invalid/api"},
                mapper={"body": "{{1.payload}}"},
            ),
        ],
        "metadata": {"scenario": {"name": "layout-linear-demo"}},
    }


def test_layout_plan_places_notes_away_from_anchored_modules() -> None:
    """Notes are positioned deterministically near, not on top of, referenced.

    modules.
    """
    root = parse_make_ast(_note_payload())

    first_plan = plan_blueprint_layout(root)
    second_plan = plan_blueprint_layout(root)
    rendered = apply_blueprint_layout(root, first_plan)

    assert first_plan == second_plan, (
        f"Layout planner is not stable across repeated runs: {first_plan}"
    )
    assert len(first_plan.notes) == 1, f"Expected one note layout: {first_plan}"
    note_layout = first_plan.notes[0]
    module_positions = {(layout.x, layout.y) for layout in first_plan.layouts}
    assert (note_layout.x, note_layout.y) not in module_positions, (
        f"Note overlaps a module coordinate: {first_plan}"
    )
    note_payload = _root_note(rendered)
    assert (note_payload.get("x"), note_payload.get("y")) == (
        note_layout.x,
        note_layout.y,
    ), f"Layout application did not write note coordinates: {rendered}"


def test_error_handler_layout_uses_distinct_lane_without_overlap() -> None:
    """Direct error handlers receive deterministic non-overlapping.

    coordinates.
    """
    root = parse_make_ast(_error_handler_payload())

    plan = plan_blueprint_layout(root)
    positions = {(layout.x, layout.y) for layout in plan.layouts}

    assert len(positions) == len(plan.layouts), (
        f"Layout planner overlapped module coordinates: {plan.layouts}"
    )
    by_id = {layout.node_id: layout for layout in plan.layouts}
    assert by_id["3"].lane != by_id["2"].lane, (
        f"Error handler should not share the main lane: {plan.layouts}"
    )


def _fixture_payload() -> JsonObject:
    payload = cast(
        "object",
        json.loads(ROUTER_TWO_BRANCHES_FIXTURE.read_text(encoding="utf-8")),
    )
    assert isinstance(payload, dict), (
        f"Expected JSON object fixture: {ROUTER_TWO_BRANCHES_FIXTURE}"
    )
    return cast("JsonObject", payload)


def _note_payload() -> JsonObject:
    payload = _linear_two_node_payload()
    payload["metadata"] = {
        "scenario": {"name": "layout-note-demo"},
        "notes": [
            {
                "content": "<p>Configure the HTTP request.</p>",
                "moduleIds": ["2"],
            }
        ],
    }
    return payload


def _error_handler_payload() -> JsonObject:
    return {
        "name": "layout-error-handler-demo",
        "flow": [
            _node(
                node_id="1",
                module="http:MakeRequest",
                parameters={"url": "https://example.invalid/api"},
                mapper={"body": "{{1.payload}}"},
            ),
            _node(
                node_id="2",
                module="slack:CreateMessage",
                parameters={"channel": "alerts"},
                mapper={"text": "{{1.body}}"},
            )
            | {
                "onerror": [
                    _node(
                        node_id="3",
                        module="builtin:Ignore",
                        parameters={},
                        mapper={},
                    )
                ]
            },
        ],
        "metadata": {"scenario": {"name": "layout-error-handler-demo"}},
    }


def _node(
    *,
    node_id: str,
    module: str,
    parameters: JsonObject,
    mapper: JsonObject,
) -> JsonObject:
    return {
        "id": node_id,
        "module": module,
        "version": 1,
        "parameters": parameters,
        "mapper": mapper,
        "metadata": {"designer": {"x": -1, "y": -1, "messages": []}},
    }


def _without_designer_coordinates(value: object) -> object:
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [_without_designer_coordinates(item) for item in items]
    if not isinstance(value, dict):
        return value
    copied = {
        str(key): _without_designer_coordinates(item)
        for key, item in cast("dict[object, object]", value).items()
    }
    if set(copied) >= {"x", "y"}:
        _ = copied.pop("x", None)
        _ = copied.pop("y", None)
    return copied


def _route_flow_ids(payload: JsonObject) -> tuple[tuple[str, ...], ...]:
    flow = cast("list[object]", payload["flow"])
    router = cast("JsonObject", flow[0])
    routes = cast("list[object]", router["routes"])
    route_ids: list[tuple[str, ...]] = []
    for route in routes:
        route_payload = cast("JsonObject", route)
        route_flow = cast("list[object]", route_payload["flow"])
        route_ids.append(
            tuple(str(cast("JsonObject", node)["id"]) for node in route_flow)
        )
    return tuple(route_ids)


def _root_note(payload: JsonObject) -> JsonObject:
    metadata = payload.get("metadata")
    assert isinstance(metadata, dict), f"Expected root metadata: {payload}"
    notes = cast("JsonObject", metadata).get("notes")
    assert isinstance(notes, list), f"Expected root notes: {payload}"
    note = cast("list[object]", notes)[0]
    assert isinstance(note, dict), f"Expected note object: {payload}"
    return cast("JsonObject", note)
