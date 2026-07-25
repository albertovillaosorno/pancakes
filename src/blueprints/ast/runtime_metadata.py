# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001044#repo.make-ast.unknown-fields-preserved
# - 001061#repo.delivery.live-verification-explicit-only
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Runtime metadata introspection for parsed Make blueprints.

Boundary contract:
- Owns: extracting runtime metadata embedded in parsed blueprint exports.
- Must not: call live services, compute AST deltas, or validate business logic.
- Allows: filter, error, note, orphan, latency, and mapping-event records.
- Split when: one metadata family needs independent policy or normalization.
- Merge when: another metadata inspector emits the same aggregate contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import TYPE_CHECKING, NamedTuple, TypeGuard, cast

from blueprints.ast.orphans import (
    DesignerOrphanGroup,
    extract_designer_orphan_groups,
)
from blueprints.ast.runtime_drift import (
    DesignerMessageEvidence,
    collect_designer_message_evidence,
)
from blueprints.ast.traversal import iter_ast_nodes

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject, MakeAstRoot


class BlueprintRuntimeFilterCondition(NamedTuple):
    """One normalized route or module filter condition."""

    left_operand: str
    operator: str
    right_operand: str
    label_name: str | None
    combinator: str | None
    raw_condition: JsonObject


class BlueprintErrorDirective(NamedTuple):
    """One normalized on-error directive."""

    node_id: str
    strategy: str
    attempt_count: int | None
    interval: int | None
    retry: bool | None
    raw_directive: JsonObject


class BlueprintRuntimeNote(NamedTuple):
    """One root-level Make designer note."""

    note_id: str
    html: str
    text: str
    color: str | None


class BlueprintLatencyObservation(NamedTuple):
    """One elapsed-time observation carried by a node export."""

    node_id: str
    module_token: str
    elapsed_seconds: float
    element_actions_count: int


class BlueprintRuntimeSampleObservation(NamedTuple):
    """One redacted Make designer sample observation."""

    node_id: str
    sample_path: str
    sample_keys: tuple[str, ...]
    metadata_keys: tuple[str, ...]
    execution_step_count: int
    token_usage_keys: tuple[str, ...]
    shape_fingerprint_sha256: str


class BlueprintRuntimeMetadata(NamedTuple):
    """Aggregated Make runtime metadata extracted from one AST."""

    filters: tuple[BlueprintRuntimeFilterCondition, ...]
    designer_messages: tuple[DesignerMessageEvidence, ...]
    error_directives: tuple[BlueprintErrorDirective, ...]
    notes: tuple[BlueprintRuntimeNote, ...]
    orphans: tuple[DesignerOrphanGroup, ...]
    latency: tuple[BlueprintLatencyObservation, ...]
    mapping_events: tuple[JsonObject, ...]
    samples: tuple[BlueprintRuntimeSampleObservation, ...]


def inspect_blueprint_runtime_metadata(
    root: MakeAstRoot,
) -> BlueprintRuntimeMetadata:
    """Extract filter, error, note, orphan, latency, and mapping metadata.

    Returns:
        The extracted filter, error, note, orphan, latency, and mapping
        metadata.
    """
    return BlueprintRuntimeMetadata(
        filters=extract_runtime_filter_conditions(root),
        designer_messages=collect_designer_message_evidence(root),
        error_directives=extract_error_directives(root),
        notes=extract_runtime_notes(root),
        orphans=extract_designer_orphan_groups(root),
        latency=extract_latency_observations(root),
        mapping_events=extract_forman_mapping_events(root),
        samples=extract_runtime_sample_observations(root),
    )


def extract_runtime_filter_conditions(
    root: MakeAstRoot,
) -> tuple[BlueprintRuntimeFilterCondition, ...]:
    """Extract normalized filter predicates from parsed AST routes.

    Returns:
        The extracted normalized filter predicates from parsed AST routes.
    """
    conditions: list[BlueprintRuntimeFilterCondition] = []
    for node in iter_ast_nodes(root):
        for route in (*node.routes, *node.branches, *node.tools):
            if route.filter is not None:
                conditions.extend(
                    _filter_conditions_from_payload(route.filter.raw_payload)
                )
    return tuple(conditions)


