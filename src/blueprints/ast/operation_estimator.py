# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract-policy
# - 001050#repo.make-ast.operation-estimator-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Conservative Make operation estimation for parsed AST blueprints.

Boundary contract:
- Owns: conservative operation estimates from parsed blueprint AST structure.
- Must not: call live Make history, claim billing certainty, or mutate AST
nodes.
- Allows: static run counts, per-run operation counts, and planning warnings.
- Split when: schedule cadence, module-only, or volume warnings need ownership.
- Merge when: another estimator returns the same static planning estimate.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

from blueprints.ast.runtime_metadata import extract_error_directives
from blueprints.ast.traversal import require_ast_node

if TYPE_CHECKING:
    from blueprints.ast.models import (
        JsonObject,
        MakeAstNode,
        MakeAstRoot,
        MakeAstRoute,
    )

type EstimateExecutionMode = Literal["scheduled", "run_once", "module_only"]
type OperationEstimatePrecision = Literal[
    "exact_static_model", "conservative_with_evidence_gaps"
]
type OperationSafetyProfile = Literal[
    "minimum_known ",
    "configured_profile ",
    "worst_reasonable_local_safety",
]

HIGH_TEST_OPERATION_THRESHOLD: Final = 1_000
ESTIMATE_SOURCE_LABEL: Final = "static_ast_no_live_run_evidence"
ESTIMATE_CONFIDENCE_LABEL: Final = "conservative_planning"
EXECUTION_MODES: Final[frozenset[str]] = frozenset(
    ("scheduled", "run_once", "module_only")
)
OPERATION_SAFETY_PROFILES: Final[frozenset[str]] = frozenset(
    (
        "minimum_known ",
        "configured_profile ",
        "worst_reasonable_local_safety",
    )
)
ESTIMATE_EVIDENCE_GAP_WARNING_CODES: Final[frozenset[str]] = frozenset(
    (
        "estimate.ai_tool_usage ",
        "estimate.module_only_target_missing ",
        "estimate.pagination_volume_unknown ",
        "estimate.retry_count_unknown ",
        "estimate.schedule_missing ",
        "estimate.schedule_unknown",
    )
)
TEXT_INTERVAL_AMOUNT_PATTERN: Final = r"(?<![\w.])(?P<amount>\d+(?:\.\d+)?)\s*"
TEXT_INTERVAL_UNIT_PATTERN: Final = r"(?P<unit>m|mins?|minutes?|h|hrs?|hours?|d|days?|w|weeks?|s|secs?|seconds?)\b"
TEXT_INTERVAL_PATTERN: Final = re.compile(
    f"{TEXT_INTERVAL_AMOUNT_PATTERN}{TEXT_INTERVAL_UNIT_PATTERN}", re.IGNORECASE
)
NODE_CHILD_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    ("routes", "branches", "tools", "onerror", "on_error")
)


class OperationEstimateWarning(NamedTuple):
    """One conservative estimator warning."""

    code: str
    node_id: str | None
    client_message: str
    internal_message: str


class OperationEstimate(NamedTuple):
    """Conservative operation estimate for a blueprint and time horizon."""

    horizon_hours: int
    execution_mode: EstimateExecutionMode
    safety_profile: OperationSafetyProfile
    run_count: int
    minimum_operations_per_run: int
    safety_overhead_per_run: int
    operations_per_run: int
    minimum_estimated_operations: int
    safety_overhead_operations: int
    estimated_operations: int
    precision_label: OperationEstimatePrecision
    confidence_label: str
    source_label: str
    evidence_gap_codes: tuple[str, ...]
    warnings: tuple[OperationEstimateWarning, ...]

    @property
    def client_summary(self) -> str:
        """Get client-safe planning summary without billing certainty claims."""
        if self.evidence_gap_codes:
            gap_text = f"Evidence gaps: {', '.join(self.evidence_gap_codes)}. "
        else:
            gap_text = "No estimator evidence gaps were detected. "
        return (
            "Static local-model estimate: "
            f"{self.estimated_operations} operations across "
            f"{self.horizon_hours} hour(s). "
            f"Profile: {self.safety_profile}. "
            f"{gap_text}"
            "Use live Make run history before treating this as billing "
            "evidence."
        )


