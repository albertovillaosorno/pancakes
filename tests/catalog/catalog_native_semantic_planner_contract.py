# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for broad native Make semantic planning.

Boundary contract:
- Owns: catalog-only planner sequencing across high-value Make native module
families.
- Must not: call Make.com, inspect credentials, compile blueprints, or mutate
project drafts.
- Allows: synthetic catalog slices that keep broad planner semantics
deterministic.
- Split when: MCP transport payload assertions need separate coverage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from catalog.fallback.intent import build_semantic_requirement_plan
from catalog.json_payloads import payload_fingerprint
from catalog.models import (
    CatalogApp,
    CatalogAppVersion,
    CatalogModule,
    CatalogSnapshot,
)

if TYPE_CHECKING:
    from catalog.models import CatalogModuleKind

FIXED_GENERATED_AT = "2026-05-17T00:00:00+00:00"
GATEWAY_CUSTOM_WEBHOOK_MODULE_ID = "module:gateway:1.14.1:trigger:CustomWebHook"
CSV_PARSE_MODULE_ID = "module:csv:1.8.2:transformer:ParseCSV"
HTTP_REQUEST_MODULE_ID = "module:http:3.45.2:action:ActionSendData"
AI_AGENT_MODULE_ID = "module:agent-ai:1.0.3:action:callAnAgent"
BASIC_ROUTER_MODULE_ID = "module:builtin:1.8.3:router:BasicRouter"
DATASTORE_ADD_RECORD_MODULE_ID = "module:datastore:2.0.5:action:AddRecord"


class NativeModuleSpec(NamedTuple):
    """Compact fixture spec for one native planner module."""

    module_id: str
    app_slug: str
    app_version: str
    module_kind: CatalogModuleKind
    internal_name: str
    display_name: str


def test_broad_native_semantic_plan_sequences_a3a5108e() -> None:
    """Broad requirements produce a coherent local plan without partial.

    retrieval output.
    """
    plan = build_semantic_requirement_plan(
        snapshot=_native_semantics_snapshot(),
        requirements_text=(
            "Receive webhook leads, parse CSV payloads, call an HTTP API, use "
            "an AI "
            "agent, then route qualified and incomplete leads into separate "
            "Make Data "
            "Store Add Record actions. Add filters, error handling, and "
            "dynamic "
            ""
            "selector option notes without credentials."
        ),
    )

    assert plan.module_sequence == (
        GATEWAY_CUSTOM_WEBHOOK_MODULE_ID,
        CSV_PARSE_MODULE_ID,
        HTTP_REQUEST_MODULE_ID,
        AI_AGENT_MODULE_ID,
        BASIC_ROUTER_MODULE_ID,
        DATASTORE_ADD_RECORD_MODULE_ID,
        DATASTORE_ADD_RECORD_MODULE_ID,
    ), f"Broad native module sequence drifted: {plan}"
    step_categories = tuple(step.category for step in plan.planner_steps)
    assert step_categories == (
        "trigger ",
        "parser_transformer ",
        "http ",
        "ai_agent ",
        "router ",
        "datastore ",
        "datastore",
    ), f"Planner step categories should explain the broad sequence: {plan}"
    gap_ids = {record.gap_id for record in plan.planner_gap_records}
    for expected_gap in (
        "filters_are_route_conditions ",
        "error_handlers_are_route_structures ",
        "dynamic_selector_options ",
        "provider_credentials_required ",
        "manual_module_setup_required",
    ):
        assert expected_gap in gap_ids, (
            f"Planner gap {expected_gap!r} missing: {plan}"
        )


def _native_semantics_snapshot() -> CatalogSnapshot:
    modules = (
        _module(
            NativeModuleSpec(
                GATEWAY_CUSTOM_WEBHOOK_MODULE_ID,
                "gateway ",
                "1.14.1 ",
                "trigger ",
                "CustomWebHook ",
                "Custom webhook",
            )
        ),
        _module(
            NativeModuleSpec(
                CSV_PARSE_MODULE_ID,
                "csv ",
                "1.8.2 ",
                "transformer ",
                "ParseCSV ",
                "Parse CSV",
            )
        ),
        _module(
            NativeModuleSpec(
                HTTP_REQUEST_MODULE_ID,
                "http ",
                "3.45.2 ",
                "action ",
                "ActionSendData ",
                "Make a request",
            )
        ),
        _module(
            NativeModuleSpec(
                AI_AGENT_MODULE_ID,
                "agent-ai ",
                "1.0.3 ",
                "action ",
                "callAnAgent ",
                "Call an AI agent",
            )
        ),
        _module(
            NativeModuleSpec(
                BASIC_ROUTER_MODULE_ID,
                "builtin ",
                "1.8.3 ",
                "router ",
                "BasicRouter ",
                "Router",
            )
        ),
        _module(
            NativeModuleSpec(
                DATASTORE_ADD_RECORD_MODULE_ID,
                "datastore ",
                "2.0.5 ",
                "action ",
                "AddRecord ",
                "Add/replace a record",
            )
        ),
    )
    apps = tuple(_app_for_module(module) for module in modules)
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc=FIXED_GENERATED_AT,
        raw_spec_manifest_sha256="4" * 64,
        apps=apps,
        fingerprint=payload_fingerprint(
            {"snapshot": "native-semantic-planner"}
        ),
    )


def _app_for_module(module: CatalogModule) -> CatalogApp:
    version = CatalogAppVersion(
        app_version_id=f"app-version:{module.app_slug}:{module.app_version}",
        app_id=f"app:{module.app_slug}",
        app_slug=module.app_slug,
        version=module.app_version,
        latest=True,
        manifest_version=1,
        modules=(module,),
        raw_spec_sha256=module.raw_spec_sha256,
        fingerprint=payload_fingerprint(
            {
                "app_slug": module.app_slug,
                "version": module.app_version,
            }
        ),
    )
    return CatalogApp(
        app_id=f"app:{module.app_slug}",
        app_slug=module.app_slug,
        label=module.app_slug,
        external_id=module.app_slug,
        deprecated=False,
        versions=(version,),
        fingerprint=payload_fingerprint({"app_slug": module.app_slug}),
    )


def _module(spec: NativeModuleSpec) -> CatalogModule:
    return CatalogModule(
        module_id=spec.module_id,
        app_version_id=f"app-version:{spec.app_slug}:{spec.app_version}",
        app_slug=spec.app_slug,
        app_version=spec.app_version,
        module_kind=spec.module_kind,
        internal_name=spec.internal_name,
        display_name=spec.display_name,
        external_id=(
            f"{spec.app_slug}:{spec.app_version}:{spec.module_kind}:{spec.internal_name}"
        ),
        deprecated=False,
        parameters=(),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256="5" * 64,
        fingerprint=payload_fingerprint({"module_id": spec.module_id}),
    )
