# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make AST reference discovery and safe node ID rewriting.

Boundary contract:
- Owns: Make expression reference discovery and explicit node ID rewriting.
- Must not: parse full AST payloads, validate catalog modules, or render JSON.
- Allows: deterministic reference collection, note checks, and ID mapping
rewrites.
- Split when: reference discovery and rewrite behavior need separate ownership.
- Merge when: another reference file reports or rewrites the same tokens
identically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple, cast

from blueprints.ast.parser import normalize_json_object
from blueprints.ast.traversal import iter_ast_nodes

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )

EXPRESSION_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(
    (
        "mapper ",
        "parameters ",
        "filter ",
        "conditions ",
        "condition ",
        "rules ",
        "expression ",
        "formula",
    )
)
CHILD_FLOW_CONTAINER_KEYS: Final[frozenset[str]] = frozenset(
    ("routes", "branches", "tools")
)
SCALAR_REFERENCE_KEYS: Final[frozenset[str]] = frozenset(("moduleId", "stepId"))
DESIGNER_BINDING_CONTAINERS: Final[frozenset[str]] = frozenset(
    ("messages", "orphans")
)
DIRECT_NODE_CHILD_KEYS: Final[tuple[str, ...]] = ("onerror", "on_error")
NOTE_BINDING_PATH_LENGTH: Final[int] = 2
DESIGNER_BINDING_PATH_LENGTH: Final[int] = 3


class MakeReferenceUsage(NamedTuple):
    """One field-level Make expression reference between two AST nodes."""

    consumer_node_id: str
    consumer_module_token: str
    source_node_id: str
    field_path: str
    expression_path: tuple[AstPathPart, ...]
    raw_expression: str


class RuntimePlaceholderUsage(NamedTuple):
    """One runtime placeholder reference inside executable AST surfaces."""

    placeholder: str
    node_id: str | None
    module_token: str
    expression_path: tuple[AstPathPart, ...]
    raw_expression: str


def collect_reference_targets(root: MakeAstRoot) -> tuple[str, ...]:
    """Return all node IDs referenced by expressions and Make note bindings."""
    targets: set[str] = set()
    for node in iter_ast_nodes(root):
        targets.update(_collect_value_references(node.raw_payload, path=()))
    targets.update(_note_module_ids(root.scenario.metadata))
    return tuple(sorted(targets))


def collect_reference_usages(
    root: MakeAstRoot,
) -> tuple[MakeReferenceUsage, ...]:
    """Return the computed result for the caller."""
    usages: list[MakeReferenceUsage] = []
    for node in iter_ast_nodes(root):
        usages.extend(_node_reference_usages(node))
    return tuple(usages)


def collect_expression_reference_usages(
    expression: str,
) -> tuple[tuple[str, str], ...]:
    """Return source node and field-path references from one Make expression.

    string.
    """
    return tuple(
        usage
        for body in _make_template_bodies(expression)
        for usage in _expression_body_reference_usages(body)
    )


def collect_runtime_placeholder_usages(
    root: MakeAstRoot,
) -> tuple[RuntimePlaceholderUsage, ...]:
    """Return runtime placeholder references from executable.

    placeholder-capable.

    fields.
    """
    usages: list[RuntimePlaceholderUsage] = []
    usages.extend(
        _runtime_placeholder_usages(
            root.scenario.metadata,
            path=("metadata",),
            node_id=None,
            module_token="",
            excluded_keys=frozenset(("placeholder_registry",)),
        )
    )
    for node in iter_ast_nodes(root):
        usages.extend(_node_runtime_placeholder_usages(node))
        for route in (*node.routes, *node.branches, *node.tools):
            if route.filter is None:
                continue
            usages.extend(
                _runtime_placeholder_usages(
                    route.filter.raw_payload,
                    path=(*route.source_trace.path, "filter"),
                    node_id=node.node_id,
                    module_token=node.module_token,
                )
            )
    return tuple(usages)


def iter_top_level_nodes(root: MakeAstRoot) -> tuple[MakeAstNode, ...]:
    """Return top-level scenario flow nodes only."""
    return tuple(
        node
        for node in iter_ast_nodes(root)
        if node.source_trace.parent_node_id is None
        and node.source_trace.container_kind == "flow"
    )


