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

"""Apply AST layout plans to blueprint JSON payloads.

Boundary contract:
- Owns: applying layout plans to copied blueprint JSON payloads.
- Must not: compute plans, analyze transitions, or mutate source AST objects.
- Allows: metadata designer coordinate writes on deterministic JSON copies.
- Split when: payload path resolution or designer writes need ownership.
- Merge when: another payload applier writes the same layout contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypeGuard, cast

if TYPE_CHECKING:
    from blueprints.ast.layout_models import (
        BlueprintLayoutPlan,
        BlueprintNodeLayout,
        BlueprintNoteLayout,
    )
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstRoot


def apply_blueprint_layout(
    root: MakeAstRoot, plan: BlueprintLayoutPlan
) -> JsonObject:
    """Return a copied blueprint payload with designer coordinates applied."""
    payload = _copy_json_object(root.raw_payload)
    for layout in plan.layouts:
        node = _resolve_object_path(payload, layout.source_path)
        _write_layout(node=node, layout=layout)
    for note_layout in plan.notes:
        note = _resolve_object_path(payload, note_layout.source_path)
        _write_note_layout(note=note, layout=note_layout)
    return payload


def _write_layout(*, node: JsonObject, layout: BlueprintNodeLayout) -> None:
    """Write one layout into a node metadata designer object."""
    metadata = node.get("metadata")
    if not _is_json_object(metadata):
        metadata = {}
        node["metadata"] = metadata
    designer = metadata.get("designer")
    if not _is_json_object(designer):
        designer = {}
        metadata["designer"] = designer
    designer["x"] = layout.x
    designer["y"] = layout.y


def _write_note_layout(
    *, note: JsonObject, layout: BlueprintNoteLayout
) -> None:
    """Write one root note position."""
    note["x"] = layout.x
    note["y"] = layout.y


def _resolve_object_path(
    payload: JsonObject, path: tuple[AstPathPart, ...]
) -> JsonObject:
    """Resolve one AST source path into a mutable JSON object.

    Returns:
        The resolved value.

    Raises:
        KeyError: If a required key is missing.
        TypeError: If an input value has an unsupported type.
    """
    current: object = payload
    for part in path:
        if isinstance(part, int):
            if not isinstance(current, list):
                message = (
                    "Layout path does not resolve through a list segment: "
                    f"{path!r}"
                )
                raise TypeError(message)
            items = cast("list[object]", current)
            if part < 0 or part >= len(items):
                message = f"Layout path does not resolve to an object: {path!r}"
                raise KeyError(message)
            current = items[part]
            continue
        if not _is_json_object(current):
            message = (
                "Layout path does not resolve through an object segment: "
                f"{path!r}"
            )
            raise TypeError(message)
        if part not in current:
            message = f"Layout path does not resolve to an object: {path!r}"
            raise KeyError(message)
        current = current[part]
    if not _is_json_object(current):
        message = f"Layout path does not target an object: {path!r}"
        raise TypeError(message)
    return current


def _copy_json_object(value: JsonObject) -> JsonObject:
    """Return a deterministic JSON-compatible object copy."""
    return cast("JsonObject", json.loads(json.dumps(value, sort_keys=True)))


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether one value is a JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