def extract_error_directives(
    root: MakeAstRoot,
) -> tuple[BlueprintErrorDirective, ...]:
    """Extract normalized on-error directives from parsed AST nodes.

    Returns:
        The extracted normalized on-error directives from parsed AST nodes.
    """
    directives: list[BlueprintErrorDirective] = []
    for node in iter_ast_nodes(root):
        for key in ("onerror", "on_error"):
            directives.extend(
                _directives_from_payload(
                    node.raw_payload.get(key), node_id=node.node_id
                )
            )
    return tuple(directives)


def extract_runtime_notes(
    root: MakeAstRoot,
) -> tuple[BlueprintRuntimeNote, ...]:
    """Extract rich note metadata embedded in root blueprint metadata.

    Returns:
        The extracted rich note metadata embedded in root blueprint metadata.
    """
    notes: list[BlueprintRuntimeNote] = []
    for container in _note_containers(root.scenario.metadata):
        if not isinstance(container, list):
            continue
        for index, item in enumerate(cast("list[object]", container), start=1):
            if not _is_json_object(item):
                continue
            html = _first_string_text(item, ("content", "html", "text"))
            if not html:
                continue
            metadata = _object_or_empty(item.get("metadata"))
            color = _optional_string_text(metadata.get("color"))
            if color is None:
                color = _optional_string_text(item.get("color"))
            notes.append(
                BlueprintRuntimeNote(
                    note_id=_note_id_text(item.get("id"), fallback_index=index),
                    html=html,
                    text=_strip_html(html),
                    color=color,
                )
            )
    return tuple(notes)


def extract_latency_observations(
    root: MakeAstRoot,
) -> tuple[BlueprintLatencyObservation, ...]:
    """Extract observed elapsed times from node metadata.

    Returns:
        The extracted observed elapsed times from node metadata.
    """
    observations: list[BlueprintLatencyObservation] = []
    for node in iter_ast_nodes(root):
        elapsed = _coerce_elapsed_seconds(
            node.raw_payload.get("elapsed")
            if "elapsed" in node.raw_payload
            else _nested_get(node.raw_payload, "metadata", "elapsed")
        )
        if elapsed is None:
            continue
        element_actions = node.raw_payload.get("element_actions")
        action_count = (
            len(cast("list[object]", element_actions))
            if isinstance(element_actions, list)
            else 0
        )
        observations.append(
            BlueprintLatencyObservation(
                node_id=node.node_id,
                module_token=node.module_token,
                elapsed_seconds=elapsed,
                element_actions_count=action_count,
            )
        )
    return tuple(observations)


def extract_forman_mapping_events(root: MakeAstRoot) -> tuple[JsonObject, ...]:
    """Extract Forman auto-complete events from explicit metadata containers.

    Returns:
        The extracted Forman auto-complete events from explicit metadata
        containers.
    """
    events: list[JsonObject] = []
    for container in _forman_event_containers(root):
        events.extend(_forman_events_from_container(container))
    deduped: list[JsonObject] = []
    seen: set[str] = set()
    for event in events:
        fingerprint = _payload_fingerprint(event)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        deduped.append(event)
    return tuple(deduped)


def extract_runtime_sample_observations(
    root: MakeAstRoot,
) -> tuple[BlueprintRuntimeSampleObservation, ...]:
    """Extract redacted sample-shape evidence from Make designer metadata.

    Returns:
        Redacted designer sample observations keyed by module id.
    """
    designer = _object_or_empty(root.scenario.metadata.get("designer"))
    samples = designer.get("samples")
    if not _is_json_object(samples):
        return ()
    observations: list[BlueprintRuntimeSampleObservation] = []
    for raw_node_id, sample in sorted(samples.items()):
        node_id = _optional_string_text(raw_node_id)
        if node_id is None or not _is_json_object(sample):
            continue
        metadata = _object_or_empty(sample.get("metadata"))
        token_usage = _object_or_empty(metadata.get("tokenUsageSummary"))
        if not token_usage:
            token_usage = _first_execution_step_token_usage(metadata)
        observations.append(
            BlueprintRuntimeSampleObservation(
                node_id=node_id,
                sample_path=f"$.metadata.designer.samples.{node_id}",
                sample_keys=tuple(sorted(sample)),
                metadata_keys=tuple(sorted(metadata)),
                execution_step_count=_execution_step_count(metadata),
                token_usage_keys=tuple(sorted(token_usage)),
                shape_fingerprint_sha256=_shape_fingerprint(sample),
            )
        )
    return tuple(observations)


