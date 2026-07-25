# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Regression tests for layout payload path resolution.

Boundary contract:
- Owns: tests for layout payload source-path resolution diagnostics.
- Must not: test coordinate planning, renderer validation gates,
  or live Make import.
- Allows: small inline blueprint payloads and explicit invalid layout paths.
- Split when: layout coordinate generation or transition analysis needs
  separate tests.
- Merge when: another AST test duplicates these path-resolution
  regressions exactly.
"""

from __future__ import annotations

from typing import Final, cast

import pytest
from blueprints.ast import (
    DEFAULT_COLUMN_SPACING,
    DEFAULT_ROW_SPACING,
    BlueprintLayoutPlan,
    BlueprintNodeLayout,
    JsonObject,
    apply_blueprint_layout,
    parse_make_ast,
)

LAYOUT_TARGET_MODULE: Final = "http:MakeRequest"


def test_resolve_object_path_accepts_valid_nested_object_path() -> None:
    """A valid nested route node path receives layout coordinates."""
    root = parse_make_ast(_payload())
    plan = _plan_for_path(("flow", 0, "routes", 0, "flow", 0))

    rendered = apply_blueprint_layout(root, plan)

    route_node = _route_node(rendered)
    designer = _designer(route_node)
    assert (designer.get("x"), designer.get("y")) == (
        DEFAULT_COLUMN_SPACING,
        DEFAULT_ROW_SPACING,
    ), f"Valid nested path did not receive coordinates: {rendered}"


def test_resolve_object_path_missing_key_raises_stable_message() -> None:
    """Missing object keys raise the stable layout path diagnostic."""
    root = parse_make_ast(_payload())
    plan = _plan_for_path(("flow", 0, "routes", 0, "missing", 0))

    with pytest.raises(
        KeyError, match=r"Layout path does not resolve to an object"
    ):
        _ = apply_blueprint_layout(root, plan)


def test_resolve_object_path_bad_list_index_raises_stable_message() -> None:
    """Out-of-range list indexes raise the stable layout path diagnostic."""
    root = parse_make_ast(_payload())
    plan = _plan_for_path(("flow", 0, "routes", 3))

    with pytest.raises(
        KeyError, match=r"Layout path does not resolve to an object"
    ):
        _ = apply_blueprint_layout(root, plan)


def test_resolve_object_path_scalar_target_raises_stable_message() -> None:
    """Scalar path traversal raises a stable layout path diagnostic."""
    root = parse_make_ast(_payload())
    plan = _plan_for_path(("flow", 0, "id", "metadata"))

    with pytest.raises(
        TypeError,
        match=r"Layout path does not resolve through an object segment",
    ):
        _ = apply_blueprint_layout(root, plan)


def _plan_for_path(path: tuple[str | int, ...]) -> BlueprintLayoutPlan:
    return BlueprintLayoutPlan(
        column_spacing=DEFAULT_COLUMN_SPACING,
        row_spacing=DEFAULT_ROW_SPACING,
        layouts=(
            BlueprintNodeLayout(
                node_id="target",
                module_token=LAYOUT_TARGET_MODULE,
                depth=1,
                lane=1,
                x=DEFAULT_COLUMN_SPACING,
                y=DEFAULT_ROW_SPACING,
                source_path=path,
            ),
        ),
        notes=(),
    )


def _payload() -> JsonObject:
    return {
        "name": "layout-path-resolution-demo",
        "flow": [
            {
                "id": "1",
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "flow": [
                            {
                                "id": "2",
                                "module": "http:MakeRequest",
                                "parameters": {
                                    "url": "https://example.invalid/demo"
                                },
                                "mapper": {"body": "{{1.payload}}"},
                            }
                        ]
                    }
                ],
            }
        ],
        "metadata": {},
    }


def _route_node(payload: JsonObject) -> JsonObject:
    flow = payload["flow"]
    assert isinstance(flow, list), f"Expected root flow list: {payload}"
    root_flow = cast("list[object]", flow)
    router = root_flow[0]
    assert isinstance(router, dict), f"Expected router object: {payload}"
    router_payload = cast("JsonObject", router)
    routes = router_payload["routes"]
    assert isinstance(routes, list), f"Expected routes list: {payload}"
    route_items = cast("list[object]", routes)
    route = route_items[0]
    assert isinstance(route, dict), f"Expected route object: {payload}"
    route_payload = cast("JsonObject", route)
    route_flow = route_payload["flow"]
    assert isinstance(route_flow, list), f"Expected route flow list: {payload}"
    route_flow_items = cast("list[object]", route_flow)
    route_node = route_flow_items[0]
    assert isinstance(route_node, dict), (
        f"Expected route node object: {payload}"
    )
    return cast("JsonObject", route_node)


def _designer(node: JsonObject) -> JsonObject:
    metadata = node.get("metadata")
    assert isinstance(metadata, dict), f"Expected metadata object: {node}"
    metadata_payload = cast("JsonObject", metadata)
    designer = metadata_payload.get("designer")
    assert isinstance(designer, dict), f"Expected designer object: {node}"
    return cast("JsonObject", designer)
