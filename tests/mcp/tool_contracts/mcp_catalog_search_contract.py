# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for the canonical catalog lookup MCP tools.

ADR: docs/adr/catalog-semantic-graph-preview-policy.md.

Boundary contract:
- Owns: public MCP catalog lookup behavior over static indexes and SQLite-backed
local facts.
- Must not: author catalog answers, advance catalog-plan cursors, or call
providers.
- Allows: synthetic SQLite fixtures for exact hits, semantic hits, and evidence
gaps.
- Split when catalog index/search/inspect need separate SQLite fixture scopes.
"""

from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from shutil import copy2, copytree
from typing import TYPE_CHECKING, Final, cast

import mcp.catalog_search as catalog_search_module
from catalog.knowledge import (
    DEFAULT_DB_SNAPSHOT_DIR,
    DEFAULT_KNOWLEDGE_DB_PATH,
    CatalogResetUnitInput,
    build_knowledge_store,
    start_catalog_quality_reset_run,
)
from catalog.placeholder_index import (
    CATALOG_PLACEHOLDER_INDEX,
    catalog_placeholder_matches,
    catalog_placeholder_normalized_text,
    catalog_placeholder_replacement_plan,
)
from mcp import execute_mcp_tool, mcp_tool_registry
from mcp.inactive_catalog_work import (
    DerivedModuleIntelligenceMetadata,
    derive_module_intelligence_metadata,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.support.json_payloads import JsonObject

REPO_ROOT = repo_root()
OBSERVED_AT = "2026-05-18T00:00:00+00:00"
SLACK_CREATE_MESSAGE_MODULE_ID = (
    "module:slack:2.14.3:action:ActionCreateMessage"
)
GMAIL_SEND_EMAIL_MODULE_ID = "module:google-email:2.4.1:action:SendEmail"
GMAIL_WATCH_EMAIL_MODULE_ID = "module:google-email:2.4.1:trigger:WatchEmail"
MICROSOFT_EMAIL_SEND_MODULE_ID = "module:microsoft-email:1.0.0:action:SendEmail"
MICROSOFT_GRAPH_API_CALL_MODULE_ID = (
    "module:microsoft-graph:1.0.0:action:MicrosoftGraphApiCall"
)
JSON_CREATE_MODULE_ID = "module:json:1.0.0:transformer:CreateJson"
JSON_PARSE_MODULE_ID = "module:json:1.0.0:transformer:ParseJson"
HUBSPOT_API_CALL_MODULE_ID = (
    "module:hubspot-marketing-hub:1.0.0:action:MakeApiCall"
)
MONDAY_GRAPHQL_QUERY_MODULE_ID = (
    "module:monday:1.0.0:action:ExecuteGraphqlQuery"
)
GENERIC_API_CALL_MODULE_ID = "module:http:1.0.0:action:MakeApiCall"
GATEWAY_CUSTOM_WEBHOOK_MODULE_ID = "module:gateway:1.0.0:trigger:CustomWebhook"
BASECAMP_CREATE_MESSAGE_MODULE_ID = (
    "module:basecamp:1.0.0:action:ActionCreateMessage"
)
AGILEPLACE_CONNECT_CARDS_MODULE_ID = (
    "module:agileplace:1.0.1:action:connectCards"
)
BASIC_ROUTER_MODULE_ID = "module:builtin:1.0.0:builtin:BasicRouter"
DATASTORE_ADD_RECORD_MODULE_ID = "module:datastore:2.0.0:action:AddRecord"
COUNT_SQL_BY_TABLE: Final[dict[str, str]] = {
    "catalog_plan_units": "SELECT COUNT(*) FROM catalog_plan_units ",
    "catalog_plan_semantic_answers": (
        "SELECT COUNT(*) FROM catalog_plan_semantic_answers "
    ),
    "catalog_plan_quarantine_records": (
        "SELECT COUNT(*) FROM catalog_plan_quarantine_records"
    ),
}


def test_catalog_lookup_tools_are_the_only_normal_ai_catalog_lookup_tools() -> (
    None
):
    """Catalog lookup and explicit worker tools stay on the intended MCP.

    surface.
    """
    tool_names = tuple(tool.name for tool in mcp_tool_registry())
    catalog_tool_names = tuple(
        name for name in tool_names if name.startswith("catalog.")
    )

    assert catalog_tool_names == (
        "catalog.index ",
        "catalog.search ",
        "catalog.inspect ",
        "catalog.graph.search ",
        "catalog.semantic.preview",
        ("catalog.work.next"),
        ("catalog.work.save"),
        "catalog.modify ",
        "catalog.node.modify ",
        "catalog.edge.propose ",
        "catalog.edge.apply ",
        "catalog.review.add",
    )
    tool_lookup = {tool.name: tool for tool in mcp_tool_registry()}
    assert "placeholder" in tool_lookup["catalog.index"].description.casefold()


def test_catalog_placeholder_index_examples_match_their_own_detector() -> None:
    """Every canonical placeholder row has typed examples that resolve through.

    the SSOT.
    """
    placeholders = [
        definition.placeholder for definition in CATALOG_PLACEHOLDER_INDEX
    ]
    canonical_kinds = [
        definition.canonical_kind for definition in CATALOG_PLACEHOLDER_INDEX
    ]

    assert len(placeholders) == len(set(placeholders))
    assert len(canonical_kinds) == len(set(canonical_kinds))
    for definition in CATALOG_PLACEHOLDER_INDEX:
        assert definition.placeholder.startswith("[")
        assert definition.placeholder.endswith("]")
        assert definition.canonical_kind
        assert definition.examples
        assert definition.aliases
        for example in definition.examples:
            matched_placeholders = {
                str(row["placeholder"])
                for row in catalog_placeholder_matches(example)
            }
            assert definition.placeholder in matched_placeholders


def test_catalog_placeholder_lookup_matches_alias_6e60ea99() -> None:
    """Index lookup terms resolve, while save-time sample-value checks stay.

    value-only.
    """
    text = (
        "Use person full name, phone number, and datetime mm/dd/yyyy hh:mm "
        "terms."
    )

    value_matches = catalog_placeholder_matches(text)
    lookup_matches = catalog_placeholder_matches(text, include_alias_only=True)

    assert value_matches == []
    assert [row["placeholder"] for row in lookup_matches] == [
        "[PERSON_FULL_NAME_FORMAT_1]",
        "[PHONE_NUMBER_FORMAT_1]",
        "[DATETIME_MM_DD_YYYY_HH_MM_FORMAT_1]",
    ]
    assert [row["matched_aliases"] for row in lookup_matches] == [
        ["full name", "person full name"],
        ["phone number"],
        ["datetime mm/dd/yyyy hh:mm"],
    ]


def test_catalog_placeholder_replacement_plan_prefers_2ac9fecd() -> None:
    """Replacement spans are deterministic and avoid date fragments inside.

    datetimes.
    """
    text = "Send John Doe, John, and Doe at +55 55555 on 2026-01-31T10:30:00Z."

    replacement_plan = catalog_placeholder_replacement_plan(text)

    assert [
        (row["matched_text"], row["replacement"], row["canonical_kind"])
        for row in replacement_plan
    ] == [
        ("John Doe", "[PERSON_FULL_NAME_FORMAT_1]", "person_full_name"),
        ("John", "[PERSON_FIRST_NAME_FORMAT_1]", "person_first_name"),
        ("Doe", "[PERSON_LAST_NAME_FORMAT_1]", "person_last_name"),
        ("+55 55555", "[PHONE_NUMBER_FORMAT_1]", "phone_number"),
        (
            "2026-01-31T10:30:00Z",
            "[DATETIME_ISO_UTC_FORMAT_1]",
            "datetime_iso_utc",
        ),
    ]
    assert catalog_placeholder_normalized_text(text) == (
        "Send [PERSON_FULL_NAME_FORMAT_1], [PERSON_FIRST_NAME_FORMAT_1], and "
        "[PERSON_LAST_NAME_FORMAT_1] at [PHONE_NUMBER_FORMAT_1] on "
        "[DATETIME_ISO_UTC_FORMAT_1]."
    )


def test_catalog_placeholder_index_separates_date_and_datetime_shapes() -> None:
    """Each date and datetime shape resolves to its own canonical technical.

    placeholder.
    """
    text = (
        "Use 01/31/26 10:30, 01/31/2026 10:30, 2026-01-31 10:30:00, "
        "01/31/26, 01/31/2026, and 2026-01-31."
    )

    replacement_plan = catalog_placeholder_replacement_plan(text)

    assert [
        (row["matched_text"], row["replacement"], row["canonical_kind"])
        for row in replacement_plan
    ] == [
        (
            "01/31/26 10:30",
            "[DATETIME_MM_DD_YY_HH_MM_FORMAT_1]",
            "datetime_mm_dd_yy_hh_mm",
        ),
        (
            "01/31/2026 10:30",
            "[DATETIME_MM_DD_YYYY_HH_MM_FORMAT_1]",
            "datetime_mm_dd_yyyy_hh_mm",
        ),
        (
            "2026-01-31 10:30:00",
            "[DATETIME_YYYY_MM_DD_HH_MM_SS_FORMAT_1]",
            "datetime_yyyy_mm_dd_hh_mm_ss",
        ),
        ("01/31/26", "[DATE_MM_DD_YY_FORMAT_1]", "date_mm_dd_yy"),
        ("01/31/2026", "[DATE_MM_DD_YYYY_FORMAT_1]", "date_mm_dd_yyyy"),
        ("2026-01-31", "[DATE_YYYY_MM_DD_FORMAT_1]", "date_yyyy_mm_dd"),
    ]


def test_catalog_index_returns_canonical_placeholder_matches(
    tmp_path: Path,
) -> None:
    """The MCP exposes direct read-only access to canonical placeholder/value.

    indexes.
    """
    result = execute_mcp_tool(
        tool_name="catalog.index",
        arguments={"query": "John Doe +55 55555 jdoe@example.com"},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload["response_contract"] == "catalog.index"
    assert payload["response_schema_version"] == 1
    assert payload["operation_mode"] == "read_only_local_catalog_index"
    assert payload["cursor_advanced"] is False
    assert payload["writes_performed"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    index_lookup = cast("JsonObject", payload["canonical_index_lookup"])
    placeholder_index = cast(
        "list[JsonObject]", payload["canonical_placeholder_index"]
    )
    value_index = cast("list[JsonObject]", payload["canonical_value_index"])
    placeholder_matches = cast(
        "list[JsonObject]",
        payload["canonical_placeholder_matches"],
    )
    replacement_plan = cast(
        "list[JsonObject]",
        payload["canonical_placeholder_replacement_plan"],
    )
    sample_value_policy = cast("JsonObject", payload["sample_value_policy"])
    assert index_lookup["tool_name"] == "catalog.index"
    assert index_lookup["full_index_payload_embedded_in_search"] is False
    assert placeholder_index[0]["placeholder"] == "[PERSON_FULL_NAME_FORMAT_1]"
    assert placeholder_index[0]["canonical_kind"] == "person_full_name"
    assert value_index[0]["table"] == "catalog_runs"
    assert payload["canonical_placeholder_normalized_query"] == (
        "[PERSON_FULL_NAME_FORMAT_1] [PHONE_NUMBER_FORMAT_1] "
        "[EMAIL_ADDRESS_FORMAT_1]"
    )
    assert [
        (row["matched_text"], row["replacement"]) for row in replacement_plan
    ] == [
        ("John Doe", "[PERSON_FULL_NAME_FORMAT_1]"),
        ("+55 55555", "[PHONE_NUMBER_FORMAT_1]"),
        ("jdoe@example.com", "[EMAIL_ADDRESS_FORMAT_1]"),
    ]
    assert sample_value_policy["replacement_plan_available"] is True
    assert sample_value_policy["replacement_examples"] == {
        "John Doe": "[PERSON_FULL_NAME_FORMAT_1]",
        "+55 55555": "[PHONE_NUMBER_FORMAT_1]",
        "jdoe@example.com": "[EMAIL_ADDRESS_FORMAT_1]",
    }
    assert [match["placeholder"] for match in placeholder_matches[:3]] == [
        "[PERSON_FULL_NAME_FORMAT_1]",
        "[EMAIL_ADDRESS_FORMAT_1]",
        "[PHONE_NUMBER_FORMAT_1]",
    ]
    phone_match = placeholder_matches[2]
    assert placeholder_matches[0]["canonical_kind"] == "person_full_name"
    assert "+55 55555" in cast("list[str]", phone_match["matched_examples"])


def test_catalog_index_resolves_canonical_placeholder_alias_terms(
    tmp_path: Path,
) -> None:
    """MCP index lookup resolves canonical terms even when no sample value is.

    present.
    """
    result = execute_mcp_tool(
        tool_name="catalog.index",
        arguments={
            "query": "person full name phone number datetime mm/dd/yyyy hh:mm",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    placeholder_matches = cast(
        "list[JsonObject]",
        payload["canonical_placeholder_matches"],
    )
    replacement_plan = cast(
        "list[JsonObject]",
        payload["canonical_placeholder_replacement_plan"],
    )

    assert replacement_plan == []
    assert [match["placeholder"] for match in placeholder_matches] == [
        "[PERSON_FULL_NAME_FORMAT_1]",
        "[PHONE_NUMBER_FORMAT_1]",
        "[DATETIME_MM_DD_YYYY_HH_MM_FORMAT_1]",
    ]


def test_catalog_search_returns_exact_modules_before_candidates(
    tmp_path: Path,
) -> None:
    """Exact module IDs are first-class hits before broader module.

    candidates.
    """
    _prepare_search_fixture(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": SLACK_CREATE_MESSAGE_MODULE_ID, "limit": 4},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    assert payload.get("response_contract") == "catalog.search"
    _assert_catalog_lookup_source_of_truth(payload)
    exact_matches = cast("list[JsonObject]", payload["exact_matches"])
    assert exact_matches[0]["module_id"] == SLACK_CREATE_MESSAGE_MODULE_ID
    assert exact_matches[0]["kind"] == "exact_module"
    assert exact_matches[0]["rank_reason"] == "exact_module_id"
    assert payload["search_short_circuit"] == "exact_module_id"
    assert payload["module_candidates"] == []
    assert payload["field_candidates"] == []
    assert payload["semantic_candidates"] == []
    assert payload["structure_prerequisites"] == []
    assert payload["missing_evidence"] == []
    assert payload["cursor_advanced"] is False
    assert payload["writes_performed"] is False
    assert "result_count" not in payload
    returned_result_count = cast("int", payload["returned_result_count"])
    total_result_count = cast("int", payload["total_result_count"])
    hidden_result_count = cast("int", payload["hidden_result_count"])
    assert payload["limit_semantics"] == "per_candidate_family"
    assert payload["returned_exact_match_count"] == len(exact_matches)
    assert payload["total_exact_match_count"] == len(exact_matches)
    assert returned_result_count == len(exact_matches)
    assert total_result_count == returned_result_count
    assert payload["returned_module_candidate_count"] == len(
        cast("list[JsonObject]", payload["module_candidates"])
    )
    assert cast("int", payload["total_module_candidate_count"]) >= cast(
        "int",
        payload["returned_module_candidate_count"],
    )
    assert payload["returned_field_candidate_count"] == 0
    assert payload["total_field_candidate_count"] == 0
    assert payload["returned_semantic_candidate_count"] == len(
        cast("list[JsonObject]", payload["semantic_candidates"])
    )
    assert cast("int", payload["total_semantic_candidate_count"]) >= cast(
        "int",
        payload["returned_semantic_candidate_count"],
    )
    assert hidden_result_count >= 0
    assert payload["next_queries"]

    inspected = execute_mcp_tool(
        tool_name="catalog.inspect",
        arguments={"module_id": SLACK_CREATE_MESSAGE_MODULE_ID},
        repo_root=tmp_path,
    )
    assert inspected.ok, inspected
    assert inspected.payload["entity_kind"] == "module"
    _assert_catalog_lookup_source_of_truth(inspected.payload)
    inspected_module = cast("JsonObject", inspected.payload["module"])
    assert inspected_module["module_id"] == SLACK_CREATE_MESSAGE_MODULE_ID


def test_catalog_search_ranks_app_intent_above_same_internal_name(
    tmp_path: Path,
) -> None:
    """An app hint such as slack outranks alphabetically earlier apps with the.

    same action.
    """
    _prepare_search_fixture(tmp_path)

    for query in (
        "slack ActionCreateMessage ",
        "slack create message ",
        "Slack Create a message ",
        "ActionCreateMessage slack",
    ):
        result = execute_mcp_tool(
            tool_name="catalog.search",
            arguments={"query": query, "limit": 6},
            repo_root=tmp_path,
        )

        assert result.ok, result
        payload = result.payload
        candidates = cast("list[JsonObject]", payload["module_candidates"])
        assert candidates[0]["module_id"] == SLACK_CREATE_MESSAGE_MODULE_ID
        assert candidates[0]["rank_reason"] in {
            "exact_app_slug_and_internal_name ",
            "exact_app_slug_and_display_name ",
            "app_slug_intent_match",
        }
        assert candidates[0]["app_slug"] == "slack"
        assert BASECAMP_CREATE_MESSAGE_MODULE_ID in {
            str(candidate["module_id"]) for candidate in candidates
        }
        semantic_candidates = cast(
            "list[JsonObject]", payload["semantic_candidates"]
        )
        assert all(
            "basecamp" not in json.dumps(candidate).casefold()
            for candidate in semantic_candidates
        )
        assert "off_intent_semantic_candidates_available" in payload
        if cast("int", payload["off_intent_semantic_candidate_count"]):
            assert payload["off_intent_semantic_candidates_available"] is True


def test_catalog_search_resolves_builtin_and_datastore_versions(
    tmp_path: Path,
) -> None:
    """Builtins and datastore modules resolve from manifest-backed SQLite.

    rows.
    """
    _prepare_search_fixture(tmp_path)

    router = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "BasicRouter", "limit": 4},
        repo_root=tmp_path,
    )
    datastore = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "datastore AddRecord", "limit": 4},
        repo_root=tmp_path,
    )

    assert router.ok, router
    assert datastore.ok, datastore
    router_candidates = cast(
        "list[JsonObject]", router.payload["module_candidates"]
    )
    datastore_candidates = cast(
        "list[JsonObject]", datastore.payload["module_candidates"]
    )
    assert router_candidates[0]["module_id"] == BASIC_ROUTER_MODULE_ID
    assert router_candidates[0]["app_slug"] == "builtin"
    assert (
        datastore_candidates[0]["module_id"] == DATASTORE_ADD_RECORD_MODULE_ID
    )
    assert (
        datastore_candidates[0]["rank_reason"]
        == "exact_app_slug_and_internal_name"
    )


def test_catalog_search_returns_canonical_placeholder_matches(
    tmp_path: Path,
) -> None:
    """Generic people and sample PII terms resolve to canonical technical.

    placeholders.
    """
    _prepare_search_fixture(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "John Doe jdoe@example.com +55 55555", "limit": 4},
        repo_root=tmp_path,
    )

    assert result.ok, result
    index_lookup = cast("JsonObject", result.payload["canonical_index_lookup"])
    value_index_status = cast(
        "JsonObject", result.payload["canonical_value_index_status"]
    )
    placeholder_matches = cast(
        "list[JsonObject]",
        result.payload["canonical_placeholder_matches"],
    )
    assert "canonical_placeholder_index" not in result.payload
    assert "canonical_value_index" not in result.payload
    assert index_lookup["tool_name"] == "catalog.index"
    assert index_lookup["operation_mode"] == "read_only_local_catalog_index"
    assert index_lookup["full_index_payload_embedded_in_search"] is False
    assert cast("int", index_lookup["placeholder_index_row_count"]) > 1
    assert cast("int", index_lookup["value_index_row_count"]) > 1
    assert value_index_status["status"] == "ok"
    assert value_index_status["violation_count"] == 0
    assert result.payload["canonical_placeholder_normalized_query"] == (
        "[PERSON_FULL_NAME_FORMAT_1] [EMAIL_ADDRESS_FORMAT_1] "
        "[PHONE_NUMBER_FORMAT_1]"
    )
    assert [match["placeholder"] for match in placeholder_matches[:3]] == [
        "[PERSON_FULL_NAME_FORMAT_1]",
        "[EMAIL_ADDRESS_FORMAT_1]",
        "[PHONE_NUMBER_FORMAT_1]",
    ]
    real_name = placeholder_matches[0]
    phone_match = placeholder_matches[2]
    assert "john doe" in cast("list[str]", real_name["matched_aliases"])
    assert "+55 55555" in cast("list[str]", phone_match["matched_examples"])
    assert "backlog_hints" not in result.payload


def test_catalog_search_reads_sqlite_without_advancing_or_writing(
    tmp_path: Path,
) -> None:
    """Search reads semantic, structure, and gap facts without mutation."""
    _prepare_search_fixture(tmp_path)
    before_counts = _catalog_runtime_counts(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "lead webhook datastore", "limit": 6},
        repo_root=tmp_path,
    )

    after_counts = _catalog_runtime_counts(tmp_path)
    assert result.ok, result
    assert after_counts == before_counts
    payload = result.payload
    _assert_catalog_lookup_source_of_truth(payload)
    semantic_candidates = cast(
        "list[JsonObject]", payload["semantic_candidates"]
    )
    structure_prerequisites = cast(
        "list[JsonObject]", payload["structure_prerequisites"]
    )
    missing_evidence = cast("list[JsonObject]", payload["missing_evidence"])

    assert payload["operation_mode"] == "read_only_local_catalog_search"
    assert payload["cursor_advanced"] is False
    assert payload["writes_performed"] is False
    assert payload["provider_api_call"] is False
    assert payload["live_make_called"] is False
    assert payload["credential_value_transfer"] is False
    assert payload["secret_output"] is False
    assert any(
        item["kind"] == "catalog_search_document"
        for item in semantic_candidates
    )
    assert any(
        item["kind"] == "catalog_semantic_answer"
        for item in semantic_candidates
    )
    assert any(
        item["kind"] == "make_webhook_structure_evidence"
        for item in structure_prerequisites
    )
    webhook_evidence = next(
        item
        for item in structure_prerequisites
        if item["kind"] == "make_webhook_structure_evidence"
    )
    assert webhook_evidence["evidence_status"] == "populated"
    assert webhook_evidence["blocking"] is False
    assert webhook_evidence["sqlite_table"] == "make_webhook_structure_evidence"
    assert "structure_json" in cast(
        "list[str]", webhook_evidence["expected_sqlite_columns"]
    )
    assert "lead" in cast(
        "tuple[str, ...]", webhook_evidence["material_matched_terms"]
    )
    assert any(
        item["kind"] == "catalog_missing_evidence" for item in missing_evidence
    )
    assert any(
        item["kind"] == "structure_evidence_not_yet_populated"
        and item["table"] == "make_datastore_structure_evidence"
        for item in missing_evidence
    )
    assert "backlog_hints" not in payload
    assert "returned_backlog_hint_count" not in payload
    assert "total_backlog_hint_count" not in payload


def test_catalog_search_surfaces_populated_webhook_structure_rows(
    tmp_path: Path,
) -> None:
    """Webhook JSON queries surface populated local structure evidence when.

    present.
    """
    _prepare_search_fixture(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "webhook JSON email", "limit": 6},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    structure_prerequisites = cast(
        "list[JsonObject]", payload["structure_prerequisites"]
    )
    missing_evidence = cast("list[JsonObject]", payload["missing_evidence"])
    webhook_evidence = next(
        item
        for item in structure_prerequisites
        if item["kind"] == "make_webhook_structure_evidence"
    )

    assert webhook_evidence["evidence_id"] == "webhook:lead"
    assert webhook_evidence["app_slug"] == "gateway"
    assert webhook_evidence["webhook_slug"] == "lead-webhook"
    assert webhook_evidence["evidence_status"] == "populated"
    assert webhook_evidence["blocking"] is False
    assert "email" in cast(
        "list[str]", webhook_evidence["structure_field_paths"]
    )
    assert "email" in cast(
        "tuple[str, ...]", webhook_evidence["material_matched_terms"]
    )
    assert not any(
        item["kind"] == "structure_evidence_not_yet_populated"
        and item["table"] == "make_webhook_structure_evidence"
        for item in missing_evidence
    )


def test_catalog_search_keeps_missing_webhook_structure_rows_non_blocking(
    tmp_path: Path,
) -> None:
    """Absent webhook structure evidence remains explicit without blocking.

    catalog search.
    """
    _prepare_search_fixture(tmp_path)
    _delete_webhook_structure_rows(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "webhook payload fields", "limit": 6},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    field_candidates = cast("list[JsonObject]", payload["field_candidates"])
    structure_prerequisites = cast(
        "list[JsonObject]", payload["structure_prerequisites"]
    )
    missing_evidence = cast("list[JsonObject]", payload["missing_evidence"])

    assert payload["status"] != "blocked"
    assert field_candidates == []
    assert not any(
        item["kind"] == "make_webhook_structure_evidence"
        for item in structure_prerequisites
    )
    webhook_gap = next(
        item
        for item in missing_evidence
        if item["kind"] == "structure_evidence_not_yet_populated"
        and item["table"] == "make_webhook_structure_evidence"
    )
    assert webhook_gap["evidence_status"] == "missing"
    assert webhook_gap["blocking"] is False
    assert webhook_gap["evidence_scope"] == "global_catalog_structure_evidence"
    assert webhook_gap["global_catalog_structure_evidence"] == "missing"
    assert (
        webhook_gap["project_local_structure_evidence"]
        == "not_evaluated_by_catalog_search"
    )
    manifest_lookup = cast(
        "JsonObject", webhook_gap["project_local_manifest_lookup"]
    )
    assert manifest_lookup["tool"] == "project.package.inspect"
    assert manifest_lookup["section"] == "live_resources"


def test_catalog_search_finds_saved_outputs_87f46461(
    tmp_path: Path,
) -> None:
    """Literal connection requests must find semantic output and fast graph.

    edges.
    """
    _prepare_search_fixture(tmp_path)

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "connect slack to gmail", "limit": 6},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    semantic_candidates = cast(
        "list[JsonObject]", payload["semantic_candidates"]
    )
    graph_candidates = cast("list[JsonObject]", payload["graph_candidates"])
    module_candidates = cast("list[JsonObject]", payload["module_candidates"])
    search_order = cast("list[str]", payload["search_order"])
    active_catalog_run = cast("JsonObject", payload["active_catalog_run"])
    legacy_baseline = cast(
        "JsonObject", payload["legacy_semantic_unit_baseline"]
    )

    assert payload["active_run_id"] == "catalog-run-search-connection-fixture"
    assert payload["catalog_run_status"] == "active"
    assert payload["coverage_status"] == "incomplete_non_blocking"
    assert payload["active_work_unit_count"] == 1
    assert payload["total_unit_count"] == 1
    assert active_catalog_run["run_id"] == payload["active_run_id"]
    assert (
        active_catalog_run["legacy_semantic_unit_baseline"] == legacy_baseline
    )
    assert legacy_baseline["legacy_unit_count"] == 2
    assert legacy_baseline["legacy_answer_count"] == 1
    assert legacy_baseline["counts_are_comparable"] is False
    assert (
        legacy_baseline["active_work_units_less_than_legacy_baseline"] is True
    )
    assert (
        legacy_baseline["relationship"]
        == "active_work_units_are_quality_batches_not_legacy_semantic_units"
    )
    assert (
        cast("JsonObject", payload["active_unit_source_surfaces"])[
            "manifest_and_control_surfaces_not_module_only"
        ]
        is True
    )
    assert cast("JsonObject", payload["semantic_graph_output_contract"]) == {
        "semantic_output_per_active_unit": True,
        "graph_output_per_active_unit": True,
        "graph_outputs_expand_answer_payload_not_lease_unit_count": True,
    }
    assert any(
        candidate["module_id"] == GMAIL_SEND_EMAIL_MODULE_ID
        for candidate in module_candidates
    )
    assert any(
        candidate["module_id"] == SLACK_CREATE_MESSAGE_MODULE_ID
        for candidate in module_candidates
    )
    assert {
        str(candidate["app_slug"]) for candidate in module_candidates[:2]
    } == {
        "slack ",
        "google-email",
    }
    assert [candidate["module_id"] for candidate in module_candidates[:2]] == [
        SLACK_CREATE_MESSAGE_MODULE_ID,
        GMAIL_SEND_EMAIL_MODULE_ID,
    ]
    assert payload["off_intent_semantic_candidates_available"] is True
    assert payload["off_intent_semantic_candidates"] == []
    assert AGILEPLACE_CONNECT_CARDS_MODULE_ID not in {
        str(candidate["module_id"]) for candidate in module_candidates[:2]
    }
    assert any(
        candidate["kind"] == "catalog_unit_output"
        and candidate["unit_id"] == "raw-spec:slack-gmail-connection:1.0.0"
        for candidate in semantic_candidates
    )
    assert semantic_candidates[0]["kind"] == "catalog_unit_output"
    assert graph_candidates[0]["kind"] == "catalog_graph_edge"
    assert graph_candidates[0]["edge_kind"] == "connects_to"
    assert graph_candidates[0]["from_label"] == "Slack"
    assert graph_candidates[0]["to_label"] == "Gmail"
    assert payload["returned_graph_candidate_count"] == len(graph_candidates)
    assert cast("int", payload["total_graph_candidate_count"]) >= len(
        graph_candidates
    )
    assert "graph_candidates" in search_order

    debug_result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={
            "query": "connect slack to gmail",
            "limit": 3,
            "output_mode": "debug",
        },
        repo_root=tmp_path,
    )
    assert debug_result.ok, debug_result
    assert cast(
        "list[JsonObject]",
        debug_result.payload["off_intent_semantic_candidates"],
    )


def test_catalog_search_explains_lookup_readiness_without_active_worker_run(
    tmp_path: Path,
) -> None:
    """Lookup usability is explicit even when semantic-worker progress is not.

    started.
    """
    _prepare_search_fixture(tmp_path)
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        _ = connection.execute(
            "UPDATE catalog_runs SET run_status = 'completed'"
        )
        connection.commit()
    finally:
        connection.close()

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "slack create message", "limit": 4},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    active_catalog_run = cast("JsonObject", payload["active_catalog_run"])
    assert payload["status"] == "ok"
    assert payload["catalog_usable"] is True
    assert payload["catalog_run_status"] == "lookup_ready_without_active_worker"
    assert payload["coverage_status"] == "lookup_ready_non_blocking"
    assert payload["catalog_lookup_status"] == "ready"
    assert payload["catalog_worker_run_status"] == "not_started"
    assert (
        payload["progress_counters_apply_to"] == "catalog_semantic_worker_run"
    )
    assert payload["completed_unit_count"] == 0
    snapshot = cast("JsonObject", payload["catalog_completion_snapshot"])
    assert snapshot["snapshot_status"] == "lookup_ready_without_active_worker"
    assert snapshot["lookup_status"] == "ready"
    assert snapshot["worker_run_status"] == "not_started"
    assert snapshot["coverage_status"] == "lookup_ready_non_blocking"
    assert snapshot["completed_unit_count"] == 0
    assert (
        snapshot["progress_counters_apply_to"] == "catalog_semantic_worker_run"
    )
    assert "lookup tables are ready" in str(snapshot["status_reason"])
    assert (
        active_catalog_run["run_status"] == "lookup_ready_without_active_worker"
    )
    assert active_catalog_run["lookup_status"] == "ready"
    assert active_catalog_run["catalog_completion_snapshot"] == snapshot
    assert active_catalog_run["worker_progress_available"] is False
    assert active_catalog_run["metrics_semantics"] == (
        "lookup readiness and worker progress are separate surfaces"
    )


def test_catalog_search_ranks_graph_candidates_by_contextual_query_intent(
    tmp_path: Path,
) -> None:
    """Graph results prefer explicit app, resource, and workflow intent over.

    generic edges.
    """
    _prepare_search_fixture(tmp_path)

    expected_edges = {
        "connect slack to gmail": "edge:catalog:slack-to-gmail ",
        "webhook json to slack and email": (
            "edge:catalog:webhook-json-to-email "
        ),
        "store state between runs": "edge:catalog:datastore-dedupe ",
        "retry failed http request": "edge:catalog:error-retry ",
        "dedupe incoming leads": "edge:catalog:datastore-dedupe",
    }
    for query, expected_edge_id in expected_edges.items():
        result = execute_mcp_tool(
            tool_name="catalog.search",
            arguments={"query": query, "limit": 6},
            repo_root=tmp_path,
        )

        assert result.ok, result
        graph_candidates = cast(
            "list[JsonObject]", result.payload["graph_candidates"]
        )
        assert graph_candidates, query
        assert graph_candidates[0]["edge_id"] == expected_edge_id
        assert graph_candidates[0]["rank_reason"] in {
            "graph_control_surface_match ",
            "graph_explicit_app_intent_match ",
            "graph_resource_or_workflow_term_match",
        }
        assert graph_candidates[0]["rationale"]
        assert len(str(graph_candidates[0]["rationale"])) <= 80
        assert graph_candidates[0]["source_ref"]
        assert graph_candidates[0]["source_refs"] == [
            graph_candidates[0]["source_ref"]
        ]
        marketing_index = next(
            (
                index
                for index, candidate in enumerate(graph_candidates)
                if candidate["edge_id"]
                == "edge:catalog:marketing-list-to-email"
            ),
            None,
        )
        if marketing_index is not None:
            assert marketing_index > 0


def test_catalog_search_demotes_json_only_graph_edges_below_intent_authority(
    tmp_path: Path,
) -> None:
    """Generic JSON or payload_json evidence must not outrank explicit graph.

    intent.
    """
    _prepare_search_fixture(tmp_path)

    expected_edges = {
        "slack json payload_json": "edge:catalog:slack-to-gmail ",
        "google email json payload_json": "edge:catalog:slack-to-gmail ",
        "webhook json payload_json": "edge:catalog:webhook-json-to-email ",
        "datastore json payload_json": "edge:catalog:datastore-dedupe ",
        "router json payload_json": "edge:catalog:router-control ",
        "filter json payload_json": "edge:catalog:filter-control",
    }
    for query, expected_edge_id in expected_edges.items():
        result = execute_mcp_tool(
            tool_name="catalog.search",
            arguments={"query": query, "limit": 10},
            repo_root=tmp_path,
        )

        assert result.ok, result
        graph_candidates = cast(
            "list[JsonObject]", result.payload["graph_candidates"]
        )
        candidate_indexes = {
            str(candidate["edge_id"]): index
            for index, candidate in enumerate(graph_candidates)
        }
        expected_index = candidate_indexes[expected_edge_id]
        json_only_index = candidate_indexes[
            "edge:catalog:generic-json-payload-field"
        ]
        expected_candidate = graph_candidates[expected_index]
        json_only_candidate = graph_candidates[json_only_index]

        assert expected_index < json_only_index, query
        assert cast("int", expected_candidate["rank_score"]) > cast(
            "int",
            json_only_candidate["rank_score"],
        )
        assert "json" not in cast(
            "tuple[str, ...]", json_only_candidate["matched_app_intents"]
        )
        assert json_only_candidate["generic_field_token_only"] is True
        assert json_only_candidate["rank_reason"] in {
            "graph_generic_field_token_fallback ",
            "graph_generic_utility_match",
        }
        assert json_only_candidate["applied_penalties"]


def test_catalog_search_v10_app_intent_queries_bind_named_apps(
    tmp_path: Path,
) -> None:
    """Explicit Gmail and Slack intent outranks wrong-app and generic utility.

    candidates.
    """
    _prepare_search_fixture(tmp_path)

    single_app_cases = {
        "Slack send channel message": SLACK_CREATE_MESSAGE_MODULE_ID,
        "Gmail watch email": GMAIL_WATCH_EMAIL_MODULE_ID,
        "Gmail send email": GMAIL_SEND_EMAIL_MODULE_ID,
        "Slack create message from webhook payload": (
            SLACK_CREATE_MESSAGE_MODULE_ID
        ),
    }
    for query, expected_module_id in single_app_cases.items():
        payload = _search_payload(tmp_path=tmp_path, query=query)
        modules = cast("list[JsonObject]", payload["module_candidates"])

        assert modules[0]["module_id"] == expected_module_id, query
        assert modules[0]["rank_reason"] in {
            "exact_app_slug_and_internal_name ",
            "exact_app_slug_and_display_name ",
            "app_slug_intent_match",
        }

    for query in (
        "Gmail to Slack notification when a new email arrives ",
        "Gmail attachment to Slack channel ",
        "Slack Gmail send message email workflow automation ",
        "Gmail Slack explicit app intent send channel message watch email",
    ):
        payload = _search_payload(tmp_path=tmp_path, query=query)
        modules = cast("list[JsonObject]", payload["module_candidates"])
        top_apps = {str(candidate["app_slug"]) for candidate in modules[:3]}

        assert {"google-email", "slack"}.issubset(top_apps), query
        assert _module_index(
            modules, MICROSOFT_EMAIL_SEND_MODULE_ID
        ) > _first_module_index(
            modules=modules,
            module_ids=(
                GMAIL_SEND_EMAIL_MODULE_ID,
                GMAIL_WATCH_EMAIL_MODULE_ID,
            ),
        )
        _assert_app_bound_graphs_outrank_empty_app_graphs(payload)


def test_catalog_search_v10_control_surfaces_beat_generic_json(
    tmp_path: Path,
) -> None:
    """Webhook, data-store, router, filter, retry, and error-handler intent.

    beats.

    JSON.
    """
    _prepare_search_fixture(tmp_path)

    expected_control_edges = {
        "webhook to datastore": "edge:catalog:webhook-to-datastore ",
        "custom webhook save payload in data store": (
            "edge:catalog:webhook-to-datastore "
        ),
        "route webhook events to different handlers": (
            "edge:catalog:router-control "
        ),
        "filter webhook payload before Slack notification": (
            "edge:catalog:filter-control "
        ),
        "retry failed Gmail to Slack workflow": "edge:catalog:error-retry ",
        "error handler for Slack message send failure": (
            "edge:catalog:error-retry"
        ),
    }
    for query, expected_edge_id in expected_control_edges.items():
        payload = _search_payload(tmp_path=tmp_path, query=query)
        graph_candidates = cast("list[JsonObject]", payload["graph_candidates"])
        expected_index = _graph_index(graph_candidates, expected_edge_id)
        generic_json_index = _graph_index_or_none(
            graph_candidates,
            "edge:catalog:generic-json-payload-field",
        )
        expected_candidate = graph_candidates[expected_index]

        if generic_json_index is not None:
            assert expected_index < generic_json_index, query
        assert expected_candidate["matched_control_surface_terms"], query
        assert "explicit_control_surface_bonus" in cast(
            "tuple[str, ...]",
            expected_candidate["applied_bonuses"],
        )


def test_catalog_search_v10_json_utility_is_promoted_only_when_requested(
    tmp_path: Path,
) -> None:
    """JSON utility candidates rank highly for JSON queries, not app-intent.

    queries.
    """
    _prepare_search_fixture(tmp_path)

    for query in (
        "create JSON from mapped fields ",
        "parse JSON payload ",
        "convert JSON to XML ",
        "aggregate records into JSON",
        (
            "generic json no app high rank graph candidate residual ranking "
            "after "
            "v9"
        ),
    ):
        payload = _search_payload(tmp_path=tmp_path, query=query)
        modules = cast("list[JsonObject]", payload["module_candidates"])
        graph_candidates = cast("list[JsonObject]", payload["graph_candidates"])
        json_candidate = graph_candidates[
            _graph_index(
                graph_candidates,
                "edge:catalog:generic-json-payload-field",
            )
        ]

        assert modules[0]["app_slug"] == "json", query
        assert modules[0]["module_id"] in {
            JSON_CREATE_MODULE_ID,
            JSON_PARSE_MODULE_ID,
        }
        assert json_candidate["generic_utility_candidate"] is True
        assert "explicit_generic_utility_bonus" in cast(
            "tuple[str, ...]",
            json_candidate["applied_bonuses"],
        )
        assert json_candidate["no_app_score_cap_applied"] is False

    app_payload = _search_payload(
        tmp_path=tmp_path,
        query="Gmail to Slack json payload",
    )
    _assert_graph_edge_is_demoted(
        payload=app_payload,
        edge_id="edge:catalog:generic-json-payload-field",
    )


def test_catalog_search_v10_api_surfaces_require_named_app_binding(
    tmp_path: Path,
) -> None:
    """Named API surfaces outrank generic endpoint-only API candidates."""
    _prepare_search_fixture(tmp_path)

    expected_modules = {
        "make an API call in HubSpot": HUBSPOT_API_CALL_MODULE_ID,
        "execute monday GraphQL query": MONDAY_GRAPHQL_QUERY_MODULE_ID,
        "Microsoft Graph API email call": MICROSOFT_GRAPH_API_CALL_MODULE_ID,
    }
    expected_edges = {
        "make an API call in HubSpot": "edge:catalog:hubspot-api-call ",
        "execute monday GraphQL query": "edge:catalog:monday-graphql-query ",
        "Microsoft Graph API email call": (
            "edge:catalog:microsoft-graph-email-api"
        ),
    }
    for query, expected_module_id in expected_modules.items():
        payload = _search_payload(tmp_path=tmp_path, query=query)
        modules = cast("list[JsonObject]", payload["module_candidates"])
        graph_candidates = cast("list[JsonObject]", payload["graph_candidates"])
        expected_graph = graph_candidates[
            _graph_index(graph_candidates, expected_edges[query])
        ]
        generic_api = graph_candidates[
            _graph_index(
                graph_candidates,
                "edge:catalog:generic-api-endpoint",
            )
        ]

        assert modules[0]["module_id"] == expected_module_id, query
        assert expected_graph["matched_app_intents"], query
        assert _graph_index(
            graph_candidates, expected_edges[query]
        ) < _graph_index(
            graph_candidates,
            "edge:catalog:generic-api-endpoint",
        )
        assert "endpoint_only_penalty" in cast(
            "tuple[str, ...]",
            generic_api["applied_penalties"],
        )

    gmail_payload = _search_payload(
        tmp_path=tmp_path,
        query="generic API call after Gmail trigger",
    )
    modules = cast("list[JsonObject]", gmail_payload["module_candidates"])
    graph_candidates = cast(
        "list[JsonObject]", gmail_payload["graph_candidates"]
    )
    generic_api = graph_candidates[
        _graph_index(graph_candidates, "edge:catalog:generic-api-endpoint")
    ]

    assert modules[0]["app_slug"] == "google-email"
    _assert_app_bound_graphs_outrank_empty_app_graphs(gmail_payload)
    assert "endpoint_only_penalty" in cast(
        "tuple[str, ...]", generic_api["applied_penalties"]
    )


def test_catalog_search_defers_field_scan_when_module_hits_fill_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """App-intent searches must not scan field rows when compact module hits.

    are.

    enough.
    """
    _prepare_search_fixture(tmp_path)

    def fail_field_scan(**_kwargs: object) -> list[JsonObject]:
        msg = "catalog.search should not scan fields for filled app-intent hits"
        raise AssertionError(msg)

    monkeypatch.setattr(
        catalog_search_module, "_field_candidate_module_rows", fail_field_scan
    )

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "connect slack to gmail", "limit": 3},
        repo_root=tmp_path,
    )

    assert result.ok, result
    module_candidates = cast(
        "list[JsonObject]", result.payload["module_candidates"]
    )
    assert [candidate["module_id"] for candidate in module_candidates[:2]] == [
        SLACK_CREATE_MESSAGE_MODULE_ID,
        GMAIL_SEND_EMAIL_MODULE_ID,
    ]


def test_catalog_search_returns_bounded_compact_field_candidates(
    tmp_path: Path,
) -> None:
    """Field-specific searches expose direct fields without dumping full.

    schemas.
    """
    _prepare_search_fixture(tmp_path)

    slack_result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "slack attachment fallback", "limit": 4},
        repo_root=tmp_path,
    )
    gmail_result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "google email attachment fields", "limit": 4},
        repo_root=tmp_path,
    )
    datastore_result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "data store key fields", "limit": 4},
        repo_root=tmp_path,
    )

    assert slack_result.ok, slack_result
    assert gmail_result.ok, gmail_result
    assert datastore_result.ok, datastore_result

    slack_fields = cast(
        "list[JsonObject]", slack_result.payload["field_candidates"]
    )
    gmail_fields = cast(
        "list[JsonObject]", gmail_result.payload["field_candidates"]
    )
    datastore_fields = cast(
        "list[JsonObject]", datastore_result.payload["field_candidates"]
    )
    search_order = cast("list[str]", slack_result.payload["search_order"])

    assert len(slack_fields) <= 4
    assert len(gmail_fields) <= 4
    assert len(datastore_fields) <= 4
    assert "field_candidates" in search_order
    assert slack_result.payload["returned_field_candidate_count"] == len(
        slack_fields
    )
    assert cast(
        "int", gmail_result.payload["total_field_candidate_count"]
    ) >= len(gmail_fields)

    fallback_field = slack_fields[0]
    assert fallback_field["kind"] == "catalog_module_field"
    assert fallback_field["module_id"] == SLACK_CREATE_MESSAGE_MODULE_ID
    assert fallback_field["field_path"] == "mapper.attachments[].fallback"
    assert fallback_field["field_type"] == "text"
    assert fallback_field["required"] is False
    assert (
        fallback_field["source_ref"]
        == "tests/mcp/tool_contracts/mcp_catalog_search_contract.py"
    )
    assert "raw_schema_json" not in fallback_field

    gmail_paths = {str(field["field_path"]) for field in gmail_fields}
    assert "mapper.attachments[]" in gmail_paths
    assert "mapper.attachments[].data" in gmail_paths
    assert "mapper.attachments[].fileName" in gmail_paths
    assert all("raw_schema_json" not in field for field in gmail_fields)

    datastore_key_field = datastore_fields[0]
    assert datastore_key_field["module_id"] == DATASTORE_ADD_RECORD_MODULE_ID
    assert datastore_key_field["field_path"] == "mapper.key"
    assert datastore_key_field["label"] == "Record key"
    assert datastore_key_field["field_type"] == "text"
    assert datastore_key_field["required"] is True
    assert datastore_key_field["source_ref"]
    assert "raw_schema_json" not in datastore_key_field


def test_module_intelligence_derives_raw_spec_metadata_without_telemetry() -> (
    None
):
    """Raw specs populate structural metadata without inventing runtime.

    telemetry.
    """
    derived = derive_module_intelligence_metadata(
        _slack_raw_spec_module_metadata()
    )

    assert derived.input_schema_json is not None
    assert derived.output_schema_json is not None
    assert derived.field_constraints_json is not None
    assert derived.output_cardinality == "single_bundle"
    assert derived.requires_iterator == 0
    assert derived.suggested_control_structures_json == '["filter"]'
    input_schema = cast("JsonObject", json.loads(derived.input_schema_json))
    output_schema = cast("JsonObject", json.loads(derived.output_schema_json))
    field_constraints = cast(
        "list[JsonObject]", json.loads(derived.field_constraints_json)
    )
    assert input_schema == {
        "channel": {"label": "Channel", "required": True, "type": "text"},
        "priority": {
            "label": "Priority",
            "options": ["normal", "urgent"],
            "required": False,
            "type": "select",
        },
        "text": {"label": "Message text", "required": True, "type": "text"},
    }
    assert output_schema == {"message_id": {"type": "text"}}
    assert field_constraints == [
        {"constraint": "required", "path": "channel"},
        {"constraint": "required", "path": "text"},
        {"constraint": "finite_options", "path": "priority"},
    ]


def test_catalog_search_and_inspect_bound_module_intelligence_details(
    tmp_path: Path,
) -> None:
    """Search stays compact, while inspect exposes full module intelligence.

    metadata.
    """
    _prepare_search_fixture(tmp_path)
    derived = derive_module_intelligence_metadata(
        _slack_raw_spec_module_metadata()
    )
    _insert_module_intelligence_metadata(
        tmp_path,
        module_id=SLACK_CREATE_MESSAGE_MODULE_ID,
        evidence_status="raw_spec_evidence",
        derived=derived,
    )

    searched = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "slack create message", "limit": 4},
        repo_root=tmp_path,
    )
    inspected = execute_mcp_tool(
        tool_name="catalog.inspect",
        arguments={
            "module_id": SLACK_CREATE_MESSAGE_MODULE_ID,
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert searched.ok, searched
    assert inspected.ok, inspected
    module_candidates = cast(
        "list[JsonObject]", searched.payload["module_candidates"]
    )
    candidate = module_candidates[0]
    compact = cast("JsonObject", candidate["module_intelligence"])
    assert compact["evidence_status"] == "raw_spec_evidence"
    assert compact["output_cardinality"] == "single_bundle"
    assert compact["requires_iterator"] is False
    assert compact["available_detail_fields"] == [
        "input_schema_json ",
        "output_schema_json ",
        "field_constraints_json ",
        "suggested_control_structures_json",
    ]
    assert "input_schema" not in compact
    assert "output_schema" not in compact
    full = cast("JsonObject", inspected.payload["module_intelligence"])
    assert full["input_schema"] == {
        "channel": {"label": "Channel", "required": True, "type": "text"},
        "priority": {
            "label": "Priority",
            "options": ["normal", "urgent"],
            "required": False,
            "type": "select",
        },
        "text": {"label": "Message text", "required": True, "type": "text"},
    }
    assert full["output_schema"] == {"message_id": {"type": "text"}}
    assert full["field_constraints"] == [
        {"constraint": "required", "path": "channel"},
        {"constraint": "required", "path": "text"},
        {"constraint": "finite_options", "path": "priority"},
    ]
    assert full["suggested_control_structures"] == ["filter"]
    telemetry = cast("JsonObject", full["telemetry"])
    assert telemetry["error_rate_percentage"] is None
    assert telemetry["api_rate_limit_rpm"] is None
    assert telemetry["avg_execution_time_ms"] is None
    assert full["auth_type"] is None
    assert full["required_scopes"] is None
    assert full["operation_cost_multiplier"] is None


def test_catalog_inspect_keeps_unknown_module_intelligence_fields_null(
    tmp_path: Path,
) -> None:
    """Unknown evidence rows remain explicit gaps rather than fabricated.

    metadata.
    """
    _prepare_search_fixture(tmp_path)
    _insert_module_intelligence_metadata(
        tmp_path,
        module_id=DATASTORE_ADD_RECORD_MODULE_ID,
        evidence_status="unknown",
        derived=DerivedModuleIntelligenceMetadata(
            input_schema_json=None,
            output_schema_json=None,
            field_constraints_json=None,
            output_cardinality=None,
            requires_iterator=None,
            suggested_control_structures_json=None,
        ),
    )

    inspected = execute_mcp_tool(
        tool_name="catalog.inspect",
        arguments={
            "module_id": DATASTORE_ADD_RECORD_MODULE_ID,
            "output_mode": "full",
        },
        repo_root=tmp_path,
    )

    assert inspected.ok, inspected
    metadata = cast("JsonObject", inspected.payload["module_intelligence"])
    telemetry = cast("JsonObject", metadata["telemetry"])
    assert metadata["evidence_status"] == "unknown"
    assert metadata["available_detail_fields"] == []
    assert metadata["input_schema"] is None
    assert metadata["output_schema"] is None
    assert metadata["field_constraints"] is None
    assert metadata["suggested_control_structures"] is None
    assert telemetry["error_rate_percentage"] is None
    assert telemetry["api_rate_limit_rpm"] is None
    assert telemetry["avg_execution_time_ms"] is None
    assert metadata["auth_type"] is None
    assert metadata["required_scopes"] is None
    assert metadata["operation_cost_multiplier"] is None


def test_catalog_search_parallel_reads_are_read_only_and_deterministic(
    tmp_path: Path,
) -> None:
    """Parallel catalog reads use read-only SQLite handles without write side.

    effects.
    """
    _prepare_search_fixture(tmp_path)
    before_counts = _catalog_runtime_counts(tmp_path)
    queries = (
        "slack ActionCreateMessage ",
        "datastore AddRecord ",
        "BasicRouter",
        SLACK_CREATE_MESSAGE_MODULE_ID,
    )

    def run_query(query: str) -> JsonObject:
        report = execute_mcp_tool(
            tool_name="catalog.search",
            arguments={"query": query, "limit": 4},
            repo_root=tmp_path,
        )
        assert report.ok, report
        return report.payload

    with ThreadPoolExecutor(max_workers=4) as executor:
        payloads = tuple(executor.map(run_query, queries * 3))

    assert _catalog_runtime_counts(tmp_path) == before_counts
    assert len(payloads) == 12
    for payload in payloads:
        read_policy = cast("JsonObject", payload["sqlite_read_policy"])
        assert read_policy["operation_class"] == "routine_mcp_read"
        assert read_policy["connection_mode"] == "read_only_uri"
        assert read_policy["query_only"] is True
        assert read_policy["shared_cache"] is True
        assert read_policy["busy_timeout_milliseconds"] == 5_000
        assert read_policy["busy_timeout_policy"] == "bounded_read_timeout"
        assert read_policy["lock_error_code"] == "sqlite_read_busy_timeout"
        assert read_policy["slow_maintenance_mode"] is False
        assert read_policy["slow_maintenance_mode_required"] is True
        assert read_policy["slow_maintenance_timeout_milliseconds"] == 300_000
        assert payload["writes_performed"] is False
        assert payload["cursor_advanced"] is False
        assert payload["provider_api_call"] is False
        assert payload["live_make_called"] is False
        if payload["query"] == "slack ActionCreateMessage":
            candidates = cast("list[JsonObject]", payload["module_candidates"])
            assert candidates[0]["module_id"] == SLACK_CREATE_MESSAGE_MODULE_ID


def test_catalog_search_reports_bounded_sqlite_lock_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read locks produce actionable MCP payloads instead of unbounded waits."""
    _prepare_search_fixture(tmp_path)
    call_count = 0

    def connect_or_lock(database_path: Path) -> sqlite3.Connection:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            return connection
        msg = "database is locked"
        raise sqlite3.OperationalError(msg)

    monkeypatch.setattr(
        catalog_search_module,
        "_connect_catalog_search_readonly",
        connect_or_lock,
    )

    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": "slack", "limit": 4},
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    read_policy = cast("JsonObject", payload["sqlite_read_policy"])
    assert payload["status"] == "blocked"
    assert payload["blocker_code"] == "sqlite_read_busy_timeout"
    assert payload["sqlite_operation"] == "catalog.search"
    assert read_policy["busy_timeout_milliseconds"] == 5_000
    assert "Pancakes SQLite lock" in str(payload["recommended_action"])


