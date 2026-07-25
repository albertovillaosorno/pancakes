# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Importability shadow telemetry tests.

Boundary contract:
- Owns: focused tests for local in-memory importability telemetry.
- Must not: persist telemetry, call Make services, test MCP surfaces, or
  inspect live data.
- Allows: sanitized AST payloads and synthetic catalog snapshots.
- Split when: persisted telemetry or MCP exposure gets a separate
  ADR-backed task.
- Merge when: another importability test owns the same shadow-event contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from blueprints.ast import parse_make_ast_json_text
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.importability import validate_importability
from catalog.generation_audit import (
    InMemoryCatalogPlanShadowSink,
    catalog_plan_shadow_field,
)

from tests.catalog.test_module_token_resolution import native_module_snapshot

if TYPE_CHECKING:
    from blueprints.ast.models import MakeAstNode


def test_shadow_telemetry_records_module_resolution_decision() -> None:
    """Module lookup decisions should be locally explainable."""
    sink = InMemoryCatalogPlanShadowSink()

    findings = validate_importability(
        nodes_for_flow(
            [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {},
                }
            ]
        ),
        catalog=native_module_snapshot(),
        telemetry=sink,
    )

    assert not (findings), (
        f"Known catalog module should not emit findings: {findings}"
    )
    assert len(sink.events) == 1, f"Expected one telemetry event: {sink.events}"
    event = sink.events[0]
    assert event.decision == "module_resolution", (
        f"Module resolution event lost decision outcome: {event}"
    )
    assert event.outcome == "catalog_confirmed", (
        f"Module resolution event lost decision outcome: {event}"
    )
    assert not (
        ("catalog_module_id", "module:gateway:1.14.1:trigger:CustomWebHook")
        not in event.provenance
    ), f"Module resolution event lost catalog provenance: {event}"


def test_shadow_telemetry_redacts_placeholder_values() -> None:
    """Telemetry must not record raw placeholders or credential-like fields."""
    sink = InMemoryCatalogPlanShadowSink()

    _ = validate_importability(
        nodes_for_flow(
            [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {"url": "{{TODO:client-webhook-url}}"},
                }
            ]
        ),
        catalog=native_module_snapshot(),
        telemetry=sink,
    )

    rendered_events = repr(sink.events)
    assert "client-webhook-url" not in rendered_events, (
        f"Telemetry leaked raw placeholder text: {sink.events}"
    )
    assert not ("[redacted:placeholder]" not in rendered_events), (
        f"Telemetry did not record placeholder redaction: {sink.events}"
    )
    assert (
        catalog_plan_shadow_field("api_token", "example-value")[1]
        == "[redacted:credential]"
    ), "Credential-like telemetry fields must be redacted."


def test_shadow_telemetry_event_order_is_deterministic() -> None:
    """Importability telemetry follows deterministic order."""
    sink = InMemoryCatalogPlanShadowSink()

    _ = validate_importability(
        nodes_for_flow(
            [
                {
                    "id": "router",
                    "module": "builtin:BasicRouter",
                    "routes": [
                        {
                            "flow": [
                                {
                                    "id": 2,
                                    "module": "datastore:AddRecord",
                                    "parameters": {
                                        "datastore": (
                                            "{{TODO:client-data-store}}"
                                        )
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        ),
        catalog=native_module_snapshot(),
        telemetry=sink,
    )

    decisions = tuple(event.decision for event in sink.events)
    assert decisions == (
        "router_topology_validation",
        "module_resolution",
        "placeholder_registry_mismatch",
        "module_resolution",
    ), f"Telemetry event order drifted: {sink.events}"
    assert tuple(event.sequence for event in sink.events) == tuple(
        range(len(sink.events))
    ), f"Telemetry sequence numbers drifted: {sink.events}"


def test_no_telemetry_is_written_when_no_sink_is_supplied() -> None:
    """Importability validation stays side-effect free."""
    unused_sink = InMemoryCatalogPlanShadowSink()

    findings = validate_importability(
        nodes_for_flow(
            [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {},
                }
            ]
        ),
        catalog=native_module_snapshot(),
    )

    assert not (findings), (
        f"Known catalog module should not emit findings: {findings}"
    )
    assert not (unused_sink.events), (
        "Telemetry sink should remain empty unless injected: "
        f"{unused_sink.events}"
    )


def nodes_for_flow(flow: list[object]) -> tuple[MakeAstNode, ...]:
    """Return AST nodes for one sanitized blueprint flow."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "shadow-telemetry",
                "flow": flow,
                "metadata": {"schedule": {"id": "schedule:manual"}},
            },
            sort_keys=True,
        )
    )
    return iter_ast_nodes(root)
