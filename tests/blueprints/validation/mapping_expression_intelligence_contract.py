# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for Make expression and mapping intelligence.

Boundary contract:
- Owns: tests for Make expression parsing, repair hints, and mapping
intelligence.
- Must not: test unrelated blueprint validation or repository tools.
- Allows: expression fixtures, catalog context, and diagnostic assertions.
- Split when: parsing and repair guidance need separate modules.
- Merge when: another expression intelligence test duplicates this behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from blueprints.validation.expression_intelligence import (
    FUNCTION_RULES,
    PROMOTED_RULE_SOURCE,
    analyze_mapping_risks,
    make_expression_function_posture,
)
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog import CatalogSnapshot

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)
CLIENT_PATH_TOKENS = ("\\", "/", "src/", "tests/", "Refactor", "C:")


def test_expression_intelligence_reports_unbalanced_expression() -> None:
    """Unbalanced expression delimiters produce a typed node-attached error."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "bad-expression",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {"url": "{{1.url"},
                    }
                ],
            }
        )
    )

    risks = analyze_mapping_risks(root)
    assert risks, f"Unbalanced expression was not detected: {risks}"
    assert risks[0].code == "mapping.expression_unbalanced", (
        f"Unbalanced expression was not detected: {risks}"
    )
    repair_message = risks[0].repair_suggestion.client_message
    assert risks[0].node_id == "1", (
        f"Risk was not attached with a useful repair suggestion: {risks[0]}"
    )
    assert not ("matching braces" not in repair_message), (
        f"Risk was not attached with a useful repair suggestion: {risks[0]}"
    )
    assert "{{1.url" not in risks[0].internal_message, (
        f"Unbalanced mapping diagnostics leaked the raw expression: {risks[0]}"
    )
    assert "{{1.url" not in risks[0].repair_suggestion.internal_detail, (
        f"Unbalanced mapping repair details leaked the raw expression: "
        f"{risks[0]}"
    )
    assert_client_text_is_path_safe(risks[0].client_message)
    assert_client_text_is_path_safe(risks[0].repair_suggestion.client_message)


def test_expression_intelligence_reports_function_argument_errors() -> None:
    """Common Make functions are checked for obvious argument-count mistakes."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "bad-function",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {"url": "{{get()}}"},
                    }
                ],
            }
        )
    )
    report = validate_blueprint(root=root, catalog=load_catalog_fixture())

    assert not ("mapping.function_argument_count" not in report.codes()), (
        f"Function argument mistake was not reported: {report.codes()}"
    )
    finding = next(
        finding
        for finding in report.findings
        if finding.code == "mapping.function_argument_count"
    )
    assert_client_text_is_path_safe(finding.client_message)


def test_expression_intelligence_reports_unknown_function_9049() -> None:
    """Unknown functions warn and pagination formulas get non-blocking hints."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "mapping-hints",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {
                            "body": "{{mysteryTransform(1.value)}}",
                            "page": "{{page + 1}}",
                        },
                    }
                ],
            }
        )
    )
    risks = analyze_mapping_risks(root)
    codes = tuple(risk.code for risk in risks)

    assert not ("mapping.function_unknown" not in codes), (
        f"Unknown function was not reported: {codes}"
    )
    assert not ("mapping.pagination_without_limit" not in codes), (
        f"Pagination hint was not reported: {codes}"
    )


def test_expression_intelligence_accepts_promoted_function_aliases() -> None:
    """Promoted Make functions are not reported as unknown or malformed."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "promoted-functions",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {
                            "clean": "{{trim(1.name)}}",
                            "amount": "{{parseNumber(1.total)}}",
                            "matched": '{{match(1.email; "/^[^@]+@[^@]+$/")}}',
                        },
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.function_unknown" not in codes, (
        f"Promoted functions were reported as unknown: {codes}"
    )
    assert "mapping.function_argument_count" not in codes, (
        f"Promoted functions were reported with bad arity: {codes}"
    )


def test_expression_intelligence_accepts_make_semicolon_arguments() -> None:
    """Make-style semicolon argument separators are counted as arguments."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "semicolon-functions",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {
                            "value": '{{get(1.collection; "email")}}',
                            "items": '{{map(1.items; "email")}}',
                            "date": (
                                "{{formatDate(1.createdAt; "
                                '"YYYY-MM-DD"; "UTC")}}'
                            ),
                            "regex": '{{regex(1.email; "^[^@]+@[^@]+$"; "i")}}',
                        },
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.function_argument_count" not in codes, (
        f"Semicolon-separated arguments were miscounted: {codes}"
    )


def test_expression_intelligence_accepts_palette_known_eff5847() -> None:
    """Screenclip-observed Make functions are known while arity stays.

    unverified.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "palette-observed-functions",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {
                            "money": '{{formatNumber(1.total; 2; ".")}}',
                            "emoji": "{{replaceEmojiCharacters(1.title)}}",
                            "intersection": (
                                "{{arrayIntersect(1.tags; 2.tags)}}"
                            ),
                            "date": "{{setMonth(1.createdAt; 5)}}",
                        },
                    }
                ],
            }
        )
    )
    risks = analyze_mapping_risks(root)
    codes = tuple(risk.code for risk in risks)

    assert "mapping.function_unknown" not in codes, (
        f"Palette-observed functions were reported as unknown: {risks}"
    )
    assert "mapping.function_argument_count" not in codes, (
        f"Palette-observed functions claimed unverified arity: {risks}"
    )

    posture = make_expression_function_posture("arrayIntersect")
    assert posture.family_ids == ("array_functions",), (
        f"Palette function family context was not preserved: {posture}"
    )
    assert posture.arity_status == "palette_observed_unverified_arity", (
        f"Palette function arity must stay unverified: {posture}"
    )


