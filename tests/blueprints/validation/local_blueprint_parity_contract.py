# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for local Make blueprint import parity checks.

Boundary contract:
- Owns: offline local parity assertions before live Make validation.
- Must not: open browsers, call Make.com, use credentials, or test live imports.
- Allows: sanitized AST fixtures and synthetic validation findings.
- Split when: live Make review needs browser-backed evidence.
- Merge when: validator tests own the same local parity evidence contract.
"""

from __future__ import annotations

import json

from blueprints.ast import parse_make_ast_json_text
from blueprints.validation.local_parity import (
    LOCAL_BLUEPRINT_PARITY_AREAS,
    validate_local_blueprint_import_parity,
)
from blueprints.validation.models import (
    BlueprintValidationFinding,
    BlueprintValidationReport,
)


def test_local_blueprint_import_parity_covers_make_surfaces() -> None:
    """A local blueprint yields parity evidence for each Make surface."""
    report = validate_local_blueprint_import_parity(
        root=parse_make_ast_json_text(
            json.dumps(_complete_blueprint(), sort_keys=True)
        ),
        validation_report=BlueprintValidationReport(
            catalog_fingerprint="local", findings=()
        ),
    )

    assert report.status == "pass"
    assert report.live_make_calls_required is False
    assert report.covered_areas == LOCAL_BLUEPRINT_PARITY_AREAS
    assert {evidence.area for evidence in report.evidence} == set(
        LOCAL_BLUEPRINT_PARITY_AREAS
    )
    assert {evidence.area: evidence.status for evidence in report.evidence} == {
        "importability": "pass",
        "modules": "pass",
        "fields": "pass",
        "routes": "pass",
        "filters": "pass",
        "error_handlers": "pass",
        "data_stores": "pass",
        "data_structures": "pass",
        "scheduling": "pass",
        "placeholders": "pass",
    }


def test_local_blueprint_import_parity_links_precise_failures_to_nodes() -> (
    None
):
    """Local parity failures identify the node and path to repair."""
    report = validate_local_blueprint_import_parity(
        root=parse_make_ast_json_text(
            json.dumps(_broken_blueprint(), sort_keys=True)
        ),
        validation_report=BlueprintValidationReport(
            catalog_fingerprint="local",
            findings=(
                BlueprintValidationFinding(
                    finding_id="placeholder-finding",
                    severity="error",
                    code="importability.placeholder_unresolved",
                    node_id="missing-module",
                    client_message=(
                        "A blueprint field still contains a handoff "
                        "placeholder."
                    ),
                    internal_message=(
                        "Synthetic unresolved placeholder fixture."
                    ),
                    source_path=("flow", 1, "parameters", "url"),
                ),
            ),
        ),
    )

    failures_by_code = {failure.code: failure for failure in report.failures}

    assert report.status == "fail"
    assert (
        failures_by_code["local_parity.modules.missing_token"].node_id
        == "missing-module"
    )
    assert (
        failures_by_code["local_parity.fields.invalid_payload"].node_id
        == "field-shape"
    )
    assert (
        failures_by_code["local_parity.routes.on_non_router"].node_id
        == "field-shape"
    )
    assert (
        failures_by_code["local_parity.filters.empty_conditions"].node_id
        == "field-shape"
    )
    assert failures_by_code[
        "local_parity.data_structures.missing_for_data_store"
    ].node_id == ("store-1")
    assert (
        failures_by_code[
            "local_parity.scheduling.missing_trigger_or_schedule"
        ].node_id
        is None
    )
    assert "importability.placeholder_unresolved" in {
        failure.code for failure in report.failures_for_area("placeholders")
    }


def test_local_blueprint_import_parity_classifies_findings() -> None:
    """Validation findings are grouped into parity evidence areas."""
    report = validate_local_blueprint_import_parity(
        root=parse_make_ast_json_text(
            json.dumps(_minimal_trigger_blueprint(), sort_keys=True)
        ),
        validation_report=BlueprintValidationReport(
            catalog_fingerprint="local",
            findings=(
                BlueprintValidationFinding(
                    finding_id="module-finding",
                    severity="error",
                    code="importability.module.unknown",
                    node_id="1",
                    client_message="A module token is unknown.",
                    internal_message="Synthetic module fixture.",
                    source_path=("flow", 0, "module"),
                ),
                BlueprintValidationFinding(
                    finding_id="route-finding",
                    severity="error",
                    code="route.routes_on_non_router",
                    node_id="1",
                    client_message=(
                        "A route container is attached to a non-router module."
                    ),
                    internal_message="Synthetic route fixture.",
                    source_path=("flow", 0, "routes"),
                ),
                BlueprintValidationFinding(
                    finding_id="schedule-finding",
                    severity="warning",
                    code="schedule.sub_minute_interval",
                    node_id=None,
                    client_message="A schedule interval is too frequent.",
                    internal_message="Synthetic schedule fixture.",
                    source_path=("metadata", "schedule"),
                ),
            ),
        ),
    )

    evidence_by_area = {evidence.area: evidence for evidence in report.evidence}

    assert (
        "importability.module.unknown"
        in evidence_by_area["importability"].finding_codes
    )
    assert (
        "importability.module.unknown"
        in evidence_by_area["modules"].finding_codes
    )
    assert (
        "route.routes_on_non_router" in evidence_by_area["routes"].finding_codes
    )
    assert (
        "schedule.sub_minute_interval"
        in evidence_by_area["scheduling"].finding_codes
    )


def _complete_blueprint() -> dict[str, object]:
    return {
        "name": "local-parity-complete",
        "flow": [
            {
                "id": "router-1",
                "module": "builtin:BasicRouter",
                "routes": [
                    {
                        "filter": {
                            "name": "Qualified lead",
                            "conditions": {
                                "left": "{{trigger.email}}",
                                "operator": "exists",
                            },
                        },
                        "flow": [
                            {
                                "id": "store-1",
                                "module": "datastore:AddRecord",
                                "parameters": {
                                    "datastore": "lead-store",
                                    "key": "{{trigger.id}}",
                                    "dataStructure": "lead_record",
                                },
                                "onerror": [
                                    {
                                        "id": "error-1",
                                        "module": "datastore:AddRecord",
                                        "parameters": {
                                            "datastore": "error-store",
                                            "key": "{{trigger.id}}",
                                            "dataStructure": "error_record",
                                        },
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        "metadata": {
            "schedule": {"id": "schedule:daily", "interval": "daily"},
            "dataStructures": [
                {
                    "id": "lead_record",
                    "fields": [{"name": "email", "type": "text"}],
                },
                {
                    "id": "error_record",
                    "fields": [{"name": "message", "type": "text"}],
                },
            ],
            "placeholder_registry": [
                {
                    "placeholder": "runtime.lead_store",
                    "kind": "data_store",
                    "target_path": (
                        "/flow/0/routes/0/flow/0/parameters/datastore"
                    ),
                    "required": True,
                    "expected_type": "string",
                    "handoff_instructions": (
                        "Bind the customer lead data store."
                    ),
                }
            ],
        },
    }


def _broken_blueprint() -> dict[str, object]:
    return {
        "name": "local-parity-broken",
        "flow": [
            {
                "id": "field-shape",
                "module": "http:MakeRequest",
                "parameters": "not-a-field-object",
                "routes": [
                    {
                        "filter": {"name": "Empty filter", "conditions": {}},
                        "flow": [
                            {
                                "id": "store-1",
                                "module": "datastore:AddRecord",
                                "parameters": {"datastore": "lead-store"},
                            }
                        ],
                    }
                ],
            },
            {
                "id": "missing-module",
                "parameters": {"url": "{{TODO:client-url}}"},
            },
        ],
        "metadata": {},
    }


def _minimal_trigger_blueprint() -> dict[str, object]:
    return {
        "name": "local-parity-minimal-trigger",
        "flow": [
            {"id": "1", "module": "gateway:CustomWebHook", "parameters": {}}
        ],
        "metadata": {},
    }
