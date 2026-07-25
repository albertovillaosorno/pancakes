# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Synthetic Make-native fixture family contracts.

Boundary contract:
- Owns: generated fixture-family coverage for Make-native parity risks.
- Must not: call Make.com, store provider state, or depend on live raw specs.
- Allows: synthetic blueprints, abstract DAMP lineage tests, and fixture
metadata.
- Split when: fixture families become persisted JSON corpora or per-module
suites.
- Merge when: Make export contracts own all fixture family generation.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final, NamedTuple, cast

if TYPE_CHECKING:
    from tests.support.json_payloads import JsonObject

REQUIRED_FIXTURE_FAMILIES: Final = (
    "router_2_branch",
    "router_10_branch",
    "nested_router",
    "linear_datastore_chain",
    "webhook_to_slack",
    "webhook_to_datastore",
    "datastore_heavy",
    "slack_heavy",
    "placeholder_heavy",
    "layout_stress",
    "zero_trace_contaminated",
    "roundtrip_reexport_pairs",
    "iterator_pipeline",
    "aggregator_pipeline",
    "flow_control_pipeline",
    "pass_through_unknown_module",
)
REQUIRED_RISK_CLASSES: Final = frozenset(
    (
        "filter_shape_delta",
        "layout_delta",
        "mapper_shape_delta",
        "metadata_expect_missing",
        "native_parity_gap",
        "restore_missing",
        "runtime_resource_placeholder",
        "zero_trace_violation",
    )
)
LINEAGE_FIXTURE_FAMILIES: Final = frozenset(
    (
        "linear_datastore_chain",
        "webhook_to_slack",
        "webhook_to_datastore",
        "datastore_heavy",
        "iterator_pipeline",
        "aggregator_pipeline",
        "flow_control_pipeline",
    )
)
PRIVATE_MARKERS: Final = (
    "actual-token",
    "api key",
    "apikey",
    "bearer ",
    "client_secret",
    "password",
    "secret value",
)


class FixtureFamilySpec(NamedTuple):
    """One generated Make-native fixture family specification."""

    name: str
    modules: tuple[str, ...]
    risk_classes: tuple[str, ...]
    evidence_sources: tuple[str, ...]
    damp_lineage_tests: tuple[JsonObject, ...] = ()
    contaminated: bool = False


def test_make_native_fixture_families_cover_required_topologies_and_risks() -> (
    None
):
    """Generated fixture families cover current Make-native parity risks."""
    families = _fixture_family_corpus()

    assert (
        tuple(family.name for family in families) == REQUIRED_FIXTURE_FAMILIES
    ), f"Fixture family list drifted: {families}"
    covered_risks = {
        risk_class for family in families for risk_class in family.risk_classes
    }
    assert covered_risks >= REQUIRED_RISK_CLASSES, (
        f"Fixture families missed Make-native P0/P1 risks: {covered_risks}"
    )
    for family in families:
        fixture = _render_family_fixture(family)
        _assert_fixture_is_local_and_non_secret(
            fixture, contaminated=family.contaminated
        )
        _assert_fixture_has_compiler_evidence(fixture)
        _assert_fixture_supports_confidence_scoring(fixture)
        if family.name in LINEAGE_FIXTURE_FAMILIES:
            _assert_damp_lineage_tests_are_abstract(fixture)