def _filter_conditions_from_payload(
    payload: object,
) -> tuple[BlueprintRuntimeFilterCondition, ...]:
    """Extract normalized filter conditions from one heterogeneous payload.

    Returns:
        The normalized filter conditions extracted from a heterogeneous payload.
    """
    if not _is_json_object(payload):
        return ()
    label_name = _optional_text(
        payload.get("label_name") or payload.get("label") or payload.get("name")
    )
    combinator = _filter_combinator(payload)
    raw_conditions = payload.get("conditions")
    normalized: tuple[BlueprintRuntimeFilterCondition, ...] = ()
    if isinstance(raw_conditions, list):
        normalized = _filter_conditions_from_list(
            cast("list[object]", raw_conditions),
            label_name=label_name,
            combinator=combinator,
        )
    elif _is_json_object(raw_conditions):
        normalized = (
            _build_filter_condition(
                raw_conditions,
                label_name=label_name,
                combinator=combinator,
            ),
        )
    else:
        normalized = _filter_conditions_from_aliases(
            payload,
            label_name=label_name,
            combinator=combinator,
        )
    return normalized


def _filter_conditions_from_list(
    raw_conditions: list[object],
    *,
    label_name: str | None,
    combinator: str | None,
) -> tuple[BlueprintRuntimeFilterCondition, ...]:
    """Extract condition objects from Make's nested AND/OR condition arrays.

    Returns:
        The flattened native Make filter conditions.
    """
    conditions: list[BlueprintRuntimeFilterCondition] = []
    for item in raw_conditions:
        if _is_json_object(item):
            conditions.append(
                _build_filter_condition(
                    item, label_name=label_name, combinator=combinator
                )
            )
            continue
        if isinstance(item, list):
            conditions.extend(
                _filter_conditions_from_list(
                    cast("list[object]", item),
                    label_name=label_name,
                    combinator=combinator,
                )
            )
    return tuple(conditions)


def _filter_conditions_from_aliases(
    payload: JsonObject,
    *,
    label_name: str | None,
    combinator: str | None,
) -> tuple[BlueprintRuntimeFilterCondition, ...]:
    """Extract normalized filter conditions from non-canonical aliases.

    Returns:
        The normalized filter conditions extracted from alias payloads.
    """
    normalized: tuple[BlueprintRuntimeFilterCondition, ...] = ()
    if isinstance(payload.get("rules"), list):
        raw_rules = cast("list[object]", payload["rules"])
        normalized = tuple(
            _build_filter_condition(
                item, label_name=label_name, combinator=combinator
            )
            for item in raw_rules
            if _is_json_object(item)
        )
    elif _is_json_object(payload.get("rules")):
        raw_rules = cast("JsonObject", payload["rules"])
        normalized = (
            _build_filter_condition(
                raw_rules,
                label_name=label_name,
                combinator=combinator,
            ),
        )
    elif _is_json_object(payload.get("expression")):
        raw_expression = cast("JsonObject", payload["expression"])
        normalized = (
            _build_filter_condition(
                raw_expression,
                label_name=label_name,
                combinator=combinator,
            ),
        )
    elif _is_non_empty_scalar(payload.get("expression")):
        raw_expression = payload["expression"]
        normalized = (
            _build_filter_condition(
                {"expression": raw_expression},
                label_name=label_name,
                combinator=combinator,
            ),
        )
    elif _is_json_object(payload.get("condition")):
        raw_condition = cast("JsonObject", payload["condition"])
        normalized = (
            _build_filter_condition(
                raw_condition,
                label_name=label_name,
                combinator=combinator,
            ),
        )
    elif _is_non_empty_scalar(payload.get("condition")):
        raw_condition = payload["condition"]
        normalized = (
            _build_filter_condition(
                {"condition": raw_condition},
                label_name=label_name,
                combinator=combinator,
            ),
        )
    elif any(
        key in payload
        for key in ("a", "b", "left", "right", "operator", "field")
    ):
        normalized = (
            _build_filter_condition(
                payload, label_name=label_name, combinator=combinator
            ),
        )
    return normalized


