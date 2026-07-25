# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make-native semantics matrix contracts.

Boundary contract:
- Owns: private Make-native semantics matrix shape and initial supported
records.
- Must not: call Make.com, test customer report output, or require live provider
state.
- Allows: local JSON matrix loading and structural field assertions.
- Split when: generated module manifests own per-module semantics directly.
- Merge when: Make adapter boundary tests own the same matrix coverage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from languages.make.semantics_matrix import (
    load_make_native_semantics_matrix,
    make_native_semantics_family_coverage,
    make_native_semantics_family_record,
    make_native_semantics_record,
    make_native_semantics_records,
)

if TYPE_CHECKING:
    from tests.support.json_payloads import JsonObject

REQUIRED_MATRIX_FIELDS = frozenset(
    (
        "module",
        "native_token",
        "version",
        "mapper_shape",
        "parameters_shape",
        "expect_shape",
        "restore_shape",
        "interface_shape",
        "connection_handling",
        "placeholder_policy",
        "known_volatile_fields",
        "roundtrip_behavior",
        "confidence",
        "fixtures",
        "last_evidence_source",
    )
)
INITIAL_REQUIRED_MODULES = frozenset(
    (
        "gateway:CustomWebHook",
        "builtin:BasicRouter",
        "builtin:Iterator",
        "builtin:BasicAggregator",
        "builtin:BasicRepeater",
        "util:FunctionIncrement",
        "util:FunctionSleep",
        "util:GetVariable2",
        "util:SetVariable2",
        "util:TextAggregator",
        "datastore:AddRecord",
        "slack:CreateMessage",
        "unknown:*",
    )
)
ALLOWED_CONFIDENCE = frozenset(
    ("low", "medium", "high", "corpus_confirmed", "policy")
)
REQUIRED_FAMILY_COVERAGE = frozenset(
    (
        "ai_agents",
        "ai_connector_families",
        "anthropic",
        "array_aggregator",
        "basic_router",
        "data_stores",
        "dynamic_selectors",
        "error_handlers",
        "gemini",
        "google_family",
        "http",
        "iterator",
        "make_code",
        "openai",
        "route_filters",
        "slack",
        "sleep",
        "text_aggregator",
        "text_parser",
        "variables",
        "webhooks",
    )
)
REQUIRED_FAMILY_FIELDS = frozenset(
    (
        "family_id",
        "module_identifiers",
        "operation_kinds",
        "required_fields",
        "dynamic_fields",
        "diagnostics",
        "import_export_behavior",
        "linter_rules",
        "planner_terms",
        "known_advisory_gaps",
        "evidence",
    )
)
REQUIRED_PATTERN_RECORDS = frozenset(
    (
        "ai-local-agent:RunLocalAIAgent",
        "ai-tools:Ask",
        "code:ExecuteCode",
        "google-email:triggerWatchNewEmails",
        "google-sheets:addRow",
        "http:MakeRequest",
        "json:ParseJSON",
        "make-ai-web-search:generateAResponse",
        "openai-gpt-3:askAnything",
        "pattern:dynamic_rpc_selector",
        "pattern:error_handler",
        "pattern:route_filter",
        "regexp:Parser",
    )
)
FULL_PATTERN_RECORD_FIELDS = frozenset(
    (
        "operation_kind",
        "dynamic_fields",
        "diagnostics",
        "import_export_behavior",
        "linter_rules",
        "planner_terms",
        "known_advisory_gaps",
    )
)


def test_make_native_semantics_matrix_is_private_engine_asset() -> None:
    """The matrix is loadable and explicitly private to the Make adapter."""
    matrix = load_make_native_semantics_matrix()

    assert matrix.get("schema_version") == 1, f"Matrix schema drifted: {matrix}"
    assert matrix.get("visibility") == "private_engine_asset", (
        f"Matrix must not be customer-facing: {matrix}"
    )
    records = make_native_semantics_records()
    modules = {str(record.get("module")) for record in records}
    assert modules >= INITIAL_REQUIRED_MODULES, (
        f"Missing initial records: {modules}"
    )

    for record in records:
        missing = REQUIRED_MATRIX_FIELDS - set(record)
        assert not missing, (
            f"Matrix record is missing fields {missing}: {record}"
        )
        assert record.get("confidence") in ALLOWED_CONFIDENCE, (
            f"Unsupported confidence level: {record}"
        )
        fixtures = record.get("fixtures")
        assert isinstance(fixtures, list) and fixtures, (
            f"Matrix records need fixture evidence or policy evidence: {record}"
        )


def test_make_native_semantics_matrix_records_initial_module_contracts() -> (
    None
):
    """Initial Make targets keep concrete native rendering contracts."""
    _assert_core_builtin_records()
    _assert_aggregator_records()
    _assert_flow_control_records()
    _assert_provider_records()


