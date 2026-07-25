# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make module projector manifest contract tests.

Boundary contract:
- Owns: Make-target module manifest loading and exporter traceability to
manifest-backed shape
  policies.
- Must not: call Make.com, depend on provider credentials, or test generic AST
behavior.
- Allows: synthetic offline catalogs and draft payloads that prove Make-native
projector manifests
  drive supported module output shape.
- Split when: generated typed manifests replace JSON manifest contracts.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, NamedTuple, cast

from blueprints.ast import parse_make_ast_json_text
from catalog.models import (
    CatalogApp,
    CatalogAppVersion,
    CatalogField,
    CatalogModule,
    CatalogSnapshot,
)
from languages.make.blueprint_export import render_make_blueprint_payload
from languages.make.module_manifests import (
    make_module_manifest_fixed_version,
    make_module_manifest_policy_required_keys,
    make_module_projector_kind,
    make_module_projector_manifest_for_native_token,
    make_module_projector_manifest_paths,
    make_module_projector_manifests,
)

if TYPE_CHECKING:
    from catalog.models import CatalogFieldDirection, CatalogModuleKind

    from tests.support.json_payloads import JsonObject


class CatalogModuleSpec(NamedTuple):
    """Synthetic Make catalog module input for manifest-backed export tests."""

    app_slug: str
    app_version: str
    module_kind: str
    internal_name: str
    display_name: str
    raw_spec_sha256: str
    fingerprint: str
    parameter_paths: tuple[str, ...] = ()
    connection_parameter_path: str | None = None


def test_make_module_projector_manifests_are_complete_contracts() -> None:
    """Supported Make module projector manifests expose the required policy.

    families.
    """
    manifests = make_module_projector_manifests()
    manifest_modules = {manifest.get("module") for manifest in manifests}

    assert {
        "gateway:CustomWebHook",
        "builtin:BasicRouter",
        "builtin:Iterator",
        "builtin:BasicAggregator",
        "builtin:BasicRepeater",
        "util:FunctionIncrement",
        "util:FunctionSleep",
        "util:GetVariable2",
        "util:TextAggregator",
        "util:SetVariable2",
        "datastore:AddRecord",
        "slack:CreateMessage",
    } <= manifest_modules
    manifest_paths = {
        "src/languages/make/"
        + path.as_posix().split("src/languages/make/", 1)[1]
        for path in make_module_projector_manifest_paths()
    }
    assert {
        "src/languages/make/modules/gateway/CustomWebHook.manifest.json",
        "src/languages/make/modules/datastore/AddRecord.manifest.json",
        "src/languages/make/modules/slack/CreateMessage.manifest.json",
        "src/languages/make/builtins/BasicAggregator.manifest.json",
        "src/languages/make/builtins/BasicRepeater.manifest.json",
        "src/languages/make/builtins/BasicRouter.manifest.json",
        "src/languages/make/builtins/FunctionIncrement.manifest.json",
        "src/languages/make/builtins/FunctionSleep.manifest.json",
        "src/languages/make/builtins/GetVariable2.manifest.json",
        "src/languages/make/builtins/Iterator.manifest.json",
        "src/languages/make/builtins/SetVariable2.manifest.json",
        "src/languages/make/builtins/TextAggregator.manifest.json",
    } <= manifest_paths

    required_policy_keys = {
        "version_policy",
        "projector",
        "mapper_policy",
        "parameters_policy",
        "metadata_expect_policy",
        "metadata_restore_policy",
        "metadata_interface_policy",
        "connection_projection_policy",
        "placeholder_policy",
        "volatile_field_policy",
        "zero_trace_constraints",
        "roundtrip_behavior",
    }
    for manifest in manifests:
        assert manifest.get("asset") == "make_module_projector_manifest"
        assert manifest.get("visibility") == "private_engine_asset"
        assert required_policy_keys <= set(manifest), (
            f"Incomplete manifest: {manifest}"
        )
        assert make_module_projector_kind(manifest), (
            f"Missing projector kind: {manifest}"
        )
        assert make_module_manifest_fixed_version(manifest), (
            f"Manifest must declare a fixed Make-native version: {manifest}"
        )
        fixtures = manifest.get("fixtures")
        assert isinstance(fixtures, list) and fixtures, (
            f"Manifest must carry fixture evidence: {manifest}"
        )


