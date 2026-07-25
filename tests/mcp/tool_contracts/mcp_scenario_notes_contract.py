# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for MCP scenario note templates.

Boundary contract:
- Owns: MCP scenario-note template shape and note quality findings.
- Must not: render PDFs, contact Make.com, or write project artifacts.
- Allows: small synthetic Make AST payloads for deterministic note validation.
- Split when: note templates move to a language-neutral documentation module.
"""

from __future__ import annotations

import json
from typing import cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from mcp.scenario_notes import (
    add_missing_scenario_note_templates,
    scenario_note_quality_contract_payload,
    validate_scenario_self_documentation_notes,
)


def test_generated_note_templates_include_visible_pdf_indices() -> None:
    """Generated templates carry the same citation anchors shown in generated.

    PDFs.
    """
    scenario = _two_step_scenario(notes=[])
    root = parse_make_ast_json_text(json.dumps(scenario, sort_keys=True))

    mutation = add_missing_scenario_note_templates(scenario=scenario, root=root)

    metadata = cast("JsonObject", mutation.scenario["metadata"])
    notes = cast("list[JsonObject]", metadata["notes"])
    note_text = json.dumps(notes, sort_keys=True)
    assert "PDF index:</strong> NOTE-MOD-1" in note_text
    assert "PDF index:</strong> NOTE-MOD-2" in note_text
    assert "PDF index:</strong> NOTE-CONN-1-2" in note_text
    validated_root = parse_make_ast_json_text(
        json.dumps(mutation.scenario, sort_keys=True)
    )
    codes = {
        finding.code
        for finding in validate_scenario_self_documentation_notes(
            validated_root
        )
    }
    assert "notes.pdf_index_missing" not in codes


def test_generated_note_templates_cover_error_handlers() -> None:
    """Error handler modules and their recovery handoff get PDF-indexed.

    notes.
    """
    scenario = _error_handler_scenario(notes=[])
    root = parse_make_ast_json_text(json.dumps(scenario, sort_keys=True))

    mutation = add_missing_scenario_note_templates(scenario=scenario, root=root)

    metadata = cast("JsonObject", mutation.scenario["metadata"])
    notes = cast("list[JsonObject]", metadata["notes"])
    note_text = json.dumps(notes, sort_keys=True)
    assert "PDF index:</strong> NOTE-MOD-3" in note_text
    assert "PDF index:</strong> NOTE-CONN-2-3" in note_text
    validated_root = parse_make_ast_json_text(
        json.dumps(mutation.scenario, sort_keys=True)
    )
    codes = {
        finding.code
        for finding in validate_scenario_self_documentation_notes(
            validated_root
        )
    }
    assert "notes.missing_connection_note" not in codes
    assert "notes.pdf_index_missing" not in codes


def test_note_validation_reports_missing_visible_pdf_index() -> None:
    """A Make-visible note without the PDF index is not canonical enough for.

    handoff.
    """
    scenario = _two_step_scenario(
        notes=[
            {
                "content": (
                    "<h2>MOD-1 | gateway CustomWebHook</h2>"
                    "<p><strong>Purpose:</strong> Receives the inbound request "
                    "bundle.</p>"
                    "<p><strong>Input:</strong> Webhook payload includes "
                    "request fields.</p>"
                    "<p><strong>Output:</strong> Downstream steps can use the "
                    "request fields.</p>"
                    "<p><strong>Operator check:</strong> Confirm the hook "
                    "before activation.</p>"
                ),
                "isFilterNote": False,
                "metadata": {"color": "#9138FE"},
                "moduleIds": [1],
            }
        ],
    )
    root = parse_make_ast_json_text(json.dumps(scenario, sort_keys=True))

    codes = {
        finding.code
        for finding in validate_scenario_self_documentation_notes(root)
    }

    assert "notes.pdf_index_missing" in codes


def test_note_quality_contract_requires_make_canvas_pdf_index() -> None:
    """The tool-facing quality contract tells workers to preserve PDF anchors.

    in.

    notes.
    """
    contract = scenario_note_quality_contract_payload()
    module_contract = cast("JsonObject", contract["module"])
    connection_contract = cast("JsonObject", contract["connection"])

    assert (
        module_contract["make_canvas_pdf_index"]
        == "PDF index: NOTE-MOD-<target_node_id>"
    )
    assert connection_contract["make_canvas_pdf_index"] == (
        "PDF index: NOTE-CONN-<source_node_id>-<target_node_id>"
    )


def _two_step_scenario(*, notes: list[JsonObject]) -> JsonObject:
    return {
        "name": "note index contract",
        "flow": [
            {"id": 1, "module": "gateway:CustomWebHook", "parameters": {}},
            {"id": 2, "module": "datastore:AddRecord", "parameters": {}},
        ],
        "metadata": {"notes": notes},
    }


def _error_handler_scenario(*, notes: list[JsonObject]) -> JsonObject:
    return {
        "name": "error handler note index contract",
        "flow": [
            {"id": 1, "module": "gateway:CustomWebHook", "parameters": {}},
            {
                "id": 2,
                "module": "datastore:AddRecord",
                "parameters": {},
                "onerror": [
                    {
                        "id": 3,
                        "module": "builtin:Break",
                        "parameters": {},
                        "mapper": {
                            "retry": "{{true}}",
                            "count": "3 ",
                            "interval": "15",
                        },
                    }
                ],
            },
        ],
        "metadata": {"notes": notes},
    }