def test_catalog_inspect_reports_bounded_sqlite_lock_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inspect read locks use the same bounded and actionable SQLite policy."""
    _prepare_search_fixture(tmp_path)
    call_count = 0

    def connect_or_lock(database_path: Path) -> sqlite3.Connection:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            return connection
        msg = "database is locked"
        raise sqlite3.OperationalError(msg)

    monkeypatch.setattr(
        catalog_search_module,
        "_connect_catalog_search_readonly",
        connect_or_lock,
    )

    result = execute_mcp_tool(
        tool_name="catalog.inspect",
        arguments={
            "module_id": SLACK_CREATE_MESSAGE_MODULE_ID,
            "output_mode": "compact",
        },
        repo_root=tmp_path,
    )

    assert result.ok, result
    payload = result.payload
    read_policy = cast("JsonObject", payload["sqlite_read_policy"])
    assert payload["status"] == "blocked"
    assert payload["blocker_code"] == "sqlite_read_busy_timeout"
    assert payload["sqlite_operation"] == "catalog.inspect"
    assert read_policy["operation_class"] == "routine_mcp_read"
    assert read_policy["busy_timeout_milliseconds"] == 5_000
    assert read_policy["slow_maintenance_mode"] is False
    assert read_policy["slow_maintenance_mode_required"] is True
    assert "Pancakes SQLite lock" in str(payload["recommended_action"])


def test_catalog_search_snapshot_fixture_uses_hardlinks(tmp_path: Path) -> None:
    """The large SQL snapshot fixture must not duplicate gigabytes per temp.

    repo.
    """
    _prepare_snapshot_dir(tmp_path)
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR / "make.sql"
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR / "make.sql"

    assert destination.exists()
    assert source.samefile(destination)


def _search_payload(
    *, tmp_path: Path, query: str, limit: int = 12
) -> JsonObject:
    """Return one debug search payload from the synthetic fixture."""
    result = execute_mcp_tool(
        tool_name="catalog.search",
        arguments={"query": query, "limit": limit, "output_mode": "debug"},
        repo_root=tmp_path,
    )
    assert result.ok, result
    return result.payload


def _module_index(modules: list[JsonObject], module_id: str) -> int:
    """Return a module candidate index or a large fallback index."""
    for index, module in enumerate(modules):
        if module["module_id"] == module_id:
            return index
    return len(modules) + 1


def _first_module_index(
    *, modules: list[JsonObject], module_ids: tuple[str, ...]
) -> int:
    """Return the first index for any matching module ID."""
    return min(_module_index(modules, module_id) for module_id in module_ids)


def _graph_index(graph_candidates: list[JsonObject], edge_id: str) -> int:
    """Return a graph edge index, failing with the visible candidate list.

    Raises:
        AssertionError: If the graph edge id is absent.
    """
    for index, candidate in enumerate(graph_candidates):
        if candidate["edge_id"] == edge_id:
            return index
    candidate_ids = [
        str(candidate["edge_id"]) for candidate in graph_candidates
    ]
    msg = f"Missing graph edge {edge_id}: {candidate_ids}"
    raise AssertionError(msg)


def _graph_index_or_none(
    graph_candidates: list[JsonObject], edge_id: str
) -> int | None:
    """Return the computed result for the caller."""
    for index, candidate in enumerate(graph_candidates):
        if candidate["edge_id"] == edge_id:
            return index
    return None


def _assert_app_bound_graphs_outrank_empty_app_graphs(
    payload: JsonObject,
) -> None:
    """Assert empty matched-app graph candidates do not outrank app-bound.

    candidates.
    """
    graph_candidates = cast("list[JsonObject]", payload["graph_candidates"])
    app_bound_indexes = [
        index
        for index, candidate in enumerate(graph_candidates)
        if candidate["matched_app_intents"]
    ]
    empty_app_indexes = [
        index
        for index, candidate in enumerate(graph_candidates)
        if not candidate["matched_app_intents"]
    ]
    assert app_bound_indexes, graph_candidates
    if empty_app_indexes:
        assert min(app_bound_indexes) < min(empty_app_indexes), graph_candidates


def _assert_graph_edge_is_demoted(*, payload: JsonObject, edge_id: str) -> None:
    """Assert one fallback graph edge is behind an app-bound result with policy.

    metadata.
    """
    graph_candidates = cast("list[JsonObject]", payload["graph_candidates"])
    candidate = graph_candidates[_graph_index(graph_candidates, edge_id)]
    candidate_index = _graph_index(graph_candidates, edge_id)
    app_bound_indexes = [
        index
        for index, graph_candidate in enumerate(graph_candidates)
        if graph_candidate["matched_app_intents"]
    ]

    assert app_bound_indexes, graph_candidates
    assert min(app_bound_indexes) < candidate_index, graph_candidates
    assert candidate["matched_app_intents"] == ()
    assert candidate["applied_penalties"], candidate


def _prepare_search_fixture(tmp_path: Path) -> None:
    """Create a synthetic SQLite SSOT fixture for catalog.search."""
    _prepare_snapshot_dir(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        _insert_search_fixture_rows(connection)
        connection.commit()
    finally:
        connection.close()


def _prepare_snapshot_dir(tmp_path: Path) -> None:
    """Copy tracked SQL snapshots into a temporary repository root."""
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination, copy_function=_copy_snapshot_file)


def _copy_snapshot_file(source: str, destination: str) -> str:
    """Return the computed result for the caller."""
    try:
        os.link(source, destination)
    except OSError:
        return copy2(source, destination)
    return destination


def _delete_webhook_structure_rows(tmp_path: Path) -> None:
    """Remove populated webhook evidence from a synthetic fixture."""
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        _ = connection.execute("DELETE FROM make_webhook_structure_evidence")
        connection.commit()
    finally:
        connection.close()


def _insert_search_fixture_rows(connection: sqlite3.Connection) -> None:
    """Insert deterministic local-only catalog facts."""
    for module in (
        (
            SLACK_CREATE_MESSAGE_MODULE_ID,
            "slack ",
            "2.14.3 ",
            "action ",
            "ActionCreateMessage ",
            "Create Message ",
            "slack-create-message",
        ),
        (
            GMAIL_SEND_EMAIL_MODULE_ID,
            "google-email ",
            "2.4.1 ",
            "action ",
            "SendEmail ",
            "Send Email ",
            "gmail-send-email",
        ),
        (
            GMAIL_WATCH_EMAIL_MODULE_ID,
            "google-email ",
            "2.4.1 ",
            "trigger ",
            "WatchEmail ",
            "Watch Email ",
            "gmail-watch-email",
        ),
        (
            MICROSOFT_EMAIL_SEND_MODULE_ID,
            "microsoft-email ",
            "1.0.0 ",
            "action ",
            "SendEmail ",
            "Send Email ",
            "microsoft-email-send-email",
        ),
        (
            MICROSOFT_GRAPH_API_CALL_MODULE_ID,
            "microsoft-graph ",
            "1.0.0 ",
            "action ",
            "MicrosoftGraphApiCall ",
            "Microsoft Graph API Call ",
            "microsoft-graph-api-call",
        ),
        (
            JSON_CREATE_MODULE_ID,
            "json ",
            "1.0.0 ",
            "transformer ",
            "CreateJson ",
            "Create JSON ",
            "json-create",
        ),
        (
            JSON_PARSE_MODULE_ID,
            "json ",
            "1.0.0 ",
            "transformer ",
            "ParseJson ",
            "Parse JSON ",
            "json-parse",
        ),
        (
            HUBSPOT_API_CALL_MODULE_ID,
            "hubspot-marketing-hub ",
            "1.0.0 ",
            "action ",
            "MakeApiCall ",
            "Make an API Call ",
            "hubspot-api-call",
        ),
        (
            MONDAY_GRAPHQL_QUERY_MODULE_ID,
            "monday ",
            "1.0.0 ",
            "action ",
            "ExecuteGraphqlQuery ",
            "Execute GraphQL Query ",
            "monday-graphql-query",
        ),
        (
            GENERIC_API_CALL_MODULE_ID,
            "http ",
            "1.0.0 ",
            "action ",
            "MakeApiCall ",
            "Make an API Call ",
            "generic-api-call",
        ),
        (
            GATEWAY_CUSTOM_WEBHOOK_MODULE_ID,
            "gateway ",
            "1.0.0 ",
            "trigger ",
            "CustomWebhook ",
            "Custom Webhook ",
            "gateway-custom-webhook",
        ),
        (
            BASECAMP_CREATE_MESSAGE_MODULE_ID,
            "basecamp ",
            "1.0.0 ",
            "action ",
            "ActionCreateMessage ",
            "Create Message ",
            "basecamp-create-message",
        ),
        (
            AGILEPLACE_CONNECT_CARDS_MODULE_ID,
            "agileplace ",
            "1.0.1 ",
            "action ",
            "connectCards ",
            "Connect Cards ",
            "agileplace-connect-cards",
        ),
        (
            BASIC_ROUTER_MODULE_ID,
            "builtin ",
            "1.0.0 ",
            "router ",
            "BasicRouter ",
            "Basic Router ",
            "basic-router",
        ),
        (
            DATASTORE_ADD_RECORD_MODULE_ID,
            "datastore ",
            "2.0.0 ",
            "action ",
            "AddRecord ",
            "Add Record ",
            "datastore-add-record",
        ),
    ):
        _insert_module(connection, module)
    _insert_field(
        connection,
        (
            "field:slack:account",
            SLACK_CREATE_MESSAGE_MODULE_ID,
            "parameters.account ",
            "Slack account",
            True,
            "connection",
            {"runtime": "connection"},
        ),
    )
    for field in (
        (
            "field:slack:attachment:fallback",
            SLACK_CREATE_MESSAGE_MODULE_ID,
            "mapper.attachments[].fallback ",
            "Attachment fallback text",
            False,
            "text",
            {
                "description": "Fallback text used when an attachment value is "
                "missing."
            },
        ),
        (
            "field:google-email:attachments",
            GMAIL_SEND_EMAIL_MODULE_ID,
            "mapper.attachments[]",
            "Email attachments",
            False,
            "array",
            {
                "items": {"type": "file"},
                "make_surface": "attachment field array",
            },
        ),
        (
            "field:google-email:attachments:fileName",
            GMAIL_SEND_EMAIL_MODULE_ID,
            "mapper.attachments[].fileName ",
            "Attachment file name",
            False,
            "text",
            {
                "description": "Attachment filename mapped into the outbound "
                "email."
            },
        ),
        (
            "field:google-email:attachments:data",
            GMAIL_SEND_EMAIL_MODULE_ID,
            "mapper.attachments[].data ",
            "Attachment file content",
            False,
            "file",
            {
                "description": "Attachment content mapped into the outbound "
                "email."
            },
        ),
        (
            "field:datastore:key",
            DATASTORE_ADD_RECORD_MODULE_ID,
            "mapper.key ",
            "Record key",
            True,
            "text",
            {
                "description": "Unique datastore key used for idempotent "
                "upserts."
            },
        ),
        (
            "field:datastore:value",
            DATASTORE_ADD_RECORD_MODULE_ID,
            "mapper.value ",
            "Record value",
            True,
            "collection",
            {"description": "Structured datastore value stored under the key."},
        ),
    ):
        _insert_field(connection, field)
    _ = connection.execute(
        """
        INSERT INTO catalog_search_documents (
          document_id, surface, title, body, record_kind, tags_json,
          search_text,
          source_kind, source_ref, fingerprint, valid_from, valid_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "doc:lead-webhook ",
            "webhook ",
            "Lead webhook payload ",
            "Lead webhook payload includes email and source fields.",
            "webhook_structure",
            json.dumps(["lead", "webhook"]),
            "lead webhook email source ",
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py ",
            "fixture-search-document",
            OBSERVED_AT,
            None,
        ),
    )
    _insert_catalog_plan_rows(connection)
    _insert_webhook_structure_row(connection)
    _insert_saved_connection_output_and_graph(connection)


