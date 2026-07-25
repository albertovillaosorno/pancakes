# ruff: noqa: S105
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001075#repo.client-blueprint-intake.shape-secret-identifier-gates
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic personal-data exposure hazards in Make blueprints.

Boundary contract:
- Owns: local unsafe-sink checks for static personal identifier literals.
- Must not: classify real customer data, perform flow analysis, or call
services.
- Allows: deterministic scans over AST node configuration and redacted findings.
- Split when: regulated-data classification or allowlist policy needs richer
state.
- Merge when: another validation slice owns the same unsafe-sink predicates.
"""

from __future__ import annotations

import re
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_network,
)
from typing import TYPE_CHECKING, Final, TypeGuard, cast
from urllib.parse import urlsplit

from blueprints.ast.module_roles import (
    module_looks_like_webhook_response,
    module_token_semantic_key,
)
from blueprints.validation.expression_templates import (
    MakeExpressionTemplateParseError,
    iter_make_expression_templates,
)
from blueprints.validation.findings import build_validation_finding
from blueprints.validation.network_hosts import host_ip_candidates

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

DATA_EXPOSURE_STATIC_PERSONAL_LITERAL_CODE: Final = (
    "data_exposure.static_personal_literal"
)
DATA_EXPOSURE_RAW_PAYLOAD_SINK_CODE: Final = "data_exposure.raw_payload_sink"
DATA_EXPOSURE_SECRET_OUTPUT_SINK_CODE: Final = (
    "data_exposure.secret_output_sink"
)
DATA_EXPOSURE_INTERNAL_URL_LITERAL_CODE: Final = (
    "data_exposure.internal_url_literal"
)
DATA_EXPOSURE_RAW_ERROR_OUTPUT_CODE: Final = "data_exposure.raw_error_output"
DATA_EXPOSURE_PAGINATION_TOKEN_OUTPUT_CODE: Final = (
    "data_exposure.pagination_token_output"
)
DATA_EXPOSURE_SENSITIVE_HTTP_RESPONSE_SINK_CODE: Final = (
    "data_exposure.sensitive_http_response_sink"
)
PERSONAL_DATA_CONTAINER_KEYS: Final[tuple[str, ...]] = (
    "parameters ",
    "mapper ",
    "response",
)
WEBHOOK_RESPONSE_CONTAINER_KEYS: Final[tuple[str, ...]] = (
    "parameters ",
    "mapper ",
    "response ",
    "respond",
)
UNSAFE_SINK_MODULE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "airtable ",
        "discord ",
        "email ",
        "gmail ",
        "googlesheet ",
        "googlesheets ",
        "http ",
        "llm ",
        "mail ",
        "openai ",
        "slack ",
        "telegram ",
        "variable ",
        "variables ",
        "webhookrespond ",
        "webhookresponse ",
        "webhooksrespond ",
        "webhooksresponse",
    )
)
RAW_PAYLOAD_UNSAFE_SINK_MODULE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        *UNSAFE_SINK_MODULE_TOKENS,
        "datastore ",
        "debug ",
        "logger ",
        "logging ",
        "note ",
        "notes ",
        "variable ",
        "variables",
    )
)
SECRET_OUTPUT_UNSAFE_SINK_MODULE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "airtable ",
        "datastore ",
        "debug ",
        "discord ",
        "email ",
        "gmail ",
        "googlesheet ",
        "googlesheets ",
        "logger ",
        "logging ",
        "llm ",
        "mail ",
        "note ",
        "notes ",
        "openai ",
        "slack ",
        "telegram ",
        "variable ",
        "variables ",
        "webhookrespond ",
        "webhookresponse ",
        "webhooksrespond ",
        "webhooksresponse",
    )
)
INTERNAL_URL_UNSAFE_SINK_MODULE_TOKENS: Final[frozenset[str]] = frozenset(
    (*SECRET_OUTPUT_UNSAFE_SINK_MODULE_TOKENS,)
)
PERSONAL_DATA_CONTENT_PATH_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "body ",
        "caption ",
        "comment ",
        "content ",
        "description ",
        "html ",
        "label ",
        "markdown ",
        "message ",
        "messages ",
        "note ",
        "notes ",
        "prompt ",
        "prompts ",
        "response ",
        "summary ",
        "text ",
        "title",
    )
)
RAW_PAYLOAD_CONTENT_PATH_TOKENS: Final[frozenset[str]] = frozenset(
    (
        *PERSONAL_DATA_CONTENT_PATH_TOKENS,
        "data ",
        "field ",
        "fields ",
        "payload ",
        "record ",
        "row ",
        "value ",
        "values",
    )
)
SECRET_OUTPUT_CONTENT_PATH_TOKENS: Final[frozenset[str]] = frozenset(
    (
        *RAW_PAYLOAD_CONTENT_PATH_TOKENS,
        "cell ",
        "cells ",
        "error ",
        "errors ",
        "tool ",
        "tools",
    )
)
INTERNAL_URL_CONTENT_PATH_TOKENS: Final[frozenset[str]] = frozenset(
    (
        *SECRET_OUTPUT_CONTENT_PATH_TOKENS,
        "link ",
        "links",
    )
)
RAW_ERROR_OUTPUT_PATH_TOKENS: Final[frozenset[str]] = frozenset(
    (
        *SECRET_OUTPUT_CONTENT_PATH_TOKENS,
        "body ",
        "content ",
        "error ",
        "errors ",
        "json",
    )
)
PAGINATION_TOKEN_OUTPUT_PATH_TOKENS: Final[frozenset[str]] = (
    RAW_ERROR_OUTPUT_PATH_TOKENS
)
SECRET_SOURCE_FIELD_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "accesskey ",
        "accesstoken ",
        "apikey ",
        "authorization ",
        "authtoken ",
        "bearer ",
        "clientsecret ",
        "cookie ",
        "password ",
        "privatekey ",
        "refreshtoken ",
        "resettoken ",
        "secret ",
        "sessionid ",
        "signature ",
        "token ",
        "xapikey",
    )
)
RAW_ERROR_DETAIL_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "body ",
        "data ",
        "detail ",
        "details ",
        "message ",
        "messages ",
        "raw ",
        "response ",
        "stack ",
        "stacktrace ",
        "trace ",
        "traceback",
    )
)
RAW_ERROR_DIRECT_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "errorbody ",
        "errordata ",
        "errormessage ",
        "errorresponse ",
        "errors ",
        "exception ",
        "providererror ",
        "rawerror ",
        "stack ",
        "stacktrace ",
        "traceback",
    )
)
PAGINATION_TOKEN_DIRECT_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "continuationtoken ",
        "cursor ",
        "cursors ",
        "nextcursor ",
        "nextpagetoken ",
        "pagecursor ",
        "pagetoken ",
        "paginationcursor ",
        "paginationtoken ",
        "scrollid ",
        "searchafter",
    )
)
SECRET_SOURCE_FALSE_POSITIVE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "tokencount ",
        "tokenlimit ",
        "tokensused ",
        "tokenusage",
    )
)
SENSITIVE_HTTP_RESPONSE_FIELD_TOKENS: Final[frozenset[str]] = frozenset(
    (
        *SECRET_SOURCE_FIELD_TOKENS,
        "accountnumber ",
        "address ",
        "birthdate ",
        "cardnumber ",
        "dob ",
        "email ",
        "emailaddress ",
        "phone ",
        "phonenumber ",
        "ssn",
    )
)
HTTP_RESPONSE_OUTPUT_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "body ",
        "content ",
        "data ",
        "headers ",
        "json ",
        "response ",
        "responsebody",
    )
)
SENSITIVE_HTTP_RESPONSE_REDACTION_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "classify ",
        "classified ",
        "filterpii ",
        "hash ",
        "hashed ",
        "mask ",
        "masked ",
        "redact ",
        "redacted ",
        "sanitize ",
        "sanitized",
    )
)
EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
PHONE_LIKE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w])(?:\+?\d[\d .()/-]{8,}\d)(?![\w])"
)
WHOLE_PAYLOAD_REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    (?:
        \d+
        (?:
            \s*
            |
            \s* [.] \s*
            (?:body|bundle|data|headers?|payload|rawBody|raw_body|rawPayload|raw_payload|request)
            \s*
            |
            \s* \[\s* ["']
            (?:body|bundle|data|headers?|payload|rawBody|raw_body|rawPayload|raw_payload|request)
            ["'] \s* \]
            \s*
        )
        |
        (?:body|bundle|data|headers?|payload|rawBody|raw_body|rawPayload|raw_payload|request)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)
WHOLE_PAYLOAD_WRAPPER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?P<function>dump|json|stringify|toJSON|toJson)\s*\((?P<argument>.*)\)",
    re.IGNORECASE,
)
MAKE_SOURCE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9_])(?P<node_id>\d+)(?=\s*(?:[.\[]|$))"
)
SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
STATIC_URL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bhttps?://[^\s<>'\"`]+",
    re.IGNORECASE,
)
STACK_TRACE_LITERAL_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE),
    re.compile(r"\bat\s+[\w.$<>]+\([^)]*:\d+\)", re.IGNORECASE),
)
INTERNAL_HOST_NAMES: Final[frozenset[str]] = frozenset(
    (
        "localhost ",
        "metadata.google.internal",
    )
)
INTERNAL_HOST_SUFFIXES: Final[tuple[str, ...]] = (
    ".cluster.local",
    ".internal",
    ".local",
    ".svc",
)
INTERNAL_IP_NETWORKS: Final[tuple[IPv4Network | IPv6Network, ...]] = (
    ip_network("10.0.0.0/8"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("::/128"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
    ip_network("fe80::/10"),
)
MIN_PHONE_DIGITS: Final = 10


def validate_data_exposure_security(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic personal-data exposure findings for unsafe sink.

    nodes.
    """
    findings: list[BlueprintValidationFinding] = []
    http_node_ids = _http_request_node_ids(nodes)
    for node in nodes:
        if _unsafe_sink_node(node):
            findings.extend(
                (
                    build_validation_finding(
                        code=DATA_EXPOSURE_STATIC_PERSONAL_LITERAL_CODE,
                        severity="warning",
                        node=(node.node_id, exposed_path),
                        catalog_module_id=None,
                        messages=(
                            (
                                "An unsafe sink contains static personal "
                                "identifier "
                                "text."
                            ),
                            (
                                f"Node {node.node_id} maps static personal "
                                f"identifier text "
                                "into an unsafe sink field; raw values are "
                                "redacted."
                            ),
                        ),
                    )
                )
                for exposed_path in _static_personal_literal_paths(node)
            )
            findings.extend(
                (
                    build_validation_finding(
                        code=DATA_EXPOSURE_SENSITIVE_HTTP_RESPONSE_SINK_CODE,
                        severity="warning",
                        node=(node.node_id, exposed_path),
                        catalog_module_id=None,
                        messages=(
                            (
                                "An unsafe sink maps sensitive-looking HTTP "
                                "response data."
                            ),
                            (
                                f"Node {node.node_id} maps sensitive HTTP "
                                f"response evidence "
                                "into an unsafe sink without visible "
                                "redaction; "
                                "raw mapping "
                                "text is redacted."
                            ),
                        ),
                    )
                )
                for exposed_path in _sensitive_http_response_sink_paths(
                    node,
                    http_node_ids=http_node_ids,
                )
            )
        if _raw_payload_unsafe_sink_node(node):
            findings.extend(
                (
                    build_validation_finding(
                        code=DATA_EXPOSURE_RAW_PAYLOAD_SINK_CODE,
                        severity="warning",
                        node=(node.node_id, exposed_path),
                        catalog_module_id=None,
                        messages=(
                            (
                                "An unsafe sink maps a whole inbound payload "
                                "value."
                            ),
                            (
                                f"Node {node.node_id} maps whole "
                                f"payload-like data into "
                                "an unsafe sink field; raw mapping text is "
                                "redacted."
                            ),
                        ),
                    )
                )
                for exposed_path in _raw_payload_sink_paths(node)
            )
        if _secret_output_unsafe_sink_node(node):
            findings.extend(
                (
                    build_validation_finding(
                        code=DATA_EXPOSURE_SECRET_OUTPUT_SINK_CODE,
                        severity="warning",
                        node=(node.node_id, exposed_path),
                        catalog_module_id=None,
                        messages=(
                            "An unsafe sink maps a secret-like value.",
                            (
                                f"Node {node.node_id} maps secret-like data "
                                f"into "
                                "an unsafe output field; raw mapping text is "
                                "redacted."
                            ),
                        ),
                    )
                )
                for exposed_path in _secret_output_sink_paths(node)
            )
        if _internal_url_unsafe_sink_node(node):
            findings.extend(
                (
                    build_validation_finding(
                        code=DATA_EXPOSURE_INTERNAL_URL_LITERAL_CODE,
                        severity="warning",
                        node=(node.node_id, exposed_path),
                        catalog_module_id=None,
                        messages=(
                            "An unsafe sink exposes an internal URL literal.",
                            (
                                f"Node {node.node_id} exposes internal URL "
                                f"evidence "
                                "through an unsafe output field; raw URL text "
                                "is redacted."
                            ),
                        ),
                    )
                )
                for exposed_path in _internal_url_literal_paths(node)
            )
        if _raw_error_output_node(node):
            findings.extend(
                (
                    build_validation_finding(
                        code=DATA_EXPOSURE_RAW_ERROR_OUTPUT_CODE,
                        severity="warning",
                        node=(node.node_id, exposed_path),
                        catalog_module_id=None,
                        messages=(
                            "A webhook response maps raw error-like output.",
                            (
                                f"Node {node.node_id} exposes raw error or "
                                f"stack-like "
                                "evidence through a response field; raw "
                                "mapping "
                                "text is "
                                "redacted."
                            ),
                        ),
                    )
                )
                for exposed_path in _raw_error_output_paths(node)
            )
        if _pagination_token_output_node(node):
            findings.extend(
                (
                    build_validation_finding(
                        code=DATA_EXPOSURE_PAGINATION_TOKEN_OUTPUT_CODE,
                        severity="warning",
                        node=(node.node_id, exposed_path),
                        catalog_module_id=None,
                        messages=(
                            (
                                "A webhook response maps pagination token-like "
                                "output."
                            ),
                            (
                                f"Node {node.node_id} exposes cursor or "
                                f"pagination "
                                "token evidence through a response field; raw "
                                "mapping "
                                "text is redacted."
                            ),
                        ),
                    )
                )
                for exposed_path in _pagination_token_output_paths(node)
            )
    return tuple(findings)


