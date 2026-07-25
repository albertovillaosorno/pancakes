# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001055#repo.mcp.required-tool-surface
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Private Make-native semantics matrix loader.

Boundary contract:
- Owns: reading the internal Make-native module rendering contract matrix.
- Must not: call Make.com, mutate matrix files, expose customer-facing report
fields, or validate
  live provider resources.
- Allows: deterministic local loading for tests, compiler helpers, and internal
diagnostics.
- Split when: module projectors gain generated typed manifests.
- Merge when: Make module manifests own the same matrix fields directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject

MAKE_NATIVE_SEMANTICS_MATRIX_PATH: Final = (
    Path(__file__).parent / "data" / "native_semantics_matrix.json"
)
MAKE_NATIVE_SEMANTICS_MATRIX_SCHEMA_VERSION: Final = 1


def load_make_native_semantics_matrix() -> JsonObject:
    """Return the repository-private Make-native semantics matrix.

    Raises:
        TypeError: If the matrix root is not a JSON object.
        ValueError: If the matrix schema is unsupported.
    """
    raw = cast(
        "object",
        json.loads(
            MAKE_NATIVE_SEMANTICS_MATRIX_PATH.read_text(encoding="utf-8")
        ),
    )
    if not isinstance(raw, dict):
        message = "Make-native semantics matrix root must be a JSON object."
        raise TypeError(message)
    payload = cast("JsonObject", raw)
    schema_version = payload.get("schema_version")
    if schema_version != MAKE_NATIVE_SEMANTICS_MATRIX_SCHEMA_VERSION:
        message = (
            f"Unsupported Make-native semantics matrix schema:"
            f"{schema_version!r}"
        )
        raise ValueError(message)
    return payload


def make_native_semantics_records() -> tuple[JsonObject, ...]:
    """Return all Make-native semantics matrix records.

    Raises:
        TypeError: If the matrix records are not a list of JSON objects.
    """
    matrix = load_make_native_semantics_matrix()
    records = matrix.get("records")
    if not isinstance(records, list):
        message = "Make-native semantics matrix records must be a list."
        raise TypeError(message)
    return tuple(
        _json_object(record) for record in cast("list[object]", records)
    )


def make_native_semantics_family_coverage() -> tuple[JsonObject, ...]:
    """Return Make-native family coverage records from the matrix.

    Raises:
        TypeError: If the family coverage rows are not a list of JSON objects.
    """
    matrix = load_make_native_semantics_matrix()
    records = matrix.get("family_coverage")
    if not isinstance(records, list):
        message = "Make-native semantics matrix family_coverage must be a list."
        raise TypeError(message)
    return tuple(
        _json_object(record) for record in cast("list[object]", records)
    )


def make_native_semantics_family_record(family_id: str) -> JsonObject | None:
    """Return the family coverage record with the given ID."""
    normalized = family_id.casefold().strip()
    for record in make_native_semantics_family_coverage():
        if record.get("family_id") == normalized:
            return record
    return None


def make_native_semantics_record(module: str) -> JsonObject | None:
    """Return the matrix record that owns a module token or alias."""
    for record in make_native_semantics_records():
        if record.get("module") == module:
            return record
        aliases = record.get("aliases")
        if isinstance(aliases, list) and module in aliases:
            return record
    return None


def _json_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return {
            str(key): item
            for key, item in cast("dict[object, object]", value).items()
        }
    message = "Make-native semantics matrix record must be a JSON object."
    raise TypeError(message)