def _build_filter_condition(
    condition: JsonObject,
    *,
    label_name: str | None,
    combinator: str | None,
) -> BlueprintRuntimeFilterCondition:
    """Normalize one Make filter condition payload.

    Returns:
        The normalized Make filter condition payload.
    """
    return BlueprintRuntimeFilterCondition(
        left_operand=_first_text(
            condition,
            (
                "a ",
                "left ",
                "lhs ",
                "operand1 ",
                "field ",
                "expression ",
                "condition",
            ),
        ),
        operator=_first_text(
            condition, ("o", "operator", "op", "comparison", "type")
        ),
        right_operand=_first_text(
            condition, ("b", "right", "rhs", "operand2", "value")
        ),
        label_name=label_name,
        combinator=combinator,
        raw_condition=dict(condition),
    )


def _filter_combinator(payload: JsonObject) -> str | None:
    """Return a route-level filter combinator when it is explicit."""
    explicit = _optional_text(
        payload.get("combinator") or payload.get("operator")
    )
    if explicit is not None:
        return explicit
    raw_condition = _optional_text(payload.get("condition"))
    if raw_condition is not None and raw_condition.lower() in {
        "all ",
        "and ",
        "any ",
        "or",
    }:
        return raw_condition
    return None


def _directives_from_payload(
    payload: object,
    *,
    node_id: str,
) -> tuple[BlueprintErrorDirective, ...]:
    """Normalize heterogeneous on-error payloads into directives.

    Returns:
        The normalized heterogeneous on-error payloads into directives.
    """
    if isinstance(payload, list):
        return tuple(
            directive
            for item in cast("list[object]", payload)
            for directive in _directives_from_payload(item, node_id=node_id)
        )
    if not _is_json_object(payload):
        return ()
    retry_payload = payload.get("retry")
    retry_mapping = _object_or_empty(retry_payload)
    strategy = _first_text(payload, ("strategy", "directive", "name", "module"))
    if not strategy:
        return ()
    return (
        BlueprintErrorDirective(
            node_id=node_id,
            strategy=strategy,
            attempt_count=_coerce_int(
                _mapping_preferred_value(retry_mapping, payload, "count")
            ),
            interval=_coerce_int(
                _mapping_preferred_value(retry_mapping, payload, "interval")
            ),
            retry=True if retry_mapping else _coerce_bool(retry_payload),
            raw_directive=dict(payload),
        ),
    )


def _note_containers(metadata: JsonObject) -> tuple[object, ...]:
    """Return Make-native note containers from root metadata only."""
    designer = _object_or_empty(metadata.get("designer"))
    return (metadata.get("notes"), designer.get("notes"))


def _forman_event_containers(root: MakeAstRoot) -> tuple[object, ...]:
    """Return metadata event containers that can hold Forman UI events."""
    containers = [root.scenario.metadata.get("events")]
    designer = _object_or_empty(root.scenario.metadata.get("designer"))
    containers.append(designer.get("events"))
    for node in iter_ast_nodes(root):
        metadata = _object_or_empty(node.raw_payload.get("metadata"))
        containers.append(metadata.get("events"))
        node_designer = _object_or_empty(metadata.get("designer"))
        containers.append(node_designer.get("events"))
    return tuple(containers)


def _forman_events_from_container(container: object) -> tuple[JsonObject, ...]:
    """Return Forman mapping events from one explicit metadata container."""
    if isinstance(container, list):
        return tuple(
            event
            for item in cast("list[object]", container)
            for event in _forman_events_from_container(item)
        )
    event = _object_or_empty(container)
    event_name = str(
        event.get("event") or event.get("event_name") or ""
    ).strip()
    return (dict(event),) if event_name == "forman_auto_complete_open" else ()


