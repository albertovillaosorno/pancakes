# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.schema-policy
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Parse Make blueprint JSON into the typed AST contract.

Boundary contract:
- Owns: converting normalized blueprint JSON into typed AST records.
- Must not: validate catalog truth, render blueprints, or rewrite node IDs.
- Allows: JSON normalization, node classification, and source-trace
preservation.
- Split when: parsing a container family needs independent ownership.
- Merge when: another parser file builds the same typed AST records identically.
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING, Final, cast

from blueprints.ast.errors import MakeAstParseError
from blueprints.ast.models import (
    AST_SCHEMA_VERSION,
    AstNodeKind,
    JsonObject,
    MakeAstFilter,
    MakeAstNode,
    MakeAstRawSpecBinding,
    MakeAstRoot,
    MakeAstRoute,
    MakeAstScenario,
    MakeAstScenarioEndpoint,
    MakeAstScheduleConfig,
    MakeAstSourceTrace,
)
from blueprints.ast.module_roles import module_looks_like_webhook_response

if TYPE_CHECKING:
    from collections.abc import Mapping

FLOW_WRAPPER_KEYS: Final[tuple[str, ...]] = ("routes", "branches", "tools")
DIRECT_ERROR_KEYS: Final[tuple[str, ...]] = ("onerror", "on_error")
DEFAULT_SCENARIO_NAME: Final = "Imported Make Scenario"
FILTER_CONDITION_KEYS: Final[tuple[str, ...]] = (
    "conditions ",
    "condition ",
    "rules ",
    "expression",
)
CLASSIFICATION_PATTERNS: Final[
    tuple[tuple[AstNodeKind, tuple[str, ...]], ...]
] = (
    ("router", ("basicrouter", ":router")),
    ("iterator", ("iterator",)),
    ("aggregator", ("aggregator",)),
    ("webhook", ("webhook",)),
    ("http_api", ("http:", "makerequest", "api")),
    ("data_store", ("datastore", "data-store")),
    ("mcp_tool", ("mcp:", "mcp")),
)
KNOWN_ROOT_KEYS: Final[frozenset[str]] = frozenset(("name", "flow", "metadata"))
KNOWN_NODE_KEYS: Final[frozenset[str]] = frozenset(
    (
        "id ",
        "module ",
        "version ",
        "label ",
        "name ",
        "parameters ",
        "mapper ",
        "metadata ",
        "routes ",
        "branches ",
        "tools ",
        "onerror ",
        "on_error",
    )
)


def parse_make_ast(payload: JsonObject) -> MakeAstRoot:
    """Parse one Make blueprint payload into a typed AST root.

    Returns:
        The typed AST root.
    """
    normalized = normalize_json_object(payload)
    scenario = _parse_scenario(normalized)
    flow = _parse_flow(
        value=normalized.get("flow"),
        path=("flow",),
        container_kind="flow",
        parent_node_id=None,
    )
    return MakeAstRoot(
        ast_schema_version=AST_SCHEMA_VERSION,
        scenario=scenario,
        flow=flow,
        raw_payload=normalized,
        unknown_fields=_unknown_fields(normalized, KNOWN_ROOT_KEYS),
    )


def parse_make_ast_json_text(source_text: str) -> MakeAstRoot:
    """Parse JSON text into a typed Make AST or raise a typed parse error.

    Returns:
        The typed AST root parsed from JSON text.

    Raises:
        MakeAstParseError: If the blueprint JSON cannot be parsed into the AST
        contract.
    """
    try:
        payload = cast("object", json.loads(source_text))
    except json.JSONDecodeError as error:
        message = "Malformed Make blueprint JSON."
        raise MakeAstParseError(message) from error
    if not isinstance(payload, dict):
        message = "Make blueprint JSON must be an object."
        raise MakeAstParseError(message)
    try:
        return parse_make_ast(
            normalize_json_object(cast("Mapping[str, object]", payload))
        )
    except (TypeError, ValueError) as error:
        raise MakeAstParseError(str(error)) from error


