# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Shared MCP payload guards for compact response contracts.

Boundary contract:
- Owns: structural assertions that compact MCP responses stay bounded and
expandable.
- Must not: execute MCP tools, own fixture generation, or assert
product-specific counts.
- Allows: recursive payload inspection for raw arrays and expansion hints.
- Split when: domain-specific payload assertions need their own support module.
- Merge when: another support module owns the same compact MCP response guards.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from tests.support.json_payloads import JsonObject

DEFAULT_COMPACT_LIST_MAX = 20
DEFAULT_COMPACT_SERIALIZED_MAX = 65_000
RAW_ARRAY_FIELD_NAMES = frozenset(
    {
        "blockers",
        "errors",
        "warnings",
        "optimization_hints",
        "missing_connection_notes",
        "missing_module_notes",
        "raw_bindings",
        "raw_translations",
        "replacement_paths",
        "runtime_placeholders",
        "scenario",
        "validation_report",
    }
)
FORBIDDEN_COMPACT_FIELD_NAMES = frozenset(
    {
        "blueprint_json",
        "missing_connection_notes",
        "missing_module_notes",
        "raw_bindings",
        "raw_replacement_paths",
        "raw_translations",
        "replacement_paths",
        "required_node_count",
        "runtime_setup_count",
        "runtime_setup_required_node_count",
        "runtime_setup_usage_count",
        "scenario_json",
        "unique_findings",
    }
)
RAW_HINT_FIELD_NAMES = frozenset(
    {
        "raw_findings_available",
        "raw_missing_notes_available",
        "raw_replacement_paths_available",
        "raw_bindings_available",
        "raw_translations_available",
    }
)
SECRET_MARKERS = (
    "APIKey",
    "AccessToken",
    "bearer token",
    "Bearer ",
)


def assert_compact_response_bounded(
    payload: JsonObject,
    *,
    max_list_len: int = DEFAULT_COMPACT_LIST_MAX,
    allow_paths: Iterable[str] = (),
) -> None:
    """Assert that a compact MCP payload is bounded and advertises raw.

    expansion.

    paths.
    """
    assert payload.get("output_mode") == "compact", (
        f"Expected compact payload: {payload}"
    )
    assert_compact_payload_is_bounded(
        payload,
        max_list_len=max_list_len,
        allow_paths=allow_paths,
    )
    assert_raw_available_hints(payload)


def assert_compact_payload_is_bounded(
    payload: JsonObject,
    *,
    max_list_len: int = DEFAULT_COMPACT_LIST_MAX,
    max_serialized_chars: int = DEFAULT_COMPACT_SERIALIZED_MAX,
    allow_paths: Iterable[str] = (),
) -> None:
    """Assert that a compact-like MCP payload stays structurally and byte.

    bounded.
    """
    assert payload.get("output_mode") in {
        "compact",
        "micro",
        "outline",
        "client_safe",
    }, f"Expected compact-like payload: {payload}"
    serialized = json.dumps(payload, default=list, sort_keys=True)
    assert len(serialized) <= max_serialized_chars, (
        f"Compact payload exceeded {max_serialized_chars} serialized "
        f"characters: {payload}"
    )
    assert_no_forbidden_compact_fields(payload)
    assert_no_large_raw_arrays(
        payload, max_len=max_list_len, allow_paths=allow_paths
    )


def assert_compact_response_exposes_raw_hints(payload: JsonObject) -> None:
    """Assert raw evidence expansion hints exist when compact output omits raw.

    surfaces.
    """
    assert_raw_available_hints(payload)


def assert_no_large_raw_arrays(
    payload: JsonObject,
    *,
    max_len: int = DEFAULT_COMPACT_LIST_MAX,
    allow_paths: Iterable[str] = (),
) -> None:
    """Assert that compact payload lists are capped unless explicitly.

    allowed.
    """
    allowed = frozenset(allow_paths)
    for path, value in _walk_payload(payload):
        if path in allowed or not isinstance(value, list | tuple):
            continue
        sequence = cast("list[object] | tuple[object, ...]", value)
        field_name = path.rsplit(".", maxsplit=1)[-1]
        assert field_name not in RAW_ARRAY_FIELD_NAMES, (
            f"Compact payload exposed raw array at {path}: {payload}"
        )
        assert len(sequence) <= max_len, (
            f"Compact payload list at {path} exceeded {max_len}: {payload}"
        )


def assert_raw_available_hints(payload: JsonObject) -> None:
    """Assert that omitted raw evidence surfaces include expansion hints."""
    serialized_hint_fields = {
        path.rsplit(".", maxsplit=1)[-1]: value
        for path, value in _walk_payload(payload)
        if path.rsplit(".", maxsplit=1)[-1] in RAW_HINT_FIELD_NAMES
    }
    assert serialized_hint_fields, (
        f"Compact payload did not expose raw availability hints: {payload}"
    )
    assert _has_next_query(payload), (
        f"Compact payload did not expose an expansion query: {payload}"
    )


def assert_no_forbidden_compact_fields(payload: JsonObject) -> None:
    """Assert compact payloads do not expose raw, ambiguous, or secret-like.

    fields.

    Raises:
        AssertionError: If the operation cannot complete.
    """
    for path, value in _walk_payload(payload):
        field_name = path.rsplit(".", maxsplit=1)[-1]
        assert field_name not in FORBIDDEN_COMPACT_FIELD_NAMES, (
            f"Compact payload exposed forbidden field at {path}: {payload}"
        )
        if field_name == "scenario_notes":
            parent_path = path.rsplit(".", maxsplit=1)[0]
            duplicate_summary = any(
                sibling_path.rsplit(".", maxsplit=1)[0] == parent_path
                and sibling_path.rsplit(".", maxsplit=1)[-1]
                == "scenario_notes_summary"
                for sibling_path, _sibling_value in _walk_payload(payload)
            )
            assert not duplicate_summary, (
                f"Compact payload duplicated scenario_notes and "
                f"scenario_notes_summary: {payload}"
            )
        if (
            "__IMTCONN__" in str(value)
            and "credential" in field_name.casefold()
        ):
            message = (
                f"Compact payload marked __IMTCONN__ as a credential: {payload}"
            )
            raise AssertionError(message)
        if isinstance(value, str):
            assert not any(marker in value for marker in SECRET_MARKERS), (
                f"Compact payload exposed secret-like marker at {path}: "
                f"{payload}"
            )
            normalized = value.replace("\\", "/")
            assert (
                not normalized.startswith("C:/")
                and "C:/Users/" not in normalized
            ), (
                f"Compact payload exposed local absolute path at {path}: "
                f"{payload}"
            )


def _walk_payload(
    payload: object, path: str = "$"
) -> tuple[tuple[str, object], ...]:
    rows: list[tuple[str, object]] = [(path, payload)]
    if isinstance(payload, dict):
        mapping = cast("Mapping[object, object]", payload)
        for key, value in mapping.items():
            rows.extend(_walk_payload(value, f"{path}.{key}"))
    elif isinstance(payload, list | tuple):
        for index, value in enumerate(
            cast("list[object] | tuple[object, ...]", payload)
        ):
            rows.extend(_walk_payload(value, f"{path}[{index}]"))
    return tuple(rows)


def _has_next_query(payload: object) -> bool:
    if isinstance(payload, dict):
        mapping = cast("Mapping[object, object]", payload)
        if isinstance(mapping.get("next_query"), str):
            return True
        return any(_has_next_query(value) for value in mapping.values())
    if isinstance(payload, list | tuple):
        return any(
            _has_next_query(value)
            for value in cast("list[object] | tuple[object, ...]", payload)
        )
    return False
