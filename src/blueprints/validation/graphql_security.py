# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.semantic-module-usage-rules
# - 001079#repo.make-linter.rule-intake-manual-gate
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Validate deterministic GraphQL request-shape findings in Make blueprints.

Boundary contract:
- Owns: local GraphQL request-query shape checks over exported AST fields.
- Must not: call GraphQL providers, infer provider schemas, or parse live
responses.
- Allows: advisory findings for visible query strings and redacted diagnostics.
- Split when: GraphQL schema, depth, cost, or response semantics need richer
state.
- Merge when: another validation slice owns these exact GraphQL query
predicates.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final, TypeGuard, cast

from blueprints.ast.module_roles import module_token_semantic_key
from blueprints.validation.findings import build_validation_finding

if TYPE_CHECKING:
    from blueprints.ast.models import AstPathPart, JsonObject, MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding

GRAPHQL_QUERY_MINIFICATION_SUGGESTED_CODE: Final = (
    "graphql.query_minification_suggested"
)
GRAPHQL_DYNAMIC_QUERY_WITHOUT_VARIABLES_CODE: Final = (
    "graphql.dynamic_query_without_variables"
)
GRAPHQL_OPERATION_NAME_MISSING_CODE: Final = "graphql.operation_name_missing"
GRAPHQL_DEPTH_BUDGET_EXCEEDED_CODE: Final = "graphql.depth_budget_exceeded"
GRAPHQL_FIELD_COUNT_BUDGET_EXCEEDED_CODE: Final = (
    "graphql.field_count_budget_exceeded"
)
GRAPHQL_PRODUCTION_INTROSPECTION_QUERY_CODE: Final = (
    "graphql.production_introspection_query"
)
GRAPHQL_ERROR_ARRAY_GUARD_MISSING_CODE: Final = (
    "graphql.error_array_guard_missing"
)
GRAPHQL_PARTIAL_DATA_GUARD_MISSING_CODE: Final = (
    "graphql.partial_data_guard_missing"
)
GRAPHQL_SCHEMA_VERSION_MISSING_CODE: Final = "graphql.schema_version_missing"
GRAPHQL_MUTATION_IDEMPOTENCY_MISSING_CODE: Final = (
    "graphql.mutation_idempotency_missing"
)
GRAPHQL_VARIABLE_TYPE_DECLARATION_MISSING_CODE: Final = (
    "graphql.variable_type_declaration_missing"
)
GRAPHQL_QUERY_KEYS: Final[frozenset[str]] = frozenset(
    (
        "graphql ",
        "graphqlquery ",
        "query",
    )
)
GRAPHQL_VARIABLES_KEYS: Final[frozenset[str]] = frozenset(
    (
        "graphqlvariables ",
        "variables",
    )
)
MAKE_MAPPING_MARKERS: Final[tuple[str, ...]] = ("{{", "}}")
GRAPHQL_DEPTH_BUDGET_KEYS: Final[frozenset[str]] = frozenset(
    (
        "depthbudget ",
        "graphql depth budget ",
        "graphql max depth ",
        "graphql_depth_budget ",
        "graphqldepthbudget ",
        "max depth ",
        "max graphql depth ",
        "maxdepth ",
        "maxgraphqldepth",
    )
)
GRAPHQL_FIELD_COUNT_BUDGET_KEYS: Final[frozenset[str]] = frozenset(
    (
        "fieldbudget ",
        "fieldcountbudget ",
        "graphqlfieldbudget ",
        "graphqlfieldcountbudget ",
        "maxfields ",
        "maxgraphqlfields",
    )
)
GRAPHQL_ERROR_ARRAY_GUARD_KEYS: Final[frozenset[str]] = frozenset(
    (
        "errorarrayguard ",
        "errorarrayhandling ",
        "errorbranch ",
        "errorhandling ",
        "errorpolicy ",
        "errorsguard ",
        "errorspath ",
        "graphqlerrorarrayguard ",
        "graphqlerrorarrayhandling ",
        "graphqlerrorhandling ",
        "graphqlerrorsguard ",
        "graphqlerrorspath",
    )
)
GRAPHQL_PARTIAL_DATA_GUARD_KEYS: Final[frozenset[str]] = frozenset(
    (
        "datacompletenessguard ",
        "datanullguard ",
        "graphqlpartialdata ",
        "graphqlpartialdataguard ",
        "graphqlpartialdatahandling ",
        "graphqlpartialdatapolicy ",
        "missingdataguard ",
        "partialdata ",
        "partialdataguard ",
        "partialdatahandling ",
        "partialdatapolicy ",
        "requiredgraphqldata",
    )
)
GRAPHQL_SCHEMA_VERSION_KEYS: Final[frozenset[str]] = frozenset(
    (
        "apischemarevision ",
        "apischemaversion ",
        "graphqlschemahash ",
        "graphqlschemaid ",
        "graphqlschemarevision ",
        "graphqlschemaversion ",
        "schemaetag ",
        "schemahash ",
        "schemarevision ",
        "schemaversion",
    )
)
GRAPHQL_MUTATION_IDEMPOTENCY_KEYS: Final[frozenset[str]] = frozenset(
    (
        "clientmutationid ",
        "dedupekey ",
        "graphqlidempotencykey ",
        "graphqlmutationidempotency ",
        "idempotency ",
        "idempotencykey ",
        "mutationidempotency ",
        "operationid ",
        "requestid ",
        "transactionid",
    )
)
PRODUCTION_PROFILE_KEYS: Final[frozenset[str]] = frozenset(
    (
        "deployment ",
        "environment ",
        "env ",
        "profile ",
        "stage",
    )
)
PRODUCTION_PROFILE_TOKENS: Final[tuple[str, ...]] = ("production",)
GRAPHQL_INTROSPECTION_RAW_TOKENS: Final[tuple[str, ...]] = (
    "__schema",
    "__type",
)
GRAPHQL_OPERATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*\{|\b(?:fragment|mutation|query|subscription)\b",
    re.IGNORECASE,
)
GRAPHQL_EXPLICIT_OPERATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:mutation|query|subscription)\b",
    re.IGNORECASE,
)
GRAPHQL_NAMED_OPERATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:mutation|query|subscription)\s+[_A-Za-z][_0-9A-Za-z]*\b",
    re.IGNORECASE,
)
GRAPHQL_MUTATION_OPERATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*mutation\b",
    re.IGNORECASE,
)
GRAPHQL_VARIABLE_REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\$[_A-Za-z][_0-9A-Za-z]*"
)
GRAPHQL_VARIABLE_DECLARATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    (
        r"^\s*(?:mutation|query|subscription)\b(?:\s+[_A-Za-z][_0-9A-Za-z]*)?"
        r"\s*\([^)]*\$[_A-Za-z][_0-9A-Za-z]*\s*:"
    ),
    re.IGNORECASE | re.DOTALL,
)
GRAPHQL_FIELD_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[_A-Za-z][_0-9A-Za-z]*\b"
)
GRAPHQL_FIELD_COUNT_EXCLUDED_TOKENS: Final[frozenset[str]] = frozenset(
    ("false", "fragment", "null", "on", "true")
)