def test_make_native_semantics_matrix_covers_required_pattern_families() -> (
    None
):
    """Matrix family coverage names every required Make-native pattern.

    family.
    """
    rows = make_native_semantics_family_coverage()
    by_family = {str(row["family_id"]): row for row in rows}
    matrix_modules = {
        str(record["module"]) for record in make_native_semantics_records()
    }

    assert set(by_family) == REQUIRED_FAMILY_COVERAGE
    for family_id, row in by_family.items():
        missing = REQUIRED_FAMILY_FIELDS - set(row)
        assert not missing, (
            f"Family row {family_id} missing fields {missing}: {row}"
        )
        module_identifiers = _text_tuple(row, "module_identifiers")
        assert module_identifiers, f"Family row needs module identifiers: {row}"
        assert any(module in matrix_modules for module in module_identifiers), (
            f"At least one family module should have a matrix row: {row}"
        )
        assert _text_tuple(row, "operation_kinds"), row
        assert isinstance(row.get("dynamic_fields"), str) and row.get(
            "dynamic_fields"
        ), row
        assert _text_tuple(row, "diagnostics") or row["diagnostics"] == [], row
        assert isinstance(row.get("import_export_behavior"), str), row
        assert _text_tuple(row, "linter_rules"), row
        assert _text_tuple(row, "planner_terms"), row
        assert _text_tuple(row, "known_advisory_gaps"), row
        assert _text_tuple(row, "evidence"), row

    dynamic = _family("dynamic_selectors")
    assert "requires_browser_live_diff_for_selector_values" in _text_tuple(
        dynamic,
        "known_advisory_gaps",
    )
    assert len(_text_tuple(_family("google_family"), "module_identifiers")) >= 5


def test_make_native_semantics_matrix_expands_7f38daa2() -> None:
    """Representative rows carry full semantics fields for TODO 0009 pattern.

    coverage.
    """
    modules = {
        str(record["module"]) for record in make_native_semantics_records()
    }

    assert modules >= REQUIRED_PATTERN_RECORDS
    for module in REQUIRED_PATTERN_RECORDS:
        record = _record(module)
        missing = FULL_PATTERN_RECORD_FIELDS - set(record)
        assert not missing, (
            f"Expanded pattern row is missing {missing}: {record}"
        )
        assert _text_tuple(record, "linter_rules"), record
        assert _text_tuple(record, "planner_terms"), record
        assert _text_tuple(record, "known_advisory_gaps"), record

    google = _record("google-sheets:addRow")
    assert _placeholder_mode(google) == "runtime_required"
    assert _shape_kind(google, "expect_shape") == "dynamic_sheet_columns"

    parser = _record("regexp:Parser")
    assert (
        _shape_kind(parser, "interface_shape") == "rpc_generated_capture_groups"
    )
    assert "pattern" in _shape_keys(parser, "parameters_shape")

    agent = _record("ai-local-agent:RunLocalAIAgent")
    assert _shape_kind(agent, "mapper_shape") == "agent_prompt_mapper"
    assert _placeholder_mode(agent) == "runtime_required"


def _assert_core_builtin_records() -> None:
    webhook = _record("gateway:CustomWebHook")
    router = _record("builtin:BasicRouter")
    iterator = _record("builtin:Iterator")

    assert webhook.get("native_token") == "gateway:CustomWebHook"
    assert webhook.get("version") == 1
    assert _shape_kind(webhook, "mapper_shape") == "empty_trigger_mapper"
    assert _shape_kind(webhook, "interface_shape") == "webhook_payload_fields"

    assert router.get("native_token") == "builtin:BasicRouter"
    assert router.get("version") == 1
    assert _shape_kind(router, "mapper_shape") == "none"
    assert _placeholder_mode(router) == "none"

    assert iterator.get("native_token") == "builtin:Iterator"
    assert iterator.get("version") == 1
    assert _shape_keys(iterator, "mapper_shape") >= {"array"}
    assert _aliases(iterator) == (
        "builtin:BasicFeeder",
        "util:Iterator",
        "tools:Iterator",
        "builtin.iterator",
        "iterator",
    )
    assert _placeholder_mode(iterator) == "none"


def _assert_aggregator_records() -> None:
    array_aggregator = _record("builtin:BasicAggregator")
    text_aggregator = _record("util:TextAggregator")

    assert array_aggregator.get("native_token") == "builtin:BasicAggregator"
    assert array_aggregator.get("version") == 1
    assert (
        _shape_kind(array_aggregator, "mapper_shape")
        == "aggregated_array_fields"
    )
    assert _shape_keys(array_aggregator, "parameters_shape") >= {"feeder"}
    assert _aliases(array_aggregator) == (
        "array aggregator",
        "builtin:ArrayAggregator",
        "builtin.array_aggregator",
    )
    assert _placeholder_mode(array_aggregator) == "none"

    assert text_aggregator.get("native_token") == "util:TextAggregator"
    assert text_aggregator.get("version") == 1
    assert _shape_keys(text_aggregator, "mapper_shape") >= {"value"}
    assert _shape_keys(text_aggregator, "parameters_shape") >= {"feeder"}
    assert _aliases(text_aggregator) == (
        "text aggregator",
        "tools:TextAggregator",
        "util.TextAggregator",
    )
    assert _placeholder_mode(text_aggregator) == "none"


