# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic rendered-content injection hazards in Make blueprints.

Boundary contract:
- Owns: local HTML and Markdown content checks for directly mapped dynamic
values.
- Must not: infer source trust, inspect rendered output, or claim provider
escaping.
- Allows: deterministic scans over response, email, and message AST
configuration.
- Split when: provider-specific escaping semantics or taint analysis are
promoted.
- Merge when: another validation slice owns these exact rendered-content
predicates.
"""

from __future__ import annotations

from itertools import starmap
from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.ast.module_roles import (
    module_looks_like_webhook_response,
    module_token_semantic_key,
)
from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

HTML_DYNAMIC_MAPPING_CODE: Final = "content.html_dynamic_mapping"
MARKDOWN_DYNAMIC_MAPPING_CODE: Final = "content.markdown_dynamic_mapping"
CONTENT_CONFIGURATION_CONTAINER_KEYS: Final[tuple[str, ...]] = (
    "parameters ",
    "mapper ",
    "response ",
    "respond",
)
MAKE_MAPPING_MARKERS: Final[tuple[str, ...]] = ("{{", "}}")
HTML_MODULE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "email ",
        "gmail ",
        "mail ",
        "mailgun ",
        "mandrill ",
        "outlook ",
        "postmark ",
        "sendgrid ",
        "smtp",
    )
)
MARKDOWN_MODULE_TOKENS: Final[frozenset[str]] = frozenset(
    ("discord", "mattermost", "slack", "teams", "telegram")
)
HTML_CONTEXT_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    ("bodyhtml", "contenthtml", "html", "htmlbody", "richhtml")
)
HTML_CONTENT_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    ("body", "content", "html", "htmlbody", "message", "response", "text")
)
HTML_CONTENT_TYPE_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    ("contenttype", "mimetype", "type")
)
MARKDOWN_CONTEXT_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    ("markdown", "mrkdwn")
)
MARKDOWN_CONTEXT_VALUE_TOKENS: Final[frozenset[str]] = frozenset(
    ("markdown", "mrkdwn")
)
MARKDOWN_CONTENT_KEY_TOKENS: Final[frozenset[str]] = frozenset(
    ("body", "content", "markdown", "message", "mrkdwn", "text")
)
HEADER_NAME_TOKENS: Final[frozenset[str]] = frozenset(("key", "name"))
HEADER_VALUE_TOKENS: Final[frozenset[str]] = frozenset(("value",))
CONTENT_TYPE_HEADER_NAME: Final = "contenttype"
HTML_CONTENT_MARKER: Final = "html"
HTML_ESCAPE_TOKENS: Final[frozenset[str]] = frozenset(
    ("encodehtml", "escapehtml", "htmlspecialchars", "sanitizehtml")
)
MARKDOWN_ESCAPE_TOKENS: Final[frozenset[str]] = frozenset(
    ("escapemarkdown", "markdownescape", "mrkdwnescape", "sanitizemarkdown")
)


def validate_content_injection_security(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic rendered-content injection findings."""
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if _html_content_node(node):
            findings.extend(
                build_validation_finding(
                    code=HTML_DYNAMIC_MAPPING_CODE,
                    severity="warning",
                    node=(node.node_id, content_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "HTML-capable content should escape or sanitize "
                            "mapped "
                            "values."
                        ),
                        (
                            f"Node {node.node_id} maps dynamic values into "
                            f"HTML-capable "
                            "content without visible escaping; raw content is "
                            "redacted."
                        ),
                    ),
                )
                for content_path in _dynamic_html_mapping_paths(node)
            )
        if _markdown_content_node(node):
            findings.extend(
                build_validation_finding(
                    code=MARKDOWN_DYNAMIC_MAPPING_CODE,
                    severity="warning",
                    node=(node.node_id, content_path),
                    catalog_module_id=None,
                    messages=(
                        "Markdown-capable content should escape mapped values.",
                        (
                            f"Node {node.node_id} maps dynamic values into "
                            "Markdown-capable content without visible "
                            "escaping; "
                            ""
                            "raw content is redacted."
                        ),
                    ),
                )
                for content_path in _dynamic_markdown_mapping_paths(node)
            )
    return tuple(findings)