def test_expression_intelligence_keeps_promoted_arity_7433792e() -> None:
    """Promoted function rules keep executable argument-count posture."""
    posture = make_expression_function_posture("get")

    assert posture.family_ids == ("collection",)
    assert posture.arity_status == "promoted_arity"
    assert posture.min_args == 2
    assert posture.max_args == 2


def test_expression_intelligence_reports_iterator_and_f29cfe40() -> None:
    """Iterator and aggregator nodes carry mapping-pattern warnings."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "iterator-aggregator",
                "flow": [
                    {"id": 1, "module": "builtin:Iterator", "parameters": {}},
                    {
                        "id": 2,
                        "module": "builtin:ArrayAggregator",
                        "parameters": {},
                    },
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert not ("mapping.iterator_source_missing" not in codes), (
        f"Iterator mapping risk was not reported: {codes}"
    )
    assert not ("mapping.aggregator_target_missing" not in codes), (
        f"Aggregator mapping risk was not reported: {codes}"
    )


def test_expression_intelligence_rejects_empty_mapping_pattern_evidence() -> (
    None
):
    """Iterator and aggregator evidence fields must contain meaningful.

    mappings.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "empty-pattern-evidence",
                "flow": [
                    {
                        "id": 1,
                        "module": "builtin:Iterator",
                        "parameters": {"array": []},
                    },
                    {
                        "id": 2,
                        "module": "builtin:ArrayAggregator",
                        "parameters": {"target": {}},
                    },
                ],
            }
        )
    )
    risks_by_node = {
        (risk.node_id, risk.code) for risk in analyze_mapping_risks(root)
    }

    assert not (
        ("1", "mapping.iterator_source_missing") not in risks_by_node
    ), f"Empty iterator evidence suppressed risk: {risks_by_node}"
    assert not (
        ("2", "mapping.aggregator_target_missing") not in risks_by_node
    ), f"Empty aggregator evidence suppressed risk: {risks_by_node}"


def test_expression_intelligence_pattern_risks_ignore_child_flow_fields() -> (
    None
):
    """Child flow fields do not satisfy parent iterator or aggregator.

    mappings.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "child-only-pattern-fields",
                "flow": [
                    {
                        "id": 1,
                        "module": "builtin:Iterator",
                        "parameters": {},
                        "routes": [
                            {
                                "flow": [
                                    {
                                        "id": 2,
                                        "module": "util:SetVariable",
                                        "parameters": {"array": "{{1.items}}"},
                                    }
                                ]
                            }
                        ],
                    },
                    {
                        "id": 3,
                        "module": "builtin:ArrayAggregator",
                        "parameters": {},
                        "routes": [
                            {
                                "flow": [
                                    {
                                        "id": 4,
                                        "module": "util:SetVariable",
                                        "parameters": {"target": "{{1.items}}"},
                                    }
                                ]
                            }
                        ],
                    },
                ],
            }
        )
    )
    risks = analyze_mapping_risks(root)
    risks_by_node = {(risk.node_id, risk.code) for risk in risks}

    assert not (
        ("1", "mapping.iterator_source_missing") not in risks_by_node
    ), f"Iterator risk was suppressed by child fields: {risks}"
    assert not (
        ("3", "mapping.aggregator_target_missing") not in risks_by_node
    ), f"Aggregator risk was suppressed by child fields: {risks}"


def test_unpromoted_course_evidence_does_not_drive_runtime_rules() -> None:
    """Expression rules are promoted by ADR/tests/runtime, not course text.

    alone.
    """
    sources = {rule.promoted_source for rule in FUNCTION_RULES}
    assert sources == {PROMOTED_RULE_SOURCE}, (
        f"Unexpected expression rule evidence sources: {sources}"
    )
    assert "course" not in PROMOTED_RULE_SOURCE.casefold(), (
        "Course-only evidence must not drive runtime mapping rules."
    )


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample catalog fixture.

    Returns:
        The loaded value.
    """
    payload = cast(
        "object", json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{CATALOG_FIXTURE} must contain a JSON object."
    )
    return catalog_snapshot_from_json(
        normalize_json_object(cast("Mapping[str, object]", payload))
    )


def assert_client_text_is_path_safe(text: str) -> None:
    """Fail if client-facing mapping guidance leaks path details."""
    leaked_tokens = [token for token in CLIENT_PATH_TOKENS if token in text]
    assert not (leaked_tokens), (
        f"Client text leaked path tokens {leaked_tokens}: {text}"
    )