def _unsafe_sink_node(node: MakeAstNode) -> bool:
    """Return whether one node writes to a potentially unsafe external sink."""
    token_key = module_token_semantic_key(node.module_token)
    if node.kind in {"ai_agent", "http_api", "scenario_output"}:
        return True
    if module_looks_like_webhook_response(node.module_token):
        return True
    return any(token in token_key for token in UNSAFE_SINK_MODULE_TOKENS)


def _http_request_node_ids(nodes: tuple[MakeAstNode, ...]) -> frozenset[str]:
    """Return node IDs for HTTP request-like modules."""
    return frozenset(node.node_id for node in nodes if _http_request_node(node))


def _http_request_node(node: MakeAstNode) -> bool:
    """Return whether one node is an HTTP request module."""
    token_key = module_token_semantic_key(node.module_token)
    return (
        node.kind == "http_api"
        or "makerequest" in token_key
        or token_key.startswith("http")
    )


def _raw_payload_unsafe_sink_node(node: MakeAstNode) -> bool:
    """Return whether one node may expose raw payload mappings."""
    token_key = module_token_semantic_key(node.module_token)
    if node.kind in {"ai_agent", "data_store", "http_api", "scenario_output"}:
        return True
    if module_looks_like_webhook_response(node.module_token):
        return True
    return any(
        token in token_key for token in RAW_PAYLOAD_UNSAFE_SINK_MODULE_TOKENS
    )


