# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make-native layout topology contracts.

Boundary contract:
- Owns: Make target-language layout invariants across synthetic topology
families.
- Must not: call Make.com, assert enterprise-demo coordinates, or change core
AST layout policy.
- Allows: local parsed blueprints that exercise Make-native layout projection
rules.
- Split when: visual editor parity needs browser/image assertions.
- Merge when: Make blueprint export contracts own every layout topology
invariant.
"""

from __future__ import annotations

import json
from itertools import pairwise
from typing import TYPE_CHECKING, NamedTuple

from blueprints.ast import parse_make_ast_json_text
from languages.make.layout import (
    MAKE_BRANCH_SPACING,
    MAKE_COLUMN_SPACING,
    plan_make_blueprint_layout,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from blueprints.ast.layout_models import (
        BlueprintLayoutPlan,
        BlueprintNodeLayout,
    )

    from tests.support.json_payloads import JsonObject


class LayoutCase(NamedTuple):
    """One topology fixture and its key layout assertions."""

    name: str
    payload: JsonObject
    router_id: str | None = None
    branch_anchor_ids: tuple[str, ...] = ()


def test_make_layout_policy_covers_required_topology_families() -> None:
    """Required topology families keep Make layout compact and.

    target-specific.
    """
    cases = (
        _linear_flow_case(),
        _router_case("one-route-router", route_count=1),
        _router_case("two-route-router", route_count=2),
        _router_case("ten-route-router", route_count=10),
        _router_case("thirty-route-stress-router", route_count=30),
        _nested_router_case(),
        _long_branch_case(),
        _iterator_branch_case(),
        _aggregator_branch_case(),
        _mixed_slack_datastore_branch_case(),
    )

    for case in cases:
        plan = _layout_plan(case.payload)
        layouts = _layouts_by_id(plan)
        assert plan.column_spacing == MAKE_COLUMN_SPACING == 300, case.name
        assert plan.row_spacing == MAKE_BRANCH_SPACING == 300, case.name
        assert all(layout.x % 300 == 0 for layout in layouts.values()), (
            f"{case.name} produced non-Make column spacing: {layouts}"
        )
        assert _max_y_gap(layouts.values()) <= 300, (
            f"{case.name} produced sparse branch layout: {layouts}"
        )
        if case.router_id is not None:
            _assert_router_midpoint(case=case, layouts=layouts)


def test_make_layout_midpoint_scales_across_router_sizes() -> None:
    """Router y is the midpoint of compact branch anchors across small and.

    large.

    routers.
    """
    for route_count in (1, 2, 10, 30):
        case = _router_case(f"router-{route_count}", route_count=route_count)
        layouts = _layouts_by_id(_layout_plan(case.payload))
        router = layouts["2"]
        trigger = layouts["1"]
        branch_ys = [layouts[node_id].y for node_id in case.branch_anchor_ids]

        assert branch_ys == [index * 300 for index in range(route_count)]
        assert router.y == _midpoint(branch_ys)
        assert trigger.y == router.y
        assert max(branch_ys, default=0) <= (route_count - 1) * 300
        assert 1850 not in branch_ys


def test_make_layout_keeps_long_branch_y_stable_while_x_advances() -> None:
    """Long route branches advance through columns without drifting.

    vertically.
    """
    layouts = _layouts_by_id(_layout_plan(_long_branch_case().payload))
    long_branch_ids = ("3", "4", "5", "6", "7")
    long_branch_ys = [layouts[node_id].y for node_id in long_branch_ids]
    long_branch_xs = [layouts[node_id].x for node_id in long_branch_ids]

    assert long_branch_ys == [0, 0, 0, 0, 0]
    assert long_branch_xs == [600, 900, 1200, 1500, 1800]
    assert layouts["2"].y == 150
    assert layouts["8"].y == 300


def _layout_plan(payload: JsonObject) -> BlueprintLayoutPlan:
    root = parse_make_ast_json_text(json.dumps(payload))
    return plan_make_blueprint_layout(root)


def _layouts_by_id(plan: BlueprintLayoutPlan) -> dict[str, BlueprintNodeLayout]:
    return {layout.node_id: layout for layout in plan.layouts}


def _assert_router_midpoint(
    *,
    case: LayoutCase,
    layouts: dict[str, BlueprintNodeLayout],
) -> None:
    assert case.router_id is not None
    router = layouts[case.router_id]
    branch_ys = [layouts[node_id].y for node_id in case.branch_anchor_ids]
    assert router.y == _midpoint(branch_ys), (
        f"{case.name} router is not centered over branch anchors: {layouts}"
    )
    assert layouts["1"].y == router.y, (
        f"{case.name} trigger should align with router midpoint: {layouts}"
    )


def _max_y_gap(layouts: Iterable[BlueprintNodeLayout]) -> int:
    values = sorted({layout.y for layout in layouts})
    if len(values) < 2:
        return 0
    return max(after - before for before, after in pairwise(values))


def _midpoint(values: list[int]) -> int:
    if not values:
        return 0
    return round((min(values) + max(values)) / 2)


def _linear_flow_case() -> LayoutCase:
    return LayoutCase(
        name="linear-flow",
        payload=_blueprint(
            [
                _webhook_node(1),
                _datastore_node(2),
                _slack_node(3),
            ]
        ),
    )


def _router_case(name: str, *, route_count: int) -> LayoutCase:
    routes: list[JsonObject] = [
        {"flow": [_datastore_node(3 + index)]} for index in range(route_count)
    ]
    return LayoutCase(
        name=name,
        payload=_blueprint([_webhook_node(1), _router_node(2, routes=routes)]),
        router_id="2",
        branch_anchor_ids=tuple(str(3 + index) for index in range(route_count)),
    )


def _nested_router_case() -> LayoutCase:
    nested_router = _router_node(
        3,
        routes=[
            {"flow": [_datastore_node(4)]},
            {"flow": [_slack_node(5)]},
        ],
    )
    return LayoutCase(
        name="nested-router",
        payload=_blueprint(
            [
                _webhook_node(1),
                _router_node(
                    2,
                    routes=[
                        {"flow": [nested_router]},
                        {"flow": [_datastore_node(6)]},
                    ],
                ),
            ]
        ),
        router_id="2",
        branch_anchor_ids=("3", "6"),
    )


def _long_branch_case() -> LayoutCase:
    return LayoutCase(
        name="long-branch",
        payload=_blueprint(
            [
                _webhook_node(1),
                _router_node(
                    2,
                    routes=[
                        {
                            "flow": [
                                _datastore_node(3),
                                _datastore_node(4),
                                _datastore_node(5),
                                _slack_node(6),
                                _datastore_node(7),
                            ],
                        },
                        {"flow": [_slack_node(8)]},
                    ],
                ),
            ]
        ),
        router_id="2",
        branch_anchor_ids=("3", "8"),
    )


def _iterator_branch_case() -> LayoutCase:
    iterator = _make_node(
        node_id=3,
        module="builtin:Iterator",
        tools=[{"flow": [_datastore_node(4)]}],
    )
    return LayoutCase(
        name="iterator-branch",
        payload=_blueprint(
            [_webhook_node(1), _router_node(2, routes=[{"flow": [iterator]}])]
        ),
        router_id="2",
        branch_anchor_ids=("3",),
    )


def _aggregator_branch_case() -> LayoutCase:
    return LayoutCase(
        name="aggregator-branch",
        payload=_blueprint(
            [
                _webhook_node(1),
                _router_node(
                    2,
                    routes=[
                        {
                            "flow": [
                                _make_node(
                                    node_id=3, module="builtin:BasicAggregator"
                                )
                            ]
                        },
                        {
                            "flow": [
                                _make_node(
                                    node_id=4, module="util:TextAggregator"
                                )
                            ]
                        },
                    ],
                ),
            ]
        ),
        router_id="2",
        branch_anchor_ids=("3", "4"),
    )


def _mixed_slack_datastore_branch_case() -> LayoutCase:
    return LayoutCase(
        name="mixed-slack-datastore-branch",
        payload=_blueprint(
            [
                _webhook_node(1),
                _router_node(
                    2,
                    routes=[
                        {"flow": [_datastore_node(3), _slack_node(4)]},
                        {"flow": [_slack_node(5), _datastore_node(6)]},
                    ],
                ),
            ]
        ),
        router_id="2",
        branch_anchor_ids=("3", "5"),
    )


def _blueprint(flow: list[JsonObject]) -> JsonObject:
    return {"name": "Synthetic Make layout topology", "flow": flow}


def _router_node(node_id: int, *, routes: list[JsonObject]) -> JsonObject:
    return _make_node(
        node_id=node_id, module="builtin:BasicRouter", routes=routes
    )


def _webhook_node(node_id: int) -> JsonObject:
    return _make_node(node_id=node_id, module="gateway:CustomWebHook")


def _datastore_node(node_id: int) -> JsonObject:
    return _make_node(node_id=node_id, module="datastore:AddRecord")


def _slack_node(node_id: int) -> JsonObject:
    return _make_node(node_id=node_id, module="slack:CreateMessage")


def _make_node(
    *,
    node_id: int,
    module: str,
    routes: list[JsonObject] | None = None,
    tools: list[JsonObject] | None = None,
) -> JsonObject:
    node: JsonObject = {"id": node_id, "module": module, "version": 1}
    if routes is not None:
        node["routes"] = routes
    if tools is not None:
        node["tools"] = tools
    return node