def test_make_module_projector_manifest_lookup_d007b13e() -> None:
    """Manifest lookup resolves current Make tokens and legacy Pancakes.

    aliases.
    """
    direct = make_module_projector_manifest_for_native_token(
        "slack:CreateMessage"
    )
    alias = make_module_projector_manifest_for_native_token(
        "slack:ActionCreateMessage"
    )
    iterator_native_alias = make_module_projector_manifest_for_native_token(
        "builtin:BasicFeeder"
    )
    text_alias = make_module_projector_manifest_for_native_token(
        "tools:TextAggregator"
    )
    array_alias = make_module_projector_manifest_for_native_token(
        "array aggregator"
    )
    sleep_alias = make_module_projector_manifest_for_native_token("delay")
    unknown = make_module_projector_manifest_for_native_token(
        "unknown:FakeModule"
    )

    assert direct is not None
    assert alias is not None
    assert iterator_native_alias is not None
    assert text_alias is not None
    assert array_alias is not None
    assert sleep_alias is not None
    assert (
        direct.get("native_token")
        == alias.get("native_token")
        == "slack:CreateMessage"
    )
    assert make_module_projector_kind(alias) == "slack_create_message"
    assert iterator_native_alias.get("native_token") == "builtin:Iterator"
    assert text_alias.get("native_token") == "util:TextAggregator"
    assert array_alias.get("native_token") == "builtin:BasicAggregator"
    assert sleep_alias.get("native_token") == "util:FunctionSleep"
    assert unknown is None


def test_manifest_backed_export_shape_matches_supported_module_contracts() -> (
    None
):
    """Supported module output shape matches the loaded Make projector.

    manifests.
    """
    root = parse_make_ast_json_text(json.dumps(_manifest_backed_draft()))

    result = render_make_blueprint_payload(
        root=root, catalog=_manifest_catalog()
    )

    _assert_manifest_backed_output(result.payload)


def test_manifest_backed_export_shape_matches_flow_control_contracts() -> None:
    """Flow-control built-ins render with manifest-backed Make-native schema.

    metadata.
    """
    root = parse_make_ast_json_text(json.dumps(_flow_control_draft()))

    result = render_make_blueprint_payload(root=root, catalog=_empty_catalog())

    flow = [
        cast("JsonObject", node)
        for node in cast("list[object]", result.payload["flow"])
    ]
    repeater, sleep, set_variable, get_variable, increment = flow
    _assert_manifest_version(repeater, "builtin:BasicRepeater")
    _assert_manifest_version(sleep, "util:FunctionSleep")
    _assert_manifest_version(set_variable, "util:SetVariable2")
    _assert_manifest_version(get_variable, "util:GetVariable2")
    _assert_manifest_version(increment, "util:FunctionIncrement")
    repeater_metadata = cast("JsonObject", repeater["metadata"])
    repeater_expect = cast("list[JsonObject]", repeater_metadata["expect"])
    assert {field["name"] for field in repeater_expect} == {
        "start",
        "repeats",
        "step",
    }
    assert cast("JsonObject", sleep["mapper"])["duration"] == "10"
    assert cast("JsonObject", set_variable["metadata"])["interface"] == [
        {"label": "lead_count", "name": "value", "type": "any"}
    ]
    assert cast("JsonObject", get_variable["metadata"])["expect"] == [
        {
            "label": "Variable name",
            "name": "name",
            "required": True,
            "type": "text",
        }
    ]
    assert cast("JsonObject", increment["metadata"])["interface"] == [
        {"label": "i", "name": "i", "type": "number"}
    ]


def _assert_manifest_backed_output(payload: JsonObject) -> None:
    flow = cast("list[object]", payload["flow"])
    gateway, router = cast("JsonObject", flow[0]), cast("JsonObject", flow[1])
    route = cast("JsonObject", cast("list[object]", router["routes"])[0])
    datastore, slack, array_aggregator, text_aggregator = (
        cast("JsonObject", node) for node in cast("list[object]", route["flow"])
    )

    _assert_manifest_version(gateway, "gateway:CustomWebHook")
    _assert_manifest_version(router, "builtin:BasicRouter")
    _assert_manifest_version(datastore, "datastore:AddRecord")
    _assert_manifest_version(slack, "slack:CreateMessage")
    _assert_manifest_version(array_aggregator, "builtin:BasicAggregator")
    _assert_manifest_version(text_aggregator, "util:TextAggregator")
    _assert_gateway_output_matches_manifest(gateway)
    _assert_datastore_output_matches_manifest(datastore)
    _assert_slack_output_matches_manifest(slack)
    _assert_array_aggregator_output_matches_manifest(array_aggregator)
    _assert_text_aggregator_output_matches_manifest(text_aggregator)


def _assert_gateway_output_matches_manifest(gateway: JsonObject) -> None:
    gateway_manifest = _manifest("gateway:CustomWebHook")
    assert (
        make_module_projector_kind(gateway_manifest) == "gateway_custom_webhook"
    )
    assert gateway["mapper"] == {}
    assert "interface" in cast("JsonObject", gateway["metadata"])


