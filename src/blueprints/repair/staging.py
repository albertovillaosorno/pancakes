# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001049#repo.blueprint-repair.offline-action-contract
# - 001061#repo.delivery.live-verification-explicit-only
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Offline blueprint staging preparation for explicit live import checks.

Boundary contract:
- Owns: import-safe blueprint copies for explicit staging verification.
- Must not: perform live imports, validate catalog truth, or own diagnostics.
- Allows: deterministic placeholder replacement and node payload normalization.
- Split when: a module-specific staging rule becomes independently complex.
- Merge when: another staging file transforms the same placeholders identically.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, TypeGuard, cast

from blueprints.ast.parser import normalize_json_object

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from blueprints.ast.models import JsonObject

PLACEHOLDER_DEFAULTS: JsonObject = {
    "ALLOWREDIRECTS": False,
    "AUTHENTICATIONTYPE": "noAuth",
    "CHANNEL_ID": "#make-canary",
    "DEFAULTMODEL": "medium",
    "HOOK": None,
    "MESSAGE": "Process the canary payload and return a concise result.",
    "METHOD": "post",
    "PARSERESPONSE": True,
    "REQUESTCOMPRESSEDCONTENT": False,
    "SHARECOOKIES": False,
    "STATUS": 200,
    "STOPONHTTPERROR": True,
    "THREADID": "",
    "URL": "https://example.com/make-canary",
}


def prepare_blueprint_for_staging_import(blueprint: JsonObject) -> JsonObject:
    """Return an import-safe copy for explicit staging checks."""
    prepared = normalize_json_object(
        cast("Mapping[str, object]", deepcopy(blueprint))
    )
    for node in _iter_node_payloads(prepared):
        module_key = str(node.get("module") or "").strip().lower()
        if module_key == "builtin:basicifelse":
            _normalize_if_else_branches(node)
        if module_key == "gateway:customwebhook":
            _prepare_custom_webhook_node(node)
        elif module_key == "http:makerequest":
            _prepare_http_request_node(node)
        elif module_key in {
            "gateway:webhookrespond",
            "gateway:webhookresponse",
        }:
            _prepare_webhook_respond_node(node)
        elif module_key == "ai-local-agent:runlocalaiagent":
            _prepare_ai_local_agent_node(node)
        _replace_placeholder_values_in_node(node)
    return prepared


def _iter_node_payloads(root: JsonObject) -> Iterable[JsonObject]:
    """Yield node dictionaries from known Make blueprint containers."""
    yield from _iter_node_list(root.get("flow"))


def _iter_node_list(value: object) -> Iterable[JsonObject]:
    """Yield node dictionaries from one flow-like list."""
    if not isinstance(value, list):
        return
    for item in cast("list[object]", value):
        if not _is_json_object(item):
            continue
        yield item
        for route_key in ("routes", "branches", "tools"):
            yield from _iter_route_nodes(item.get(route_key))
        for error_key in ("onerror", "on_error"):
            yield from _iter_error_nodes(item.get(error_key))


def _iter_route_nodes(value: object) -> Iterable[JsonObject]:
    """Yield route child nodes from routes, branches, or tools."""
    if not isinstance(value, list):
        return
    for route in cast("list[object]", value):
        if _is_json_object(route):
            yield from _iter_node_list(route.get("flow"))


def _iter_error_nodes(value: object) -> Iterable[JsonObject]:
    """Yield direct error-handler nodes."""
    if _is_json_object(value):
        yield value
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            if _is_json_object(item):
                yield item


def _normalize_if_else_branches(node: JsonObject) -> None:
    """Ensure BasicIfElse branches carry explicit branch types."""
    raw_branches = node.get("branches")
    if not isinstance(raw_branches, list):
        return
    for index, branch in enumerate(cast("list[object]", raw_branches)):
        if _is_json_object(branch):
            branch["type"] = "condition" if index == 0 else "else"


def _prepare_custom_webhook_node(node: JsonObject) -> None:
    """Use an unbound webhook representation."""
    parameters = _ensure_mapping(node, "parameters")
    parameters["hook"] = None
    _ = parameters.setdefault("maxResults", 1)
    if not _is_json_object(node.get("mapper")):
        node["mapper"] = {}