def normalize_json_object(payload: Mapping[str, object]) -> JsonObject:
    """Return a JSON object with validated recursively copied values.

    Raises:
        TypeError: If a key or value has an invalid JSON shape.
    """
    normalized: JsonObject = {}
    for key, value in cast("Mapping[object, object]", payload).items():
        if not isinstance(key, str):
            message = "Make AST JSON object keys must be strings."
            raise TypeError(message)
        normalized[key] = _normalize_json_value(value)
    return normalized


def _normalize_json_value(value: object) -> object:
    """Return a recursively validated JSON value.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            message = "Non-finite JSON numbers are not valid Make AST values."
            raise TypeError(message)
        return value
    if isinstance(value, dict):
        return normalize_json_object(cast("Mapping[str, object]", value))
    if isinstance(value, list):
        return [
            _normalize_json_value(item) for item in cast("list[object]", value)
        ]
    message = f"Unsupported JSON value type in Make AST: {type(value).__name__}"
    raise TypeError(message)


def _parse_scenario(payload: JsonObject) -> MakeAstScenario:
    """Parse root scenario metadata.

    Returns:
        The parsed root scenario metadata.
    """
    metadata = _object_or_empty(payload.get("metadata"))
    scenario_metadata = _object_or_empty(metadata.get("scenario"))
    root_name = (
        _required_string_text(payload, "name") if "name" in payload else None
    )
    scenario_name = (
        _optional_string_text(scenario_metadata, "name") or root_name
    )
    return MakeAstScenario(
        name=scenario_name or DEFAULT_SCENARIO_NAME,
        inputs=_parse_endpoints(
            metadata.get("parameters"), kind="scenario_input"
        ),
        outputs=_parse_endpoints(
            metadata.get("expect"), kind="scenario_output"
        ),
        schedule=_parse_schedule(metadata),
        metadata=metadata,
    )


def _parse_endpoints(
    value: object,
    *,
    kind: AstNodeKind,
) -> tuple[MakeAstScenarioEndpoint, ...]:
    """Parse scenario input or output declarations.

    Returns:
        The parsed scenario input or output declarations.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        message = f"Scenario {kind} declarations must be a list."
        raise TypeError(message)
    endpoints: list[MakeAstScenarioEndpoint] = []
    for index, item in enumerate(cast("list[object]", value)):
        endpoint = _object_member_from_item(item, label=f"{kind}[{index}]")
        name = _optional_text(endpoint, "name") or f"{kind}_{index}"
        endpoints.append(
            MakeAstScenarioEndpoint(
                endpoint_id=f"{kind}:{name}",
                kind=kind,
                name=name,
                raw_payload=endpoint,
            )
        )
    return tuple(endpoints)


def _parse_schedule(metadata: JsonObject) -> MakeAstScheduleConfig | None:
    """Parse schedule or trigger metadata when present.

    Returns:
        The parsed schedule or trigger metadata when present.

    Raises:
        TypeError: If a value has an invalid type.
    """
    schedule = metadata.get("schedule")
    if schedule is None:
        schedule = metadata.get("trigger")
    if schedule is None:
        return None
    if not isinstance(schedule, dict):
        message = "Scenario schedule or trigger metadata must be an object."
        raise TypeError(message)
    payload = normalize_json_object(cast("Mapping[str, object]", schedule))
    schedule_id = _optional_text(payload, "id") or "schedule:default"
    return MakeAstScheduleConfig(
        schedule_id=schedule_id,
        kind="schedule_trigger",
        raw_payload=payload,
    )


