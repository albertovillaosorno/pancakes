# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001055#repo.mcp.required-tool-surface
# - 001068#repo.operator-commands.diff-blueprint.structured-comparison
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Make roundtrip re-export parity corpus loader.

Boundary contract:
- Owns: loading the private local generated-vs-reexport parity corpus.
- Must not: call Make.com, read browser state, store provider payloads, or
  activate candidates.
- Allows: deterministic offline checks that every observed delta routes to a
  general rule.
- Split when: live Browser maintenance produces sanitized persisted re-export
  captures.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, TypeGuard, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

JsonObject = dict[str, object]

ROUNDTRIP_REEXPORT_PARITY_ASSET: Final = "make_roundtrip_reexport_parity_corpus"
ROUNDTRIP_REEXPORT_PARITY_PATH: Final = (
    Path(__file__).with_name("data") / "roundtrip_reexport_parity_corpus.json"
)
REQUIRED_ROUNDTRIP_PARITY_CATEGORIES: Final[frozenset[str]] = frozenset(
    (
        "filter_shape_delta",
        "layout_delta",
        "mapper_shape_delta",
        "metadata_expect_missing",
        "native_parity_gap",
        "restore_missing",
        "runtime_resource_placeholder",
        "semantic_lineage_breakage",
        "volatile_make_noise",
        "zero_trace_violation",
    )
)
REQUIRED_ROUNDTRIP_TOPOLOGIES: Final[frozenset[str]] = frozenset(
    (
        "aggregators",
        "ai_modules",
        "dynamic_placeholders",
        "error_handlers",
        "filters",
        "large_canvas_layout",
        "notes",
        "routers",
    )
)


class MakeRoundtripParityCategoryRecord(NamedTuple):
    """One Make roundtrip parity category and its deterministic rule target."""

    category: str
    severity: str
    roundtrip_discovery_class: str
    rule_target: str
    stable_normalization_rule: str
    fixture_triplets: tuple[str, ...]
    deterministic_tests: tuple[str, ...]
    promotion_gate: str


class MakeRoundtripParityFixtureTriplet(NamedTuple):
    """One local generated/re-export/known-good fixture triplet."""

    triplet_id: str
    generated_path: str
    make_reexport_path: str
    known_good_path: str
    topology_coverage: tuple[str, ...]
    expected_categories: tuple[str, ...]
    zero_trace_posture: str


def load_make_roundtrip_reexport_parity_payload() -> JsonObject:
    """Return the private roundtrip re-export parity corpus payload.

    Raises:
        TypeError: If the corpus root or a required member is not the
            expected JSON shape.
    """
    raw = cast(
        "object",
        json.loads(ROUNDTRIP_REEXPORT_PARITY_PATH.read_text(encoding="utf-8")),
    )
    if not _is_json_object(raw):
        message = (
            "Expected roundtrip parity object: "
            f"{ROUNDTRIP_REEXPORT_PARITY_PATH}"
        )
        raise TypeError(message)
    _validate_payload(raw)
    return raw


def make_roundtrip_parity_category_records() -> tuple[
    MakeRoundtripParityCategoryRecord, ...
]:
    """Return roundtrip parity category records in source order."""
    payload = load_make_roundtrip_reexport_parity_payload()
    return tuple(
        _category_record(record)
        for record in _json_object_list(
            payload.get("categories"), member_name="categories"
        )
    )


def make_roundtrip_parity_fixture_triplets() -> tuple[
    MakeRoundtripParityFixtureTriplet, ...
]:
    """Return local fixture triplets in source order."""
    payload = load_make_roundtrip_reexport_parity_payload()
    return tuple(
        _fixture_triplet(record)
        for record in _json_object_list(
            payload.get("fixture_triplets"),
            member_name="fixture_triplets",
        )
    )


def make_roundtrip_parity_category_record(
    category: str,
) -> MakeRoundtripParityCategoryRecord | None:
    """Return one category record by Make-native diff category."""
    normalized = category.casefold().strip()
    for record in make_roundtrip_parity_category_records():
        if record.category.casefold() == normalized:
            return record
    return None


def _validate_payload(payload: Mapping[str, object]) -> None:
    if payload.get("schema_version") != 1:
        message = (
            "Unsupported roundtrip parity schema: "
            f"{payload.get('schema_version')!r}"
        )
        raise ValueError(message)
    if payload.get("asset") != ROUNDTRIP_REEXPORT_PARITY_ASSET:
        message = f"Unexpected roundtrip parity asset: {payload.get('asset')!r}"
        raise ValueError(message)
    safety = _json_object(
        payload.get("safety_contract"), member_name="safety_contract"
    )
    if any(bool(value) for value in safety.values()):
        message = (
            "Roundtrip parity corpus must not claim live or "
            "secret-bearing capture."
        )
        raise ValueError(message)
    records = tuple(
        _category_record(record)
        for record in _json_object_list(
            payload.get("categories"), member_name="categories"
        )
    )
    categories = frozenset(record.category for record in records)
    if categories != REQUIRED_ROUNDTRIP_PARITY_CATEGORIES:
        message = f"Roundtrip parity categories drifted: {sorted(categories)}"
        raise ValueError(message)


def _category_record(payload: JsonObject) -> MakeRoundtripParityCategoryRecord:
    return MakeRoundtripParityCategoryRecord(
        category=_required_text(payload, "category"),
        severity=_required_text(payload, "severity"),
        roundtrip_discovery_class=_required_text(
            payload, "roundtrip_discovery_class"
        ),
        rule_target=_required_text(payload, "rule_target"),
        stable_normalization_rule=_required_text(
            payload, "stable_normalization_rule"
        ),
        fixture_triplets=_required_text_tuple(payload, "fixture_triplets"),
        deterministic_tests=_required_text_tuple(
            payload, "deterministic_tests"
        ),
        promotion_gate=_required_text(payload, "promotion_gate"),
    )


def _fixture_triplet(payload: JsonObject) -> MakeRoundtripParityFixtureTriplet:
    return MakeRoundtripParityFixtureTriplet(
        triplet_id=_required_text(payload, "triplet_id"),
        generated_path=_required_text(payload, "generated_path"),
        make_reexport_path=_required_text(payload, "make_reexport_path"),
        known_good_path=_required_text(payload, "known_good_path"),
        topology_coverage=_required_text_tuple(payload, "topology_coverage"),
        expected_categories=_required_text_tuple(
            payload, "expected_categories"
        ),
        zero_trace_posture=_required_text(payload, "zero_trace_posture"),
    )


def _json_object(value: object, *, member_name: str) -> JsonObject:
    if not _is_json_object(value):
        message = f"Expected object at roundtrip parity member {member_name!r}."
        raise TypeError(message)
    return value


def _json_object_list(
    value: object, *, member_name: str
) -> tuple[JsonObject, ...]:
    if not isinstance(value, list):
        message = f"Expected list at roundtrip parity member {member_name!r}."
        raise TypeError(message)
    return tuple(
        _json_object(item, member_name=member_name)
        for item in cast("list[object]", value)
    )


def _required_text(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Missing roundtrip parity text field {key!r}."
        raise ValueError(message)
    return value.strip()


def _required_text_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Expected list at roundtrip parity field {key!r}."
        raise TypeError(message)
    strings: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str) or not item.strip():
            message = (
                f"Expected non-empty string at roundtrip parity field {key!r}."
            )
            raise TypeError(message)
        strings.append(item.strip())
    return tuple(strings)


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    raw = cast("Mapping[object, object]", value)
    return all(isinstance(key, str) for key in raw)