def note_binding_errors(root: MakeAstRoot) -> tuple[str, ...]:
    """Return note-binding validation errors for Make-native note anchors."""
    notes = root.scenario.metadata.get("notes")
    if notes is None:
        return ()
    if not isinstance(notes, list):
        return ("metadata.notes must be a list.",)
    node_ids = {node.node_id for node in iter_ast_nodes(root)}
    errors: list[str] = []
    for index, note in enumerate(cast("list[object]", notes), start=1):
        if not isinstance(note, dict):
            errors.append(f"metadata.notes[{index}] is not an object.")
            continue
        errors.extend(
            _note_module_id_errors(
                note=cast("object", note), index=index, node_ids=node_ids
            )
        )
    return tuple(errors)


def cross_node_reference_errors(root: MakeAstRoot) -> tuple[str, ...]:
    """Return errors for references to missing Make AST node IDs."""
    node_ids = {node.node_id for node in iter_ast_nodes(root)}
    errors = [
        f"Blueprint references unknown module id '{target}'."
        for target in collect_reference_targets(root)
        if target not in node_ids
    ]
    errors.extend(note_binding_errors(root))
    return tuple(errors)


def rewrite_cross_node_references(
    payload: JsonObject,
    *,
    id_mapping: Mapping[str, str],
) -> JsonObject:
    """Rewrite module IDs in templates, Make note bindings, and node IDs.

    Returns:
        The result produced by rewrite module IDs in templates, Make note
        bindings, and node IDs.

    Raises:
        TypeError: If an input value has an unsupported type.
    """
    rewritten = _rewrite_value(payload, id_mapping=id_mapping, path=())
    if not isinstance(rewritten, dict):
        message = "Rewritten Make blueprint payload must remain a JSON object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", rewritten))


def _node_reference_usages(node: MakeAstNode) -> tuple[MakeReferenceUsage, ...]:
    usages: list[MakeReferenceUsage] = []
    for local_path, value in _iter_json_values(node.raw_payload, path=()):
        if not isinstance(value, str) or not _path_allows_make_templates(
            local_path,
            node_local=True,
        ):
            continue
        source_path = (*node.source_trace.path, *local_path)
        for body in _make_template_bodies(value):
            usages.extend(
                MakeReferenceUsage(
                    consumer_node_id=node.node_id,
                    consumer_module_token=node.module_token,
                    source_node_id=source_node_id,
                    field_path=field_path,
                    expression_path=source_path,
                    raw_expression=body,
                )
                for (
                    source_node_id,
                    field_path,
                ) in _expression_body_reference_usages(body)
            )
    return tuple(usages)


def _node_runtime_placeholder_usages(
    node: MakeAstNode,
) -> tuple[RuntimePlaceholderUsage, ...]:
    usages: list[RuntimePlaceholderUsage] = []
    for key in ("parameters", "mapper", "metadata", "expect", "interface"):
        if key not in node.raw_payload:
            continue
        usages.extend(
            _runtime_placeholder_usages(
                node.raw_payload[key],
                path=(*node.source_trace.path, key),
                node_id=node.node_id,
                module_token=node.module_token,
            )
        )
    return tuple(usages)


def _runtime_placeholder_usages(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    node_id: str | None,
    module_token: str,
    excluded_keys: frozenset[str] = frozenset(),
) -> tuple[RuntimePlaceholderUsage, ...]:
    usages: list[RuntimePlaceholderUsage] = []
    for local_path, item in _iter_json_values(
        value, path=path, excluded_keys=excluded_keys
    ):
        if not isinstance(item, str):
            continue
        usages.extend(
            RuntimePlaceholderUsage(
                placeholder=placeholder,
                node_id=node_id,
                module_token=module_token,
                expression_path=local_path,
                raw_expression=item,
            )
            for placeholder in _runtime_placeholders(item)
        )
    return tuple(usages)


def _collect_value_references(
    value: object, *, path: tuple[AstPathPart, ...]
) -> set[str]:
    targets: set[str] = set()
    if isinstance(value, str):
        if _path_allows_make_templates(path, node_local=True):
            targets.update(_make_template_reference_ids(value))
        return targets
    if isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            targets.update(_collect_value_references(item, path=(*path, index)))
        return targets
    if isinstance(value, dict):
        for raw_key, item in cast("Mapping[object, object]", value).items():
            if not isinstance(raw_key, str):
                continue
            targets.update(
                _collect_keyed_reference_targets(raw_key, item, path=path)
            )
    return targets


def _collect_keyed_reference_targets(
    key: str,
    item: object,
    *,
    path: tuple[AstPathPart, ...],
) -> set[str]:
    targets: set[str] = set()
    if (
        key == "moduleIds"
        and isinstance(item, list)
        and _path_allows_scalar_reference(path, key)
    ):
        targets.update(_normalized_note_module_ids(cast("list[object]", item)))
        return targets
    if key in SCALAR_REFERENCE_KEYS and _path_allows_scalar_reference(
        path, key
    ):
        normalized = _normalized_scalar_id(cast("object", item))
        return {normalized} if normalized else set()
    targets.update(
        _collect_value_references(cast("object", item), path=(*path, key))
    )
    return targets


