# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for Make expression template parsing.

Boundary contract:
- Owns: quote-aware Make expression template parsing and executable path
filtering.
- Must not: test output contracts, catalog validation, or blueprint rendering.
- Allows: AST fixtures that exercise expression delimiter and literal handling.
- Split when: parser tests need a richer token-level Make expression contract.
- Merge when: another expression-template test duplicates these behaviors.
"""

from __future__ import annotations

import json

import pytest
from blueprints.ast import parse_make_ast_json_text
from blueprints.validation.expression_intelligence import analyze_mapping_risks
from blueprints.validation.expression_templates import (
    MakeExpressionTemplateParseError,
    iter_make_expression_templates,
)


def test_make_expression_templates_extract_multiple_quote_aware_bodies() -> (
    None
):
    """Quoted delimiters inside a body do not close the template."""
    templates = iter_make_expression_templates(
        'prefix {{replace(1.text; "}}"; "")}} and {{trim(2.name)}}'
    )

    assert tuple(template.body for template in templates) == (
        'replace(1.text; "}}"; "")',
        "trim(2.name)",
    ), f"Template bodies drifted: {templates}"


def test_make_expression_templates_reject_unmatched_close_delimiter() -> None:
    """A closing delimiter outside a template is invalid."""
    with pytest.raises(MakeExpressionTemplateParseError):
        _ = iter_make_expression_templates("literal }} text")


def test_expression_intelligence_ignores_separators_inside_ac6() -> None:
    """Quoted semicolons and commas are not argument separators."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "quoted-separators",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {"value": '{{replace(1.text; ";"; ",")}}'},
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.function_argument_count" not in codes, (
        f"Quoted separators were counted as arguments: {codes}"
    )


def test_expression_intelligence_ignores_parentheses_inside_74() -> None:
    """Quoted parentheses do not terminate function argument extraction."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "quoted-parentheses",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {"value": '{{replace(1.text; ")"; "")}}'},
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.function_argument_count" not in codes, (
        f"Quoted parentheses broke argument extraction: {codes}"
    )


def test_expression_intelligence_ignores_array_separators_559c() -> None:
    """Array literal separators do not count as top-level function arguments."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "array-literal-arguments",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {"value": '{{join([1; 2]; ",")}}'},
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.function_argument_count" not in codes, (
        f"Array separators were counted as top-level arguments: {codes}"
    )


def test_expression_intelligence_ignores_function_like_quoted_text() -> None:
    """Function-looking text inside quoted literals is not executable mapping.

    code.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "quoted-functions",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {
                            "message": (
                                "{{if(1.status; "
                                '"mysteryTransform(1.value)"; 1.name)}}'
                            )
                        },
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.function_unknown" not in codes, (
        f"Quoted function-like text was parsed as executable: {codes}"
    )


def test_expression_intelligence_ignores_pagination_words_inside_quotes() -> (
    None
):
    """Quoted pagination-looking text is not executable pagination logic."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "quoted-pagination",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {"message": '{{if(true; "page"; 1.name)}}'},
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.pagination_without_limit" not in codes, (
        f"Quoted pagination text was parsed as executable: {codes}"
    )


def test_expression_intelligence_ignores_delimiters_inside_ebf() -> None:
    """Quoted brace delimiters inside arguments do not unbalance the.

    expression.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "quoted-brace-delimiters",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "mapper": {"value": '{{replace(1.text; "}}"; "")}}'},
                    }
                ],
            }
        )
    )
    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert "mapping.expression_unbalanced" not in codes, (
        f"Quoted delimiters were treated as executable braces: {codes}"
    )
    assert "mapping.function_argument_count" not in codes, (
        f"Quoted delimiters broke argument counting: {codes}"
    )


def test_expression_intelligence_scans_filter_condition_alias_paths() -> None:
    """Filter rules and expression aliases are executable mapping surfaces."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "filter-expression-aliases",
                "flow": [
                    {
                        "id": 1,
                        "module": "builtin:BasicRouter",
                        "routes": [
                            {
                                "filter": {
                                    "name": "Expression alias",
                                    "expression": "{{1.score",
                                },
                                "flow": [],
                            },
                            {
                                "filter": {
                                    "name": "Rules alias",
                                    "rules": [
                                        {
                                            "field": "status",
                                            "operator": "equal",
                                            "value": (
                                                "{{mysteryTransform(1.status)}}"
                                            ),
                                        }
                                    ],
                                },
                                "flow": [],
                            },
                        ],
                    }
                ],
            }
        )
    )

    codes = tuple(risk.code for risk in analyze_mapping_risks(root))

    assert not ("mapping.expression_unbalanced" not in codes), (
        f"Filter expression alias was not scanned: {codes}"
    )
    assert not ("mapping.function_unknown" not in codes), (
        f"Filter rules alias was not scanned: {codes}"
    )


def test_expression_intelligence_ignores_designer_documentation_examples() -> (
    None
):
    """Designer documentation examples are not executable mapping.

    expressions.
    """
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "metadata-doc-example",
                "flow": [
                    {
                        "id": 1,
                        "module": "http:MakeRequest",
                        "metadata": {
                            "designer": {
                                "messages": [
                                    {
                                        "message": "Example only: "
                                        "{{mysteryTransform(1.value)}}"
                                    }
                                ]
                            }
                        },
                    }
                ],
            }
        )
    )

    risks = analyze_mapping_risks(root)
    assert not (risks), (
        f"Designer documentation should not be parsed as mapping code: {risks}"
    )