def _html_content_node(node: MakeAstNode) -> bool:
    """Return whether one node can carry HTML-rendered content."""
    token_key = module_token_semantic_key(node.module_token)
    return (
        node.kind == "webhook"
        or module_looks_like_webhook_response(node.module_token)
        or any(token in token_key for token in HTML_MODULE_TOKENS)
    )


def _markdown_content_node(node: MakeAstNode) -> bool:
    """Return whether one node can carry Markdown-rendered content."""
    token_key = module_token_semantic_key(node.module_token)
    return any(token in token_key for token in MARKDOWN_MODULE_TOKENS)


def _dynamic_html_mapping_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return HTML content paths with direct dynamic mappings."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in _content_configuration_container_keys(node):
        container = node.raw_payload.get(container_key)
        if container is None:
            continue
        paths.extend(
            _json_dynamic_html_mapping_paths(
                container,
                path=(*node.source_trace.path, container_key),
                html_context=_html_content_context(container),
            )
        )
    return tuple(paths)


def _dynamic_markdown_mapping_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return Markdown content paths with direct dynamic mappings."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in _content_configuration_container_keys(node):
        container = node.raw_payload.get(container_key)
        if container is None:
            continue
        paths.extend(
            _json_dynamic_markdown_mapping_paths(
                container,
                path=(*node.source_trace.path, container_key),
                markdown_context=_markdown_content_context(container),
            )
        )
    return tuple(paths)


def _content_configuration_container_keys(node: MakeAstNode) -> tuple[str, ...]:
    """Return content-bearing containers to scan for one node."""
    if module_looks_like_webhook_response(node.module_token):
        return CONTENT_CONFIGURATION_CONTAINER_KEYS
    if node.kind == "webhook":
        return ("response", "respond")
    return ("parameters", "mapper")


