# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make roundtrip re-export parity corpus contracts.

Boundary contract:
- Owns: deterministic validation for local generated-vs-reexport parity
fixtures.
- Must not: call Make.com, use authenticated browser state, or persist live
provider exports.
- Allows: synthetic fixture triplets and strict-redacted diff/evidence
assertions.
- Split when: live Browser import/export captures become sanitized persisted
evidence.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from languages.make.roundtrip_parity import (
    REQUIRED_ROUNDTRIP_PARITY_CATEGORIES,
    REQUIRED_ROUNDTRIP_TOPOLOGIES,
    load_make_roundtrip_reexport_parity_payload,
    make_roundtrip_parity_category_record,
    make_roundtrip_parity_category_records,
    make_roundtrip_parity_fixture_triplets,
)
from mcp.diff_blueprint import diff_blueprint
from mcp.reexport_evidence import ingest_make_reexport_evidence

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
CORPUS_PATH = "src/languages/make/data/roundtrip_reexport_parity_corpus.json"
INVENTORY_PATH = "src/languages/make/data/non_raw_evidence_inventory.json"
LIVE_JSON_PARSE_GENERATED = (
    "tests/blueprints/fixtures/diff_blueprint/live_api_roundtrip/"
    "json_parse_generated.json"
)
LIVE_JSON_PARSE_REEXPORT = (
    "tests/blueprints/fixtures/diff_blueprint/live_api_roundtrip/"
    "json_parse_make_reexport.json"
)
LIVE_JSON_PARSE_KNOWN_GOOD = (
    "tests/blueprints/fixtures/diff_blueprint/live_api_roundtrip/"
    "json_parse_known_good.json"
)


def test_roundtrip_parity_corpus_covers_required_categories_and_scope() -> None:
    """The local corpus accounts for every current Make re-export parity.

    class.
    """
    payload = load_make_roundtrip_reexport_parity_payload()
    safety = cast("JsonObject", payload["safety_contract"])
    assert safety == {
        "live_make_called": False,
        "authenticated_make_ui_used": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "customer_facing": False,
    }

    category_records = make_roundtrip_parity_category_records()
    assert {record.category for record in category_records} == (
        REQUIRED_ROUNDTRIP_PARITY_CATEGORIES
    )
    for record in category_records:
        assert record.fixture_triplets, (
            f"Category lost fixture triplet evidence: {record}"
        )
        assert record.deterministic_tests, (
            f"Category lost deterministic tests: {record}"
        )
        assert make_roundtrip_parity_category_record(record.category) == record

    triplets = make_roundtrip_parity_fixture_triplets()
    assert len(triplets) == 1
    triplet = triplets[0]
    assert set(triplet.topology_coverage) >= REQUIRED_ROUNDTRIP_TOPOLOGIES
    assert (
        set(triplet.expected_categories) == REQUIRED_ROUNDTRIP_PARITY_CATEGORIES
    )
    assert (
        triplet.zero_trace_posture
        == "intentionally_contaminated_for_gate_coverage"
    )
    for relative_path in (
        triplet.generated_path,
        triplet.make_reexport_path,
        triplet.known_good_path,
    ):
        assert (REPO_ROOT / relative_path).is_file(), (
            f"Missing corpus fixture: {relative_path}"
        )


def test_roundtrip_parity_complex_fixture_diff_7d197494() -> None:
    """The complex synthetic triplet classifies every required delta bucket."""
    triplet = make_roundtrip_parity_fixture_triplets()[0]

    payload = diff_blueprint(
        {
            "generated_path": triplet.generated_path,
            "make_exported_path": triplet.make_reexport_path,
            "known_good_path": triplet.known_good_path,
            "label": "roundtrip-parity-complex",
            "redaction_mode": "strict",
        },
        REPO_ROOT,
    )

    summary = cast("JsonObject", payload["summary"])
    counts = cast("JsonObject", summary["native_parity_category_counts"])
    for category in REQUIRED_ROUNDTRIP_PARITY_CATEGORIES:
        assert _int_member(counts, category) >= 1, (
            f"Roundtrip parity fixture missed {category}: {payload}"
        )

    comparisons = cast("list[JsonObject]", payload["comparisons"])
    make_vs_known_good = _comparison_by_label(
        comparisons,
        "roundtrip-parity-complex:make_exported_vs_known_good",
    )
    make_summary = cast("JsonObject", make_vs_known_good["summary"])
    assert make_summary["finding_count"] == 0, (
        f"Make re-export fixture must match the known-good reference: {payload}"
    )
    encoded = json.dumps(payload, sort_keys=True)
    assert "source_draft" not in encoded
    assert "Pancakes local draft" not in encoded


