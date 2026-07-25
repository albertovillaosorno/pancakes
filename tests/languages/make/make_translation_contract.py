# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for the Make adapter translation boundary.

Boundary contract:
- Owns: Make JSON to Pancakes AST and IR adapter behavior.
- Must not: call live Make services, validate catalogs, or claim other adapters.
- Allows: synthetic Make blueprint payloads and source-preserving round trips.
- Split when: another language adapter becomes executable.
- Merge when: another test owns this exact Make adapter translation contract.
"""

from __future__ import annotations

from typing import cast

from ir import validate_ir_graph
from languages.make import (
    MAKE_BLUEPRINT_OUTPUT_LANGUAGE_ID,
    MAKE_LANGUAGE_ID,
    PANCAKES_AST_MODEL_ID,
    render_pancakes_ast_to_make_blueprint_payload,
    translate_make_blueprint_to_pancakes_projection,
)

type JsonObject = dict[str, object]


def test_make_adapter_translates_make_json_to_pancakes_ast_and_ir() -> None:
    """Make is a source adapter, while Pancakes AST and IR are product.

    models.
    """
    payload = lead_routing_make_payload()

    projection = translate_make_blueprint_to_pancakes_projection(payload)

    assert projection.pancakes_ast.scenario.name == "lead-routing-demo"
    assert projection.ir_document.source_language_id == MAKE_LANGUAGE_ID
    assert (
        projection.ir_document.graph.metadata["product_ast"]
        == PANCAKES_AST_MODEL_ID
    )
    assert projection.ir_document.graph.metadata["output_language"] == (
        MAKE_BLUEPRINT_OUTPUT_LANGUAGE_ID
    )
    assert validate_ir_graph(projection.ir_document.graph) == ()
    ir_nodes_by_id = {
        node.node_id: node for node in projection.ir_document.graph.nodes
    }
    assert ir_nodes_by_id["1"].kind == "webhook"
    assert ir_nodes_by_id["2"].kind == "router"
    assert ir_nodes_by_id["route:2:routes:0"].kind == "route"
    filter_nodes = [
        node
        for node in projection.ir_document.graph.nodes
        if node.kind == "filter"
    ]
    assert len(filter_nodes) == 1
    assert filter_nodes[0].label == "Only qualified leads"
    assert ir_nodes_by_id["3"].kind == "http_api"
    assert ir_nodes_by_id["11"].kind == "error_handler"
    assert ir_nodes_by_id["3"].source_refs[0].language_id == MAKE_LANGUAGE_ID


def test_make_adapter_preserves_make_payload_without_owning_product_core() -> (
    None
):
    """The Make adapter can emit Make JSON without making Make the core.

    model.
    """
    payload = lead_routing_make_payload()
    projection = translate_make_blueprint_to_pancakes_projection(payload)
    rendered = render_pancakes_ast_to_make_blueprint_payload(
        projection.pancakes_ast
    )

    assert rendered == projection.make_payload
    assert rendered["name"] == payload["name"]
    rendered_flow = list_member(rendered, "flow")
    first_node = object_at(rendered_flow, 0)
    assert first_node["module"] == "gateway:CustomWebHook"
    router_node = object_at(rendered_flow, 1)
    route = object_at(list_member(router_node, "routes"), 0)
    route_filter = object_member(route, "filter")
    assert route_filter["name"] == "Only qualified leads"
    assert (
        projection.ir_document.graph.metadata["source_language"]
        == MAKE_LANGUAGE_ID
    )
    assert (
        projection.ir_document.graph.metadata["product_ast"]
        == PANCAKES_AST_MODEL_ID
    )


def lead_routing_make_payload() -> JsonObject:
    """Return one representative Make blueprint JSON payload."""
    return {
        "name": "lead-routing-demo",
        "flow": [
            {
                "id": "1",
                "module": "gateway:CustomWebHook",
            },
            {
                "id": "2",
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "filter": {
                            "name": "Only qualified leads",
                            "conditions": {
                                "left": "{{1.score}}",
                                "op": "gt",
                                "right": 80,
                            },
                        },
                        "flow": [
                            {
                                "id": "3",
                                "module": "http:MakeRequest",
                                "onerror": [
                                    {"id": "11", "module": "builtin:Ignore"}
                                ],
                            }
                        ],
                    }
                ],
            },
        ],
        "metadata": {
            "parameters": [{"name": "lead"}],
            "expect": [{"name": "result"}],
            "schedule": {"id": "schedule:every-minute"},
        },
    }


def list_member(payload: JsonObject, key: str) -> list[object]:
    """Return one list member from a JSON object."""
    value = payload.get(key)
    assert isinstance(value, list), f"Expected list member {key!r}: {payload}"
    return cast("list[object]", value)


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return one object member from a JSON object."""
    value = payload.get(key)
    assert isinstance(value, dict), f"Expected object member {key!r}: {payload}"
    return cast("JsonObject", value)


def object_at(values: list[object], index: int) -> JsonObject:
    """Return one object at an index from a JSON list."""
    value = values[index]
    assert isinstance(value, dict), f"Expected object at {index}: {values}"
    return cast("JsonObject", value)
