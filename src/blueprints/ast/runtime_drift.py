# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.delta-reporting
# - 001061#repo.delivery.live-verification-explicit-only
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""In-memory runtime drift helpers for Make blueprint round trips.

Boundary contract:
- Owns: in-memory drift evaluation for two parsed blueprint AST roots.
- Must not: execute round trips, fetch live scenarios, or repair drift.
- Allows: designer-message evidence and accepted coordinate normalization.
- Split when: drift categories need independent acceptance policy.
- Merge when another drift evaluator reports the same paths.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, NamedTuple, TypeGuard, cast

from blueprints.ast.delta import BlueprintAstDelta, compute_ast_delta
from blueprints.ast.orphans import extract_designer_orphan_groups
from blueprints.ast.traversal import iter_ast_nodes

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject, MakeAstRoot

DESIGNER_COORDINATE_FIELDS = ("x", "y")


class DesignerMessageEvidence(NamedTuple):
    """One root or node-level designer message."""

    signature: str
    path: str
    node_id: str | None
    module_token: str | None
    payload: JsonObject


class BlueprintRuntimeDrift(NamedTuple):
    """Round-trip drift report with allowed coordinate shifts separated."""

    raw_delta: BlueprintAstDelta
    accepted_changed_paths: tuple[str, ...]
    unsupported_added_paths: tuple[str, ...]
    unsupported_removed_paths: tuple[str, ...]
    unsupported_changed_paths: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        """Return whether all observed drift is supported normalization."""
        return not (
            self.unsupported_added_paths
            or self.unsupported_removed_paths
            or self.unsupported_changed_paths
        )


def collect_designer_message_evidence(
    root: MakeAstRoot,
) -> tuple[DesignerMessageEvidence, ...]:
    """Collect unique designer messages from a parsed blueprint.

    Returns:
        The collected values.
    """
    messages: dict[str, DesignerMessageEvidence] = {}
    _collect_root_messages(root, messages)
    for node in iter_ast_nodes(root):
        designer = _designer_object(node.raw_payload)
        if designer is None:
            continue
        _collect_messages(
            raw_messages=designer.get("messages"),
            path=_path_text(
                (*node.source_trace.path, "metadata", "designer", "messages")
            ),
            node_id=node.node_id,
            module_token=node.module_token,
            messages=messages,
        )
    _collect_orphan_messages(root, messages)
    return tuple(messages[key] for key in sorted(messages))


def designer_message_signature(message: JsonObject) -> str:
    """Return a stable designer-message signature."""
    category = _optional_text(message.get("category")) or ""
    severity = (
        _optional_text(message.get("severity"))
        or _optional_text(message.get("level"))
        or ""
    )
    text = (
        _optional_text(message.get("message"))
        or _optional_text(message.get("text"))
        or ""
    )
    return f"{category}|{severity}|{text}"


def evaluate_runtime_drift(
    before: MakeAstRoot, after: MakeAstRoot
) -> BlueprintRuntimeDrift:
    """Evaluate AST JSON drift while accepting designer coordinates.

    Returns:
        The drift report after accepting designer coordinate normalization.
    """
    delta = compute_ast_delta(before.raw_payload, after.raw_payload)
    allowed_coordinate_paths = _designer_coordinate_paths(
        before
    ) | _designer_coordinate_paths(after)
    accepted_changed = tuple(
        path for path in delta.changed_paths if path in allowed_coordinate_paths
    )
    return BlueprintRuntimeDrift(
        raw_delta=delta,
        accepted_changed_paths=accepted_changed,
        unsupported_added_paths=delta.added_paths,
        unsupported_removed_paths=delta.removed_paths,
        unsupported_changed_paths=tuple(
            path for path in delta.changed_paths if path not in accepted_changed
        ),
    )


def _designer_coordinate_paths(root: MakeAstRoot) -> set[str]:
    paths: set[str] = set()
    for node in iter_ast_nodes(root):
        paths.update(
            _path_text(
                (
                    *node.source_trace.path,
                    "metadata",
                    "designer",
                    coordinate_field,
                )
            )
            for coordinate_field in DESIGNER_COORDINATE_FIELDS
        )
    return paths


def _collect_root_messages(
    root: MakeAstRoot,
    messages: dict[str, DesignerMessageEvidence],
) -> None:
    """Collect root designer messages."""
    metadata = root.scenario.metadata
    designer = metadata.get("designer")
    if not _is_json_object(designer):
        return
    _collect_messages(
        raw_messages=designer.get("messages"),
        path="$.metadata.designer.messages",
        node_id=None,
        module_token=None,
        messages=messages,
    )


def _collect_orphan_messages(
    root: MakeAstRoot,
    messages: dict[str, DesignerMessageEvidence],
) -> None:
    """Collect root-designer orphan module messages."""
    for group in extract_designer_orphan_groups(root):
        for node_index, node in enumerate(group.nodes):
            designer = _designer_object(node.raw_payload)
            if designer is None:
                continue
            _collect_messages(
                raw_messages=designer.get("messages"),
                path=(
                    "$.metadata.designer.orphans"
                    f"[{group.group_index}][{node_index}].metadata.designer.messages"
                ),
                node_id=node.node_id,
                module_token=node.module_token,
                messages=messages,
            )


def _collect_messages(
    *,
    raw_messages: object,
    path: str,
    node_id: str | None,
    module_token: str | None,
    messages: dict[str, DesignerMessageEvidence],
) -> None:
    """Collect list-shaped designer messages."""
    if not isinstance(raw_messages, list):
        return
    for item in cast("list[object]", raw_messages):
        if not _is_json_object(item):
            continue
        signature = designer_message_signature(item)
        if signature.endswith("|"):
            continue
        key = json.dumps(
            (
                path,
                signature,
                _designer_message_field_path(item),
                node_id,
                module_token,
            ),
            ensure_ascii=True,
        )
        messages[key] = DesignerMessageEvidence(
            signature, path, node_id, module_token, item
        )


def _designer_object(payload: JsonObject) -> JsonObject | None:
    """Return a node designer object when present."""
    metadata = payload.get("metadata")
    if not _is_json_object(metadata):
        return None
    designer = metadata.get("designer")
    return designer if _is_json_object(designer) else None


def _path_text(path: tuple[str | int, ...]) -> str:
    """Render an AST source path as a JSONPath-like string.

    Returns:
        The rendered value.
    """
    text = "$"
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else f".{part}"
    return text


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _designer_message_field_path(message: JsonObject) -> str:
    for key in ("field", "fieldPath", "path"):
        text = _optional_text(message.get(key))
        if text is not None:
            return text
    return ""