def test_roundtrip_parity_reexport_evidence_blocks_4d34921b() -> None:
    """Zero-trace fixtures stay useful as blockers without activating candidate.

    updates.
    """
    triplet = make_roundtrip_parity_fixture_triplets()[0]

    report = ingest_make_reexport_evidence(
        {
            "generated_path": triplet.generated_path,
            "make_reexport_path": triplet.make_reexport_path,
            "known_good_path": triplet.known_good_path,
            "label": "roundtrip-parity-complex",
        },
        REPO_ROOT,
    )

    assert report["status"] == "blocked"
    assert report["zero_trace_status"] == "failed"
    assert report["candidate_updates_active"] is False
    assert report["candidate_update_count"]
    native_changes = cast("JsonObject", report["native_parity_changes"])
    assert native_changes["zero_trace_violation"], (
        f"Zero-trace blocker disappeared from re-export evidence: {report}"
    )


def test_live_api_json_parse_reexport_af809e3c() -> None:
    """Live API roundtrip evidence proves Make injects metadata.instant=false.

    as.

    a default.
    """
    payload = diff_blueprint(
        {
            "generated_path": LIVE_JSON_PARSE_GENERATED,
            "make_exported_path": LIVE_JSON_PARSE_REEXPORT,
            "known_good_path": LIVE_JSON_PARSE_KNOWN_GOOD,
            "label": "live-api-json-parse",
            "redaction_mode": "strict",
        },
        REPO_ROOT,
    )

    canonicalization = cast("JsonObject", payload["canonicalization"])
    comparisons = cast("list[JsonObject]", payload["comparisons"])
    assert _int_member(canonicalization, "removed_volatile_field_count") >= 2
    assert "$.metadata.instant" in json.dumps(canonicalization, sort_keys=True)
    for label in (
        "live-api-json-parse:generated_vs_make_exported",
        "live-api-json-parse:generated_vs_known_good",
        "live-api-json-parse:make_exported_vs_known_good",
    ):
        comparison = _comparison_by_label(comparisons, label)
        summary = cast("JsonObject", comparison["summary"])
        assert summary["finding_count"] == 0, (
            f"Unexpected live API parity delta: {payload}"
        )


def test_roundtrip_parity_corpus_is_registered_in_non_raw_inventory() -> None:
    """The corpus is discoverable as private Make evidence, not raw provider.

    data.
    """
    inventory = _read_json_object(REPO_ROOT / INVENTORY_PATH)
    surfaces = cast("list[JsonObject]", inventory["surfaces"])
    surface = next(
        (
            record
            for record in surfaces
            if record.get("surface_id")
            == "make_roundtrip_reexport_parity_corpus"
        ),
        None,
    )

    assert surface is not None, "Roundtrip parity corpus is not indexed."
    assert surface["path"] == CORPUS_PATH
    assert surface["kind"] == "engine_input"
    assert (
        "tests/languages/make/make_roundtrip_reexport_parity_corpus_contract.py"
        in cast(
            "list[object]",
            surface["validation_tests"],
        )
    )


def _read_json_object(path: Path) -> JsonObject:
    raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(raw, dict), f"Expected JSON object: {path}"
    return cast("JsonObject", raw)


def _int_member(payload: JsonObject, key: str) -> int:
    value = payload.get(key)
    assert isinstance(value, int), f"Expected integer {key}: {payload}"
    return value


def _comparison_by_label(
    comparisons: list[JsonObject], label: str
) -> JsonObject:
    for comparison in comparisons:
        summary = cast("JsonObject", comparison["summary"])
        if summary.get("label") == label:
            return comparison
    msg = f"Missing comparison {label}: {comparisons}"
    raise AssertionError(msg)