def _assert_datastore_output_matches_manifest(datastore: JsonObject) -> None:
    datastore_manifest = _manifest("datastore:AddRecord")
    mapper_required = make_module_manifest_policy_required_keys(
        datastore_manifest,
        "mapper_policy",
    )
    expect_required = make_module_manifest_policy_required_keys(
        datastore_manifest,
        "metadata_expect_policy",
    )
    datastore_mapper = cast("JsonObject", datastore["mapper"])
    datastore_expect = cast(
        "list[object]", cast("JsonObject", datastore["metadata"])["expect"]
    )
    assert set(mapper_required) <= set(datastore_mapper)
    assert "email" in cast("JsonObject", datastore_mapper["data"])
    assert {
        cast("JsonObject", item)["name"] for item in datastore_expect
    } == set(expect_required)


def _assert_slack_output_matches_manifest(slack: JsonObject) -> None:
    slack_manifest = _manifest("slack:CreateMessage")
    assert make_module_projector_kind(slack_manifest) == "slack_create_message"
    slack_parameters = cast("JsonObject", slack["parameters"])
    slack_mapper = cast("JsonObject", slack["mapper"])
    assert slack_parameters["__IMTCONN__"] == "slack-ops"
    assert "account" not in slack_parameters
    assert slack_mapper["text"] == "Lead {{1.email}}"


def _assert_array_aggregator_output_matches_manifest(
    array_aggregator: JsonObject,
) -> None:
    aggregator_manifest = _manifest("builtin:BasicAggregator")
    assert make_module_projector_kind(aggregator_manifest) == "array_aggregator"
    assert array_aggregator["module"] == "builtin:BasicAggregator"
    assert cast("JsonObject", array_aggregator["parameters"])["feeder"] == 3
    metadata = cast("JsonObject", array_aggregator["metadata"])
    assert "expect" in metadata
    assert "interface" in metadata
    assert "restore" in metadata


def _assert_text_aggregator_output_matches_manifest(
    text_aggregator: JsonObject,
) -> None:
    aggregator_manifest = _manifest("util:TextAggregator")
    assert make_module_projector_kind(aggregator_manifest) == "text_aggregator"
    assert text_aggregator["module"] == "util:TextAggregator"
    assert (
        cast("JsonObject", text_aggregator["mapper"])["value"]
        == "{{5.array.email}}"
    )
    metadata = cast("JsonObject", text_aggregator["metadata"])
    assert cast("list[object]", metadata["expect"])[0] == {
        "label": "Text",
        "multiline": True,
        "name": "value",
        "type": "text",
    }
    assert (
        cast("JsonObject", text_aggregator["parameters"])["rowSeparator"]
        == "\n"
    )


def _assert_manifest_version(node: JsonObject, module: str) -> None:
    manifest = _manifest(module)
    assert node["version"] == make_module_manifest_fixed_version(manifest)


def _manifest(module: str) -> JsonObject:
    manifest = make_module_projector_manifest_for_native_token(module)
    assert manifest is not None, f"Missing manifest for {module}"
    return manifest