def _first_execution_step_token_usage(metadata: JsonObject) -> JsonObject:
    """Return the first execution-step token usage object when present."""
    steps = metadata.get("executionSteps")
    if not isinstance(steps, list):
        return {}
    for step in cast("list[object]", steps):
        step_payload = _object_or_empty(step)
        token_usage = _object_or_empty(step_payload.get("tokenUsage"))
        if token_usage:
            return token_usage
    return {}


def _execution_step_count(metadata: JsonObject) -> int:
    """Return the count of object-shaped execution steps in sample metadata."""
    steps = metadata.get("executionSteps")
    if not isinstance(steps, list):
        return 0
    return sum(
        1 for step in cast("list[object]", steps) if _is_json_object(step)
    )


def _nested_get(mapping: JsonObject, *keys: str) -> object:
    """Return a nested value from one mapping."""
    current: object = mapping
    for key in keys:
        if not _is_json_object(current):
            return None
        current = current.get(key)
    return current


def _coerce_elapsed_seconds(value: object) -> float | None:
    """Convert elapsed metadata into seconds when possible.

    Returns:
        The documented result.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        parsed = float(value)
        return parsed if parsed >= 0 and math.isfinite(parsed) else None
    if isinstance(value, str):
        try:
            parsed = float(value.strip().lower().removesuffix("s"))
        except ValueError:
            return None
        return parsed if parsed >= 0 and math.isfinite(parsed) else None
    return None


def _coerce_int(value: object) -> int | None:
    """Convert one numeric-like value to int when possible.

    Returns:
        The documented result.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _coerce_bool(value: object) -> bool | None:
    """Convert one bool-like payload into bool when possible.

    Returns:
        The documented result.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _first_text(mapping: JsonObject, keys: tuple[str, ...]) -> str:
    """Return the first non-empty text value from known keys."""
    for key in keys:
        value = mapping.get(key)
        if _is_non_empty_scalar(value):
            return str(value).strip()
    return ""


def _optional_text(value: object) -> str | None:
    """Return a stripped optional text value."""
    text = str(value).strip() if _is_non_empty_scalar(value) else ""
    return text or None


def _first_string_text(mapping: JsonObject, keys: tuple[str, ...]) -> str:
    """Return the first non-empty string from known keys."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _optional_string_text(value: object) -> str | None:
    """Return optional text only when the source value is already text."""
    text = value.strip() if isinstance(value, str) else ""
    return text or None


def _note_id_text(value: object, *, fallback_index: int) -> str:
    """Return a note id without synthesizing text from containers."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return str(value)
    return f"note:{fallback_index}"


def _is_non_empty_scalar(value: object) -> bool:
    """Return whether a value can be carried as one scalar filter expression."""
    if isinstance(value, bool):
        return False
    return isinstance(value, str | int | float) and bool(str(value).strip())


def _object_or_empty(value: object) -> JsonObject:
    """Return a JSON object or an empty object."""
    return value if _is_json_object(value) else {}


def _mapping_preferred_value(
    primary: JsonObject, fallback: JsonObject, key: str
) -> object:
    """Return primary value by key presence without treating zero as absent."""
    return primary[key] if key in primary else fallback.get(key)


def _strip_html(html: str) -> str:
    """Return a plain-text representation of HTML note content."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _payload_fingerprint(value: JsonObject) -> str:
    """Return a deterministic SHA-256 hex digest for JSON-compatible data."""
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def _shape_fingerprint(value: JsonObject) -> str:
    """Return a deterministic SHA-256 hex digest for a redacted JSON shape."""
    return hashlib.sha256(
        json.dumps(
            _redacted_shape(value),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _redacted_shape(value: object) -> object:
    """Return the computed result for the caller."""
    if _is_json_object(value):
        return {
            key: _redacted_shape(item) for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        array_value = cast("list[object]", value)
        return {
            "count": len(array_value),
            "items": [_redacted_shape(item) for item in array_value[:3]],
            "type": "array",
        }
    scalar_shape = _scalar_shape_label(value)
    return scalar_shape if scalar_shape is not None else type(value).__name__


def _scalar_shape_label(value: object) -> str | None:
    """Return a stable shape label for JSON scalar values."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, str):
        return "string"
    return None


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    """Return whether a value is a string-keyed JSON object."""
    if not isinstance(value, dict):
        return False
    raw = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in raw)
