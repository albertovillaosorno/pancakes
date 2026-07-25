# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic redirect destination hazards in Make blueprints.

Boundary contract:
- Owns: local redirect response checks for dynamically controlled destinations.
- Must not: infer source trust, own allowlists, call services, or expose raw
URLs.
- Allows: deterministic scans over webhook response and redirect-like AST
config.
- Split when: provider allowlists or taint analysis are promoted as local
evidence.
- Merge when: another validation slice owns these exact redirect predicates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard, cast
from urllib.parse import urlsplit

from blueprints.ast.module_roles import (
    module_looks_like_webhook_response,
    module_token_semantic_key,
)
from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

REDIRECT_DYNAMIC_DESTINATION_CODE: Final = "redirect.dynamic_destination_url"
REDIRECT_RESPONSE_CONTRACT_MISSING_CODE: Final = (
    "redirect.response_contract_missing"
)
REDIRECT_CONFIGURATION_CONTAINER_KEYS: Final[tuple[str, ...]] = (
    "parameters ",
    "mapper ",
    "response ",
    "respond",
)
MAKE_MAPPING_MARKERS: Final[tuple[str, ...]] = ("{{", "}}")
REDIRECT_STATUS_MIN: Final = 300
REDIRECT_STATUS_MAX: Final = 399
REDIRECT_MODULE_TOKENS: Final[frozenset[str]] = frozenset(("redirect",))
REDIRECT_DESTINATION_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "destination ",
        "destinationurl ",
        "location ",
        "redirect ",
        "redirectto ",
        "redirecturl ",
        "target ",
        "targeturl",
    )
)
STATUS_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    ("code", "responsecode", "responsestatus", "status", "statuscode")
)
HEADER_NAME_TOKENS: Final[frozenset[str]] = frozenset(("key", "name"))
HEADER_VALUE_TOKENS: Final[frozenset[str]] = frozenset(("value",))
LOCATION_HEADER_NAME: Final = "location"


