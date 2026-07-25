# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make public research evidence contracts.

Boundary contract:
- Owns: source-boundary checks for compact Make public research ingestion.
- Must not: call Make.com, use authenticated browser state, or copy public docs
verbatim.
- Allows: offline JSON and loader assertions for source IDs, gates, and local
surfaces.
- Split when: live Browser maintenance creates separate redacted evidence
ledgers.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from languages.make.public_research import (
    PUBLIC_RESEARCH_EVIDENCE_ASSET,
    make_public_research_evidence_record,
    make_public_research_evidence_records,
    make_public_research_source_ids,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

PUBLIC_RESEARCH_PATH = "src/languages/make/data/public_research_evidence.json"
INVENTORY_PATH = "src/languages/make/data/non_raw_evidence_inventory.json"
REQUIRED_FAMILIES = {
    "ai_agents_and_tools",
    "blueprint_diff_and_roundtrip",
    "builtins_default_modules",
    "catalog_plan_term_maps",
    "dynamic_selectors_and_rpcs",
    "expression_functions",
    "native_semantics_matrix",
}
ALLOWED_SOURCE_KINDS = {
    "official_public_doc",
    "public_fixture_corpus",
    "operator_approved_screenclip_summary",
    "sanitized_local_fixture",
    "local_raw_spec_manifest",
}


def test_public_research_evidence_is_private_offline_source_ledger() -> None:
    """Public research evidence stays a compact private ledger, not a docs.

    dump.
    """
    payload = _payload()

    assert payload["schema_version"] == 1
    assert payload["asset"] == PUBLIC_RESEARCH_EVIDENCE_ASSET
    assert payload["visibility"] == "private_engine_asset"
    assert payload["safety_contract"] == {
        "live_make_called_by_pancakes": False,
        "authenticated_make_ui_used": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "customer_facing": False,
    }
    source_policy = cast("JsonObject", payload["source_policy"])
    assert set(cast("list[str]", source_policy["allowed_source_kinds"])) == (
        ALLOWED_SOURCE_KINDS
    )
    forbidden = set(cast("list[str]", source_policy["forbidden_material"]))
    assert "authenticated raw provider payloads" in forbidden
    assert "customer blueprints" in forbidden


def test_public_research_evidence_covers_required_make_research_families() -> (
    None
):
    """The ledger accounts for every required TODO 0008 evidence family."""
    records = make_public_research_evidence_records()
    by_family = {record.family_id: record for record in records}

    assert set(by_family) == REQUIRED_FAMILIES
    assert by_family["dynamic_selectors_and_rpcs"].source_kinds == (
        "official_public_doc",
        "local_raw_spec_manifest",
    )
    assert (
        "make_help_ai_agents_new_app"
        in by_family["ai_agents_and_tools"].public_source_ids
    )
    assert (
        "src/languages/make/data/native_semantics_matrix.json"
        in by_family["native_semantics_matrix"].local_surfaces
    )
    assert (
        "tests/blueprints/fixtures/diff_blueprint"
        in by_family["blueprint_diff_and_roundtrip"].local_surfaces
    )


def test_public_research_sources_are_official_public_make_urls() -> None:
    """Official public source records are retained as URLs and support tags.

    only.
    """
    payload = _payload()
    sources = cast("list[JsonObject]", payload["public_sources"])
    source_ids = make_public_research_source_ids()

    assert len(sources) == len(source_ids) == 9
    assert {"make_developer_dynamic_fields_rpc", "make_help_blueprints"} <= set(
        source_ids
    )
    for source in sources:
        assert source["source_kind"] == "official_public_doc"
        assert source["publisher"] == "Make"
        url = str(source["url"])
        assert url.startswith(
            ("https://help.make.com/", "https://developers.make.com/")
        )
        assert source["last_checked_date"] == "2026-05-17"
        assert isinstance(source["supports"], list) and source["supports"], (
            source
        )


def test_public_research_records_keep_local_gates_and_live_followups() -> None:
    """Research rows must stay bounded and require live evidence before parity.

    claims.
    """
    all_source_ids = set(make_public_research_source_ids())
    for record in make_public_research_evidence_records():
        assert set(record.source_kinds) <= ALLOWED_SOURCE_KINDS
        assert set(record.public_source_ids) <= all_source_ids
        assert record.ingestion_status.startswith("ingested_")
        assert record.promotion_gate
        assert record.live_browser_follow_up == (
            "0012-full-make-catalog-live-browser-diff-validation"
        )
        assert record.local_surfaces
        assert all(
            surface.startswith(
                ("src/languages/make/", "src/mcp/", "tests/", "src/data/")
            )
            for surface in record.local_surfaces
        )
        assert record.validation_tests


def test_public_research_loader_resolves_family_records() -> None:
    """The loader gives planners a typed view without reading broad docs."""
    dynamic = make_public_research_evidence_record("dynamic_selectors_and_rpcs")
    missing = make_public_research_evidence_record("not-real")

    assert dynamic is not None
    assert dynamic.ingestion_status == "ingested_selector_shape_terms_only"
    assert "make_developer_dynamic_options_rpc" in dynamic.public_source_ids
    assert missing is None


def test_public_research_evidence_is_registered_in_non_raw_inventory() -> None:
    """The non-raw inventory exposes this compact public research surface."""
    inventory = _read_json_object(_repo_root() / INVENTORY_PATH)
    surfaces = cast("list[JsonObject]", inventory["surfaces"])
    surface = next(
        (
            record
            for record in surfaces
            if record.get("surface_id") == "make_public_research_evidence"
        ),
        None,
    )

    assert surface is not None, (
        "Public research evidence surface is not indexed."
    )
    assert surface["path"] == PUBLIC_RESEARCH_PATH
    assert surface["kind"] == "engine_input"
    assert (
        "tests/languages/make/make_public_research_evidence_contract.py"
        in cast(
            "list[object]",
            surface["validation_tests"],
        )
    )


def _payload() -> JsonObject:
    return _read_json_object(_repo_root() / PUBLIC_RESEARCH_PATH)


def _read_json_object(path: Path) -> JsonObject:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"Expected JSON object: {path}"
    return cast("JsonObject", payload)


def _repo_root() -> Path:
    return repo_root()