def _parse_flow(
    *,
    value: object,
    path: tuple[str | int, ...],
    container_kind: str,
    parent_node_id: str | None,
) -> tuple[MakeAstNode, ...]:
    """Parse one flow array into AST nodes.

    Returns:
        The parsed AST node flow.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        message = f"Make AST flow at {path!r} must be a list."
        raise TypeError(message)
    nodes: list[MakeAstNode] = []
    for index, item in enumerate(cast("list[object]", value)):
        node_payload = _object_member_from_item(item, label=f"{path}[{index}]")
        nodes.append(
            _parse_node(
                payload=node_payload,
                path=(*path, index),
                container_kind=container_kind,
                parent_node_id=parent_node_id,
            )
        )
    return tuple(nodes)


def _parse_node(
    *,
    payload: JsonObject,
    path: tuple[str | int, ...],
    container_kind: str,
    parent_node_id: str | None,
) -> MakeAstNode:
    """Parse one Make AST node.

    Returns:
        The parsed Make AST node.
    """
    node_id = _optional_text(payload, "id") or _path_node_id(path)
    module_token = _optional_text(payload, "module") or ""
    kind = _classify_node(
        module_token=module_token, container_kind=container_kind
    )
    source_trace = MakeAstSourceTrace(
        path=path,
        container_kind=container_kind,
        parent_node_id=parent_node_id,
        raw_node_id=node_id,
        raw_module_token=module_token,
    )
    return MakeAstNode(
        node_id=node_id,
        kind=kind,
        module_token=module_token,
        label=_optional_text(payload, "label")
        or _optional_text(payload, "name")
        or module_token,
        source_trace=source_trace,
        raw_spec_binding=_parse_raw_spec_binding(payload),
        routes=_parse_routes(
            payload.get("routes"),
            parent_path=path,
            parent_node_id=node_id,
            container_kind="routes",
        ),
        branches=_parse_routes(
            payload.get("branches"),
            parent_path=path,
            parent_node_id=node_id,
            container_kind="branches",
        ),
        tools=_parse_routes(
            payload.get("tools"),
            parent_path=path,
            parent_node_id=node_id,
            container_kind="tools",
        ),
        error_handlers=_parse_error_handlers(
            payload, parent_path=path, parent_node_id=node_id
        ),
        raw_payload=payload,
        unknown_fields=_unknown_fields(payload, KNOWN_NODE_KEYS),
    )


def _parse_routes(
    value: object,
    *,
    parent_path: tuple[str | int, ...],
    parent_node_id: str,
    container_kind: str,
) -> tuple[MakeAstRoute, ...]:
    """Parse route, branch, or tool wrapper arrays.

    Returns:
        The parsed route, branch, or tool wrapper arrays.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        message = f"Route container at {parent_path!r} must be a list."
        raise TypeError(message)
    routes: list[MakeAstRoute] = []
    for index, item in enumerate(cast("list[object]", value)):
        route_payload = _object_member_from_item(
            item, label=f"{container_kind}[{index}]"
        )
        route_path = (*parent_path, container_kind, index)
        routes.append(
            MakeAstRoute(
                route_id=f"{parent_node_id}:{container_kind}:{index}",
                container_kind=container_kind,
                source_trace=MakeAstSourceTrace(
                    path=route_path,
                    container_kind=container_kind,
                    parent_node_id=parent_node_id,
                    raw_node_id=f"{parent_node_id}:{container_kind}:{index}",
                    raw_module_token="",
                ),
                filter=_parse_filter(
                    route_payload.get("filter"), route_path=route_path
                ),
                flow=_parse_flow(
                    value=route_payload.get("flow"),
                    path=(*route_path, "flow"),
                    container_kind=container_kind,
                    parent_node_id=parent_node_id,
                ),
                raw_payload=route_payload,
            )
        )
    return tuple(routes)