def _fixture_family_corpus() -> tuple[FixtureFamilySpec, ...]:
    """Return the generated Make-native fixture family corpus."""
    return (
        _family(
            "router_2_branch",
            ("gateway:CustomWebHook", "builtin:BasicRouter"),
            (
                "filter_shape_delta",
                "layout_delta",
            ),
        ),
        _family(
            "router_10_branch",
            ("gateway:CustomWebHook", "builtin:BasicRouter"),
            (
                "filter_shape_delta",
                "layout_delta",
            ),
        ),
        _family(
            "nested_router",
            ("gateway:CustomWebHook", "builtin:BasicRouter"),
            (
                "filter_shape_delta",
                "layout_delta",
                "native_parity_gap",
            ),
        ),
        _family(
            "linear_datastore_chain",
            ("gateway:CustomWebHook", "datastore:AddRecord"),
            (
                "mapper_shape_delta",
                "metadata_expect_missing",
                "restore_missing",
            ),
            lineage=True,
        ),
        _family(
            "webhook_to_slack",
            ("gateway:CustomWebHook", "slack:CreateMessage"),
            (
                "runtime_resource_placeholder",
                "mapper_shape_delta",
            ),
            lineage=True,
        ),
        _family(
            "webhook_to_datastore",
            ("gateway:CustomWebHook", "datastore:AddRecord"),
            (
                "mapper_shape_delta",
                "metadata_expect_missing",
            ),
            lineage=True,
        ),
        _family(
            "datastore_heavy",
            ("gateway:CustomWebHook", "datastore:AddRecord"),
            (
                "mapper_shape_delta",
                "metadata_expect_missing",
                "restore_missing",
            ),
            lineage=True,
        ),
        _family(
            "slack_heavy",
            ("gateway:CustomWebHook", "slack:CreateMessage"),
            (
                "runtime_resource_placeholder",
                "restore_missing",
            ),
        ),
        _family(
            "placeholder_heavy",
            ("gateway:CustomWebHook", "datastore:AddRecord"),
            (
                "runtime_resource_placeholder",
                "native_parity_gap",
            ),
        ),
        _family(
            "layout_stress",
            ("gateway:CustomWebHook", "builtin:BasicRouter"),
            ("layout_delta",),
        ),
        _family(
            "zero_trace_contaminated",
            ("gateway:CustomWebHook", "datastore:AddRecord"),
            ("zero_trace_violation",),
            contaminated=True,
        ),
        _family(
            "roundtrip_reexport_pairs",
            ("gateway:CustomWebHook", "builtin:BasicRouter"),
            (
                "filter_shape_delta",
                "mapper_shape_delta",
                "layout_delta",
            ),
        ),
        _family(
            "iterator_pipeline",
            ("builtin:Iterator", "datastore:AddRecord"),
            (
                "mapper_shape_delta",
                "native_parity_gap",
            ),
            lineage=True,
        ),
        _family(
            "aggregator_pipeline",
            ("builtin:BasicAggregator", "slack:CreateMessage"),
            (
                "metadata_expect_missing",
                "restore_missing",
                "runtime_resource_placeholder",
            ),
            lineage=True,
        ),
        _family(
            "flow_control_pipeline",
            ("util:FunctionSleep", "util:SetVariable2"),
            (
                "mapper_shape_delta",
                "restore_missing",
            ),
            lineage=True,
        ),
        _family(
            "pass_through_unknown_module",
            ("partner:ExperimentalAction",),
            ("native_parity_gap",),
        ),
    )


def _family(
    name: str,
    modules: tuple[str, ...],
    risk_classes: tuple[str, ...],
    *,
    lineage: bool = False,
    contaminated: bool = False,
) -> FixtureFamilySpec:
    """Return the computed result for the caller."""
    return FixtureFamilySpec(
        name=name,
        modules=modules,
        risk_classes=risk_classes,
        evidence_sources=tuple(_evidence_source(module) for module in modules),
        damp_lineage_tests=_lineage_tests(name) if lineage else (),
        contaminated=contaminated,
    )


def _render_family_fixture(family: FixtureFamilySpec) -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "name": f"Make Native Fixture {family.name.replace('_', ' ').title()}",
        "metadata": {
            "fixture_family": family.name,
            "fixture_scope": "synthetic_make_native_parity",
            "risk_classes": list(family.risk_classes),
            "evidence": [
                {
                    "module": module,
                    "source": evidence_source,
                    "status": "synthetic_contract_evidence",
                }
                for module, evidence_source in zip(
                    family.modules,
                    family.evidence_sources,
                    strict=True,
                )
            ],
            "parity_confidence_inputs": {
                "topology": family.name,
                "module_count": len(family.modules),
                "risk_class_count": len(family.risk_classes),
                "lineage_test_count": len(family.damp_lineage_tests),
            },
            "damp_lineage_tests": list(family.damp_lineage_tests),
        },
        "flow": _flow_for_modules(family.modules),
        "notes": _notes_for_family(family),
    }


def _flow_for_modules(modules: tuple[str, ...]) -> list[JsonObject]:
    """Return a small Make-like flow for a fixture family."""
    flow: list[JsonObject] = []
    for index, module in enumerate(modules, start=1):
        flow.append(
            {
                "id": index,
                "module": module,
                "version": 1,
                "parameters": _parameters_for_module(module),
                "mapper": _mapper_for_module(module),
                "metadata": {
                    "designer": {"x": (index - 1) * 300, "y": 0},
                    "expect": _expect_for_module(module),
                    "restore": _restore_for_module(module),
                },
            }
        )
    return flow


def _parameters_for_module(module: str) -> JsonObject:
    if module == "gateway:CustomWebHook":
        return {"hook": "{{runtime.webhook.synthetic_fixture}}"}
    if module == "datastore:AddRecord":
        return {"datastore": "{{runtime.datastore.synthetic_fixture}}"}
    if module == "slack:CreateMessage":
        return {"__IMTCONN__": "__IMTCONN__"}
    return {}