def _prepare_http_request_node(node: JsonObject) -> None:
    """Replace required HTTP placeholders with import-safe values."""
    mapper = _ensure_mapping(node, "mapper")
    _set_if_missing_or_unresolved(mapper, "authenticationType", "noAuth")
    _set_if_missing_or_unresolved(mapper, "url", PLACEHOLDER_DEFAULTS["URL"])
    _set_if_missing_or_unresolved(
        mapper, "method", PLACEHOLDER_DEFAULTS["METHOD"]
    )
    for key in (
        "parseResponse",
        "stopOnHttpError",
        "allowRedirects",
        "shareCookies",
        "requestCompressedContent",
    ):
        _set_if_missing_or_unresolved(
            mapper, key, PLACEHOLDER_DEFAULTS[key.upper()]
        )


def _prepare_webhook_respond_node(node: JsonObject) -> None:
    """Replace response placeholders with deterministic sample values."""
    mapper = _ensure_mapping(node, "mapper")
    _replace_if_unresolved(mapper, "status", PLACEHOLDER_DEFAULTS["STATUS"])
    _ = mapper.setdefault("body", '{"ok":true}')


def _prepare_ai_local_agent_node(node: JsonObject) -> None:
    """Make AI-agent staging payloads importable without provider binding."""
    mapper = _ensure_mapping(node, "mapper")
    _ = mapper.pop("makeConnectionId", None)
    _set_if_missing_or_unresolved(
        mapper, "defaultModel", PLACEHOLDER_DEFAULTS["DEFAULTMODEL"]
    )
    _set_if_missing_or_unresolved(
        mapper, "message", PLACEHOLDER_DEFAULTS["MESSAGE"]
    )
    _set_if_missing_or_unresolved(
        mapper, "threadId", PLACEHOLDER_DEFAULTS["THREADID"]
    )
    if _is_unresolved(mapper.get("files")) or _is_json_object(
        mapper.get("files")
    ):
        mapper["files"] = []
    _ = mapper.setdefault("outputType", "text")


def _replace_placeholder_values_in_node(node: JsonObject) -> None:
    """Replace unresolved placeholders in parameters and mapper only."""
    for key in ("parameters", "mapper"):
        current = node.get(key)
        if _is_json_object(current):
            node[key] = cast("JsonObject", _replace_placeholder_values(current))


def _replace_placeholder_values(value: object) -> object:
    """Replace unresolved placeholder strings with deterministic defaults.

    Returns:
        The result produced by replacing unresolved placeholder strings with
        deterministic defaults.
    """
    if _is_json_object(value):
        return {
            key: _replace_placeholder_values(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _replace_placeholder_values(item)
            for item in cast("list[object]", value)
        ]
    if isinstance(value, str):
        token = _placeholder_token(value)
        return (
            deepcopy(PLACEHOLDER_DEFAULTS.get(token))
            if token is not None
            else value
        )
    return value


def _placeholder_token(value: str) -> str | None:
    """Return the placeholder token name when a value is unresolved."""
    stripped = value.strip()
    if not (stripped.startswith("{{PLACEHOLDER_") and stripped.endswith("}}")):
        return None
    return stripped.removeprefix("{{PLACEHOLDER_").removesuffix("}}")


def _ensure_mapping(node: JsonObject, key: str) -> JsonObject:
    """Return one mutable mapping child on a node."""
    current = node.get(key)
    if _is_json_object(current):
        return current
    mapping: JsonObject = {}
    node[key] = mapping
    return mapping


def _replace_if_unresolved(
    mapping: JsonObject, key: str, value: object
) -> None:
    """Replace one mapping value only when the current value is unresolved."""
    if key in mapping and _is_unresolved(mapping.get(key)):
        mapping[key] = value


def _set_if_missing_or_unresolved(
    mapping: JsonObject, key: str, value: object
) -> None:
    """Set one mapping value when it is missing or unresolved."""
    if key not in mapping or _is_unresolved(mapping.get(key)):
        mapping[key] = value


def _is_unresolved(value: object) -> bool:
    """Return whether one value is still unresolved for staging import."""
    return value is None or (
        isinstance(value, str) and _placeholder_token(value) is not None
    )


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