def _rewrite_value(
    value: object,
    *,
    id_mapping: Mapping[str, str],
    path: tuple[AstPathPart, ...],
) -> object:
    if isinstance(value, str):
        if not _path_allows_make_templates(path, node_local=False):
            return value
        return _rewrite_make_template_references(value, id_mapping=id_mapping)
    if isinstance(value, list):
        return [
            _rewrite_value(item, id_mapping=id_mapping, path=(*path, index))
            for index, item in enumerate(cast("list[object]", value))
        ]
    if isinstance(value, dict):
        return _rewrite_mapping(
            cast("Mapping[object, object]", value),
            id_mapping=id_mapping,
            path=path,
        )
    return value


def _rewrite_mapping(
    value: Mapping[object, object],
    *,
    id_mapping: Mapping[str, str],
    path: tuple[AstPathPart, ...],
) -> JsonObject:
    rewritten: JsonObject = {}
    is_node = _looks_like_make_node(value, path=path)
    for raw_key, item in value.items():
        if not isinstance(raw_key, str):
            message = "Make reference rewrite object keys must be strings."
            raise TypeError(message)
        rewritten[raw_key] = _rewrite_mapping_value(
            key=raw_key,
            item=item,
            id_mapping=id_mapping,
            path=path,
            is_node=is_node,
        )
    return rewritten


def _rewrite_mapping_value(
    *,
    key: str,
    item: object,
    id_mapping: Mapping[str, str],
    path: tuple[AstPathPart, ...],
    is_node: bool,
) -> object:
    if (
        key == "moduleIds"
        and isinstance(item, list)
        and _path_allows_scalar_reference(path, key)
    ):
        items = cast("list[object]", item)
        return [
            _rewrite_scalar_id(entry, id_mapping=id_mapping) for entry in items
        ]
    if key in SCALAR_REFERENCE_KEYS and _path_allows_scalar_reference(
        path, key
    ):
        return _rewrite_scalar_id(cast("object", item), id_mapping=id_mapping)
    if key == "id" and is_node:
        return _rewrite_scalar_id(cast("object", item), id_mapping=id_mapping)
    return _rewrite_value(
        cast("object", item), id_mapping=id_mapping, path=(*path, key)
    )


def _rewrite_scalar_id(
    value: object, *, id_mapping: Mapping[str, str]
) -> object:
    if not isinstance(value, str | int) or isinstance(value, bool):
        return value
    if isinstance(value, int) and value <= 0:
        return value
    normalized = str(value).strip()
    if not normalized:
        return value
    replacement = id_mapping.get(normalized)
    if replacement is None:
        return value
    if isinstance(value, int) and _canonical_integer_text(replacement):
        return int(replacement)
    return replacement


def _canonical_integer_text(value: str) -> bool:
    """Return whether text can round-trip through an integer unchanged."""
    return value.isdigit() and str(int(value)) == value


def _note_module_ids(metadata: JsonObject) -> set[str]:
    notes = metadata.get("notes")
    if not isinstance(notes, list):
        return set()
    targets: set[str] = set()
    for note in cast("list[object]", notes):
        if not isinstance(note, dict):
            continue
        module_ids = cast("Mapping[str, object]", note).get("moduleIds")
        if isinstance(module_ids, list):
            targets.update(
                _normalized_note_module_ids(cast("list[object]", module_ids))
            )
    return targets


def _note_module_id_errors(
    *,
    note: object,
    index: int,
    node_ids: set[str],
) -> tuple[str, ...]:
    note_mapping = cast("Mapping[str, object]", note)
    module_ids = note_mapping.get("moduleIds")
    if module_ids is None:
        return ()
    if not isinstance(module_ids, list):
        return (f"metadata.notes[{index}].moduleIds must be a list.",)
    errors: list[str] = []
    for module_index, module_id in enumerate(
        cast("list[object]", module_ids), start=1
    ):
        normalized = _normalized_note_module_id(module_id)
        if not normalized:
            message = (
                f"metadata.notes[{index}].moduleIds[{module_index}] must be a "
                f"string or integer ID."
            )
            errors.append(message)
            continue
        if normalized not in node_ids:
            errors.append(
                f"metadata.notes[{index}] references unknown module id "
                f"'{normalized}'."
            )
    return tuple(errors)