def _parse_filter(
    value: object, *, route_path: tuple[str | int, ...]
) -> MakeAstFilter | None:
    """Parse one route filter payload.

    Returns:
        The parsed route filter payload.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        message = f"Route filter at {route_path!r} must be an object."
        raise TypeError(message)
    payload = normalize_json_object(cast("Mapping[str, object]", value))
    return MakeAstFilter(
        filter_id=f"{_path_node_id(route_path)}:filter",
        kind="filter",
        name=_optional_text(payload, "name")
        or _optional_text(payload, "label")
        or "filter",
        conditions=_parse_filter_conditions(payload),
        raw_payload=payload,
    )


def _parse_filter_conditions(payload: JsonObject) -> JsonObject:
    """Return normalized filter conditions from known Make export shapes."""
    present_keys = tuple(key for key in FILTER_CONDITION_KEYS if key in payload)
    if not present_keys:
        return {}
    if present_keys == ("conditions",):
        raw_conditions = payload.get("conditions")
        if raw_conditions is None:
            return {}
        if isinstance(raw_conditions, dict):
            return normalize_json_object(
                cast("Mapping[str, object]", raw_conditions)
            )
        return {"conditions": _copy_json_value(raw_conditions)}
    return {key: _copy_json_value(payload[key]) for key in present_keys}


def _parse_error_handlers(
    payload: JsonObject,
    *,
    parent_path: tuple[str | int, ...],
    parent_node_id: str,
) -> tuple[MakeAstNode, ...]:
    """Parse direct error-handler children from onerror/on_error arrays.

    Returns:
        The parsed direct error-handler children from onerror/on_error arrays.

    Raises:
        TypeError: If a value has an invalid type.
    """
    handlers: list[MakeAstNode] = []
    for error_key in DIRECT_ERROR_KEYS:
        raw_handlers = payload.get(error_key)
        if raw_handlers is None:
            continue
        if isinstance(raw_handlers, dict):
            handlers.extend(
                _parse_error_handler_item(
                    item=cast("object", raw_handlers),
                    path=(*parent_path, error_key),
                    container_kind=error_key,
                    parent_node_id=parent_node_id,
                )
            )
            continue
        if not isinstance(raw_handlers, list):
            message = (
                f"Error handler container {error_key!r} must be an object or "
                f"list."
            )
            raise TypeError(message)
        for index, item in enumerate(cast("list[object]", raw_handlers)):
            handlers.extend(
                _parse_error_handler_item(
                    item=item,
                    path=(*parent_path, error_key, index),
                    container_kind=error_key,
                    parent_node_id=parent_node_id,
                )
            )
    return tuple(handlers)


def _parse_error_handler_item(
    *,
    item: object,
    path: tuple[str | int, ...],
    container_kind: str,
    parent_node_id: str,
) -> tuple[MakeAstNode, ...]:
    """Parse one direct error-handler module or flow wrapper.

    Returns:
        Parsed error-handler AST nodes.
    """
    payload = _object_member_from_item(item, label=str(path))
    if "flow" in payload and "module" not in payload:
        return _parse_flow(
            value=payload.get("flow"),
            path=(*path, "flow"),
            container_kind=container_kind,
            parent_node_id=parent_node_id,
        )
    return (
        _parse_node(
            payload=payload,
            path=path,
            container_kind=container_kind,
            parent_node_id=parent_node_id,
        ),
    )


def _parse_raw_spec_binding(payload: JsonObject) -> MakeAstRawSpecBinding:
    """Parse raw-spec binding fields from node metadata.

    Returns:
        The parsed raw-spec binding fields from node metadata.
    """
    raw_metadata = payload.get("metadata")
    metadata = (
        normalize_json_object(cast("Mapping[str, object]", raw_metadata))
        if isinstance(raw_metadata, dict)
        else {}
    )
    binding = metadata.get("raw_spec")
    if binding is None:
        binding = payload.get("raw_spec")
    if binding is None:
        return MakeAstRawSpecBinding(
            status="unresolved",
            catalog_module_id=None,
            raw_spec_sha256=None,
            issues=("missing_raw_spec_binding",),
        )
    if not isinstance(binding, dict):
        return MakeAstRawSpecBinding(
            status="unresolved",
            catalog_module_id=None,
            raw_spec_sha256=None,
            issues=("invalid_raw_spec_binding",),
        )
    binding_payload = normalize_json_object(
        cast("Mapping[str, object]", binding)
    )
    try:
        issues = _string_tuple(binding_payload.get("issues"))
    except TypeError:
        issues = ("invalid_raw_spec_binding",)
    invalid_fields: list[str] = []
    status = _optional_raw_spec_binding_text(
        binding_payload,
        "status",
        invalid_fields=invalid_fields,
    )
    catalog_module_id = _optional_raw_spec_binding_text(
        binding_payload,
        "catalog_module_id",
        invalid_fields=invalid_fields,
    )
    raw_spec_sha256 = _optional_raw_spec_binding_text(
        binding_payload,
        "raw_spec_sha256",
        invalid_fields=invalid_fields,
    )
    if invalid_fields:
        issues = (*issues, "invalid_raw_spec_binding")
    return MakeAstRawSpecBinding(
        status=status or "unresolved",
        catalog_module_id=catalog_module_id,
        raw_spec_sha256=raw_spec_sha256,
        issues=_deduplicate_texts(issues) or ("missing_raw_spec_binding",),
    )


def _classify_node(*, module_token: str, container_kind: str) -> AstNodeKind:
    """Return the typed AST kind for one node."""
    if container_kind in DIRECT_ERROR_KEYS:
        return "error_handler"
    if not module_token:
        return "unresolved"
    return _classify_module_token(module_token)


def _classify_module_token(module_token: str) -> AstNodeKind:
    """Return the typed AST kind for one non-empty module token."""
    lowered = module_token.casefold().replace("_", "").replace(" ", "")
    if module_looks_like_webhook_response(module_token):
        return "module"
    if "ai" in lowered and "agent" in lowered:
        return "ai_agent"
    for kind, patterns in CLASSIFICATION_PATTERNS:
        if any(
            _classification_matches(lowered, pattern) for pattern in patterns
        ):
            return kind
    if module_token.startswith("builtin:"):
        return "module"
    return "unresolved" if ":" not in module_token else "module"


def _classification_matches(lowered: str, pattern: str) -> bool:
    """Return whether one lowered token matches a classification pattern."""
    if pattern.endswith(":"):
        return lowered.startswith(pattern)
    return pattern in lowered


def _object_or_empty(value: object) -> JsonObject:
    """Return a JSON object or an empty object.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        message = "Expected a JSON object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", value))


