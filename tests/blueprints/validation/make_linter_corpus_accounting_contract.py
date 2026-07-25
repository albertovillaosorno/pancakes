# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for Make linter corpus accounting.

Boundary contract:
- Owns: non-loss accounting between split linter source ledgers, the master
  coverage map, and the manual decision ledger.
- Must not: activate linter behavior, read completed TODO archives, or inspect
  customer blueprints.
- Allows: static reads from sanitized linter corpus and decision JSON ledgers.
- Split when: candidate source reconstruction becomes an executable migration.
- Merge when: linter candidate intake persistence owns the same non-loss checks.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import TYPE_CHECKING, cast

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

type JsonObject = dict[str, object]

REPO_ROOT = repo_root()
LINTER_CORPUS_ROOT = (
    REPO_ROOT / "src" / "blueprints" / "validation" / "data" / "linter"
)
ACCOUNTING_PATH = (
    LINTER_CORPUS_ROOT / "corpus" / "linter-corpus-accounting.json"
)
COVERAGE_MAP_PATH = (
    LINTER_CORPUS_ROOT / "corpus" / "linter-master-coverage-map.json"
)
DECISION_LEDGER_PATH = (
    LINTER_CORPUS_ROOT / "decisions" / "linter-candidate-decisions.json"
)
EXPECTED_MASTER_CANDIDATE_COUNT = 1046
EXPECTED_DECISION_TOTALS: JsonObject = {
    "accepted": 0,
    "rewritten": 14,
    "downgraded": 262,
    "quarantined": 678,
    "rejected": 4,
    "aliased": 88,
    "pending_manual_review": 0,
}
DECISION_TOTAL_KEYS = {
    "accept": "accepted",
    "rewrite": "rewritten",
    "downgrade": "downgraded",
    "quarantine": "quarantined",
    "reject": "rejected",
    "alias_to_canonical": "aliased",
}


def test_linter_corpus_accounting_records_complete_review_state() -> None:
    """The compact corpus ledger records the closed manual-review counts."""
    accounting = load_json_object(ACCOUNTING_PATH)

    assert (
        str_member(accounting, "status")
        == "complete_manual_review_master_reconciled"
    )
    assert bool_member(accounting, "master_total_matches_split_total")
    assert (
        object_member(accounting, "decision_totals") == EXPECTED_DECISION_TOTALS
    )
    assert (
        int_member(
            object_member(accounting, "decision_totals"),
            "pending_manual_review",
        )
        == 0
    )
    assert (
        reviewed_candidate_total(accounting) == EXPECTED_MASTER_CANDIDATE_COUNT
    )


def test_linter_master_coverage_map_preserves_every_candidate_once() -> None:
    """The master coverage map has one record for every split candidate ID."""
    accounting = load_json_object(ACCOUNTING_PATH)
    coverage_map = load_json_object(COVERAGE_MAP_PATH)
    split_candidate_ids = split_source_candidate_ids(accounting)
    coverage_records = object_rows(coverage_map, "records")
    coverage_candidate_ids = tuple(
        str_member(record, "candidate_id") for record in coverage_records
    )
    duplicates = duplicate_items(coverage_candidate_ids)

    assert str_member(coverage_map, "coverage_state") == "complete"
    assert (
        int_member(coverage_map, "master_candidate_count")
        == EXPECTED_MASTER_CANDIDATE_COUNT
    )
    assert (
        int_member(coverage_map, "split_candidate_count")
        == EXPECTED_MASTER_CANDIDATE_COUNT
    )
    assert string_rows(coverage_map, "unmapped_master_candidate_ids") == ()
    assert string_rows(coverage_map, "extra_split_candidate_ids") == ()
    assert len(coverage_candidate_ids) == EXPECTED_MASTER_CANDIDATE_COUNT
    assert not duplicates, (
        f"Duplicate master coverage candidate IDs: {duplicates}"
    )
    assert frozenset(coverage_candidate_ids) == frozenset(split_candidate_ids)