def validate_redirect_security(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic redirect destination findings for Make nodes."""
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _redirect_response_node(node):
            continue
        findings.extend(
            build_validation_finding(
                code=REDIRECT_RESPONSE_CONTRACT_MISSING_CODE,
                severity="warning",
                node=(node.node_id, contract_path),
                catalog_module_id=None,
                messages=(
                    (
                        "Redirect responses should declare both a 3xx status "
                        "and "
                        "Location header."
                    ),
                    (
                        f"Node {node.node_id} has partial redirect response "
                        f"evidence; "
                        "raw redirect target text is redacted."
                    ),
                ),
            )
            for contract_path in _partial_redirect_response_contract_paths(node)
        )
        findings.extend(
            build_validation_finding(
                code=REDIRECT_DYNAMIC_DESTINATION_CODE,
                severity="warning",
                node=(node.node_id, destination_path),
                catalog_module_id=None,
                messages=(
                    (
                        "Redirect responses should keep the destination host "
                        "static "
                        "or allowlisted."
                    ),
                    (
                        f"Node {node.node_id} has a redirect destination "
                        f"with dynamic "
                        "scheme or host evidence; raw redirect URL text is "
                        "redacted."
                    ),
                ),
            )
            for destination_path in _dynamic_redirect_destination_paths(node)
        )
    return tuple(findings)


def _redirect_response_node(node: MakeAstNode) -> bool:
    """Return whether one node can carry redirect response configuration."""
    token_key = module_token_semantic_key(node.module_token)
    return (
        node.kind == "webhook"
        or module_looks_like_webhook_response(node.module_token)
        or any(token in token_key for token in REDIRECT_MODULE_TOKENS)
    )


def _dynamic_redirect_destination_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return redirect destination paths with dynamic host evidence."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in _redirect_configuration_container_keys(node):
        container = node.raw_payload.get(container_key)
        if container is None:
            continue
        paths.extend(
            _json_dynamic_redirect_destination_paths(
                container,
                path=(*node.source_trace.path, container_key),
                redirect_context=_redirect_context(container),
            )
        )
    return tuple(paths)


def _partial_redirect_response_contract_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return the computed result for the caller."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in _redirect_configuration_container_keys(node):
        container = node.raw_payload.get(container_key)
        if container is None:
            continue
        if not _redirect_contract_context(container):
            continue
        if _has_redirect_status_deep(container) and _has_location_header(
            container
        ):
            continue
        paths.append((*node.source_trace.path, container_key))
    return tuple(paths)


def _redirect_configuration_container_keys(
    node: MakeAstNode,
) -> tuple[str, ...]:
    """Return the computed result for the caller."""
    token_key = module_token_semantic_key(node.module_token)
    if module_looks_like_webhook_response(node.module_token) or any(
        token in token_key for token in REDIRECT_MODULE_TOKENS
    ):
        return REDIRECT_CONFIGURATION_CONTAINER_KEYS
    return ("response", "respond")


def _json_dynamic_redirect_destination_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    redirect_context: bool,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return the computed result for the caller."""
    if _is_json_object(value):
        header_path = _location_header_dynamic_destination_path(
            value, path=path
        )
        if header_path is not None:
            return (header_path,)

        object_redirect_context = redirect_context or _redirect_context(value)
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            item_path = (*path, key)
            if (
                isinstance(item, str)
                and _redirect_destination_key(key)
                and _dynamic_destination_host(item)
                and object_redirect_context
            ):
                object_paths.append(item_path)
                continue
            object_paths.extend(
                _json_dynamic_redirect_destination_paths(
                    item,
                    path=item_path,
                    redirect_context=object_redirect_context,
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_dynamic_redirect_destination_paths(
                    item,
                    path=(*path, index),
                    redirect_context=redirect_context,
                )
            )
        return tuple(list_paths)
    return ()


def _location_header_dynamic_destination_path(
    value: JsonObject,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[AstPathPart, ...] | None:
    """Return a Location header value path with dynamic host evidence, if.

    present.
    """
    header_name = _header_name(value)
    header_value_path = _header_value_path(value)
    if (
        header_name == LOCATION_HEADER_NAME
        and header_value_path is not None
        and _dynamic_destination_host(cast("str", value[header_value_path[-1]]))
    ):
        return (*path, *header_value_path)
    return None


def _header_name(value: JsonObject) -> str | None:
    """Return a normalized header name from a Make header object."""
    for key, item in value.items():
        if module_token_semantic_key(key) in HEADER_NAME_TOKENS and isinstance(
            item, str
        ):
            return module_token_semantic_key(item)
    return None


def _header_value_path(value: JsonObject) -> tuple[str, ...] | None:
    """Return a header value key path when the value is text."""
    for key, item in value.items():
        if module_token_semantic_key(key) in HEADER_VALUE_TOKENS and isinstance(
            item, str
        ):
            return (key,)
    return None


def _redirect_context(value: object) -> bool:
    """Return whether one JSON object describes redirect response behavior."""
    if not _is_json_object(value):
        return False
    return _has_redirect_status(value) or _has_redirect_destination_value(value)


def _redirect_contract_context(value: object) -> bool:
    """Return if JSON-like data carries partial redirect response evidence."""
    return (
        _has_redirect_status_deep(value)
        or _has_location_header(value)
        or _has_redirect_destination_value(value)
    )


def _has_redirect_status(value: JsonObject) -> bool:
    """Return whether a JSON object declares a 3xx response status."""
    for key, item in value.items():
        if module_token_semantic_key(key) not in STATUS_KEY_TOKENS:
            continue
        if isinstance(item, int):
            return REDIRECT_STATUS_MIN <= item <= REDIRECT_STATUS_MAX
        if isinstance(item, str) and item.strip().isdigit():
            status_code = int(item.strip())
            return REDIRECT_STATUS_MIN <= status_code <= REDIRECT_STATUS_MAX
    return False


def _has_redirect_status_deep(value: object) -> bool:
    """Return whether JSON-like data declares a 3xx response status."""
    if _is_json_object(value):
        return _has_redirect_status(value) or any(
            _has_redirect_status_deep(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(
            _has_redirect_status_deep(item)
            for item in cast("list[object]", value)
        )
    return False


def _has_location_header(value: object) -> bool:
    """Return whether JSON-like data declares a Location response header."""
    if _is_json_object(value):
        if any(
            module_token_semantic_key(key) == LOCATION_HEADER_NAME
            and isinstance(item, str)
            and bool(item.strip())
            for key, item in value.items()
        ):
            return True
        if (
            _header_name(value) == LOCATION_HEADER_NAME
            and _header_value_path(value) is not None
        ):
            return True
        return any(_has_location_header(item) for item in value.values())
    if isinstance(value, list):
        return any(
            _has_location_header(item) for item in cast("list[object]", value)
        )
    return False


def _has_redirect_destination_value(value: object) -> bool:
    """Return if JSON-like data declares a concrete redirect destination."""
    if _is_json_object(value):
        for key, item in value.items():
            if _redirect_destination_key(key) and _redirect_destination_value(
                item
            ):
                return True
        return any(
            _has_redirect_destination_value(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(
            _has_redirect_destination_value(item)
            for item in cast("list[object]", value)
        )
    return False


def _redirect_destination_value(value: object) -> bool:
    """Return the computed result for the caller."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(
            _redirect_destination_value(item)
            for item in cast("list[object]", value)
        )
    return _is_json_object(value) and bool(value)


def _redirect_destination_key(key: str) -> bool:
    """Return whether a field name denotes a redirect destination."""
    return module_token_semantic_key(key) in REDIRECT_DESTINATION_KEY_TOKENS


def _dynamic_destination_host(url: str) -> bool:
    """Return whether a redirect URL has a dynamic scheme or authority."""
    if not _contains_make_mapping(url):
        return False
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc or parts.hostname is None:
        return True
    scheme_and_authority = f"{parts.scheme}://{parts.netloc}"
    return _contains_make_mapping(scheme_and_authority)


def _contains_make_mapping(value: str) -> bool:
    """Return whether a string contains Make expression mapping markers."""
    return any(marker in value for marker in MAKE_MAPPING_MARKERS)


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a JSON object."""
    return isinstance(value, dict)
