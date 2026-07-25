# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Reusable MCP compact-output assertions.

Boundary contract:
- Owns: behavior-level test helpers for compact MCP payload shape.
- Must not: execute MCP tools, load repositories, or define production policy.
- Allows: recursive payload assertions used by MCP contract tests.
- Split when: helpers become a shared test support package outside MCP
contracts.
- Merge when: another MCP test helper owns the same compact response invariants.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from tests.support.json_payloads import JsonObject

RAW_WALL_KEYS = frozenset(
    (
        "scenario_json",
        "blueprint_json",
        "raw_bindings",
        "raw_replacement_paths",
        "raw_translations",
        "artifact_would_include_raw_json",
        "blueprint_artifact_json_available_in_written_package",
    )
)
SECRET_MARKERS = ("APIKey", "AccessToken", "Bearer ", "bearer token")


def assert_compact_response_bounded(payload: JsonObject) -> None:
    """Assert a compact MCP payload exposes bounded collections and hidden.

    counts.
    """
    assert payload.get("output_mode") in {"micro", "compact", "outline"}, (
        payload
    )
    for path, key, value in _walk(payload):
        if isinstance(value, Sequence) and not isinstance(
            value, str | bytes | bytearray
        ):
            sequence = cast("Sequence[object]", value)
            assert len(sequence) <= 100, (
                f"{path} returned an unbounded compact sequence"
            )
        if key.startswith("hidden_") and key.endswith("_count"):
            assert isinstance(value, int), f"{path} hidden count must be an int"


def assert_no_raw_walls(payload: JsonObject) -> None:
    """Assert compact MCP payloads do not expose raw JSON walls."""
    for path, key, value in _walk(payload):
        assert key not in RAW_WALL_KEYS, f"{path} exposed a raw wall"
        if isinstance(value, str):
            assert len(value) <= 1000, f"{path} exposed an oversized text wall"


def assert_hidden_counts_when_truncated(payload: JsonObject) -> None:
    """Assert any truncated compact surface reports hidden counts."""
    graph_view = payload.get("graph_view")
    if isinstance(graph_view, Mapping):
        graph_mapping = cast("Mapping[str, object]", graph_view)
        returned_nodes = _int_value(graph_mapping, "returned_node_count")
        hidden_nodes = _int_value(graph_mapping, "hidden_node_count")
        total_nodes = _int_value(
            cast("Mapping[str, object]", payload.get("scenario_overview", {})),
            "module_count",
        )
        if returned_nodes < total_nodes:
            assert hidden_nodes == total_nodes - returned_nodes, payload


def assert_next_query_when_raw_omitted(payload: JsonObject) -> None:
    """Assert omitted raw or truncated data has an explicit next query."""
    for path, key, value in _walk(payload):
        if key == "omitted" and value is True:
            parent = _lookup_parent(payload, path)
            assert parent.get("next_query") or parent.get("next_queries"), (
                f"{path} omitted raw data without next_query"
            )
    graph_view = payload.get("graph_view")
    if isinstance(graph_view, Mapping) and (
        _int_value(
            cast("Mapping[str, object]", graph_view), "hidden_node_count"
        )
        or _int_value(
            cast("Mapping[str, object]", graph_view), "hidden_connection_count"
        )
    ):
        graph_mapping = cast("Mapping[str, object]", graph_view)
        assert graph_mapping.get("next_query"), payload


def assert_no_secret_or_credential_values(payload: JsonObject) -> None:
    """Assert compact MCP payloads do not expose credential-shaped values."""
    for path, _key, value in _walk(payload):
        if isinstance(value, str):
            assert not any(marker in value for marker in SECRET_MARKERS), path


def assert_no_duplicate_summary_payload(payload: JsonObject) -> None:
    """Assert compact responses do not repeat the same summary object in nested.

    previews.
    """
    nested_preview = payload.get("preview")
    assert not isinstance(nested_preview, Mapping), (
        "compact payload duplicated preview summary"
    )
    if "module_translation_summary" in payload:
        assert "make_preview" not in payload, (
            "compact payload duplicated Make preview summaries"
        )


