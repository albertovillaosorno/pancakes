# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001044#repo.make-ast.contract-policy
# - 001046#repo.blueprint-validation.validator-policy
# - 001063#repo.architecture.file-boundary.contract-required
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Local Make blueprint parity checks before any live Make validation.

Boundary contract:
- Owns: offline import-parity evidence for parsed Make blueprint ASTs.
- Must not: call Make.com, inspect credentials, mutate blueprints, or read
provider state.
- Allows: AST scans, existing validation findings, and bounded node-linked
evidence.
- Split when: live browser review owns Make.com import/run behavior.
- Merge when: blueprint validation owns the same local parity report contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

from blueprints.ast.references import collect_runtime_placeholder_usages
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.importability import placeholder_registry_entries

if TYPE_CHECKING:
    from collections.abc import Iterable

    from blueprints.ast.models import (
        AstPathPart,
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
    )
    from blueprints.validation.models import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )

type LocalBlueprintParityArea = Literal[
    "importability",
    "modules",
    "fields",
    "routes",
    "filters",
    "error_handlers",
    "data_stores",
    "data_structures",
    "scheduling",
    "placeholders",
]
type LocalBlueprintParityStatus = Literal["pass", "fail", "not_applicable"]
type LocalBlueprintParityReportStatus = Literal["pass", "fail"]

LOCAL_BLUEPRINT_PARITY_AREAS: Final[tuple[LocalBlueprintParityArea, ...]] = (
    "importability",
    "modules",
    "fields",
    "routes",
    "filters",
    "error_handlers",
    "data_stores",
    "data_structures",
    "scheduling",
    "placeholders",
)
LOCAL_BLUEPRINT_PARITY_LIVE_CALLS_REQUIRED: Final = False
MODULE_FIELD_KEYS: Final = ("parameters", "mapper")
ROUTE_CONTAINER_NAMES: Final = ("routes", "branches", "tools")
DATA_STRUCTURE_KEYS: Final[frozenset[str]] = frozenset(
    (
        "datastructure",
        "datastructures",
        "data_structure",
        "data_structures",
        "fields",
        "schema",
        "schemas",
        "structure",
    )
)
FINDING_AREA_RULES: Final[
    tuple[
        tuple[
            LocalBlueprintParityArea,
            tuple[str, ...],
            tuple[str, ...],
        ],
        ...,
    ]
] = (
    ("placeholders", (), ("placeholder",)),
    ("importability", ("importability.",), ()),
    ("modules", ("raw_spec.",), ("module",)),
    ("fields", (), ("field", "parameter", "mapping")),
    ("routes", ("route.", "router."), ()),
    ("filters", ("filter.",), ()),
    ("error_handlers", (), ("error_handler", "errorhandler")),
    ("data_stores", ("data_store.",), ("datastore",)),
    ("data_structures", (), ("data_structure", "datastructure", "schema")),
    ("scheduling", ("schedule.",), ("trigger",)),
)


class LocalBlueprintParityFailure(NamedTuple):
    """One node-linked local parity failure."""

    failure_id: str
    area: LocalBlueprintParityArea
    code: str
    node_id: str | None
    source_path: tuple[AstPathPart, ...]
    message: str


class LocalBlueprintParityEvidence(NamedTuple):
    """Evidence that one local parity area was checked."""

    area: LocalBlueprintParityArea
    status: LocalBlueprintParityStatus
    node_ids: tuple[str, ...]
    source_paths: tuple[tuple[AstPathPart, ...], ...]
    finding_codes: tuple[str, ...]
    summary: str


class LocalBlueprintParityReport(NamedTuple):
    """Offline Make import parity report for a parsed blueprint."""

    status: LocalBlueprintParityReportStatus
    live_make_calls_required: bool
    covered_areas: tuple[LocalBlueprintParityArea, ...]
    evidence: tuple[LocalBlueprintParityEvidence, ...]
    failures: tuple[LocalBlueprintParityFailure, ...]

    def failures_for_area(
        self,
        area: LocalBlueprintParityArea,
    ) -> tuple[LocalBlueprintParityFailure, ...]:
        """Return failures for one local parity area."""
        return tuple(
            failure for failure in self.failures if failure.area == area
        )