def _normalized_note_module_ids(values: list[object]) -> set[str]:
    return {
        normalized
        for item in values
        if (normalized := _normalized_note_module_id(item))
    }


def _normalized_note_module_id(value: object) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int):
        return str(value) if value > 0 else ""
    if isinstance(value, str):
        return value.strip()
    return ""


def _normalized_scalar_id(value: object) -> str:
    return _normalized_note_module_id(value)


def _iter_json_values(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    excluded_keys: frozenset[str] = frozenset(),
) -> tuple[tuple[tuple[AstPathPart, ...], object], ...]:
    entries = [(path, value)]
    if isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            entries.extend(
                _iter_json_values(
                    item, path=(*path, index), excluded_keys=excluded_keys
                )
            )
    elif isinstance(value, dict):
        for raw_key, item in cast("Mapping[object, object]", value).items():
            if isinstance(raw_key, str) and raw_key not in excluded_keys:
                entries.extend(
                    _iter_json_values(
                        item,
                        path=(*path, raw_key),
                        excluded_keys=excluded_keys,
                    )
                )
    return tuple(entries)


def _looks_like_make_node(
    value: Mapping[object, object], *, path: tuple[AstPathPart, ...]
) -> bool:
    return "module" in value and _path_allows_make_node_id_rewrite(path)


def _path_allows_make_node_id_rewrite(path: tuple[AstPathPart, ...]) -> bool:
    string_parts = tuple(part for part in path if isinstance(part, str))
    return not string_parts or string_parts[-1] in {
        "flow",
        *DIRECT_NODE_CHILD_KEYS,
    }


def _path_allows_make_templates(
    path: tuple[AstPathPart, ...], *, node_local: bool
) -> bool:
    string_parts = tuple(part for part in path if isinstance(part, str))
    if "metadata" in string_parts:
        return False
    if node_local and _descends_into_child_node(string_parts):
        return False
    return any(part in EXPRESSION_CONTAINER_KEYS for part in string_parts)


def _descends_into_child_node(path: tuple[str, ...]) -> bool:
    """Return whether a node-local path belongs to a nested child node."""
    if any(part in DIRECT_NODE_CHILD_KEYS for part in path):
        return True
    return any(
        _has_flow_after_child_container(path, child_key)
        for child_key in CHILD_FLOW_CONTAINER_KEYS
    )


def _has_flow_after_child_container(
    path: tuple[str, ...], child_key: str
) -> bool:
    """Return whether a route-like container path enters a child flow node."""
    if child_key not in path:
        return False
    child_index = path.index(child_key)
    return "flow" in path[child_index + 1 :]


def _path_allows_scalar_reference(
    path: tuple[AstPathPart, ...], key: str
) -> bool:
    string_parts = tuple(part for part in path if isinstance(part, str))
    if key == "moduleIds":
        return len(string_parts) >= NOTE_BINDING_PATH_LENGTH and string_parts[
            -2:
        ] == (
            "metadata ",
            "notes",
        )
    if key not in SCALAR_REFERENCE_KEYS:
        return False
    if len(string_parts) < DESIGNER_BINDING_PATH_LENGTH or string_parts[
        -3:-1
    ] != (
        "metadata ",
        "designer",
    ):
        return False
    return string_parts[-1] in DESIGNER_BINDING_CONTAINERS


def _make_template_reference_ids(value: str) -> set[str]:
    targets: set[str] = set()
    for body in _make_template_bodies(value):
        targets.update(
            source_node_id
            for source_node_id, _ in _expression_body_reference_usages(body)
        )
    return targets


def _runtime_placeholders(value: str) -> tuple[str, ...]:
    return tuple(
        placeholder
        for body in _make_template_bodies(value)
        if (placeholder := body.strip()).startswith("runtime.")
    )


def _rewrite_make_template_references(
    value: str, *, id_mapping: Mapping[str, str]
) -> str:
    if "{{" not in value:
        return value
    parts: list[str] = []
    index = 0
    while index < len(value):
        start = value.find("{{", index)
        if start < 0:
            parts.append(value[index:])
            break
        body_start = start + 2
        body_end = _make_template_body_end(value, body_start)
        if body_end is None:
            parts.append(value[index:])
            break
        parts.extend(
            (
                value[index:start],
                "{{",
                _rewrite_expression_body_references(
                    value[body_start:body_end], id_mapping
                ),
                "}}",
            )
        )
        index = body_end + 2
    return "".join(parts)