def _manifest_backed_draft() -> JsonObject:
    return cast(
        "JsonObject",
        {
            "name": "manifest backed export",
            "flow": [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {"hook": "{{runtime.webhook.lead_intake}}"},
                    "mapper": {
                        "email": "{{1.email}}",
                        "request_id": "{{1.request_id}}",
                    },
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": (
                                "module:gateway:1.14.1:trigger:CustomWebHook"
                            ),
                            "raw_spec_sha256": "1" * 64,
                            "status": "resolved",
                        }
                    },
                },
                {
                    "id": 2,
                    "module": "builtin:BasicRouter",
                    "metadata": {
                        "raw_spec": {
                            "catalog_module_id": (
                                "module:builtin:1.8.3:router:BasicRouter"
                            ),
                            "raw_spec_sha256": "2" * 64,
                            "status": "resolved",
                        }
                    },
                    "routes": [
                        {
                            "flow": [
                                {
                                    "id": 3,
                                    "module": "datastore:AddRecord",
                                    "parameters": {
                                        "datastore": "{{runtime.datastore.leads}}"
                                    },
                                    "mapper": {
                                        "email": "{{1.email}}",
                                        "request_id": "{{1.request_id}}",
                                    },
                                    "metadata": {
                                        "raw_spec": {
                                            "catalog_module_id": (
                                                "module:datastore:2.0.0:action:AddRecord"
                                            ),
                                            "raw_spec_sha256": "3" * 64,
                                            "status": "resolved",
                                        }
                                    },
                                },
                                {
                                    "id": 4,
                                    "module": "slack:ActionCreateMessage",
                                    "parameters": {
                                        "account": "slack-ops",
                                        "channel": "sales-ops",
                                        "text": "Lead {{1.email}}",
                                    },
                                    "metadata": {
                                        "raw_spec": {
                                            "catalog_module_id": (
                                                "module:slack:2.14.3:action:ActionCreateMessage"
                                            ),
                                            "raw_spec_sha256": "4" * 64,
                                            "status": "resolved",
                                        }
                                    },
                                },
                                {
                                    "id": 5,
                                    "module": "builtin:ArrayAggregator",
                                    "parameters": {"feeder": 3},
                                    "mapper": {"email": "{{3.email}}"},
                                    "metadata": {
                                        "raw_spec": {
                                            "catalog_module_id": (
                                                "module:builtin:1.8.3:aggregator:BasicAggregator"
                                            ),
                                            "raw_spec_sha256": "5" * 64,
                                            "status": "resolved",
                                        }
                                    },
                                },
                                {
                                    "id": 6,
                                    "module": "tools:TextAggregator",
                                    "parameters": {
                                        "feeder": 5,
                                        "rowSeparator": "\n",
                                    },
                                    "mapper": {"value": "{{5.array.email}}"},
                                    "metadata": {
                                        "raw_spec": {
                                            "catalog_module_id": (
                                                "module:util:1.11.14:aggregator:TextAggregator"
                                            ),
                                            "raw_spec_sha256": "6" * 64,
                                            "status": "resolved",
                                        }
                                    },
                                },
                            ]
                        }
                    ],
                },
            ],
            "metadata": {
                "scenario": {"slots": None},
                "notes": [],
                "placeholder_registry": [
                    {
                        "expected_type": "hook_id",
                        "handoff_instructions": (
                            "Create the webhook before activation."
                        ),
                        "kind": "runtime_setup",
                        "placeholder": "runtime.webhook.lead_intake",
                        "required": True,
                        "target_path": "/flow/0/parameters/hook",
                    },
                    {
                        "expected_type": "id",
                        "handoff_instructions": (
                            "Create the data store before activation."
                        ),
                        "kind": "runtime_setup",
                        "placeholder": "runtime.datastore.leads",
                        "required": True,
                        "target_path": (
                            "/flow/1/routes/0/flow/0/parameters/datastore"
                        ),
                    },
                ],
            },
        },
    )


def _flow_control_draft() -> JsonObject:
    return cast(
        "JsonObject",
        {
            "name": "flow control export",
            "flow": [
                {
                    "id": 1,
                    "module": "builtin:BasicRepeater",
                    "mapper": {"repeats": "3", "start": "1", "step": "1"},
                },
                {
                    "id": 2,
                    "module": "util:FunctionSleep",
                    "mapper": {"duration": "10"},
                },
                {
                    "id": 3,
                    "module": "util:SetVariable2",
                    "mapper": {
                        "name": "lead_count",
                        "scope": "roundtrip",
                        "value": "{{1.i}}",
                    },
                },
                {
                    "id": 4,
                    "module": "util:GetVariable2",
                    "mapper": {"name": "lead_count"},
                },
                {
                    "id": 5,
                    "module": "util:FunctionIncrement",
                    "parameters": {"reset": "scenario"},
                    "mapper": {},
                },
            ],
            "metadata": {"scenario": {"slots": None}, "notes": []},
        },
    )