def _secret_output_unsafe_sink_node(node: MakeAstNode) -> bool:
    """Return if one node may expose secret-like values to visible outputs."""
    token_key = module_token_semantic_key(node.module_token)
    if node.kind in {"ai_agent", "data_store", "scenario_output"}:
        return True
    if module_looks_like_webhook_response(node.module_token):
        return True
    return any(
        token in token_key for token in SECRET_OUTPUT_UNSAFE_SINK_MODULE_TOKENS
    )


def _internal_url_unsafe_sink_node(node: MakeAstNode) -> bool:
    """Return whether one node may expose internal URLs to visible outputs."""
    token_key = module_token_semantic_key(node.module_token)
    if node.kind in {"ai_agent", "data_store", "scenario_output"}:
        return True
    if module_looks_like_webhook_response(node.module_token):
        return True
    return any(
        token in token_key for token in INTERNAL_URL_UNSAFE_SINK_MODULE_TOKENS
    )


def _raw_error_output_node(node: MakeAstNode) -> bool:
    """Return whether one node may expose public webhook response content."""
    return node.kind == "webhook" or module_looks_like_webhook_response(
        node.module_token
    )


def _pagination_token_output_node(node: MakeAstNode) -> bool:
    """Return whether one node may expose public webhook response content."""
    return _raw_error_output_node(node)