def test_linter_decision_ledger_matches_accounting_sources() -> None:
    """Every split source candidate has exactly one closed decision record."""
    accounting = load_json_object(ACCOUNTING_PATH)
    decision_ledger = load_json_object(DECISION_LEDGER_PATH)
    decision_sources = source_records_by_file(decision_ledger)
    actual_totals: Counter[str] = Counter(
        dict.fromkeys(DECISION_TOTAL_KEYS.values(), 0)
    )
    diagnostics: list[str] = []

    for source in split_source_rows(accounting):
        source_file = str_member(source, "source_file")
        decision_source = decision_sources.get(source_file)
        if decision_source is None:
            diagnostics.append(f"{source_file}: missing from decision ledger")
            continue
        expected_ids = string_rows(source, "parsed_unique_candidate_ids")
        actual_records = object_rows(decision_source, "records")
        actual_ids = tuple(
            str_member(record, "candidate_id") for record in actual_records
        )
        if actual_ids != expected_ids:
            diagnostics.append(
                f"{source_file}: decision record order or IDs drifted"
            )
        for record in actual_records:
            decision = str_member(record, "decision")
            total_key = DECISION_TOTAL_KEYS.get(decision)
            if total_key is None:
                diagnostics.append(
                    f"{source_file}: unsupported decision {decision!r}"
                )
            else:
                actual_totals[total_key] += 1

    expected_totals = dict(EXPECTED_DECISION_TOTALS)
    _ = expected_totals.pop("pending_manual_review")
    assert not diagnostics, f"Linter decision ledger drifted: {diagnostics}"
    assert dict(actual_totals) == expected_totals


def reviewed_candidate_total(accounting: JsonObject) -> int:
    """Return the total parsed split-source candidate count."""
    return sum(
        int_member(source, "parsed_unique_candidate_id_count")
        for source in split_source_rows(accounting)
    )


def split_source_candidate_ids(accounting: JsonObject) -> tuple[str, ...]:
    """Return all split-source candidate IDs in ledger order."""
    return tuple(
        candidate_id
        for source in split_source_rows(accounting)
        for candidate_id in string_rows(source, "parsed_unique_candidate_ids")
    )


def split_source_rows(accounting: JsonObject) -> tuple[JsonObject, ...]:
    """Return accounting rows that own imported split-source candidates."""
    return tuple(
        source
        for source in object_rows(accounting, "sources")
        if int_member(source, "parsed_unique_candidate_id_count") > 0
        and str_member(source, "source_file")
        != str_member(accounting, "master_source_file")
    )


def source_records_by_file(
    decision_ledger: JsonObject,
) -> dict[str, JsonObject]:
    """Return decision-ledger source rows keyed by source file."""
    return {
        str_member(source, "source_file"): source
        for source in object_rows(decision_ledger, "sources")
    }


def duplicate_items(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return values that occur more than once."""
    counts = Counter(values)
    return tuple(sorted(value for value, count in counts.items() if count > 1))


def load_json_object(path: Path) -> JsonObject:
    """Load one JSON object payload from a repository path.

    Returns:
        The parsed JSON object.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"JSON payload must be an object: {path}"
    return cast("JsonObject", payload)


def object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return one object member."""
    value = payload.get(key)
    assert isinstance(value, dict), (
        f"JSON member {key!r} must be an object: {payload}"
    )
    return cast("JsonObject", value)


def object_rows(payload: JsonObject, key: str) -> tuple[JsonObject, ...]:
    """Return one list-of-objects member."""
    value = payload.get(key)
    assert isinstance(value, list), (
        f"JSON member {key!r} must be a list: {payload}"
    )
    rows: list[JsonObject] = []
    for item in cast("list[object]", value):
        assert isinstance(item, dict), (
            f"JSON member {key!r} must contain objects: {payload}"
        )
        rows.append(cast("JsonObject", item))
    return tuple(rows)


def string_rows(payload: JsonObject, key: str) -> tuple[str, ...]:
    """Return one list-of-strings member."""
    value = payload.get(key)
    assert isinstance(value, list), (
        f"JSON member {key!r} must be a list: {payload}"
    )
    rows: list[str] = []
    for item in cast("list[object]", value):
        assert isinstance(item, str), (
            f"JSON member {key!r} must contain strings: {payload}"
        )
        rows.append(item)
    return tuple(rows)


def bool_member(payload: JsonObject, key: str) -> bool:
    """Return one boolean member."""
    value = payload.get(key)
    assert isinstance(value, bool), (
        f"JSON member {key!r} must be a boolean: {payload}"
    )
    return value


def int_member(payload: JsonObject, key: str) -> int:
    """Return one integer member."""
    value = payload.get(key)
    assert isinstance(value, int), (
        f"JSON member {key!r} must be an integer: {payload}"
    )
    assert not isinstance(value, bool), (
        f"JSON member {key!r} must be an integer: {payload}"
    )
    return value


def str_member(payload: JsonObject, key: str) -> str:
    """Return one string member."""
    value = payload.get(key)
    assert isinstance(value, str), (
        f"JSON member {key!r} must be a string: {payload}"
    )
    return value