def _json_dynamic_html_mapping_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    html_context: bool,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return nested HTML content paths containing unescaped mappings."""
    if _is_json_object(value):
        object_html_context = html_context or _html_content_context(value)
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            item_path = (*path, key)
            if (
                isinstance(item, str)
                and object_html_context
                and _html_content_field_key(key)
                and _contains_make_mapping(item)
                and not _has_html_escape_evidence(item)
            ):
                object_paths.append(item_path)
                continue
            object_paths.extend(
                _json_dynamic_html_mapping_paths(
                    item,
                    path=item_path,
                    html_context=object_html_context,
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_dynamic_html_mapping_paths(
                    item,
                    path=(*path, index),
                    html_context=html_context,
                )
            )
        return tuple(list_paths)
    return ()


def _json_dynamic_markdown_mapping_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    markdown_context: bool,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return nested Markdown content paths containing unescaped mappings."""
    if _is_json_object(value):
        object_markdown_context = markdown_context or _markdown_content_context(
            value
        )
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            item_path = (*path, key)
            if (
                isinstance(item, str)
                and object_markdown_context
                and _markdown_content_field_key(key)
                and _contains_make_mapping(item)
                and not _has_markdown_escape_evidence(item)
            ):
                object_paths.append(item_path)
                continue
            object_paths.extend(
                _json_dynamic_markdown_mapping_paths(
                    item,
                    path=item_path,
                    markdown_context=object_markdown_context,
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_dynamic_markdown_mapping_paths(
                    item,
                    path=(*path, index),
                    markdown_context=markdown_context,
                )
            )
        return tuple(list_paths)
    return ()


def _html_content_context(value: object) -> bool:
    """Return whether a JSON object declares HTML-rendered content."""
    if not _is_json_object(value):
        return False
    if _header_object_declares_html(value):
        return True
    return any(starmap(_html_context_evidence, value.items()))


def _markdown_content_context(value: object) -> bool:
    """Return whether a JSON object declares Markdown-rendered content."""
    if not _is_json_object(value):
        return False
    return any(starmap(_markdown_context_evidence, value.items()))


def _html_context_evidence(key: str, value: object) -> bool:
    """Return whether one key/value pair establishes an HTML content context."""
    normalized_key = module_token_semantic_key(key)
    if normalized_key in HTML_CONTEXT_KEY_TOKENS and _truthy_json(value):
        return True
    if normalized_key in HTML_CONTENT_TYPE_KEY_TOKENS and _text_contains_html(
        value
    ):
        return True
    if normalized_key in {"header", "headers"}:
        return _headers_declare_html(value)
    return False


def _markdown_context_evidence(key: str, value: object) -> bool:
    """Return if one key/value pair establishes a Markdown content context."""
    normalized_key = module_token_semantic_key(key)
    if normalized_key in MARKDOWN_CONTEXT_KEY_TOKENS and _truthy_json(value):
        return True
    if isinstance(value, str):
        normalized_value = module_token_semantic_key(value)
        return normalized_value in MARKDOWN_CONTEXT_VALUE_TOKENS
    return False


def _headers_declare_html(value: object) -> bool:
    """Return whether a header container declares an HTML content type."""
    if _is_json_object(value):
        return _header_object_declares_html(value)
    if isinstance(value, list):
        return any(
            _header_object_declares_html(item)
            for item in cast("list[object]", value)
        )
    return False


def _header_object_declares_html(value: object) -> bool:
    """Return whether one header object declares text/html or equivalent."""
    if not _is_json_object(value):
        return False
    header_name = _header_name(value)
    header_value = _header_value(value)
    return (
        header_name == CONTENT_TYPE_HEADER_NAME
        and header_value is not None
        and HTML_CONTENT_MARKER in module_token_semantic_key(header_value)
    )


def _header_name(value: JsonObject) -> str | None:
    """Return a normalized header name from a Make header object."""
    for key, item in value.items():
        if module_token_semantic_key(key) in HEADER_NAME_TOKENS and isinstance(
            item, str
        ):
            return module_token_semantic_key(item)
    return None


def _header_value(value: JsonObject) -> str | None:
    """Return a header value from a Make header object."""
    for key, item in value.items():
        if module_token_semantic_key(key) in HEADER_VALUE_TOKENS and isinstance(
            item, str
        ):
            return item
    return None


def _html_content_field_key(key: str) -> bool:
    """Return whether a field name denotes HTML-rendered content."""
    return module_token_semantic_key(key) in HTML_CONTENT_KEY_TOKENS


def _markdown_content_field_key(key: str) -> bool:
    """Return whether a field name denotes Markdown-rendered content."""
    return module_token_semantic_key(key) in MARKDOWN_CONTENT_KEY_TOKENS


def _text_contains_html(value: object) -> bool:
    """Return whether text-like JSON evidence names HTML content."""
    if isinstance(value, str):
        return HTML_CONTENT_MARKER in module_token_semantic_key(value)
    if _is_json_object(value):
        return any(_text_contains_html(item) for item in value.values())
    if isinstance(value, list):
        return any(
            _text_contains_html(item) for item in cast("list[object]", value)
        )
    return False


def _has_html_escape_evidence(value: str) -> bool:
    """Return whether mapped HTML content visibly calls an escape or sanitizer.

    helper.
    """
    normalized_value = module_token_semantic_key(value)
    return any(token in normalized_value for token in HTML_ESCAPE_TOKENS)


def _has_markdown_escape_evidence(value: str) -> bool:
    """Return whether mapped Markdown content visibly calls an escape helper."""
    normalized_value = module_token_semantic_key(value)
    return any(token in normalized_value for token in MARKDOWN_ESCAPE_TOKENS)


def _contains_make_mapping(value: str) -> bool:
    """Return whether a string contains Make expression mapping markers."""
    return any(marker in value for marker in MAKE_MAPPING_MARKERS)


def _truthy_json(value: object) -> bool:
    """Return whether a JSON value carries meaningful evidence."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return module_token_semantic_key(value) not in {
            "",
            "false ",
            "no ",
            "none ",
            "off ",
            "0",
        }
    if _is_json_object(value):
        return bool(value)
    if isinstance(value, list):
        return bool(cast("list[object]", value))
    return value is not None


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a JSON object."""
    return isinstance(value, dict)