def _mapper_for_module(module: str) -> JsonObject:
    mapper_by_module: dict[str, JsonObject] = {
        "builtin:BasicAggregator": {"feeder": "{{2.array}}", "target": "array"},
        "builtin:Iterator": {"array": "{{1.items}}"},
        "datastore:AddRecord": {
            "key": "{{1.request_id}}",
            "overwrite": False,
            "data": {"email": "{{1.email}}", "company": "{{1.company}}"},
        },
        "slack:CreateMessage": {
            "channel": "synthetic-ops",
            "text": "Lead {{1.email}}",
        },
        "util:FunctionSleep": {"duration": 5},
        "util:GetVariable2": _variable_mapper(),
        "util:SetVariable2": _variable_mapper(),
    }
    return mapper_by_module.get(module, {})


def _variable_mapper() -> JsonObject:
    return {"name": "lead_email", "scope": "scenario", "value": "{{1.email}}"}


def _expect_for_module(module: str) -> list[JsonObject]:
    if module == "datastore:AddRecord":
        return [
            {"name": "key", "type": "text", "required": True},
            {"name": "overwrite", "type": "boolean", "required": True},
            {"name": "data", "type": "collection", "required": True},
        ]
    return []


def _restore_for_module(module: str) -> JsonObject:
    if module == "datastore:AddRecord":
        return {"parameters": {"datastore": {"label": "Synthetic data store"}}}
    if module == "slack:CreateMessage":
        return {"parameters": {"__IMTCONN__": {"label": "Slack connection"}}}
    return {}


def _notes_for_family(family: FixtureFamilySpec) -> list[JsonObject]:
    content = (
        "Pancakes local draft source_draft note."
        if family.contaminated
        else f"<h2>{family.name}</h2><p>Synthetic fixture family.</p>"
    )
    return [
        {"content": content, "metadata": {"color": "#9138FE"}, "moduleIds": [1]}
    ]


def _lineage_tests(name: str) -> tuple[JsonObject, ...]:
    return (
        {
            "test_id": f"{name}-email-lineage",
            "description": (
                "Webhook email reaches the downstream business module."
            ),
            "source_node_id": "1",
            "source_field": "email",
            "target_node_id": "2",
            "target_path": "/flow/1/mapper/data/email",
        },
    )


def _evidence_source(module: str) -> str:
    if module.startswith(("builtin:", "util:")):
        return "make_builtin_manifest"
    return "raw_spec_manifest"


def _assert_fixture_is_local_and_non_secret(
    fixture: JsonObject,
    *,
    contaminated: bool,
) -> None:
    text = json.dumps(fixture, sort_keys=True).casefold()
    for marker in PRIVATE_MARKERS:
        assert marker not in text, (
            f"Fixture leaked secret-shaped text {marker!r}: {fixture}"
        )
    contains_zero_trace_text = (
        "source_draft" in text or "pancakes local draft" in text
    )
    assert contains_zero_trace_text is contaminated, (
        f"Zero-trace contamination should be intentional only: {fixture}"
    )


def _assert_fixture_has_compiler_evidence(fixture: JsonObject) -> None:
    metadata = cast("JsonObject", fixture["metadata"])
    evidence = cast("list[JsonObject]", metadata["evidence"])
    assert evidence, f"Fixture family lost compiler evidence: {fixture}"
    for item in evidence:
        assert item.get("source") in {
            "raw_spec_manifest",
            "make_builtin_manifest",
        }, (
            f"Fixture evidence must point at raw specs or built-in "
            f"manifests: {fixture}"
        )


def _assert_fixture_supports_confidence_scoring(fixture: JsonObject) -> None:
    metadata = cast("JsonObject", fixture["metadata"])
    confidence = cast("JsonObject", metadata["parity_confidence_inputs"])
    module_count = confidence["module_count"]
    risk_class_count = confidence["risk_class_count"]
    assert isinstance(module_count, int) and module_count >= 1, (
        f"Fixture lost module count: {fixture}"
    )
    assert isinstance(risk_class_count, int) and risk_class_count >= 1, (
        f"Fixture lost risk coverage: {fixture}"
    )


def _assert_damp_lineage_tests_are_abstract(fixture: JsonObject) -> None:
    metadata = cast("JsonObject", fixture["metadata"])
    tests = cast("list[JsonObject]", metadata["damp_lineage_tests"])
    assert tests, f"Lineage-sensitive fixture needs DAMP tests: {fixture}"
    encoded_tests = json.dumps(tests, sort_keys=True)
    assert "version" not in encoded_tests.casefold(), (
        f"DAMP tests must remain abstract and versionless: {fixture}"
    )
