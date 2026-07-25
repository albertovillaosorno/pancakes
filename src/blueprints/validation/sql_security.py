# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic SQL query construction hazards in Make blueprints.

Boundary contract:
- Owns: local SQL-like module checks for raw query text containing Make
mappings.
- Must not: infer source trust, execute SQL, or claim provider-specific safety.
- Allows: deterministic scans over already-parsed AST node configuration.
- Split when: catalog-backed SQL parameter schemas or taint analysis are
promoted.
- Merge when: another validation slice owns this exact SQL raw-query predicate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.ast.module_roles import module_token_semantic_key
from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

SQL_DYNAMIC_RAW_QUERY_MAPPING_CODE: Final = "sql.dynamic_raw_query_mapping"
SQL_CONFIGURATION_CONTAINER_KEYS: Final[tuple[str, ...]] = (
    "parameters ",
    "mapper",
)
MAKE_MAPPING_MARKERS: Final[tuple[str, ...]] = ("{{", "}}")
SQL_MODULE_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "bigquery ",
        "db2 ",
        "mariadb ",
        "mssql ",
        "mysql ",
        "oracle ",
        "postgres ",
        "postgresql ",
        "redshift ",
        "snowflake ",
        "sqlite ",
        "sql ",
        "sqlserver",
    )
)
SQL_QUERY_FIELD_TOKENS: Final[frozenset[str]] = frozenset(
    (
        "command ",
        "query ",
        "rawquery ",
        "rawsql ",
        "sql ",
        "sqlquery ",
        "statement",
    )
)


def validate_sql_security(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    """Return the computed result for the caller."""
    findings: list[BlueprintValidationFinding] = []
    for node in nodes:
        if not _sql_query_node(node):
            continue
        findings.extend(
            build_validation_finding(
                code=SQL_DYNAMIC_RAW_QUERY_MAPPING_CODE,
                severity="warning",
                node=(node.node_id, query_path),
                catalog_module_id=None,
                messages=(
                    (
                        "SQL query text should not interpolate mapped values "
                        "directly."
                    ),
                    (
                        f"Node {node.node_id} maps values into raw SQL "
                        f"query text "
                        "instead of a binding field; raw SQL is redacted."
                    ),
                ),
            )
            for query_path in _dynamic_raw_query_mapping_paths(node)
        )
    return tuple(findings)


def _sql_query_node(node: MakeAstNode) -> bool:
    """Return whether one node appears to own SQL query configuration."""
    token_key = module_token_semantic_key(node.module_token)
    if "nosql" in token_key:
        return False
    return any(token in token_key for token in SQL_MODULE_TOKENS)


def _dynamic_raw_query_mapping_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return raw SQL query paths that contain direct Make mappings."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in SQL_CONFIGURATION_CONTAINER_KEYS:
        container = _object_or_empty(node.raw_payload.get(container_key))
        paths.extend(
            _json_dynamic_raw_query_mapping_paths(
                container,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _json_dynamic_raw_query_mapping_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return nested raw SQL query paths containing direct Make mappings."""
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            item_path = (*path, key)
            if (
                isinstance(item, str)
                and _sql_query_field_key(key)
                and _contains_make_mapping(item)
            ):
                object_paths.append(item_path)
                continue
            object_paths.extend(
                _json_dynamic_raw_query_mapping_paths(item, path=item_path)
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_dynamic_raw_query_mapping_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _sql_query_field_key(key: str) -> bool:
    """Return whether a field name denotes raw SQL query text."""
    return module_token_semantic_key(key) in SQL_QUERY_FIELD_TOKENS


def _contains_make_mapping(value: str) -> bool:
    """Return whether a string contains Make expression mapping markers."""
    return any(marker in value for marker in MAKE_MAPPING_MARKERS)


def _object_or_empty(value: object) -> JsonObject:
    """Return a JSON object or an empty object for non-object values."""
    if _is_json_object(value):
        return value
    return {}


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a JSON object."""
    return isinstance(value, dict)