def _insert_module(
    connection: sqlite3.Connection,
    module: tuple[str, str, str, str, str, str, str],
) -> None:
    """Insert one synthetic module row."""
    _ = connection.execute(
        """
        INSERT INTO modules (
          module_id, app_slug, app_version, module_kind, internal_name,
          display_name,
          external_id, deprecated, raw_spec_sha256, source_kind, source_ref,
          valid_from,
          valid_to, fingerprint, adr_anchor
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            module[0],
            module[1],
            module[2],
            module[3],
            module[4],
            module[5],
            module[6],
            0,
            f"test-sha:{module[0]}",
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
            OBSERVED_AT,
            None,
            f"fixture-module:{module[0]}",
            "test.catalog.search.module",
        ),
    )


def _insert_field(
    connection: sqlite3.Connection,
    field: tuple[str, str, str, str, bool, str, object],
) -> None:
    """Insert one synthetic field row for fuzzy fallback coverage."""
    _ = connection.execute(
        """
        INSERT INTO fields (
          field_id, module_id, direction, path, label, required, field_type,
          raw_schema_json, source_kind, source_ref, valid_from, valid_to,
          fingerprint,
          adr_anchor
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            field[0],
            field[1],
            "parameter",
            field[2],
            field[3],
            int(field[4]),
            field[5],
            json.dumps(field[6], sort_keys=True),
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
            OBSERVED_AT,
            None,
            f"fixture-field:{field[0]}",
            "test.catalog.search.field",
        ),
    )