def _static_personal_literal_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return sink configuration paths containing static personal identifier.

    literals.
    """
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in PERSONAL_DATA_CONTAINER_KEYS:
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_static_personal_literal_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _raw_payload_sink_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return sink paths that map whole payload-like values."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in PERSONAL_DATA_CONTAINER_KEYS:
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_raw_payload_sink_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _secret_output_sink_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return sink paths that map or contain secret-like values."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in PERSONAL_DATA_CONTAINER_KEYS:
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_secret_output_sink_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _sensitive_http_response_sink_paths(
    node: MakeAstNode,
    *,
    http_node_ids: frozenset[str],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return sink paths that map sensitive-looking HTTP response fields."""
    if not http_node_ids:
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in PERSONAL_DATA_CONTAINER_KEYS:
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_sensitive_http_response_sink_paths(
                value,
                path=(*node.source_trace.path, container_key),
                http_node_ids=http_node_ids,
            )
        )
    return tuple(paths)


def _internal_url_literal_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return sink paths that contain static internal URL literals."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in PERSONAL_DATA_CONTAINER_KEYS:
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_internal_url_literal_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _raw_error_output_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return response paths that expose raw error-like evidence."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in _raw_error_output_container_keys(node):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_raw_error_output_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _pagination_token_output_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return response paths that expose pagination token-like evidence."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in _raw_error_output_container_keys(node):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_pagination_token_output_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _raw_error_output_container_keys(node: MakeAstNode) -> tuple[str, ...]:
    """Return response-bearing containers to scan for raw error output."""
    if module_looks_like_webhook_response(node.module_token):
        return WEBHOOK_RESPONSE_CONTAINER_KEYS
    return ("response", "respond")


