# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic cryptographic algorithm hazards in Make blueprints.

Boundary contract:
- Owns: local weak-hash warnings and JWT none-algorithm errors for
security-scoped
  blueprint fields.
- Must not: perform cryptographic verification, rate algorithms, infer expected
JWT
  algorithms, or call services.
- Allows: deterministic scans over AST node configuration and redacted findings.
- Split when: provider-specific cryptographic policy or profiles need richer
state.
- Merge when: another validation slice owns the same security hash predicates.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.ast.module_roles import module_token_semantic_key
from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

CRYPTO_WEAK_SECURITY_HASH_CODE: Final = "crypto.weak_security_hash"
CRYPTO_JWT_NONE_ALGORITHM_CODE: Final = "crypto.jwt_none_algorithm"
CRYPTO_SCAN_CONTAINER_KEYS: Final[tuple[str, ...]] = (
    "parameters ",
    "mapper ",
    "response",
)
JWT_CONTEXT_TOKENS: Final[frozenset[str]] = frozenset(
    ("jsonwebtoken", "jws", "jwt")
)
JWT_ALGORITHM_FIELD_TOKENS: Final[frozenset[str]] = frozenset(("alg", "algs"))
JWT_NONE_ALGORITHM_KEYS: Final[frozenset[str]] = frozenset(
    ("none", "algnone", "jwtalgnone")
)
SECURITY_HASH_CONTEXT_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "algorithm ",
        "auth ",
        "authentication ",
        "checksum ",
        "digest ",
        "hash ",
        "hmac ",
        "integrity ",
        "sign ",
        "signature ",
        "token ",
        "verify ",
        "verification ",
        "webhooksecret ",
        "xsignature",
    )
)
WEAK_SECURITY_HASH_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bmd5\b", re.IGNORECASE),
    re.compile(r"\bsha[-_ ]?1\b", re.IGNORECASE),
)


def validate_crypto_security(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic cryptographic security findings."""
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        findings.extend(
            (
                build_validation_finding(
                    code=CRYPTO_WEAK_SECURITY_HASH_CODE,
                    severity="warning",
                    node=(node.node_id, weak_hash_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Security hash settings should use SHA-256 or "
                            "stronger "
                            "where possible."
                        ),
                        (
                            f"Node {node.node_id} declares a weak hash "
                            f"algorithm in "
                            "security-scoped configuration; raw values are "
                            "redacted."
                        ),
                    ),
                )
            )
            for weak_hash_path in _weak_security_hash_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=CRYPTO_JWT_NONE_ALGORITHM_CODE,
                    severity="error",
                    node=(node.node_id, none_algorithm_path),
                    catalog_module_id=None,
                    messages=(
                        "JWT validation must not allow the none algorithm.",
                        (
                            f"Node {node.node_id} declares JWT none-algorithm "
                            "acceptance; raw values are redacted."
                        ),
                    ),
                )
            )
            for none_algorithm_path in _jwt_none_algorithm_paths(node)
        )
    return tuple(findings)


def _jwt_none_algorithm_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JWT validation configuration paths that allow alg none."""
    paths: list[tuple[AstPathPart, ...]] = []
    node_jwt_context = _node_has_jwt_context(node)
    for container_key in CRYPTO_SCAN_CONTAINER_KEYS:
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_jwt_none_algorithm_paths(
                value,
                path=(*node.source_trace.path, container_key),
                jwt_context=node_jwt_context,
                algorithm_context=False,
            )
        )
    return tuple(paths)


def _json_jwt_none_algorithm_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
    jwt_context: bool,
    algorithm_context: bool,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where JWT algorithm fields statically allow none."""
    if isinstance(value, str):
        if jwt_context and algorithm_context and _jwt_none_algorithm(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        object_jwt_context = (
            jwt_context
            or _path_has_jwt_context(path)
            or any(_key_is_jwt_context(key) for key in value)
        )
        for key, item in value.items():
            object_paths.extend(
                _json_jwt_none_algorithm_paths(
                    item,
                    path=(*path, key),
                    jwt_context=object_jwt_context,
                    algorithm_context=algorithm_context
                    or _key_is_jwt_algorithm_field(key),
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_jwt_none_algorithm_paths(
                    item,
                    path=(*path, index),
                    jwt_context=jwt_context,
                    algorithm_context=algorithm_context,
                )
            )
        return tuple(list_paths)
    return ()


def _weak_security_hash_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return security-scoped configuration paths containing weak hash names."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in CRYPTO_SCAN_CONTAINER_KEYS:
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_weak_security_hash_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _json_weak_security_hash_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where security-scoped weak hash strings appear."""
    if isinstance(value, str):
        if _path_is_security_hash_context(path) and _weak_hash_algorithm(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_weak_security_hash_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_weak_security_hash_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _path_is_security_hash_context(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path is security or integrity hash scoped."""
    for part in path:
        if not isinstance(part, str):
            continue
        normalized = module_token_semantic_key(part)
        if any(token in normalized for token in SECURITY_HASH_CONTEXT_TOKENS):
            return True
    return False


def _node_has_jwt_context(node: MakeAstNode) -> bool:
    """Return if one node token or label explicitly names JWT/JWS handling."""
    context_values = (
        node.module_token,
        node.label,
        node.raw_spec_binding.catalog_module_id or "",
    )
    return any(_text_has_jwt_context(value) for value in context_values)


def _path_has_jwt_context(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one path explicitly names JWT/JWS handling."""
    return any(
        isinstance(part, str) and _text_has_jwt_context(part) for part in path
    )


def _key_is_jwt_context(key: str) -> bool:
    """Return whether one JSON key provides JWT/JWS sibling context."""
    return _text_has_jwt_context(key)


def _key_is_jwt_algorithm_field(key: str) -> bool:
    """Return whether one JSON key is a JWT algorithm selector."""
    normalized = module_token_semantic_key(key)
    return (
        normalized in JWT_ALGORITHM_FIELD_TOKENS
        or "algorithm" in normalized
        or normalized.endswith(("alg", "algs"))
    )


def _text_has_jwt_context(value: str) -> bool:
    """Return whether normalized text explicitly names JWT or JWS material."""
    normalized = module_token_semantic_key(value)
    return any(token in normalized for token in JWT_CONTEXT_TOKENS)


def _jwt_none_algorithm(value: str) -> bool:
    """Return whether a static JWT algorithm value declares none."""
    if "{{" in value or "}}" in value:
        return False
    return module_token_semantic_key(value) in JWT_NONE_ALGORITHM_KEYS


def _weak_hash_algorithm(value: str) -> bool:
    """Return whether a string names MD5 or SHA-1."""
    return any(pattern.search(value) for pattern in WEAK_SECURITY_HASH_PATTERNS)


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