def estimate_blueprint_operations(
    *,
    root: MakeAstRoot,
    horizon_hours: int = 24,
    execution_mode: EstimateExecutionMode = "scheduled",
    module_only_node_id: str | None = None,
    safety_profile: OperationSafetyProfile = "minimum_known",
) -> OperationEstimate:
    """Estimate Make operations conservatively from a parsed AST.

    Returns:
        The result produced by estimate Make operations conservatively from a
        parsed AST.
    """
    _validate_estimate_request(
        horizon_hours=horizon_hours,
        execution_mode=execution_mode,
        safety_profile=safety_profile,
    )
    warnings: list[OperationEstimateWarning] = []
    run_count = _run_count(
        root=root,
        horizon_hours=horizon_hours,
        execution_mode=execution_mode,
        warnings=warnings,
    )
    minimum_operations_per_run = _operations_per_run(
        root=root,
        execution_mode=execution_mode,
        module_only_node_id=module_only_node_id,
        warnings=warnings,
    )
    safety_overhead_per_run = _safety_overhead_per_run(
        root=root,
        execution_mode=execution_mode,
        module_only_node_id=module_only_node_id,
        safety_profile=safety_profile,
        warnings=warnings,
    )
    operations_per_run = minimum_operations_per_run + safety_overhead_per_run
    minimum_estimated_operations = run_count * minimum_operations_per_run
    safety_overhead_operations = run_count * safety_overhead_per_run
    estimated_operations = run_count * operations_per_run
    warnings.extend(_large_test_cost_warnings(estimated_operations))
    evidence_gap_codes = _evidence_gap_codes(tuple(warnings))
    return OperationEstimate(
        horizon_hours=horizon_hours,
        execution_mode=execution_mode,
        safety_profile=safety_profile,
        run_count=run_count,
        minimum_operations_per_run=minimum_operations_per_run,
        safety_overhead_per_run=safety_overhead_per_run,
        operations_per_run=operations_per_run,
        minimum_estimated_operations=minimum_estimated_operations,
        safety_overhead_operations=safety_overhead_operations,
        estimated_operations=estimated_operations,
        precision_label=_precision_label(evidence_gap_codes),
        confidence_label=ESTIMATE_CONFIDENCE_LABEL,
        source_label=ESTIMATE_SOURCE_LABEL,
        evidence_gap_codes=evidence_gap_codes,
        warnings=tuple(warnings),
    )