def _manifest_catalog() -> CatalogSnapshot:
    gateway = _catalog_module(
        CatalogModuleSpec(
            app_slug="gateway",
            app_version="1.14.1",
            module_kind="trigger",
            internal_name="CustomWebHook",
            display_name="Custom webhook",
            raw_spec_sha256="a" * 64,
            fingerprint="1" * 64,
            parameter_paths=("hook",),
        )
    )
    builtin = _catalog_module(
        CatalogModuleSpec(
            app_slug="builtin",
            app_version="1.8.3",
            module_kind="router",
            internal_name="BasicRouter",
            display_name="Basic router",
            raw_spec_sha256="b" * 64,
            fingerprint="2" * 64,
        )
    )
    datastore = _catalog_module(
        CatalogModuleSpec(
            app_slug="datastore",
            app_version="2.0.0",
            module_kind="action",
            internal_name="AddRecord",
            display_name="Add/replace a record",
            raw_spec_sha256="c" * 64,
            fingerprint="3" * 64,
            parameter_paths=("datastore",),
        )
    )
    slack_old = _catalog_module(
        CatalogModuleSpec(
            app_slug="slack",
            app_version="2.14.3",
            module_kind="action",
            internal_name="ActionCreateMessage",
            display_name="Create a message",
            raw_spec_sha256="d" * 64,
            fingerprint="4" * 64,
        )
    )
    slack_current = _catalog_module(
        CatalogModuleSpec(
            app_slug="slack",
            app_version="4.12.22",
            module_kind="action",
            internal_name="CreateMessage",
            display_name="Send a Message",
            raw_spec_sha256="e" * 64,
            fingerprint="5" * 64,
            parameter_paths=("channel", "text"),
            connection_parameter_path="__IMTCONN__",
        )
    )
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-05-14T00:00:00+00:00",
        raw_spec_manifest_sha256="f" * 64,
        apps=(
            _catalog_app("builtin", "Make builtin", (builtin,), "6" * 64),
            _catalog_app("datastore", "Data store", (datastore,), "7" * 64),
            _catalog_app("gateway", "Webhooks", (gateway,), "8" * 64),
            _catalog_app(
                "slack", "Slack", (slack_old, slack_current), "9" * 64
            ),
        ),
        fingerprint="0" * 64,
    )


def _empty_catalog() -> CatalogSnapshot:
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="empty-test-catalog",
        raw_spec_manifest_sha256="f" * 64,
        apps=(),
        fingerprint="0" * 64,
    )


def _catalog_module(spec: CatalogModuleSpec) -> CatalogModule:
    module_id = f"module:{spec.app_slug}:{spec.app_version}:{spec.module_kind}:{spec.internal_name}"
    connection_parameters = (
        (
            _catalog_connection_field(
                module_id=module_id,
                field_name=spec.connection_parameter_path,
            ),
        )
        if spec.connection_parameter_path is not None
        else ()
    )
    parameters = connection_parameters + tuple(
        _catalog_field(module_id=module_id, field_name=field_name)
        for field_name in spec.parameter_paths
    )
    return CatalogModule(
        module_id=module_id,
        app_version_id=f"app-version:{spec.app_slug}:{spec.app_version}",
        app_slug=spec.app_slug,
        app_version=spec.app_version,
        module_kind=cast("CatalogModuleKind", spec.module_kind),
        internal_name=spec.internal_name,
        display_name=spec.display_name,
        external_id=(
            f"{spec.app_slug}:{spec.app_version}:{spec.module_kind}:{spec.internal_name}"
        ),
        deprecated=False,
        parameters=parameters,
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256=spec.raw_spec_sha256,
        fingerprint=spec.fingerprint,
    )


def _catalog_connection_field(
    *, module_id: str, field_name: str
) -> CatalogField:
    raw_schema: JsonObject = {
        "name": field_name,
        "required": True,
        "type": "account:slack2",
    }
    return CatalogField(
        field_id=f"{module_id}:parameter:{field_name}",
        module_id=module_id,
        direction=cast("CatalogFieldDirection", "parameter"),
        path=(field_name,),
        label="Connection",
        required=True,
        field_type="account:slack2",
        advanced=False,
        external_id=field_name,
        rpc_dependencies=(),
        raw_schema=raw_schema,
        constraints=(),
        fingerprint="0" * 64,
    )


def _catalog_field(*, module_id: str, field_name: str) -> CatalogField:
    raw_schema: JsonObject = {
        "name": field_name,
        "required": True,
        "type": "text",
    }
    return CatalogField(
        field_id=f"{module_id}:parameter:{field_name}",
        module_id=module_id,
        direction=cast("CatalogFieldDirection", "parameter"),
        path=(field_name,),
        label=field_name,
        required=True,
        field_type="text",
        advanced=False,
        external_id=field_name,
        rpc_dependencies=(),
        raw_schema=raw_schema,
        constraints=(),
        fingerprint="0" * 64,
    )


def _catalog_app(
    app_slug: str,
    label: str,
    modules: tuple[CatalogModule, ...],
    fingerprint: str,
) -> CatalogApp:
    versions = tuple(
        CatalogAppVersion(
            app_version_id=f"app-version:{app_slug}:{module.app_version}",
            app_id=f"app:{app_slug}",
            app_slug=app_slug,
            version=module.app_version,
            latest=module == modules[-1],
            manifest_version=1,
            modules=(module,),
            raw_spec_sha256=module.raw_spec_sha256,
            fingerprint=module.fingerprint,
        )
        for module in modules
    )
    return CatalogApp(
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        label=label,
        external_id=app_slug,
        deprecated=False,
        versions=versions,
        fingerprint=fingerprint,
    )