def _insert_catalog_plan_rows(connection: sqlite3.Connection) -> None:
    """Insert one semantic answer and one missing-evidence record."""
    _ = connection.execute(
        """
        INSERT INTO catalog_plan_ranges (
          range_id, range_label, range_start, range_end, surface, status,
          source_kind,
          source_ref, fingerprint, valid_from, valid_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "000001-000002",
            1,
            2,
            "lead webhook and datastore semantics ",
            "active ",
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py ",
            "fixture-range",
            OBSERVED_AT,
            None,
        ),
    )
    for unit_number, unit_id, status in (
        (1, "000001", "semantic_answered"),
        (2, "000002", "quarantined"),
    ):
        _ = connection.execute(
            """
            INSERT INTO catalog_plan_units (
              unit_number, range_id, status, surface, evidence_path,
              commit_hash,
              semantic_answer_sha256, updated_at_utc, source_kind, source_ref,
              fingerprint,
              valid_from, valid_to
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit_number,
                1,
                status,
                "lead webhook and datastore semantics",
                f"synthetic/{unit_id}.md",
                "",
                None,
                OBSERVED_AT,
                "test_fixture ",
                "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
                f"fixture-unit-{unit_id}",
                OBSERVED_AT,
                None,
            ),
        )
    _ = connection.execute(
        """
        INSERT INTO catalog_plan_semantic_answers (
          unit_number, unit_id, answer_json, answer_sha256, answer_status,
          evidence_status, source_kind, source_ref, created_at_utc,
          saved_by_tool, valid_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            1,
            "000001",
            json.dumps(
                {
                    "legacy_note": (
                        "Legacy semantic answer mentioning a generic connect "
                        "workflow must not "
                        "outrank saved canonical catalog outputs."
                    ),
                    "summary": "Lead webhook semantic fixture.",
                },
                sort_keys=True,
            ),
            "fixture-answer-sha ",
            "semantic_answered ",
            "synthetic_evidence ",
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
            OBSERVED_AT,
            "catalog.work.save",
            None,
        ),
    )
    _ = connection.execute(
        """
        INSERT INTO catalog_plan_quarantine_records (
          quarantine_id, unit_number, unit_id, quarantine_kind, reason,
          evidence_gap_json,
          retry_policy_json, priority, source_kind, source_ref, status,
          created_at_utc,
          resolved_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "quarantine:000002",
            2,
            "000002 ",
            "missing_structure_evidence ",
            "Lead datastore structure sample is missing.",
            json.dumps({"missing": ["datastore structure"]}, sort_keys=True),
            json.dumps({"next": "scrape datastore and retry"}, sort_keys=True),
            100,
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py ",
            "open",
            OBSERVED_AT,
            None,
        ),
    )