def _validate_estimate_request(
    *,
    horizon_hours: int,
    execution_mode: EstimateExecutionMode,
    safety_profile: OperationSafetyProfile,
) -> None:
    """Validate caller-owned estimate request fields.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    if type(horizon_hours) is not int or horizon_hours <= 0:
        message = "Operation estimate horizon_hours must be a positive integer."
        raise ValueError(message)
    if execution_mode not in EXECUTION_MODES:
        message = (
            f"Unsupported operation estimate execution mode:{execution_mode!r}."
        )
        raise ValueError(message)
    if safety_profile not in OPERATION_SAFETY_PROFILES:
        message = (
            f"Unsupported operation estimate safety profile:{safety_profile!r}."
        )
        raise ValueError(message)


def _run_count(
    *,
    root: MakeAstRoot,
    horizon_hours: int,
    execution_mode: EstimateExecutionMode,
    warnings: list[OperationEstimateWarning],
) -> int:
    """Return estimated run count for the horizon."""
    if execution_mode in {"run_once", "module_only"}:
        return 1
    schedule = root.scenario.schedule
    if schedule is None:
        warnings.append(
            _warning(
                code="estimate.schedule_missing",
                node_id=None,
                client_message=(
                    "No schedule is declared, so one planning run is assumed."
                ),
                internal_message="Schedule metadata is absent.",
            )
        )
        return 1
    minutes = _schedule_interval_minutes(schedule.raw_payload)
    if minutes is None or minutes <= 0:
        warnings.append(
            _warning(
                code="estimate.schedule_unknown",
                node_id=None,
                client_message=(
                    "Schedule cadence is unclear, so one planning run is "
                    "assumed."
                ),
                internal_message=(
                    "Schedule cadence could not be derived from local "
                    "metadata; "
                    "raw "
                    "schedule values are redacted."
                ),
            )
        )
        return 1
    return max(1, math.ceil((horizon_hours * 60) / minutes))


def _operations_per_run(
    *,
    root: MakeAstRoot,
    execution_mode: EstimateExecutionMode,
    module_only_node_id: str | None,
    warnings: list[OperationEstimateWarning],
) -> int:
    """Return static operation count for one run."""
    if execution_mode == "module_only":
        if module_only_node_id is None:
            warnings.append(
                _warning(
                    code="estimate.module_only_target_missing",
                    node_id=None,
                    client_message=(
                        "Run-this-module-only mode needs a selected module."
                    ),
                    internal_message="module_only_node_id was not provided.",
                )
            )
            return 1
        _ = require_ast_node(root, module_only_node_id)
        return 1
    return sum(_node_operation_count(node, warnings) for node in root.flow)


def _safety_overhead_per_run(
    *,
    root: MakeAstRoot,
    execution_mode: EstimateExecutionMode,
    module_only_node_id: str | None,
    safety_profile: OperationSafetyProfile,
    warnings: list[OperationEstimateWarning],
) -> int:
    """Return explicit safety overhead for the requested profile."""
    if safety_profile == "minimum_known":
        return 0
    retry_overhead = _configured_retry_overhead(
        root=root,
        execution_mode=execution_mode,
        module_only_node_id=module_only_node_id,
        warnings=warnings,
    )
    if safety_profile == "configured_profile":
        return retry_overhead
    handler_overhead = _missing_handler_safety_overhead(
        root=root,
        execution_mode=execution_mode,
        module_only_node_id=module_only_node_id,
    )
    if handler_overhead:
        warnings.append(
            _warning(
                code="estimate.safety_handler_overhead_included",
                node_id=None,
                client_message=(
                    "Worst reasonable local safety profile adds one handler "
                    "branch for "
                    "modules without direct error handlers."
                ),
                internal_message=(
                    "Worst reasonable local safety profile adds "
                    f"{handler_overhead} operation(s) per run for missing "
                    f"handler branches."
                ),
            )
        )
    return retry_overhead + handler_overhead


def _configured_retry_overhead(
    *,
    root: MakeAstRoot,
    execution_mode: EstimateExecutionMode,
    module_only_node_id: str | None,
    warnings: list[OperationEstimateWarning],
) -> int:
    """Return retry overhead from explicit local error-directive metadata."""
    overhead = 0
    unknown_retry_count_nodes: list[str] = []
    target_node_ids = _safety_profile_target_node_ids(
        root=root,
        execution_mode=execution_mode,
        module_only_node_id=module_only_node_id,
    )
    for directive in extract_error_directives(root):
        if (
            target_node_ids is not None
            and directive.node_id not in target_node_ids
        ):
            continue
        if directive.attempt_count is not None and directive.attempt_count > 0:
            overhead += directive.attempt_count
            continue
        if directive.retry is True:
            overhead += 1
            unknown_retry_count_nodes.append(directive.node_id)
    if overhead:
        internal_message = (
            f"Configured retry directives add {overhead} operation(s) per run."
        )
        warnings.append(
            _warning(
                code="estimate.configured_retry_overhead_included",
                node_id=None,
                client_message="Configured retry safety may add operations.",
                internal_message=internal_message,
            )
        )
    warnings.extend(
        (
            _warning(
                code="estimate.retry_count_unknown",
                node_id=node_id,
                client_message=(
                    "A retry directive lacks an explicit retry count."
                ),
                internal_message=(
                    f"Node {node_id} has retry=true without a numeric count."
                ),
            )
        )
        for node_id in sorted(set(unknown_retry_count_nodes))
    )
    return overhead


def _missing_handler_safety_overhead(
    *,
    root: MakeAstRoot,
    execution_mode: EstimateExecutionMode,
    module_only_node_id: str | None,
) -> int:
    """Return the computed result for the caller."""
    return sum(
        1
        for node in _safety_profile_target_nodes(
            root=root,
            execution_mode=execution_mode,
            module_only_node_id=module_only_node_id,
        )
        if _safety_handler_candidate(node)
    )


def _safety_profile_target_node_ids(
    *,
    root: MakeAstRoot,
    execution_mode: EstimateExecutionMode,
    module_only_node_id: str | None,
) -> frozenset[str] | None:
    """Return the computed result for the caller."""
    if execution_mode != "module_only":
        return None
    if module_only_node_id is None:
        return frozenset()
    _ = require_ast_node(root, module_only_node_id)
    return frozenset((module_only_node_id,))


def _safety_profile_target_nodes(
    *,
    root: MakeAstRoot,
    execution_mode: EstimateExecutionMode,
    module_only_node_id: str | None,
) -> tuple[MakeAstNode, ...]:
    """Return nodes affected by safety-profile overhead."""
    if execution_mode == "module_only":
        if module_only_node_id is None:
            return ()
        return (require_ast_node(root, module_only_node_id),)
    return tuple(_iter_safety_profile_nodes(root.flow))


def _iter_safety_profile_nodes(
    nodes: tuple[MakeAstNode, ...],
) -> tuple[MakeAstNode, ...]:
    """Return the computed result for the caller."""
    selected: list[MakeAstNode] = []
    for node in nodes:
        if node.kind != "router":
            selected.append(node)
        for route in (*node.routes, *node.branches, *node.tools):
            if not _route_disabled(route):
                selected.extend(_iter_safety_profile_nodes(route.flow))
        selected.extend(_iter_safety_profile_nodes(node.error_handlers))
    return tuple(selected)


def _safety_handler_candidate(node: MakeAstNode) -> bool:
    """Return whether worst-case local safety would add a handler branch."""
    return (
        node.kind != "router"
        and bool(node.module_token)
        and not node.error_handlers
    )


def _node_operation_count(
    node: MakeAstNode,
    warnings: list[OperationEstimateWarning],
) -> int:
    """Return conservative operation count for one node and descendants."""
    count = 0 if node.kind == "router" else 1
    _append_node_warnings(node, warnings)
    count += _routes_operation_count(
        (*node.routes, *node.branches, *node.tools), warnings
    )
    if node.error_handlers:
        warnings.append(
            _warning(
                code="estimate.error_routes_included",
                node_id=node.node_id,
                client_message=(
                    "Error-handler steps are included in the conservative "
                    "estimate."
                ),
                internal_message=(
                    f"Node {node.node_id} has direct error handlers."
                ),
            )
        )
    count += sum(
        _node_operation_count(handler, warnings)
        for handler in node.error_handlers
    )
    return count


def _routes_operation_count(
    routes: tuple[MakeAstRoute, ...],
    warnings: list[OperationEstimateWarning],
) -> int:
    """Return conservative operation count for route-like wrappers."""
    count = 0
    for route in routes:
        if _route_disabled(route):
            warnings.append(
                _warning(
                    code="estimate.disabled_route_skipped",
                    node_id=route.source_trace.parent_node_id,
                    client_message=(
                        "A disabled route is excluded from the planning "
                        "estimate."
                    ),
                    internal_message=(
                        f"Disabled route skipped: {route.route_id}."
                    ),
                )
            )
            continue
        count += sum(
            _node_operation_count(node, warnings) for node in route.flow
        )
    return count


def _append_node_warnings(
    node: MakeAstNode,
    warnings: list[OperationEstimateWarning],
) -> None:
    """Append node-specific estimator warnings."""
    if node.kind == "ai_agent" or node.tools:
        warnings.append(
            _warning(
                code="estimate.ai_tool_usage",
                node_id=node.node_id,
                client_message=(
                    "AI agent or tool usage may add variable runtime work."
                ),
                internal_message=f"Node {node.node_id} has AI/tool behavior.",
            )
        )
    if node.kind in {"iterator", "aggregator"}:
        warnings.append(
            _warning(
                code=f"estimate.{node.kind}_multiplier_unknown",
                node_id=node.node_id,
                client_message=(
                    "Iterator or aggregator volume may multiply operations."
                ),
                internal_message=(
                    f"Node {node.node_id} kind {node.kind} has unknown volume."
                ),
            )
        )
    if _contains_text(node.raw_payload, "page", node_local=True):
        warnings.append(
            _warning(
                code="estimate.pagination_volume_unknown",
                node_id=node.node_id,
                client_message=(
                    "Pagination may multiply operations beyond the static "
                    "module count."
                ),
                internal_message=(
                    f"Node {node.node_id} contains pagination-like text."
                ),
            )
        )


def _schedule_interval_minutes(payload: JsonObject) -> float | None:
    """Return schedule cadence in minutes when statically known."""
    every_minutes = _positive_number(payload.get("every_minutes"))
    if every_minutes is not None:
        return every_minutes
    every = _positive_number(payload.get("every"))
    unit = _optional_text(payload, "unit")
    interval_text = _optional_text(payload, "interval")
    if every is not None and unit is not None:
        return every * _unit_minutes(unit)
    interval_seconds = _positive_number(payload.get("interval"))
    if interval_seconds is not None:
        return interval_seconds / 60
    if interval_text is not None:
        unit_minutes = _unit_minutes(interval_text)
        if unit_minutes > 0:
            return unit_minutes
    text_interval = _text_interval_minutes(payload)
    if text_interval is not None:
        return text_interval
    return None


def _unit_minutes(unit: str) -> float:
    """Return minutes for a supported schedule unit."""
    normalized = unit.casefold().rstrip("s")
    if normalized in {"m", "min", "minute"}:
        return 1
    if normalized in {"h", "hr", "hour"}:
        return 60
    if normalized in {"d", "day", "daily"}:
        return 1_440
    if normalized in {"w", "week", "weekly"}:
        return 10_080
    if normalized in {"s", "sec", "second"}:
        return 1 / 60
    return 0


def _large_test_cost_warnings(
    estimated_operations: int,
) -> tuple[OperationEstimateWarning, ...]:
    """Return warning when a test horizon may be costly."""
    if estimated_operations <= HIGH_TEST_OPERATION_THRESHOLD:
        return ()
    return (
        _warning(
            code="estimate.large_test_cost",
            node_id=None,
            client_message="The test horizon may consume many operations.",
            internal_message=(
                f"Estimated operations {estimated_operations} exceedsthreshold."
            ),
        ),
    )


def _evidence_gap_codes(
    warnings: tuple[OperationEstimateWarning, ...],
) -> tuple[str, ...]:
    """Return warning codes that make the static estimate inexact."""
    gap_codes: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if not _warning_is_evidence_gap(warning.code) or warning.code in seen:
            continue
        seen.add(warning.code)
        gap_codes.append(warning.code)
    return tuple(gap_codes)


def _warning_is_evidence_gap(code: str) -> bool:
    """Return if one warning means required estimate evidence is missing."""
    return code in ESTIMATE_EVIDENCE_GAP_WARNING_CODES or code.endswith(
        "_multiplier_unknown"
    )


def _precision_label(
    evidence_gap_codes: tuple[str, ...],
) -> OperationEstimatePrecision:
    """Return precision label for the local static model."""
    if evidence_gap_codes:
        return "conservative_with_evidence_gaps"
    return "exact_static_model"


def _route_disabled(route: MakeAstRoute) -> bool:
    """Return whether a route-like wrapper is disabled."""
    return _truthy_flag(route.raw_payload.get("disabled")) or _disabled_flag(
        route.raw_payload.get("enabled"),
    )


def _truthy_flag(value: object) -> bool:
    """Return if a route flag is explicitly enabled by JSON-like evidence."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes"}
    return False