def assert_safety_flags_false(payload: JsonObject) -> None:
    """Assert local-only safety flags are present and false."""
    for key in (
        "provider_api_call",
        "live_make_called",
        "credential_value_transfer",
        "secret_output",
    ):
        assert payload.get(key) is False, f"{key} must be false"


def assert_no_bare_ready_when_surfaces_differ(payload: JsonObject) -> None:
    """Assert top-level readiness names the surface when other surfaces.

    differ.
    """
    surface_statuses = {
        key: value
        for key, value in payload.items()
        if key.endswith("_status") and key != "status"
    }
    has_blocked_surface = any(
        isinstance(value, str) and value.startswith("blocked")
        for value in surface_statuses.values()
    )
    if has_blocked_surface:
        assert payload.get("status") != "ready", payload
        if str(payload.get("status", "")).endswith("_ready"):
            assert payload.get("status_surface"), payload
            assert payload.get("status_reason"), payload


def assert_no_ambiguous_available_flags(payload: JsonObject) -> None:
    """Assert bare available booleans are not used without status context."""
    for path, key, value in _walk(payload):
        if key == "available" and value is True:
            parent = _lookup_parent(payload, path)
            assert any(
                str(parent_key).endswith("_status") for parent_key in parent
            ), path


def assert_no_empty_detail_arrays_in_compact(payload: JsonObject) -> None:
    """Assert compact payloads do not ship empty detail arrays when counts.

    suffice.
    """
    for path, key, value in _walk(payload):
        if (
            isinstance(value, Sequence)
            and not isinstance(value, str | bytes | bytearray)
            and len(cast("Sequence[object]", value)) == 0
        ):
            assert key not in {"notes", "nodes", "connections", "resources"}, (
                path
            )


def assert_no_orphan_capabilities(payload: JsonObject) -> None:
    """Assert any live capability reference appears in the package capability.

    matrix.
    """
    matrix = payload.get("make_mcp_capabilities")
    if not isinstance(matrix, Mapping):
        return
    matrix_mapping = cast("Mapping[str, object]", matrix)
    capability_ids = set(matrix_mapping)
    for path, key, value in _walk(payload):
        if key in {
            "live_tool_required",
            "required_live_capability",
            "cleanup_live_capability",
        }:
            assert str(value) in capability_ids, (
                f"{path} references an orphan capability"
            )
        if key in {
            "write_operation_capabilities",
            "read_operation_capabilities",
        } and isinstance(
            value,
            Sequence,
        ):
            for capability in cast("Sequence[object]", value):
                assert str(capability) in capability_ids, (
                    f"{path} references orphan capability {capability}"
                )


def _walk(
    value: object,
    path: str = "$",
) -> tuple[tuple[str, str, object], ...]:
    rows: list[tuple[str, str, object]] = []
    if isinstance(value, Mapping):
        for key, child in cast("Mapping[object, object]", value).items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            rows.append((child_path, key_text, child))
            rows.extend(_walk(child, child_path))
    elif isinstance(value, Sequence) and not isinstance(
        value, str | bytes | bytearray
    ):
        for index, child in enumerate(cast("Sequence[object]", value)):
            rows.extend(_walk(child, f"{path}[{index}]"))
    return tuple(rows)


def _lookup_parent(payload: JsonObject, path: str) -> Mapping[str, object]:
    parent_path = path.rsplit(".", maxsplit=1)[0]
    current: object = payload
    for part in parent_path.removeprefix("$.").split("."):
        if not part:
            continue
        if not isinstance(current, Mapping):
            return {}
        current = cast("Mapping[str, object]", current).get(part, {})
    if isinstance(current, Mapping):
        return cast("Mapping[str, object]", current)
    return {}


def _int_value(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0