def _insert_webhook_structure_row(connection: sqlite3.Connection) -> None:
    """Insert one matching webhook structure evidence row."""
    _ = connection.execute(
        """
        INSERT INTO make_webhook_structure_evidence (
          evidence_id, app_slug, webhook_slug, structure_json, source_kind,
          source_ref,
          observed_at_utc, fingerprint, valid_from, valid_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "webhook:lead ",
            "gateway ",
            "lead-webhook",
            json.dumps({"fields": ["email", "source"]}, sort_keys=True),
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
            OBSERVED_AT,
            "fixture-webhook",
            OBSERVED_AT,
            None,
        ),
    )


def _insert_saved_connection_output_and_graph(
    connection: sqlite3.Connection,
) -> None:
    """Insert a saved canonical catalog output and graph edge for connection.

    lookup.
    """
    _ = start_catalog_quality_reset_run(
        connection=connection,
        run_id="catalog-run-search-connection-fixture",
        units=(
            CatalogResetUnitInput(
                unit_id="raw-spec:slack-gmail-connection:1.0.0",
                unit_type="raw_spec",
                priority_band="popular_apps",
                source_ref="synthetic:raw/slack-gmail-connection",
                source_hash="sha256:slack-gmail-connection",
                source_size_bytes=4_096,
                complexity_score=4_096,
            ),
        ),
        source_ref="test.catalog.search.connection-graph",
        observed_at_utc=OBSERVED_AT,
    )
    output_json = {
        "semantic_summary": (
            "Connect Slack to Gmail by receiving Slack message context and "
            "sending a Gmail "
            "email with mapped text, recipient, and subject fields."
        ),
        "app_family_aliases": ["slack", "gmail", "google-email"],
        "module_roles": [
            {
                "module_id": SLACK_CREATE_MESSAGE_MODULE_ID,
                "role": "upstream Slack message or event source",
            },
            {
                "module_id": GMAIL_SEND_EMAIL_MODULE_ID,
                "role": "downstream Gmail email send action",
            },
        ],
        "setup_dependencies": ["Slack connection", "Gmail connection"],
        "workflow_edges": [
            {
                "from_app": "slack ",
                "to_app": "google-email ",
                "intent": "connect slack to gmail",
            },
        ],
        "graph_nodes": [
            {"node_id": "node:catalog:app:slack", "label": "Slack"},
            {"node_id": "node:catalog:app:google-email", "label": "Gmail"},
        ],
        "graph_edges": [
            {
                "edge_kind": "connects_to ",
                "from_node_id": "node:catalog:app:slack ",
                "to_node_id": "node:catalog:app:google-email",
            },
        ],
        "quarantine": [],
        "coverage": {
            "status": "complete_evidence_bound ",
            "semantic": "complete ",
            "graph": "complete",
        },
    }
    output_text = json.dumps(output_json, sort_keys=True)
    _ = connection.execute(
        """
        INSERT INTO catalog_unit_outputs (
          run_id, unit_id, lease_token, worker_id, output_json, output_sha256,
          validation_status, saved_by_tool, created_at_utc, source_kind,
          source_ref,
          fingerprint
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "catalog-run-search-connection-fixture ",
            "raw-spec:slack-gmail-connection:1.0.0 ",
            "lease-token:search-fixture ",
            "ChatGPT.com/catalog-search-fixture",
            output_text,
            "sha256:search-fixture-output ",
            "valid ",
            "catalog.work.save",
            OBSERVED_AT,
            "test_fixture ",
            "tests/mcp/tool_contracts/mcp_catalog_search_contract.py ",
            "fingerprint:search-fixture-output",
        ),
    )
    for node_id, canonical_label, payload_json in (
        (
            "node:catalog:app:slack ",
            "Slack",
            {"app_slug": "slack", "aliases": ["slack"]},
        ),
        (
            "node:catalog:app:google-email ",
            "Gmail",
            {"app_slug": "google-email", "aliases": ["gmail", "google mail"]},
        ),
        (
            "node:catalog:app:gateway ",
            "Webhook",
            {"app_slug": "gateway", "aliases": ["webhook", "custom webhook"]},
        ),
        (
            "node:catalog:app:json",
            "JSON",
            {"app_slug": "json", "aliases": ["json", "parse json"]},
        ),
        (
            "node:catalog:app:datastore ",
            "Data store",
            {"app_slug": "datastore", "aliases": ["datastore", "dedupe"]},
        ),
        (
            "node:catalog:app:hubspot-marketing-hub ",
            "HubSpot",
            {"app_slug": "hubspot-marketing-hub", "aliases": ["hubspot"]},
        ),
        (
            "node:catalog:app:monday ",
            "monday.com",
            {"app_slug": "monday", "aliases": ["monday", "monday.com"]},
        ),
        (
            "node:catalog:app:microsoft-email ",
            "Microsoft Email",
            {
                "app_slug": "microsoft-email",
                "aliases": ["outlook", "microsoft email"],
            },
        ),
        (
            "node:catalog:app:microsoft-graph ",
            "Microsoft Graph",
            {
                "app_slug": "microsoft-graph",
                "aliases": ["microsoft graph", "ms graph"],
            },
        ),
        (
            "node:catalog:control:router ",
            "Router",
            {"aliases": ["router", "routers", "basic router"]},
        ),
        (
            "node:catalog:control:filter ",
            "Filter",
            {"aliases": ["filter", "filters", "conditional routing"]},
        ),
        (
            "node:catalog:field:payload-json ",
            "Payload JSON field",
            {"field": "payload_json", "field_type": "json"},
        ),
        (
            "node:catalog:field:json ",
            "JSON field",
            {"field": "json", "field_type": "json"},
        ),
        (
            "node:catalog:api:generic-endpoint ",
            "Generic API endpoint",
            {"aliases": ["api", "api call", "endpoint", "rest endpoint"]},
        ),
        (
            "node:catalog:api:graphql-endpoint ",
            "GraphQL endpoint",
            {"aliases": ["graphql", "graphql endpoint", "query"]},
        ),
        (
            "node:catalog:workflow:error-handler ",
            "Error handler",
            {"aliases": ["error", "error handler"]},
        ),
        (
            "node:catalog:workflow:retry ",
            "Retry",
            {"aliases": ["retry", "retry policy"]},
        ),
        (
            "node:catalog:app:mailchimp ",
            "Marketing list",
            {
                "app_slug": "mailchimp",
                "aliases": ["marketing list", "campaign"],
            },
        ),
    ):
        _ = connection.execute(
            """
            INSERT INTO entity_nodes (
              node_id, domain, entity_kind, canonical_label, payload_json,
              source_kind,
              source_ref, valid_from, valid_to, fingerprint, ingest_run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node_id,
                "catalog ",
                "app",
                canonical_label,
                json.dumps(payload_json, sort_keys=True),
                "test_fixture ",
                "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
                OBSERVED_AT,
                None,
                f"fingerprint:{node_id}",
                "test.catalog.search.connection-graph",
            ),
        )
    for edge_id, edge_kind, from_node_id, to_node_id, payload_json in (
        (
            "edge:catalog:slack-to-gmail ",
            "connects_to ",
            "node:catalog:app:slack ",
            "node:catalog:app:google-email",
            {
                "from_app": "slack ",
                "intent": "connect slack to gmail ",
                "to_app": "google-email",
            },
        ),
        (
            "edge:catalog:webhook-json-to-email ",
            "can_feed ",
            "node:catalog:app:gateway ",
            "node:catalog:app:google-email",
            {
                "from_app": "gateway ",
                "intent": "webhook json to email",
                "resource_terms": ["webhook", "json", "email"],
                "to_app": "google-email",
            },
        ),
        (
            "edge:catalog:datastore-dedupe ",
            "duplicates_resource ",
            "node:catalog:app:datastore ",
            "node:catalog:app:datastore",
            {
                "from_app": "datastore ",
                "intent": "datastore dedupe state between runs by unique key",
                "resource_terms": [
                    "datastore ",
                    "dedupe ",
                    "state ",
                    "runs ",
                    "unique key",
                ],
                "to_app": "datastore",
            },
        ),
        (
            "edge:catalog:webhook-to-datastore ",
            "can_feed ",
            "node:catalog:app:gateway ",
            "node:catalog:app:datastore",
            {
                "from_app": "gateway ",
                "intent": "custom webhook save payload in data store",
                "resource_terms": [
                    "webhook ",
                    "payload ",
                    "datastore ",
                    "data store",
                ],
                "to_app": "datastore",
            },
        ),
        (
            "edge:catalog:router-control ",
            "has_capability ",
            "node:catalog:control:router ",
            "node:catalog:workflow:retry",
            {
                "intent": "router controls workflow branches",
                "resource_terms": ["router", "workflow", "control flow"],
            },
        ),
        (
            "edge:catalog:filter-control ",
            "filters ",
            "node:catalog:control:filter ",
            "node:catalog:workflow:retry",
            {
                "intent": "filter controls conditional routing",
                "resource_terms": ["filter", "filters", "conditional routing"],
            },
        ),
        (
            "edge:catalog:generic-json-payload-field ",
            "catalog_semantic_edge ",
            "node:catalog:field:payload-json ",
            "node:catalog:field:json",
            {
                "payload_json": {"field": "payload_json", "field_type": "json"},
                "resource_terms": ["json", "payload_json", "field"],
            },
        ),
        (
            "edge:catalog:error-retry ",
            "fallback_for ",
            "node:catalog:workflow:error-handler ",
            "node:catalog:workflow:retry",
            {
                "intent": "error retry workflow",
                "resource_terms": ["error", "retry", "error handler"],
            },
        ),
        (
            "edge:catalog:marketing-list-to-email ",
            "connects_to ",
            "node:catalog:app:mailchimp ",
            "node:catalog:app:google-email",
            {
                "from_app": "mailchimp ",
                "intent": "marketing list email campaign",
                "resource_terms": ["marketing", "list", "email"],
                "to_app": "google-email",
            },
        ),
        (
            "edge:catalog:hubspot-api-call ",
            "calls_api_surface ",
            "node:catalog:app:hubspot-marketing-hub ",
            "node:catalog:api:generic-endpoint",
            {
                "from_app": "hubspot-marketing-hub ",
                "intent": "make an API call in HubSpot",
                "resource_terms": ["api", "api call", "endpoint"],
                "to_surface": "api endpoint",
            },
        ),
        (
            "edge:catalog:monday-graphql-query ",
            "calls_api_surface ",
            "node:catalog:app:monday ",
            "node:catalog:api:graphql-endpoint",
            {
                "from_app": "monday ",
                "intent": "execute monday GraphQL query",
                "resource_terms": ["api", "graphql", "query"],
                "to_surface": "graphql endpoint",
            },
        ),
        (
            "edge:catalog:microsoft-graph-email-api ",
            "calls_api_surface ",
            "node:catalog:app:microsoft-graph ",
            "node:catalog:app:microsoft-email",
            {
                "from_app": "microsoft-graph ",
                "intent": "Microsoft Graph API email call",
                "resource_terms": ["api", "email", "microsoft graph"],
                "to_app": "microsoft-email",
            },
        ),
        (
            "edge:catalog:generic-api-endpoint ",
            "calls_api_surface ",
            "node:catalog:api:generic-endpoint ",
            "node:catalog:field:payload-json",
            {
                "payload_json": {"endpoint": "/v1/resource", "method": "POST"},
                "resource_terms": [
                    "api ",
                    "endpoint ",
                    "graphql ",
                    "payload_json",
                ],
            },
        ),
    ):
        _ = connection.execute(
            """
            INSERT INTO entity_edges (
              edge_id, domain, edge_kind, from_node_id, to_node_id,
              payload_json, source_kind,
              source_ref, valid_from, valid_to, fingerprint, ingest_run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge_id,
                "catalog",
                edge_kind,
                from_node_id,
                to_node_id,
                json.dumps(payload_json, sort_keys=True),
                "test_fixture ",
                "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
                OBSERVED_AT,
                None,
                f"fingerprint:{edge_id}",
                "test.catalog.search.connection-graph",
            ),
        )