def _disabled_flag(value: object) -> bool:
    """Return if a route flag is explicitly disabled by JSON-like evidence."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, str):
        return value.strip().casefold() in {"0", "false", "no"}
    return False


def _positive_number(value: object) -> float | None:
    """Return a finite positive non-boolean number from JSON-like input."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value > 0:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 and math.isfinite(parsed) else None
    return None


def _text_interval_minutes(payload: JsonObject) -> float | None:
    """Return a text-declared interval when schedule metadata carries one."""
    for value in payload.values():
        if not isinstance(value, str):
            continue
        match = TEXT_INTERVAL_PATTERN.search(value)
        if match is None:
            continue
        amount = _positive_number(match.group("amount"))
        if amount is None:
            continue
        return amount * _unit_minutes(match.group("unit"))
    return None


def _optional_text(payload: JsonObject, key: str) -> str | None:
    """Return optional text from a JSON object."""
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _contains_text(
    value: object, needle: str, *, node_local: bool = False
) -> bool:
    """Return whether a JSON-like value contains text."""
    if isinstance(value, str):
        return needle.casefold() in value.casefold()
    if _is_json_object(value):
        return any(
            _contains_text(child, needle, node_local=False)
            for key, child in value.items()
            if not node_local or not _is_node_child_payload_key(key)
        )
    if isinstance(value, list):
        return any(
            _contains_text(child, needle, node_local=False)
            for child in cast("list[object]", value)
        )
    return False


def _is_node_child_payload_key(key: object) -> bool:
    """Return whether one root node payload key owns parsed child nodes."""
    return str(key) in NODE_CHILD_PAYLOAD_KEYS


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw_mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw_mapping)


def _warning(
    *,
    code: str,
    node_id: str | None,
    client_message: str,
    internal_message: str,
) -> OperationEstimateWarning:
    """Build one operation estimate warning.

    Returns:
        The constructed value.
    """
    return OperationEstimateWarning(
        code=code,
        node_id=node_id,
        client_message=client_message,
        internal_message=internal_message,
    )