def _assert_flow_control_records() -> None:
    repeater = _record("builtin:BasicRepeater")
    sleep = _record("util:FunctionSleep")
    set_variable = _record("util:SetVariable2")
    get_variable = _record("util:GetVariable2")
    increment = _record("util:FunctionIncrement")

    assert repeater.get("native_token") == "builtin:BasicRepeater"
    assert _shape_keys(repeater, "mapper_shape") >= {"start", "repeats", "step"}
    assert _placeholder_mode(repeater) == "none"

    assert sleep.get("native_token") == "util:FunctionSleep"
    assert _shape_keys(sleep, "mapper_shape") >= {"duration"}
    assert _placeholder_mode(sleep) == "none"

    assert set_variable.get("native_token") == "util:SetVariable2"
    assert _shape_keys(set_variable, "mapper_shape") >= {"name", "scope"}
    assert _placeholder_mode(set_variable) == "none"

    assert get_variable.get("native_token") == "util:GetVariable2"
    assert _shape_keys(get_variable, "mapper_shape") >= {"name"}
    assert _placeholder_mode(get_variable) == "none"

    assert increment.get("native_token") == "util:FunctionIncrement"
    assert _shape_keys(increment, "parameters_shape") >= {"reset"}
    assert _placeholder_mode(increment) == "none"


def _assert_provider_records() -> None:
    datastore = _record("datastore:AddRecord")
    slack = _record("slack:CreateMessage")
    unknown = _record("unknown:*")

    assert datastore.get("native_token") == "datastore:AddRecord"
    assert datastore.get("version") == 2
    assert _shape_keys(datastore, "mapper_shape") >= {
        "key",
        "overwrite",
        "data",
    }
    assert _shape_keys(datastore, "expect_shape") >= {
        "key",
        "overwrite",
        "data",
    }
    assert _placeholder_mode(datastore) == "runtime_required"

    assert slack.get("native_token") == "slack:CreateMessage"
    assert slack.get("version") == 4
    assert _aliases(slack) == ("slack:ActionCreateMessage",)
    assert _connection_projection(slack) == "__IMTCONN__"
    assert _placeholder_mode(slack) == "runtime_required"

    assert _shape_kind(unknown, "mapper_shape") == "pass_through"
    assert _shape_kind(unknown, "parameters_shape") == "pass_through"
    assert _placeholder_mode(unknown) == "preserve_source"


def test_make_native_semantics_matrix_resolves_aliases() -> None:
    """Alias lookup points legacy module names at the native module record."""
    direct = make_native_semantics_record("slack:CreateMessage")
    alias = make_native_semantics_record("slack:ActionCreateMessage")

    assert direct is not None, "Missing Slack native record."
    assert alias is not None, "Missing Slack alias record."
    assert (
        alias.get("native_token")
        == direct.get("native_token")
        == "slack:CreateMessage"
    )


def _record(module: str) -> JsonObject:
    record = make_native_semantics_record(module)
    assert record is not None, f"Missing matrix record for {module}"
    return record


def _family(family_id: str) -> JsonObject:
    record = make_native_semantics_family_record(family_id)
    assert record is not None, f"Missing family coverage record for {family_id}"
    return record


def _shape(record: JsonObject, key: str) -> JsonObject:
    value = record.get(key)
    assert isinstance(value, dict), f"Expected object {key}: {record}"
    return cast("JsonObject", value)


def _shape_kind(record: JsonObject, key: str) -> str:
    value = _shape(record, key).get("kind")
    assert isinstance(value, str), f"Expected shape kind {key}: {record}"
    return value


def _shape_keys(record: JsonObject, key: str) -> set[str]:
    required = _shape(record, key).get("required_keys")
    assert isinstance(required, list), f"Expected required_keys {key}: {record}"
    return {str(item) for item in cast("list[object]", required)}


def _placeholder_mode(record: JsonObject) -> str:
    value = _shape(record, "placeholder_policy").get("mode")
    assert isinstance(value, str), f"Expected placeholder mode: {record}"
    return value


def _connection_projection(record: JsonObject) -> str:
    value = _shape(record, "connection_handling").get("projection")
    assert isinstance(value, str), f"Expected connection projection: {record}"
    return value


def _aliases(record: JsonObject) -> tuple[str, ...]:
    aliases = record.get("aliases")
    assert isinstance(aliases, list), f"Expected aliases list: {record}"
    return tuple(str(alias) for alias in cast("list[object]", aliases))


def _text_tuple(record: JsonObject, key: str) -> tuple[str, ...]:
    values = record.get(key)
    assert isinstance(values, list), f"Expected text list {key}: {record}"
    return tuple(str(value) for value in cast("list[object]", values))
