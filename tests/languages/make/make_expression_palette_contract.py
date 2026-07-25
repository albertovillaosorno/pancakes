# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make expression palette observation contracts.

Boundary contract:
- Owns: local evidence that the Make expression editor exposed specific palette
tokens.
- Must not: call Make.com, infer function arity, or promote executable
expression semantics.
- Allows: private JSON evidence checks for functions, operators, keywords, and
display labels.
- Split when: a full Make expression grammar or evaluator owns token semantics.
- Merge when: expression intelligence consumes this palette through a dedicated
loader.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from languages.make.expression_palette import (
    PALETTE_OBSERVED_ARITY_STATUS,
    known_make_expression_function_names,
    make_expression_function_facts,
    make_expression_function_family_ids,
    make_expression_token_facts,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from tests.support.json_payloads import JsonObject

PALETTE_PATH = "src/languages/make/data/expression_palette.json"
INVENTORY_PATH = "src/languages/make/data/non_raw_evidence_inventory.json"


def test_expression_palette_observations_are_private_offline_evidence() -> None:
    """Expression palette screenshots are preserved without claiming runtime.

    authority.
    """
    palette = _palette()

    assert palette["schema_version"] == 1
    assert palette["asset"] == "make_expression_palette_observations"
    assert palette["visibility"] == "private_engine_asset"
    assert palette["source_kind"] == "operator_screenclip"
    assert palette["raw_image_paths_omitted"] is True
    assert palette["safety_contract"] == {
        "live_make_called_by_pancakes": False,
        "provider_api_call": False,
        "credential_value_transfer": False,
        "secret_output": False,
        "customer_facing": False,
    }
    assert "Function arity" in cast(
        "list[object]", palette["not_authority_for"]
    )


def test_expression_palette_indexes_observed_function_groups() -> None:
    """Observed Make palette groups keep their variables, functions, operators,.

    and keywords.
    """
    palettes = _palettes_by_id()

    assert {
        "general_functions",
        "math_functions",
        "text_and_binary_functions",
        "date_and_time",
        "array_functions",
        "custom_and_system_variables",
    } == set(palettes)

    _assert_contains(
        palettes["general_functions"], "variables", {"executionId"}
    )
    _assert_contains(
        palettes["general_functions"], "functions", {"get", "set", "if", "pick"}
    )
    _assert_contains(
        palettes["general_functions"], "operators", {"=", "!=", "and", "or"}
    )
    _assert_contains(
        palettes["general_functions"], "keywords", {"ignore", "erase"}
    )

    _assert_contains(palettes["math_functions"], "variables", {"pi", "random"})
    _assert_contains(
        palettes["math_functions"],
        "functions",
        {"parseNumber", "formatNumber", "stdevS", "stdevP"},
    )
    _assert_contains(
        palettes["math_functions"], "operators", {"mod", "<=", ">="}
    )

    _assert_contains(
        palettes["text_and_binary_functions"],
        "functions",
        {"replaceEmojiCharacters", "escapeMarkdown", "sha256", "base64"},
    )
    _assert_contains(
        palettes["text_and_binary_functions"],
        "keywords",
        {"emptystring", "carriagereturn"},
    )

    _assert_contains(
        palettes["date_and_time"],
        "functions",
        {"addSeconds", "setMonth", "formatDate", "parseDate"},
    )
    assert palettes["date_and_time"]["observed_selected_date"] == "2026-05-17"

    _assert_contains(
        palettes["array_functions"],
        "functions",
        {"arrayIntersect", "arrayDiff", "toCollection", "toArray"},
    )
    _assert_contains(palettes["array_functions"], "keywords", {"emptyarray"})


def test_expression_palette_preserves_system_variable_display_labels() -> None:
    """System variable screenshots keep display labels without inventing hidden.

    token ids.
    """
    system = _palettes_by_id()["custom_and_system_variables"]

    _assert_contains(
        system,
        "scenario_variables",
        {
            "Credits consumed",
            "Data consumed",
            "Execution id",
            "Execution URL",
            "Operations consumed",
            "Scenario URI",
        },
    )
    _assert_contains(system, "team_variables", {"Team id", "Team name"})
    _assert_contains(
        system,
        "organization_variables",
        {"Data left", "Organization id", "Remaining credits", "Zone domain"},
    )


def test_expression_palette_is_registered_in_non_raw_evidence_inventory() -> (
    None
):
    """The palette is visible in Make non-raw evidence accounting."""
    inventory = _read_json_object(_repo_root() / INVENTORY_PATH)
    surfaces = cast("list[JsonObject]", inventory["surfaces"])
    surface = next(
        (
            record
            for record in surfaces
            if record.get("surface_id")
            == "make_expression_palette_observations"
        ),
        None,
    )
    assert surface is not None, (
        "Expression palette evidence surface is not indexed."
    )
    assert surface["path"] == PALETTE_PATH
    assert surface["kind"] == "engine_input"
    assert "tests/languages/make/make_expression_palette_contract.py" in cast(
        "list[object]",
        surface["validation_tests"],
    )


def test_expression_palette_loader_deduplicates_function_family_context() -> (
    None
):
    """Loader facts keep every observed function family while deduping names."""
    function_names = known_make_expression_function_names()

    assert function_names.count("length") == 1
    assert function_names.count("contains") == 1
    assert "replaceEmojiCharacters" in function_names
    assert make_expression_function_family_ids("length") == (
        "text_and_binary_functions",
        "array_functions",
    )
    assert make_expression_function_family_ids("contains") == (
        "text_and_binary_functions",
        "array_functions",
    )

    facts = make_expression_function_facts("arrayIntersect")
    assert tuple(fact.arity_status for fact in facts) == (
        PALETTE_OBSERVED_ARITY_STATUS,
    )


def test_expression_palette_symbol_tokens_do_not_share_empty_lookup_key() -> (
    None
):
    """Symbol-only function and operator lookups must not collide with each.

    other.
    """
    empty_call_facts = make_expression_token_facts("()", kind="function")
    equals_facts = make_expression_token_facts("=", kind="operator")
    not_equals_facts = make_expression_token_facts("!=", kind="operator")
    less_than_facts = make_expression_token_facts("<", kind="operator")
    less_equal_facts = make_expression_token_facts("<=", kind="operator")

    assert tuple(fact.token for fact in empty_call_facts) == ("()",)
    assert tuple(fact.token for fact in equals_facts) == ("=",)
    assert tuple(fact.token for fact in not_equals_facts) == ("!=",)
    assert tuple(fact.token for fact in less_than_facts) == ("<",)
    assert tuple(fact.token for fact in less_equal_facts) == ("<=",)


def _palette() -> JsonObject:
    return _read_json_object(_repo_root() / PALETTE_PATH)


def _palettes_by_id() -> dict[str, JsonObject]:
    palettes = cast("list[JsonObject]", _palette()["palettes"])
    return {str(palette["palette_id"]): palette for palette in palettes}


def _assert_contains(record: JsonObject, key: str, expected: set[str]) -> None:
    raw_values = record.get(key)
    assert isinstance(raw_values, list), f"Expected list at {key}: {record}"
    values = {str(value) for value in cast("list[object]", raw_values)}
    assert expected <= values, (
        f"Missing {expected - values} from {key}: {record}"
    )


def _read_json_object(path: Path) -> JsonObject:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"Expected JSON object: {path}"
    return cast("JsonObject", payload)


def _repo_root() -> Path:
    return repo_root()