def _json_static_personal_literal_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where static personal identifier literals appear."""
    if isinstance(value, str):
        if _path_is_personal_data_sink_field(path) and _static_personal_literal(
            value
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_static_personal_literal_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_static_personal_literal_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_raw_payload_sink_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where sink content maps whole payload-like values."""
    if isinstance(value, str):
        if _path_is_raw_payload_sink_field(path) and _maps_whole_payload(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_raw_payload_sink_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_raw_payload_sink_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_secret_output_sink_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where sink content exposes secret-like values."""
    if isinstance(value, str):
        if _path_is_secret_output_sink_field(path) and _secret_output_value(
            value
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_secret_output_sink_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_secret_output_sink_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_sensitive_http_response_sink_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    http_node_ids: frozenset[str],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where sink content exposes sensitive HTTP responses."""
    if isinstance(value, str):
        if _path_is_secret_output_sink_field(
            path
        ) and _maps_sensitive_http_response_field(
            value,
            http_node_ids=http_node_ids,
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_sensitive_http_response_sink_paths(
                    item,
                    path=(*path, key),
                    http_node_ids=http_node_ids,
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_sensitive_http_response_sink_paths(
                    item,
                    path=(*path, index),
                    http_node_ids=http_node_ids,
                )
            )
        return tuple(list_paths)
    return ()


def _json_internal_url_literal_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where sink content exposes static internal URLs."""
    if isinstance(value, str):
        if _path_is_internal_url_sink_field(
            path
        ) and _static_internal_url_literal(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_internal_url_literal_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_internal_url_literal_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_raw_error_output_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return the computed result for the caller."""
    if isinstance(value, str):
        if _path_is_raw_error_output_field(path) and _raw_error_output_value(
            value
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_raw_error_output_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_raw_error_output_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_pagination_token_output_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where webhook responses expose pagination token-like.

    output.
    """
    if isinstance(value, str):
        if _path_is_pagination_token_output_field(
            path
        ) and _pagination_token_output_value(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_pagination_token_output_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_pagination_token_output_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _path_is_personal_data_sink_field(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is a message/body/prompt-like sink field."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in PERSONAL_DATA_CONTENT_PATH_TOKENS
        for part in path
    )


def _path_is_raw_payload_sink_field(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is a content or record-like sink field."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in RAW_PAYLOAD_CONTENT_PATH_TOKENS
        for part in path
    )


def _path_is_secret_output_sink_field(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is a visible output or record sink field."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in SECRET_OUTPUT_CONTENT_PATH_TOKENS
        for part in path
    )


def _path_is_internal_url_sink_field(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is a visible output or link sink field."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in INTERNAL_URL_CONTENT_PATH_TOKENS
        for part in path
    )


def _path_is_raw_error_output_field(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is a webhook response output field."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in RAW_ERROR_OUTPUT_PATH_TOKENS
        for part in path
    )


def _path_is_pagination_token_output_field(
    path: tuple[AstPathPart, ...],
) -> bool:
    """Return whether one AST path is a webhook response output field."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part)
        in PAGINATION_TOKEN_OUTPUT_PATH_TOKENS
        for part in path
    )


def _static_personal_literal(value: str) -> bool:
    """Return whether a string contains static personal identifier text."""
    stripped = value.strip()
    if not stripped:
        return False
    return EMAIL_PATTERN.search(
        stripped
    ) is not None or _contains_phone_like_value(stripped)


def _secret_output_value(value: str) -> bool:
    """Return whether text contains static or mapped secret-like evidence."""
    stripped = value.strip()
    if not stripped:
        return False
    if any(
        pattern.search(stripped) is not None
        for pattern in SECRET_VALUE_PATTERNS
    ):
        return True
    return _maps_secret_like_source_field(stripped)


def _static_internal_url_literal(value: str) -> bool:
    """Return whether text contains a static internal URL literal."""
    return any(
        _internal_url_literal(match.group(0))
        for match in STATIC_URL_PATTERN.finditer(value)
    )


def _raw_error_output_value(value: str) -> bool:
    """Return whether text exposes raw error or stack-like evidence."""
    stripped = value.strip()
    if not stripped:
        return False
    if any(
        pattern.search(stripped) is not None
        for pattern in STACK_TRACE_LITERAL_PATTERNS
    ):
        return True
    return _maps_raw_error_source_field(stripped)


def _pagination_token_output_value(value: str) -> bool:
    """Return whether text exposes cursor or pagination token-like evidence."""
    stripped = value.strip()
    if not stripped:
        return False
    return _maps_pagination_token_source_field(stripped)


def _maps_whole_payload(value: str) -> bool:
    """Return whether text contains a mapping for a whole payload-like value."""
    return any(
        _whole_payload_expression(expression)
        for expression in _mapping_expression_bodies(value)
    )


def _maps_secret_like_source_field(value: str) -> bool:
    """Return whether text maps a source field whose name is secret-like."""
    return any(
        _secret_like_expression(expression)
        for expression in _mapping_expression_bodies(value)
    )


def _maps_sensitive_http_response_field(
    value: str,
    *,
    http_node_ids: frozenset[str],
) -> bool:
    """Return if text maps sensitive HTTP response data without redaction."""
    return any(
        _sensitive_http_response_expression(
            expression,
            http_node_ids=http_node_ids,
        )
        for expression in _mapping_expression_bodies(value)
    )


def _maps_raw_error_source_field(value: str) -> bool:
    """Return whether text maps a raw error-like source field."""
    return any(
        _raw_error_expression(expression)
        for expression in _mapping_expression_bodies(value)
    )


def _maps_pagination_token_source_field(value: str) -> bool:
    """Return whether text maps a pagination token-like source field."""
    return any(
        _pagination_token_expression(expression)
        for expression in _mapping_expression_bodies(value)
    )


def _mapping_expression_bodies(value: str) -> tuple[str, ...]:
    """Return parsed mapping bodies, or malformed body evidence for broken.

    delimiters.
    """
    if "{{" not in value and "}}" not in value:
        return ()
    try:
        return tuple(
            template.body.strip()
            for template in iter_make_expression_templates(value)
        )
    except MakeExpressionTemplateParseError:
        return _malformed_mapping_body_candidates(value)


def _malformed_mapping_body_candidates(value: str) -> tuple[str, ...]:
    """Return conservative body candidates from malformed Make mapping text."""
    open_index = value.find("{{")
    if open_index >= 0:
        tail = value[open_index + 2 :]
        close_index = tail.find("}}")
        candidate = tail[:close_index] if close_index >= 0 else tail
        stripped = candidate.strip()
        return (stripped,) if stripped else (value,)
    close_index = value.find("}}")
    if close_index >= 0:
        candidate = value[:close_index].strip()
        return (candidate,) if candidate else (value,)
    return (value,)


def _whole_payload_expression(expression: str) -> bool:
    """Return whether one expression body names a whole payload-like value."""
    if WHOLE_PAYLOAD_REFERENCE_PATTERN.fullmatch(expression):
        return True
    wrapper_match = WHOLE_PAYLOAD_WRAPPER_PATTERN.fullmatch(expression)
    if wrapper_match is None:
        return False
    argument = wrapper_match.group("argument").strip()
    return WHOLE_PAYLOAD_REFERENCE_PATTERN.fullmatch(argument) is not None


def _secret_like_expression(expression: str) -> bool:
    """Return whether one expression body names a secret-like source field."""
    normalized_expression = module_token_semantic_key(expression)
    if any(
        token in normalized_expression
        for token in SECRET_SOURCE_FALSE_POSITIVE_TOKENS
    ):
        return False
    return any(
        token in normalized_expression for token in SECRET_SOURCE_FIELD_TOKENS
    )


def _sensitive_http_response_expression(
    expression: str,
    *,
    http_node_ids: frozenset[str],
) -> bool:
    """Return if an expression maps sensitive fields from an HTTP response."""
    normalized_expression = module_token_semantic_key(expression)
    if any(
        token in normalized_expression
        for token in SENSITIVE_HTTP_RESPONSE_REDACTION_TOKENS
    ):
        return False
    if any(
        token in normalized_expression
        for token in SECRET_SOURCE_FALSE_POSITIVE_TOKENS
    ):
        return False
    if not _expression_references_node_id(expression, node_ids=http_node_ids):
        return False
    return any(
        token in normalized_expression for token in HTTP_RESPONSE_OUTPUT_TOKENS
    ) and any(
        token in normalized_expression
        for token in SENSITIVE_HTTP_RESPONSE_FIELD_TOKENS
    )


def _expression_references_node_id(
    expression: str, *, node_ids: frozenset[str]
) -> bool:
    """Return whether a Make expression references one of the given source node.

    IDs.
    """
    return any(
        match.group("node_id") in node_ids
        for match in MAKE_SOURCE_ID_PATTERN.finditer(expression)
    )


def _raw_error_expression(expression: str) -> bool:
    """Return whether one expression body references raw error-like output."""
    normalized_expression = module_token_semantic_key(expression)
    if any(token in normalized_expression for token in RAW_ERROR_DIRECT_TOKENS):
        return True
    tokens = tuple(
        module_token_semantic_key(match.group(0))
        for match in re.finditer(r"[A-Za-z][A-Za-z0-9_]*", expression)
    )
    if not tokens:
        return False
    if tokens[-1] == "error":
        return True
    return "error" in tokens and any(
        token in RAW_ERROR_DETAIL_TOKENS for token in tokens
    )


def _pagination_token_expression(expression: str) -> bool:
    """Return if one expression body references pagination token-like output."""
    normalized_expression = module_token_semantic_key(expression)
    return any(
        token in normalized_expression
        for token in PAGINATION_TOKEN_DIRECT_TOKENS
    )


def _internal_url_literal(value: str) -> bool:
    """Return whether one URL literal targets internal infrastructure."""
    if "{{" in value or "}}" in value:
        return False
    cleaned = value.rstrip(".,);]}")
    parts = urlsplit(cleaned)
    host = parts.hostname
    if host is None:
        return False
    return _internal_host_name(host)


def _internal_host_name(host: str) -> bool:
    """Return if one URL host is private, local, or infrastructure-scoped."""
    normalized = host.casefold().strip("[]").rstrip(".")
    if normalized in INTERNAL_HOST_NAMES or normalized.endswith(
        INTERNAL_HOST_SUFFIXES
    ):
        return True
    return any(_internal_ip(ip) for ip in host_ip_candidates(normalized))


def _internal_ip(ip: IPv4Address | IPv6Address) -> bool:
    """Return if one parsed address belongs to an internal network range."""
    return any(ip in network for network in INTERNAL_IP_NETWORKS)


def _contains_phone_like_value(value: str) -> bool:
    """Return whether a string contains a phone-like contact value."""
    for match in PHONE_LIKE_PATTERN.finditer(value):
        digits = "".join(
            character for character in match.group(0) if character.isdigit()
        )
        if len(digits) >= MIN_PHONE_DIGITS:
            return True
    return False


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