def validate_local_blueprint_import_parity(
    *,
    root: MakeAstRoot,
    validation_report: BlueprintValidationReport | None = None,
) -> LocalBlueprintParityReport:
    """Return the computed result for the caller."""
    nodes = iter_ast_nodes(root)
    failures = (
        *_validation_finding_failures(
            validation_report.findings if validation_report is not None else ()
        ),
        *_structural_failures(root=root, nodes=nodes),
    )
    evidence = tuple(
        _area_evidence(area=area, root=root, nodes=nodes, failures=failures)
        for area in LOCAL_BLUEPRINT_PARITY_AREAS
    )
    return LocalBlueprintParityReport(
        status="fail" if failures else "pass",
        live_make_calls_required=LOCAL_BLUEPRINT_PARITY_LIVE_CALLS_REQUIRED,
        covered_areas=LOCAL_BLUEPRINT_PARITY_AREAS,
        evidence=evidence,
        failures=failures,
    )


def _validation_finding_failures(
    findings: tuple[BlueprintValidationFinding, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    failures: list[LocalBlueprintParityFailure] = []
    for finding in findings:
        failures.extend(
            LocalBlueprintParityFailure(
                failure_id=f"{area}:{finding.finding_id}",
                area=area,
                code=finding.code,
                node_id=finding.node_id,
                source_path=finding.source_path,
                message=finding.client_message,
            )
            for area in _areas_for_finding_code(finding.code)
        )
    return tuple(failures)


def _areas_for_finding_code(code: str) -> tuple[LocalBlueprintParityArea, ...]:
    normalized = code.casefold()
    return tuple(
        area
        for area, prefixes, tokens in FINDING_AREA_RULES
        if _code_matches_area(
            normalized=normalized, prefixes=prefixes, tokens=tokens
        )
    )


def _code_matches_area(
    *,
    normalized: str,
    prefixes: tuple[str, ...],
    tokens: tuple[str, ...],
) -> bool:
    return (bool(prefixes) and normalized.startswith(prefixes)) or any(
        token in normalized for token in tokens
    )


def _structural_failures(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    return (
        *_module_failures(nodes),
        *_field_failures(nodes),
        *_route_failures(nodes),
        *_filter_failures(nodes),
        *_error_handler_failures(nodes),
        *_data_structure_failures(root=root, nodes=nodes),
        *_scheduling_failures(root=root, nodes=nodes),
    )


def _module_failures(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    if not nodes:
        return (
            _failure(
                area="modules",
                code="local_parity.modules.empty_flow",
                node_id=None,
                source_path=("flow",),
                message=(
                    "The blueprint flow has no local module nodes to import."
                ),
            ),
        )
    return tuple(
        _failure(
            area="modules",
            code="local_parity.modules.missing_token",
            node_id=node.node_id,
            source_path=(*node.source_trace.path, "module"),
            message="A local module node does not declare a Make module token.",
        )
        for node in nodes
        if not node.module_token
    )


def _field_failures(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    failures: list[LocalBlueprintParityFailure] = []
    for node in nodes:
        for key in MODULE_FIELD_KEYS:
            value = node.raw_payload.get(key)
            if value is None or _is_json_object(value):
                continue
            failures.append(
                _failure(
                    area="fields",
                    code="local_parity.fields.invalid_payload",
                    node_id=node.node_id,
                    source_path=(*node.source_trace.path, key),
                    message=(
                        "A module field payload must be a JSON object for local"
                        "import parity."
                    ),
                )
            )
    return tuple(failures)


def _route_failures(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    return tuple(
        _failure(
            area="routes",
            code="local_parity.routes.on_non_router",
            node_id=node.node_id,
            source_path=(*node.source_trace.path, "routes"),
            message="A route container is attached to a non-router module.",
        )
        for node in nodes
        if node.kind != "router" and node.routes
    )


def _filter_failures(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    failures: list[LocalBlueprintParityFailure] = []
    for node in nodes:
        for route in (*node.routes, *node.branches, *node.tools):
            if route.filter is None or route.filter.conditions:
                continue
            failures.append(
                _failure(
                    area="filters",
                    code="local_parity.filters.empty_conditions",
                    node_id=route.source_trace.parent_node_id,
                    source_path=(*route.source_trace.path, "filter"),
                    message=(
                        "A local route filter does not expose executable"
                        "conditions."
                    ),
                )
            )
    return tuple(failures)


def _error_handler_failures(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    return tuple(
        _failure(
            area="error_handlers",
            code="local_parity.error_handlers.missing_token",
            node_id=handler.node_id,
            source_path=(*handler.source_trace.path, "module"),
            message=(
                "A local error-handler node does not declare a Make module"
                "token."
            ),
        )
        for node in nodes
        for handler in node.error_handlers
        if not handler.module_token
    )


def _data_structure_failures(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    data_store_nodes = _data_store_nodes(nodes)
    if not data_store_nodes:
        return ()
    if _has_data_structure_evidence(root.raw_payload):
        return ()
    return tuple(
        _failure(
            area="data_structures",
            code="local_parity.data_structures.missing_for_data_store",
            node_id=node.node_id,
            source_path=node.source_trace.path,
            message="A data-store module lacks local data-structure evidence.",
        )
        for node in data_store_nodes
        if not _has_data_structure_evidence(node.raw_payload)
    )


def _scheduling_failures(
    *,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[LocalBlueprintParityFailure, ...]:
    if root.scenario.schedule is not None or any(
        _node_is_trigger_like(node) for node in nodes
    ):
        return ()
    return (
        _failure(
            area="scheduling",
            code="local_parity.scheduling.missing_trigger_or_schedule",
            node_id=None,
            source_path=("metadata", "schedule"),
            message=(
                "The blueprint has no local schedule metadata or trigger-like"
                "start module."
            ),
        ),
    )


def _area_evidence(
    *,
    area: LocalBlueprintParityArea,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
    failures: tuple[LocalBlueprintParityFailure, ...],
) -> LocalBlueprintParityEvidence:
    area_failures = tuple(
        failure for failure in failures if failure.area == area
    )
    area_node_ids = _area_node_ids(area=area, root=root, nodes=nodes)
    failure_node_ids = tuple(
        failure.node_id
        for failure in area_failures
        if failure.node_id is not None
    )
    applicable = _area_applicable(area=area, root=root, nodes=nodes) or bool(
        area_failures
    )
    status: LocalBlueprintParityStatus
    if area_failures:
        status = "fail"
    elif applicable:
        status = "pass"
    else:
        status = "not_applicable"
    return LocalBlueprintParityEvidence(
        area=area,
        status=status,
        node_ids=tuple(dict.fromkeys((*area_node_ids, *failure_node_ids))),
        source_paths=_dedupe_paths(
            failure.source_path for failure in area_failures
        ),
        finding_codes=tuple(
            dict.fromkeys(failure.code for failure in area_failures)
        ),
        summary=_area_summary(area=area, status=status, failures=area_failures),
    )


def _area_node_ids(
    *,
    area: LocalBlueprintParityArea,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> tuple[str, ...]:
    node_ids: tuple[str, ...]
    if area in {"importability", "modules"}:
        node_ids = tuple(node.node_id for node in nodes if node.node_id)
    elif area == "fields":
        node_ids = tuple(
            node.node_id
            for node in nodes
            if node.node_id
            and any(key in node.raw_payload for key in MODULE_FIELD_KEYS)
        )
    elif area == "routes":
        node_ids = tuple(
            node.node_id
            for node in nodes
            if node.node_id
            and any(
                _route_container(node, key) for key in ROUTE_CONTAINER_NAMES
            )
        )
    elif area == "filters":
        node_ids = tuple(
            node.node_id
            for node in nodes
            if node.node_id
            and any(
                route.filter is not None
                for route in (*node.routes, *node.branches, *node.tools)
            )
        )
    elif area == "error_handlers":
        node_ids = tuple(
            node.node_id
            for node in nodes
            if node.node_id
            and (node.error_handlers or node.kind == "error_handler")
        )
    elif area in {"data_stores", "data_structures"}:
        node_ids = tuple(
            node.node_id for node in _data_store_nodes(nodes) if node.node_id
        )
    elif area == "scheduling":
        node_ids = tuple(
            node.node_id
            for node in nodes
            if node.node_id and _node_is_trigger_like(node)
        )
    elif area == "placeholders":
        node_ids = tuple(
            usage.node_id
            for usage in collect_runtime_placeholder_usages(root)
            if usage.node_id
        )
    else:
        node_ids = ()
    return node_ids


def _area_applicable(
    *,
    area: LocalBlueprintParityArea,
    root: MakeAstRoot,
    nodes: tuple[MakeAstNode, ...],
) -> bool:
    applicable: bool
    if area in {"importability", "scheduling"}:
        applicable = True
    elif area == "modules":
        applicable = bool(nodes)
    elif area == "fields":
        applicable = any(
            key in node.raw_payload
            for node in nodes
            for key in MODULE_FIELD_KEYS
        )
    elif area == "routes":
        applicable = any(
            node.kind == "router"
            or any(_route_container(node, key) for key in ROUTE_CONTAINER_NAMES)
            for node in nodes
        )
    elif area == "filters":
        applicable = any(
            route.filter is not None
            for node in nodes
            for route in (*node.routes, *node.branches, *node.tools)
        )
    elif area == "error_handlers":
        applicable = any(
            node.error_handlers or node.kind == "error_handler"
            for node in nodes
        )
    elif area == "data_stores":
        applicable = bool(_data_store_nodes(nodes))
    elif area == "data_structures":
        applicable = bool(
            _data_store_nodes(nodes)
        ) or _has_data_structure_evidence(root.raw_payload)
    elif area == "placeholders":
        applicable = bool(collect_runtime_placeholder_usages(root)) or bool(
            placeholder_registry_entries(root.scenario.metadata)
        )
    else:
        applicable = False
    return applicable


def _area_summary(
    *,
    area: LocalBlueprintParityArea,
    status: LocalBlueprintParityStatus,
    failures: tuple[LocalBlueprintParityFailure, ...],
) -> str:
    if failures:
        return f"{area} local parity has {len(failures)} precise failure(s)."
    if status == "not_applicable":
        return (
            f"{area} local parity was checked and is not applicable to this"
            f"blueprint."
        )
    return f"{area} local parity passed without live Make calls."


def _failure(
    *,
    area: LocalBlueprintParityArea,
    code: str,
    node_id: str | None,
    source_path: tuple[AstPathPart, ...],
    message: str,
) -> LocalBlueprintParityFailure:
    path_token = ".".join(str(part) for part in source_path)
    return LocalBlueprintParityFailure(
        failure_id=f"{area}:{code}:{node_id or 'root'}:{path_token}",
        area=area,
        code=code,
        node_id=node_id,
        source_path=source_path,
        message=message,
    )


def _route_container(node: MakeAstNode, key: str) -> tuple[object, ...]:
    if key == "routes":
        return cast("tuple[object, ...]", node.routes)
    if key == "branches":
        return cast("tuple[object, ...]", node.branches)
    return cast("tuple[object, ...]", node.tools)


def _data_store_nodes(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[MakeAstNode, ...]:
    return tuple(node for node in nodes if node.kind == "data_store")


def _node_is_trigger_like(node: MakeAstNode) -> bool:
    module_token = node.module_token.casefold()
    return (
        node.kind in {"webhook", "schedule_trigger"}
        or "trigger" in module_token
    )


def _has_data_structure_evidence(value: object) -> bool:
    if isinstance(value, dict):
        payload = cast("dict[object, object]", value)
        for raw_key, item in payload.items():
            if not isinstance(raw_key, str):
                continue
            normalized_key = raw_key.replace("-", "_").casefold()
            if normalized_key in DATA_STRUCTURE_KEYS and _has_meaningful_value(
                item
            ):
                return True
            if _has_data_structure_evidence(item):
                return True
    if isinstance(value, list):
        return any(
            _has_data_structure_evidence(item)
            for item in cast("list[object]", value)
        )
    return False


def _has_meaningful_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return len(cast("dict[object, object]", value)) > 0
    if isinstance(value, list):
        return len(cast("list[object]", value)) > 0
    return True


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    payload = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in payload)


def _dedupe_paths(
    paths: Iterable[tuple[AstPathPart, ...]],
) -> tuple[tuple[AstPathPart, ...], ...]:
    typed_paths = tuple(paths)
    return tuple(
        path
        for path in sorted(
            dict.fromkeys(typed_paths),
            key=lambda source_path: tuple(str(part) for part in source_path),
        )
    )