def _slack_raw_spec_module_metadata() -> JsonObject:
    """Return one local raw-spec-derived Slack action metadata fixture."""
    return {
        "module_id": SLACK_CREATE_MESSAGE_MODULE_ID,
        "raw_spec_operation": {
            "type": "action",
            "parameters": [
                {
                    "name": "channel ",
                    "type": "text ",
                    "label": "Channel",
                    "required": True,
                },
                {
                    "name": "text ",
                    "type": "text ",
                    "label": "Message text",
                    "required": True,
                },
                {
                    "name": "priority ",
                    "type": "select ",
                    "label": "Priority",
                    "required": False,
                    "options": ["normal", "urgent"],
                },
            ],
            "interface": [{"name": "message_id", "type": "text"}],
        },
    }


def _insert_module_intelligence_metadata(
    tmp_path: Path,
    *,
    module_id: str,
    evidence_status: str,
    derived: DerivedModuleIntelligenceMetadata,
) -> None:
    """Insert one module intelligence metadata row into the synthetic search.

    fixture.
    """
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        _ = connection.execute(
            """
            INSERT INTO catalog_module_intelligence_metadata (
              run_id, unit_id, module_id, input_schema_json, output_schema_json,
              field_constraints_json, error_rate_percentage, api_rate_limit_rpm,
              avg_execution_time_ms, common_error_codes_json, auth_type,
              required_scopes_json,
              token_refresh_supported, output_cardinality, requires_iterator,
              suggested_control_structures_json, operation_cost_multiplier,
              batch_processing_supported, cheaper_alternative_module_id,
              evidence_status,
              source_kind, source_ref, created_at_utc, valid_to, fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?)
            """,
            (
                "catalog-run-search-connection-fixture ",
                "raw-spec:slack-gmail-connection:1.0.0",
                module_id,
                derived.input_schema_json,
                derived.output_schema_json,
                derived.field_constraints_json,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                derived.output_cardinality,
                derived.requires_iterator,
                derived.suggested_control_structures_json,
                None,
                None,
                None,
                evidence_status,
                "test_fixture ",
                "tests/mcp/tool_contracts/mcp_catalog_search_contract.py",
                OBSERVED_AT,
                None,
                f"fixture-module-intelligence:{module_id}",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _catalog_runtime_counts(tmp_path: Path) -> dict[str, int]:
    """Return cursor and persistence table counts that catalog.search must not.

    mutate.
    """
    connection = sqlite3.connect(tmp_path / DEFAULT_KNOWLEDGE_DB_PATH)
    try:
        return {
            "catalog_plan_units": _count_rows(connection, "catalog_plan_units"),
            "catalog_plan_semantic_answers": _count_rows(
                connection,
                "catalog_plan_semantic_answers",
            ),
            "catalog_plan_quarantine_records": _count_rows(
                connection,
                "catalog_plan_quarantine_records",
            ),
        }
    finally:
        connection.close()


def _assert_catalog_lookup_source_of_truth(payload: JsonObject) -> None:
    """Assert catalog lookup surfaces name SQLite as their only lookup.

    authority.
    """
    source_of_truth = cast("JsonObject", payload["source_of_truth"])
    assert source_of_truth["sqlite_ssot"] is True
    assert (
        source_of_truth["database_path"] == DEFAULT_KNOWLEDGE_DB_PATH.as_posix()
    )
    assert source_of_truth["module_lookup"] == "sqlite:modules"
    assert source_of_truth["field_lookup"] == "sqlite:fields"
    assert "catalog_search_documents" in str(source_of_truth["semantic_lookup"])
    assert "catalog_plan_semantic_answers" in str(
        source_of_truth["semantic_lookup"]
    )
    assert (
        source_of_truth["graph_lookup"]
        == "sqlite:entity_nodes/entity_edges/catalog_edge_proposals"
    )
    assert "backlog_lookup" not in source_of_truth
    assert source_of_truth["legacy_json_authority"] is False


def _count_rows(connection: sqlite3.Connection, table_name: str) -> int:
    """Return one table row count."""
    row = cast(
        "tuple[int]",
        connection.execute(COUNT_SQL_BY_TABLE[table_name]).fetchone(),
    )
    return row[0]