def validate_graphql_security(
    nodes: tuple[MakeAstNode, ...],
    *,
    scenario_metadata: JsonObject | None = None,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return deterministic GraphQL query-shape findings."""
    findings: list[BlueprintValidationFinding] = []
    root_metadata = _object_or_empty(scenario_metadata)
    for node in nodes:
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_QUERY_MINIFICATION_SUGGESTED_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "GraphQL queries should be minified before "
                            "outbound "
                            ""
                            "requests."
                        ),
                        (
                            f"Node {node.node_id} contains formatted "
                            f"GraphQL query text; "
                            "raw query content is redacted."
                        ),
                    ),
                )
            )
            for query_path in _formatted_graphql_query_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_DYNAMIC_QUERY_WITHOUT_VARIABLES_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "GraphQL dynamic inputs should be passed through a "
                            "variables object."
                        ),
                        (
                            f"Node {node.node_id} maps dynamic values "
                            f"directly into a "
                            "GraphQL query string without visible "
                            "variables-object "
                            "evidence; raw query content is redacted."
                        ),
                    ),
                )
            )
            for query_path in _dynamic_graphql_query_without_variables_paths(
                node
            )
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_OPERATION_NAME_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        "GraphQL operations should declare an operation name.",
                        (
                            f"Node {node.node_id} contains an anonymous "
                            f"GraphQL "
                            "operation; raw query content is redacted."
                        ),
                    ),
                )
            )
            for query_path in _anonymous_graphql_operation_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_VARIABLE_TYPE_DECLARATION_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "GraphQL variables should declare operation-level "
                            "types."
                        ),
                        (
                            f"Node {node.node_id} supplies a GraphQL variables "
                            "object while the query references variables "
                            "without "
                            "visible operation variable type declarations; raw "
                            "query content is redacted."
                        ),
                    ),
                )
            )
            for query_path in _graphql_variable_type_declaration_missing_paths(
                node
            )
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_DEPTH_BUDGET_EXCEEDED_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "GraphQL query depth should stay within the local "
                            "depth budget."
                        ),
                        (
                            f"Node {node.node_id} contains a GraphQL query "
                            f"deeper "
                            "than its declared local depth budget; raw "
                            "query content "
                            "is redacted."
                        ),
                    ),
                )
            )
            for query_path in _graphql_depth_budget_exceeded_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_FIELD_COUNT_BUDGET_EXCEEDED_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "GraphQL selected field count should stay within "
                            "the local budget."
                        ),
                        (
                            f"Node {node.node_id} contains a GraphQL query "
                            f"with more "
                            "selected fields than its declared local "
                            "field-count "
                            "budget; raw query content is redacted."
                        ),
                    ),
                )
            )
            for query_path in _graphql_field_count_budget_exceeded_paths(node)
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_PRODUCTION_INTROSPECTION_QUERY_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Production GraphQL requests should not execute "
                            "introspection queries."
                        ),
                        (
                            f"Node {node.node_id} contains GraphQL "
                            f"introspection "
                            "evidence in a production-scoped scenario; raw "
                            "query "
                            "content is redacted."
                        ),
                    ),
                )
            )
            for query_path in _production_graphql_introspection_paths(
                node,
                scenario_metadata=root_metadata,
            )
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_ERROR_ARRAY_GUARD_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Production GraphQL requests should declare "
                            "error-array handling."
                        ),
                        (
                            f"Node {node.node_id} contains a production-scoped "
                            "GraphQL request without visible "
                            "response.errors guard "
                            "evidence; raw query and response content are "
                            "redacted."
                        ),
                    ),
                )
            )
            for query_path in _graphql_error_array_guard_missing_paths(
                node,
                scenario_metadata=root_metadata,
            )
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_PARTIAL_DATA_GUARD_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Production GraphQL requests should declare "
                            "partial-data handling."
                        ),
                        (
                            f"Node {node.node_id} contains a production-scoped "
                            "GraphQL request without visible nullable or "
                            "partial "
                            "data guard evidence; raw query and response "
                            "content "
                            "are redacted."
                        ),
                    ),
                )
            )
            for query_path in _graphql_partial_data_guard_missing_paths(
                node,
                scenario_metadata=root_metadata,
            )
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_SCHEMA_VERSION_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Production GraphQL requests should declare "
                            "schema-version evidence."
                        ),
                        (
                            f"Node {node.node_id} contains a production-scoped "
                            "GraphQL request without visible schema version, "
                            "revision, hash, or ETag evidence; raw query "
                            "content "
                            "is redacted."
                        ),
                    ),
                )
            )
            for query_path in _graphql_schema_version_missing_paths(
                node,
                scenario_metadata=root_metadata,
            )
        )
        findings.extend(
            (
                build_validation_finding(
                    code=GRAPHQL_MUTATION_IDEMPOTENCY_MISSING_CODE,
                    severity="warning",
                    node=(node.node_id, query_path),
                    catalog_module_id=None,
                    messages=(
                        (
                            "Production GraphQL mutations should declare "
                            "idempotency evidence."
                        ),
                        (
                            f"Node {node.node_id} contains a production-scoped "
                            "GraphQL mutation without visible idempotency key, "
                            "client mutation ID, or request identity evidence; "
                            "raw query content is redacted."
                        ),
                    ),
                )
            )
            for query_path in _graphql_mutation_idempotency_missing_paths(
                node,
                scenario_metadata=root_metadata,
            )
        )
    return tuple(findings)


def _formatted_graphql_query_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return paths for visibly formatted GraphQL query strings."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_formatted_graphql_query_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _dynamic_graphql_query_without_variables_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return the computed result for the caller."""
    if _declares_graphql_variables_object(node):
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_dynamic_graphql_query_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _anonymous_graphql_operation_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return query paths for GraphQL operations without operation names."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_anonymous_graphql_operation_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _graphql_variable_type_declaration_missing_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return query paths where supplied variables lack operation type.

    declarations.
    """
    if not _declares_graphql_variables_object(node):
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_graphql_variable_type_declaration_missing_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _graphql_depth_budget_exceeded_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return query paths where visible GraphQL depth exceeds local budget."""
    budget = _declared_graphql_depth_budget(node)
    if budget is None:
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_graphql_depth_budget_exceeded_paths(
                value,
                budget=budget,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _graphql_field_count_budget_exceeded_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return query paths where visible GraphQL field count exceeds local.

    budget.
    """
    budget = _declared_graphql_field_count_budget(node)
    if budget is None:
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_graphql_field_count_budget_exceeded_paths(
                value,
                budget=budget,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _production_graphql_introspection_paths(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return production GraphQL introspection query paths."""
    if not _production_profile_applies(
        node, scenario_metadata=scenario_metadata
    ):
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_graphql_introspection_query_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _graphql_error_array_guard_missing_paths(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return production GraphQL query paths without local errors-array guard.

    evidence.
    """
    if not _production_profile_applies(
        node,
        scenario_metadata=scenario_metadata,
    ) or _declares_graphql_error_array_guard(node):
        return ()
    return _graphql_query_paths(node)


def _graphql_partial_data_guard_missing_paths(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return production GraphQL query paths without local partial-data guard.

    evidence.
    """
    if not _production_profile_applies(
        node,
        scenario_metadata=scenario_metadata,
    ) or _declares_graphql_partial_data_guard(node):
        return ()
    return _graphql_query_paths(node)


def _graphql_schema_version_missing_paths(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return production GraphQL query paths without schema-version evidence."""
    if not _production_profile_applies(
        node,
        scenario_metadata=scenario_metadata,
    ) or _declares_graphql_schema_version_evidence(node):
        return ()
    return _graphql_query_paths(node)


def _graphql_mutation_idempotency_missing_paths(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return production GraphQL mutation paths without idempotency evidence."""
    if not _production_profile_applies(
        node,
        scenario_metadata=scenario_metadata,
    ) or _declares_graphql_mutation_idempotency_evidence(node):
        return ()
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_graphql_mutation_without_idempotency_paths(
                value,
                path=(*node.source_trace.path, container_key),
            )
        )
    return tuple(paths)


def _graphql_query_paths(
    node: MakeAstNode,
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return visible GraphQL query field paths on one node."""
    paths: list[tuple[AstPathPart, ...]] = []
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if value is None:
            continue
        paths.extend(
            _json_graphql_query_paths(
                value, path=(*node.source_trace.path, container_key)
            )
        )
    return tuple(paths)


def _json_formatted_graphql_query_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where formatted GraphQL query text appears."""
    if isinstance(value, str):
        if _path_is_graphql_query_field(path) and _formatted_graphql_query(
            value
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_formatted_graphql_query_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_formatted_graphql_query_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_graphql_query_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where GraphQL query text appears."""
    if isinstance(value, str):
        if _path_is_graphql_query_field(path) and _graphql_operation_like_text(
            value
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_graphql_query_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_graphql_query_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_graphql_introspection_query_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where GraphQL query text contains introspection.

    evidence.
    """
    if isinstance(value, str):
        if _path_is_graphql_query_field(path) and _graphql_introspection_query(
            value
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_graphql_introspection_query_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_graphql_introspection_query_paths(
                    item, path=(*path, index)
                )
            )
        return tuple(list_paths)
    return ()


def _json_graphql_mutation_without_idempotency_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return paths where GraphQL mutation text lacks idempotency evidence."""
    if isinstance(value, str):
        if (
            _path_is_graphql_query_field(path)
            and _graphql_mutation_operation(value)
            and not _graphql_text_has_idempotency_evidence(value)
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_graphql_mutation_without_idempotency_paths(
                    item, path=(*path, key)
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_graphql_mutation_without_idempotency_paths(
                    item, path=(*path, index)
                )
            )
        return tuple(list_paths)
    return ()


def _json_graphql_field_count_budget_exceeded_paths(
    value: object,
    *,
    budget: int,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where GraphQL selected field count exceeds budget."""
    if isinstance(value, str):
        if (
            _path_is_graphql_query_field(path)
            and _graphql_field_count(value) > budget
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_graphql_field_count_budget_exceeded_paths(
                    item,
                    budget=budget,
                    path=(*path, key),
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_graphql_field_count_budget_exceeded_paths(
                    item,
                    budget=budget,
                    path=(*path, index),
                )
            )
        return tuple(list_paths)
    return ()


def _json_graphql_depth_budget_exceeded_paths(
    value: object,
    *,
    budget: int,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where GraphQL query depth exceeds a local budget."""
    if isinstance(value, str):
        if (
            _path_is_graphql_query_field(path)
            and _graphql_depth(value) > budget
        ):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_graphql_depth_budget_exceeded_paths(
                    item,
                    budget=budget,
                    path=(*path, key),
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_graphql_depth_budget_exceeded_paths(
                    item,
                    budget=budget,
                    path=(*path, index),
                )
            )
        return tuple(list_paths)
    return ()


def _json_anonymous_graphql_operation_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where GraphQL operations omit operation names."""
    if isinstance(value, str):
        if _path_is_graphql_query_field(
            path
        ) and _graphql_operation_name_missing(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_anonymous_graphql_operation_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_anonymous_graphql_operation_paths(
                    item, path=(*path, index)
                )
            )
        return tuple(list_paths)
    return ()


def _json_dynamic_graphql_query_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return the computed result for the caller."""
    if isinstance(value, str):
        if _path_is_graphql_query_field(path) and _dynamic_graphql_query(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_dynamic_graphql_query_paths(item, path=(*path, key))
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_dynamic_graphql_query_paths(item, path=(*path, index))
            )
        return tuple(list_paths)
    return ()


def _json_graphql_variable_type_declaration_missing_paths(
    value: object,
    *,
    path: tuple[AstPathPart, ...],
) -> tuple[tuple[AstPathPart, ...], ...]:
    """Return JSON paths where GraphQL variable references lack local type.

    declarations.
    """
    if isinstance(value, str):
        if _path_is_graphql_query_field(
            path
        ) and _graphql_variable_type_declaration_missing(value):
            return (path,)
        return ()
    if _is_json_object(value):
        object_paths: list[tuple[AstPathPart, ...]] = []
        for key, item in value.items():
            object_paths.extend(
                _json_graphql_variable_type_declaration_missing_paths(
                    item,
                    path=(*path, key),
                )
            )
        return tuple(object_paths)
    if isinstance(value, list):
        list_paths: list[tuple[AstPathPart, ...]] = []
        for index, item in enumerate(cast("list[object]", value)):
            list_paths.extend(
                _json_graphql_variable_type_declaration_missing_paths(
                    item,
                    path=(*path, index),
                )
            )
        return tuple(list_paths)
    return ()


def _declares_graphql_variables_object(node: MakeAstNode) -> bool:
    """Return whether a node declares a GraphQL variables object."""
    for container_key in ("parameters", "mapper"):
        value = node.raw_payload.get(container_key)
        if _json_has_variables_object(value):
            return True
    return False


def _declares_graphql_error_array_guard(node: MakeAstNode) -> bool:
    """Return if a node declares GraphQL response.errors handling evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        value = node.raw_payload.get(container_key)
        if _json_has_evidence_key_token(
            value, tokens=GRAPHQL_ERROR_ARRAY_GUARD_KEYS
        ):
            return True
    return False


def _declares_graphql_partial_data_guard(node: MakeAstNode) -> bool:
    """Return whether a node declares GraphQL partial-data handling evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        value = node.raw_payload.get(container_key)
        if _json_has_evidence_key_token(
            value, tokens=GRAPHQL_PARTIAL_DATA_GUARD_KEYS
        ):
            return True
    return False


def _declares_graphql_schema_version_evidence(node: MakeAstNode) -> bool:
    """Return whether a node declares GraphQL schema-version evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        value = node.raw_payload.get(container_key)
        if _json_has_evidence_key_token(
            value, tokens=GRAPHQL_SCHEMA_VERSION_KEYS
        ):
            return True
    return False


def _declares_graphql_mutation_idempotency_evidence(node: MakeAstNode) -> bool:
    """Return whether a node declares GraphQL mutation idempotency evidence."""
    for container_key in ("parameters", "mapper", "metadata"):
        value = node.raw_payload.get(container_key)
        if _json_has_evidence_key_token(
            value, tokens=GRAPHQL_MUTATION_IDEMPOTENCY_KEYS
        ):
            return True
    return False


def _json_has_variables_object(value: object) -> bool:
    """Return whether JSON-like data contains a non-empty variables object."""
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if normalized_key in GRAPHQL_VARIABLES_KEYS and _non_empty_object(
                item
            ):
                return True
            if _json_has_variables_object(item):
                return True
    if isinstance(value, list):
        return any(
            _json_has_variables_object(item)
            for item in cast("list[object]", value)
        )
    return False


def _json_has_evidence_key_token(
    value: object, *, tokens: frozenset[str]
) -> bool:
    """Return if JSON-like data contains a token-bearing key with evidence."""
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if normalized_key in tokens and _has_evidence_value(item):
                return True
            if _json_has_evidence_key_token(item, tokens=tokens):
                return True
    if isinstance(value, list):
        return any(
            _json_has_evidence_key_token(item, tokens=tokens)
            for item in cast("list[object]", value)
        )
    return False


def _has_evidence_value(value: object) -> bool:
    """Return whether a JSON value carries meaningful local evidence."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return bool(
            module_token_semantic_key(value)
        ) and module_token_semantic_key(value) not in {
            "0 ",
            "false ",
            "no ",
            "none ",
            "off",
        }
    if _is_json_object(value):
        return any(_has_evidence_value(item) for item in value.values())
    if isinstance(value, list):
        return any(
            _has_evidence_value(item) for item in cast("list[object]", value)
        )
    return value is not None


def _declared_graphql_depth_budget(node: MakeAstNode) -> int | None:
    """Return the first positive GraphQL depth budget declared on a node."""
    for container_key in ("parameters", "mapper", "metadata"):
        value = node.raw_payload.get(container_key)
        budget = _json_graphql_depth_budget(value)
        if budget is not None:
            return budget
    return None


def _declared_graphql_field_count_budget(node: MakeAstNode) -> int | None:
    """Return the computed result for the caller."""
    for container_key in ("parameters", "mapper", "metadata"):
        value = node.raw_payload.get(container_key)
        budget = _json_graphql_field_count_budget(value)
        if budget is not None:
            return budget
    return None


def _json_graphql_depth_budget(value: object) -> int | None:
    """Return the computed result for the caller."""
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if normalized_key in GRAPHQL_DEPTH_BUDGET_KEYS:
                budget = _positive_int(item)
                if budget is not None:
                    return budget
            nested_budget = _json_graphql_depth_budget(item)
            if nested_budget is not None:
                return nested_budget
    if isinstance(value, list):
        for item in cast("list[object]", value):
            budget = _json_graphql_depth_budget(item)
            if budget is not None:
                return budget
    return None


def _json_graphql_field_count_budget(value: object) -> int | None:
    """Return a positive GraphQL field-count budget from JSON-like data."""
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if normalized_key in GRAPHQL_FIELD_COUNT_BUDGET_KEYS:
                budget = _positive_int(item)
                if budget is not None:
                    return budget
            nested_budget = _json_graphql_field_count_budget(item)
            if nested_budget is not None:
                return nested_budget
    if isinstance(value, list):
        for item in cast("list[object]", value):
            budget = _json_graphql_field_count_budget(item)
            if budget is not None:
                return budget
    return None


def _production_profile_applies(
    node: MakeAstNode,
    *,
    scenario_metadata: JsonObject,
) -> bool:
    """Return whether root or node-local metadata declares production scope."""
    if _json_has_production_profile(scenario_metadata):
        return True
    for container_key in ("parameters", "mapper", "metadata"):
        value = node.raw_payload.get(container_key)
        if _json_has_production_profile(value):
            return True
    return False


def _json_has_production_profile(value: object) -> bool:
    """Return whether JSON-like metadata declares a production profile."""
    if _is_json_object(value):
        for key, item in value.items():
            normalized_key = module_token_semantic_key(key)
            if (
                normalized_key in PRODUCTION_PROFILE_KEYS
                and _json_text_has_token(
                    item,
                    tokens=PRODUCTION_PROFILE_TOKENS,
                )
            ):
                return True
            if _json_has_production_profile(item):
                return True
    if isinstance(value, list):
        return any(
            _json_has_production_profile(item)
            for item in cast("list[object]", value)
        )
    return False


def _json_text_has_token(value: object, *, tokens: tuple[str, ...]) -> bool:
    """Return whether JSON-like scalar text contains one normalized token."""
    normalized_tokens = tuple(
        module_token_semantic_key(token) for token in tokens
    )
    if isinstance(value, str):
        normalized_value = module_token_semantic_key(value)
        return any(token in normalized_value for token in normalized_tokens)
    if isinstance(value, int | float | bool) or value is None:
        return False
    if _is_json_object(value):
        return any(
            _json_text_has_token(item, tokens=tokens) for item in value.values()
        )
    if isinstance(value, list):
        return any(
            _json_text_has_token(item, tokens=tokens)
            for item in cast("list[object]", value)
        )
    return False


def _path_is_graphql_query_field(path: tuple[AstPathPart, ...]) -> bool:
    """Return whether one AST path names a GraphQL query field."""
    return any(
        isinstance(part, str)
        and module_token_semantic_key(part) in GRAPHQL_QUERY_KEYS
        for part in path
    )


def _formatted_graphql_query(value: str) -> bool:
    """Return whether text is a GraphQL query with formatting whitespace."""
    if not _graphql_operation_like_text(value):
        return False
    return "\n" in value or "\t" in value or "  " in value


def _dynamic_graphql_query(value: str) -> bool:
    """Return whether GraphQL query text contains direct Make mappings."""
    if not _graphql_operation_like_text(value):
        return False
    return any(marker in value for marker in MAKE_MAPPING_MARKERS)


def _graphql_operation_name_missing(value: str) -> bool:
    """Return whether GraphQL operation text omits a stable operation name."""
    stripped = value.lstrip()
    if stripped.startswith("{"):
        return True
    if GRAPHQL_EXPLICIT_OPERATION_PATTERN.match(stripped) is None:
        return False
    return GRAPHQL_NAMED_OPERATION_PATTERN.match(stripped) is None


def _graphql_variable_type_declaration_missing(value: str) -> bool:
    """Return whether GraphQL variable references lack operation variable.

    declarations.
    """
    if not _graphql_operation_like_text(value):
        return False
    if GRAPHQL_VARIABLE_REFERENCE_PATTERN.search(value) is None:
        return False
    return GRAPHQL_VARIABLE_DECLARATION_PATTERN.search(value) is None


def _graphql_mutation_operation(value: str) -> bool:
    """Return whether text visibly declares a GraphQL mutation operation."""
    return GRAPHQL_MUTATION_OPERATION_PATTERN.match(value) is not None


def _graphql_text_has_idempotency_evidence(value: str) -> bool:
    """Return whether GraphQL text itself names idempotency evidence."""
    normalized_value = module_token_semantic_key(value)
    return any(
        token in normalized_value for token in GRAPHQL_MUTATION_IDEMPOTENCY_KEYS
    )


def _graphql_introspection_query(value: str) -> bool:
    """Return whether GraphQL query text contains introspection evidence."""
    if not _graphql_operation_like_text(value):
        return False
    lowered = value.casefold()
    if any(token in lowered for token in GRAPHQL_INTROSPECTION_RAW_TOKENS):
        return True
    normalized_value = module_token_semantic_key(value)
    return "introspectionquery" in normalized_value


def _graphql_depth(value: str) -> int:
    """Return the computed result for the caller."""
    if not _graphql_operation_like_text(value):
        return 0
    depth = 0
    max_depth = 0
    for character in value:
        if character == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif character == "}":
            depth = max(0, depth - 1)
    return max_depth


def _graphql_field_count(value: str) -> int:
    """Return an approximate selected-field count for visible GraphQL text."""
    if not _graphql_operation_like_text(value):
        return 0
    selection_text = _graphql_selection_text(value)
    selection_without_arguments = _remove_parenthetical_text(selection_text)
    tokens = cast(
        "list[str]",
        GRAPHQL_FIELD_NAME_PATTERN.findall(selection_without_arguments),
    )
    return sum(
        token.casefold() not in GRAPHQL_FIELD_COUNT_EXCLUDED_TOKENS
        for token in tokens
    )


def _graphql_selection_text(value: str) -> str:
    """Return the visible GraphQL selection-set text when present."""
    start = value.find("{")
    end = value.rfind("}")
    if start == -1 or end <= start:
        return ""
    return value[start : end + 1]


def _remove_parenthetical_text(value: str) -> str:
    """Return text with parenthetical argument lists blanked out."""
    output: list[str] = []
    depth = 0
    for character in value:
        if character == "(":
            depth += 1
            output.append(" ")
            continue
        if character == ")":
            depth = max(0, depth - 1)
            output.append(" ")
            continue
        output.append(" " if depth else character)
    return "".join(output)


def _graphql_operation_like_text(value: str) -> bool:
    """Return whether text visibly contains GraphQL operation syntax."""
    return GRAPHQL_OPERATION_PATTERN.search(value) is not None


def _positive_int(value: object) -> int | None:
    """Return a positive integer from JSON-like values when exact."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _non_empty_object(value: object) -> bool:
    """Return whether a value is a non-empty JSON object."""
    return _is_json_object(value) and bool(value)


def _object_or_empty(value: object) -> JsonObject:
    """Return a JSON object value or an empty object for metadata inspection."""
    return value if _is_json_object(value) else {}


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