def _object_member_from_item(item: object, *, label: str) -> JsonObject:
    """Return a JSON object from one list item.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if not isinstance(item, dict):
        message = f"Make AST item {label} must be an object."
        raise TypeError(message)
    return normalize_json_object(cast("Mapping[str, object]", item))


def _required_string_text(payload: JsonObject, key: str) -> str:
    """Return one required non-empty string member.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = _optional_string_text(payload, key)
    if value is None:
        message = f"Make AST member {key!r} must be non-empty text."
        raise ValueError(message)
    return value


def _optional_raw_spec_binding_text(
    payload: JsonObject,
    key: str,
    *,
    invalid_fields: list[str],
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        invalid_fields.append(key)
        return None
    text = value.strip()
    return text or None


def _optional_text(payload: JsonObject, key: str) -> str | None:
    """Return one optional non-empty text member."""
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_string_text(payload: JsonObject, key: str) -> str | None:
    """Return one optional non-empty string member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        message = f"Make AST member {key!r} must be text."
        raise TypeError(message)
    text = value.strip()
    return text or None


def _deduplicate_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return tuple(deduplicated)


def _string_tuple(value: object) -> tuple[str, ...]:
    """Return a tuple of strings from an optional JSON list.

    Raises:
        TypeError: If a value has an invalid type.
    """
    if value is None:
        return ()
    if not isinstance(value, list):
        message = "Expected a string list."
        raise TypeError(message)
    strings: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str):
            message = "Expected a string list."
            raise TypeError(message)
        text = item.strip()
        if text:
            strings.append(text)
    return tuple(strings)


def _unknown_fields(
    payload: JsonObject, known_keys: frozenset[str]
) -> JsonObject:
    """Return fields not modeled directly by the typed AST contract."""
    return {
        key: _copy_json_value(value)
        for key, value in payload.items()
        if key not in known_keys
    }


def _copy_json_value(value: object) -> object:
    """Return a deep JSON copy for unknown field preservation."""
    return cast("object", json.loads(json.dumps(value, sort_keys=True)))


def _path_node_id(path: tuple[str | int, ...]) -> str:
    """Return a deterministic fallback ID from a source path."""
    return ".".join(str(part) for part in path)