def _make_template_bodies(value: str) -> tuple[str, ...]:
    bodies: list[str] = []
    index = 0
    while index < len(value):
        start = value.find("{{", index)
        if start < 0:
            break
        body_start = start + 2
        body_end = _make_template_body_end(value, body_start)
        if body_end is None:
            break
        bodies.append(value[body_start:body_end])
        index = body_end + 2
    return tuple(bodies)


def _make_template_body_end(value: str, body_start: int) -> int | None:
    index = body_start
    quote: str | None = None
    escaped = False
    while index < len(value) - 1:
        character = value[index]
        if quote is not None:
            escaped, quote = _advance_inside_quote(
                character, quote, escaped=escaped
            )
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if character == "}" and value[index + 1] == "}":
            return index
        index += 1
    return None


def _advance_inside_quote(
    character: str,
    quote: str,
    *,
    escaped: bool,
) -> tuple[bool, str | None]:
    if escaped:
        return False, quote
    if character == "\\":
        return True, quote
    if character == quote:
        return False, None
    return False, quote


def _expression_body_reference_usages(body: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (body[start:end], _reference_field_path(body, end))
        for start, end in _reference_token_spans(body)
    )


def _rewrite_expression_body_references(
    body: str, id_mapping: Mapping[str, str]
) -> str:
    spans = _reference_token_spans(body)
    if not spans:
        return body
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(body[cursor:start])
        module_id = body[start:end]
        parts.append(id_mapping.get(module_id, module_id))
        cursor = end
    parts.append(body[cursor:])
    return "".join(parts)


def _reference_field_path(body: str, module_id_end: int) -> str:
    index = module_id_end
    parts: list[str] = []
    while index < len(body):
        if body[index] == ".":
            segment, index = _consume_dot_field_segment(body, index + 1)
        elif body[index] == "[":
            segment, index = _consume_bracket_field_segment(body, index)
        else:
            break
        if not segment:
            break
        parts.append(segment)
    return ".".join(parts)


def _consume_dot_field_segment(body: str, index: int) -> tuple[str, int]:
    if index >= len(body) or not (body[index].isalpha() or body[index] == "_"):
        return "", index
    start = index
    index += 1
    while index < len(body) and (
        body[index].isalnum() or body[index] in {"_", "-"}
    ):
        index += 1
    return body[start:index], index


def _consume_bracket_field_segment(body: str, index: int) -> tuple[str, int]:
    index += 1
    while index < len(body) and body[index].isspace():
        index += 1
    if index >= len(body):
        return "", index
    if body[index].isdigit():
        return _consume_bracket_index_segment(body, index)
    if body[index] not in {"'", '"'}:
        return "", index
    return _consume_bracket_quoted_segment(body, index)


def _consume_bracket_index_segment(body: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(body) and body[index].isdigit():
        index += 1
    segment = body[start:index]
    while index < len(body) and body[index].isspace():
        index += 1
    if index < len(body) and body[index] == "]":
        return segment, index + 1
    return "", index


def _consume_bracket_quoted_segment(body: str, index: int) -> tuple[str, int]:
    quote = body[index]
    index += 1
    start = index
    while index < len(body):
        if body[index] == "\\":
            index += 2
            continue
        if body[index] == quote:
            return _close_bracket_quoted_segment(body, start, index)
        index += 1
    return "", index


def _close_bracket_quoted_segment(
    body: str, start: int, index: int
) -> tuple[str, int]:
    segment = body[start:index]
    index += 1
    while index < len(body) and body[index].isspace():
        index += 1
    if index < len(body) and body[index] == "]":
        return segment, index + 1
    return "", index


def _reference_token_spans(body: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    index = 0
    quote: str | None = None
    while index < len(body):
        character = body[index]
        if quote is not None:
            if character == "\\":
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if not character.isdigit():
            index += 1
            continue
        end = _numeric_token_end(body, index)
        if _is_module_reference_token(body, index, end):
            spans.append((index, end))
        index = end
    return tuple(spans)


def _numeric_token_end(body: str, start: int) -> int:
    end = start + 1
    while end < len(body) and body[end].isdigit():
        end += 1
    return end


def _is_module_reference_token(body: str, start: int, end: int) -> bool:
    previous = body[start - 1] if start > 0 else ""
    if previous and (previous.isalnum() or previous in {"_", "."}):
        return False
    if body.strip() == body[start:end]:
        return True
    if end >= len(body):
        return False
    next_character = body[end]
    if next_character == "[":
        return True
    if next_character != ".":
        return False
    lookahead = body[end + 1] if end + 1 < len(body) else ""
    return not lookahead.isdigit()
