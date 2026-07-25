# ruff: noqa: E501
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for the Pancakes Make live upload command.

Boundary contract:
- Owns: local package loading, dry-run validation, dependency order, and
secret-free apply payloads.
- Must not: call Make.com, require real credentials, or persist runtime API
tokens.
- Allows: injected fake Make clients and small package fixtures.
- Split when: hosted web uploader session handling becomes independent.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from languages.make.live_upload import (
    LiveUploadError,
    MakeLiveApiClient,
    apply_project_upload,
    dry_run_project_upload,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from tests.support.json_payloads import JsonObject


class FakeMakeClient:
    """Capture ordered Make API calls without network access."""

    def __init__(self) -> None:
        self.calls: list[JsonObject] = []

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        body: JsonObject | None = None,
    ) -> JsonObject:
        call: JsonObject = {
            "method": method,
            "path": path,
            "query": dict(query or {}),
            "body": dict(body or {}),
        }
        self.calls.append(call)
        if method == "POST" and path == "/data-structures":
            return {"id": 101, "name": "Requests Data Structure"}
        if method == "POST" and path == "/data-stores":
            return {"id": 202, "name": "Requests Data Store"}
        if method == "POST" and path == "/hooks":
            return {
                "id": 303,
                "name": "Incoming Webhook ",
                "url": "webhook_url_redacted",
            }
        if method == "POST" and path == "/scenarios":
            body = cast("JsonObject", call["body"])
            blueprint = cast("JsonObject", json.loads(str(body["blueprint"])))
            return {
                "scenario": {
                    "id": 404,
                    "name": blueprint["name"],
                    "teamId": 2171774,
                    "isActive": False,
                    "isinvalid": False,
                }
            }
        if method == "POST" and path == "/scenarios/404/notes/batch":
            body = cast("JsonObject", call["body"])
            notes = cast("list[JsonObject]", body["create"])
            return {
                "notes": [
                    {"id": 900 + index, **note}
                    for index, note in enumerate(notes)
                ]
            }
        if method == "GET" and path == "/scenarios/404/blueprint":
            scenario_call = next(
                item
                for item in self.calls
                if item["method"] == "POST" and item["path"] == "/scenarios"
            )
            return {
                "response": {
                    "blueprint": json.loads(
                        str(
                            cast("JsonObject", scenario_call["body"])[
                                "blueprint"
                            ]
                        )
                    )
                }
            }
        msg = f"Unexpected fake Make call: {method} {path}"
        raise AssertionError(msg)


class FailingAfterDataStoreMakeClient(FakeMakeClient):
    """Capture rollback calls after a later Make API failure."""

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, object] | None = None,
        body: JsonObject | None = None,
    ) -> JsonObject:
        if method == "POST" and path == "/hooks":
            call: JsonObject = {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": dict(body or {}),
            }
            self.calls.append(call)
            msg = "Injected hook failure."
            raise LiveUploadError(msg)
        if method == "DELETE":
            call = {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": dict(body or {}),
            }
            self.calls.append(call)
            return {"status": "deleted"}
        return super().request_json(method, path, query=query, body=body)


def test_live_upload_dry_run_uses_first_class_resource_artifacts_without_token(
    tmp_path: Path,
) -> None:
    """Dry-run validates the complete upload sequence without reading a.

    token.
    """
    project_folder = _write_live_upload_project(tmp_path)

    result = dry_run_project_upload(
        project_folder=project_folder,
        team_id=2171774,
        organization_id=7342166,
        connection_bindings={
            "runtime.connection.slack_ops": "123 ",
            "runtime.connection.google_email_ops": "456",
        },
        runtime_values={"runtime.slack.channel.ops_alerts": "C0123"},
    )

    assert result["status"] == "dry_run_ready"
    assert result["writes_performed"] is False
    assert result["provider_api_call"] is False
    assert result["live_make_called"] is False
    would_create = cast("JsonObject", result["would_create"])
    assert would_create == {
        "data_structures": 1,
        "data_stores": 1,
        "webhooks": 1,
        "scenario_notes": 1,
        "scenarios": 1,
    }
    assert result["missing_connection_bindings"] == ()
    assert result["missing_runtime_values"] == ()
    assert result["client_supplied_connection_count"] == 2
    assert result["webhook_create_prompt_allowed"] is False
    guided_policy = cast("JsonObject", result["guided_make_deployment_policy"])
    assert guided_policy["status"] == "blocked_missing_customer_prerequisites"
    assert guided_policy["deployment_order"] == [
        "data_structures ",
        "data_stores ",
        "webhooks ",
        "custom_apps_if_any ",
        "inactive_scenario",
    ]
    assert guided_policy["public_form_secret_collection_allowed"] is False
    assert guided_policy["temporary_make_api_token_storage_allowed"] is False
    assert (
        guided_policy["scenario_activation_allowed_before_customer_review"]
        is False
    )
    policy = cast("JsonObject", result["dynamic_api_key_policy"])
    assert policy["artifact_storage_allowed"] is False
    assert policy["recommended_env_var"] == "MAKE_API_TOKEN"


def test_live_upload_apply_creates_resources_before_bound_scenario(
    tmp_path: Path,
) -> None:
    """Apply creates Data Structure, Data Store, webhook, then scenario with.

    bound IDs.
    """
    project_folder = _write_live_upload_project(tmp_path)
    client = FakeMakeClient()

    result = apply_project_upload(
        project_folder=project_folder,
        team_id=2171774,
        organization_id=7342166,
        client=client,
        connection_bindings={
            "runtime.connection.slack_ops": "777 ",
            "runtime.connection.google_email_ops": "888",
        },
        runtime_values={"runtime.slack.channel.ops_alerts": "C0123"},
    )

    assert result["status"] == "live_upload_applied"
    assert result["writes_performed"] is True
    assert result["provider_api_call"] is True
    assert result["credential_value_transfer"] is False
    assert result["secret_output"] is False
    assert [f"{call['method']} {call['path']}" for call in client.calls] == [
        "POST /data-structures ",
        "POST /data-stores ",
        "POST /hooks ",
        "POST /scenarios ",
        "POST /scenarios/404/notes/batch ",
        "GET /scenarios/404/blueprint",
    ]
    store_body = cast("JsonObject", client.calls[1]["body"])
    assert store_body["datastructureId"] == 101
    scenario_body = cast("JsonObject", client.calls[3]["body"])
    assert scenario_body["scheduling"] == '{"type": "on-demand"}'
    bound_blueprint = cast(
        "JsonObject", json.loads(str(scenario_body["blueprint"]))
    )
    flow = cast("list[JsonObject]", bound_blueprint["flow"])
    assert cast("JsonObject", flow[0]["parameters"])["hook"] == 303
    assert cast("JsonObject", flow[1]["parameters"])["datastore"] == 202
    assert cast("JsonObject", flow[2]["parameters"])["__IMTCONN__"] == "777"
    assert cast("JsonObject", flow[2]["mapper"])["channel"] == "C0123"
    assert cast("JsonObject", flow[3]["parameters"])["__IMTCONN__"] == "888"
    assert result["scenario_notes_status"] == "created"
    assert result["scenario_notes_created_count"] == 1
    notes_call = client.calls[4]
    assert notes_call["query"] == {"organizationId": 7342166, "teamId": 2171774}
    notes_body = cast("JsonObject", notes_call["body"])
    created_notes = cast("list[JsonObject]", notes_body["create"])
    assert created_notes[0]["moduleIds"] == [2]
    assert "PDF index:</strong> NOTE-MOD-2" in str(created_notes[0]["content"])


def test_live_upload_blocks_secret_like_artifacts(tmp_path: Path) -> None:
    """Live upload refuses package artifacts that contain token-looking.

    material.
    """
    project_folder = _write_live_upload_project(tmp_path)
    package_path = project_folder / "artifacts" / "make-import-package.json"
    payload = cast(
        "JsonObject", json.loads(package_path.read_text(encoding="utf-8"))
    )
    payload["leaked"] = "Authorization: Bearer sk_test_secret_like_value"
    _ = package_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(LiveUploadError, match="secret-like"):
        _ = dry_run_project_upload(
            project_folder=project_folder,
            team_id=2171774,
            organization_id=7342166,
        )


def test_live_upload_blocks_private_public_artifact_traces(
    tmp_path: Path,
) -> None:
    """Live upload also refuses private implementation traces in local package.

    JSON.
    """
    project_folder = _write_live_upload_project(tmp_path)
    package_path = project_folder / "artifacts" / "make-import-package.json"
    payload = cast(
        "JsonObject", json.loads(package_path.read_text(encoding="utf-8"))
    )
    blueprint = cast("JsonObject", payload["blueprint_artifact_json"])
    scenario = cast("JsonObject", blueprint["scenario"])
    scenario["metadata"] = {
        "designer": {
            "message": "Schoenwald source_draft C:\\Users\\humbe\\draft.json"
        }
    }
    _ = package_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(LiveUploadError, match="public-safe artifact boundary"):
        _ = dry_run_project_upload(
            project_folder=project_folder,
            team_id=2171774,
            organization_id=7342166,
        )


def test_live_upload_reports_safe_make_api_error_details() -> None:
    """Make API failures include actionable safe codes without leaking request.

    secrets.
    """
    error = MakeLiveApiClient.format_http_error(
        status_code=400,
        method="POST",
        path="/data-stores",
        response_body=b'{"message":"Not enough space in storage.","code":"IM003"}',
    )

    assert str(error) == (
        "Make API failed for POST /data-stores with status 400 "
        "(code IM003: Not enough space in storage.)."
    )
    assert "Authorization" not in str(error)
    assert "Token" not in str(error)


def test_live_upload_rollback_confirms_destructive_data_resource_deletes(
    tmp_path: Path,
) -> None:
    """Rollback confirms Make data-resource deletes so quota cleanup actually.

    runs.
    """
    project_folder = _write_live_upload_project(tmp_path)
    client = FailingAfterDataStoreMakeClient()

    with pytest.raises(LiveUploadError, match="Injected hook failure"):
        _ = apply_project_upload(
            project_folder=project_folder,
            team_id=2171774,
            organization_id=7342166,
            client=client,
            connection_bindings={
                "runtime.connection.slack_ops": "777 ",
                "runtime.connection.google_email_ops": "888",
            },
            runtime_values={"runtime.slack.channel.ops_alerts": "C0123"},
        )

    delete_calls = [
        call
        for call in client.calls
        if call["method"] == "DELETE"
        and call["path"] in {"/data-stores/202", "/data-structures/101"}
    ]
    assert [call["path"] for call in delete_calls] == [
        "/data-stores/202",
        "/data-structures/101",
    ]
    assert all(call["query"] == {"confirmed": True} for call in delete_calls)


def _write_live_upload_project(tmp_path: Path) -> Path:
    project_folder = tmp_path / "project"
    live_folder = project_folder / "artifacts" / "make-live"
    live_folder.mkdir(parents=True)
    _write_json(
        project_folder / "artifacts" / "make-import-package.json",
        {
            "project_id": "live-test",
            "blueprint_artifact_json": {
                "scenario": {
                    "name": "Live Upload Test",
                    "flow": [
                        {
                            "id": 1,
                            "module": "gateway:CustomWebHook",
                            "parameters": {
                                "hook": "{{runtime.webhook.incoming}}"
                            },
                        },
                        {
                            "id": 2,
                            "module": "datastore:AddRecord",
                            "parameters": {
                                "datastore": "{{runtime.datastore.requests}}"
                            },
                            "mapper": {
                                "key": "request_id",
                                "data": {"request_id": "{{1.id}}"},
                            },
                        },
                        {
                            "id": 3,
                            "module": "slack:ActionCreateMessage",
                            "parameters": {"__IMTCONN__": "__IMTCONN__"},
                            "mapper": {
                                "channel": "{{runtime.slack.channel.ops_alerts}}"
                            },
                        },
                        {
                            "id": 4,
                            "module": "google-email:ActionSendEmail",
                            "parameters": {"__IMTCONN__": "__IMTCONN__"},
                            "mapper": {
                                "to": "ops@example.invalid ",
                                "subject": "Alert",
                            },
                        },
                    ],
                    "metadata": {
                        "designer": {
                            "notes": [
                                {
                                    "content": (
                                        "<h2>MOD-2 | Request record</h2>"
                                        "<p><strong>PDF index:</strong> "
                                        "NOTE-MOD-2</p>"
                                        "<p><strong>Purpose:</strong> Stores "
                                        "the request record.</p>"
                                    ),
                                    "isFilterNote": False,
                                    "metadata": {"color": "#9138FE"},
                                    "moduleIds": [2],
                                }
                            ]
                        },
                        "notes": [
                            {
                                "content": (
                                    "<h2>MOD-2 | Request record</h2>"
                                    "<p><strong>PDF index:</strong> "
                                    "NOTE-MOD-2</p>"
                                    "<p><strong>Purpose:</strong> Stores the "
                                    "request record.</p>"
                                ),
                                "isFilterNote": False,
                                "metadata": {"color": "#9138FE"},
                                "moduleIds": [2],
                            }
                        ],
                    },
                }
            },
        },
    )
    _write_json(
        live_folder / "datastructure.json",
        {
            "artifact_kind": "make_live_data_structures",
            "resources": [
                {
                    "resource_key": "requests ",
                    "name": "Requests Data Structure",
                    "strict": True,
                    "spec": [
                        {
                            "name": "request_id ",
                            "label": "Request Id ",
                            "type": "text",
                            "required": True,
                        }
                    ],
                    "bind_ref": "requests",
                }
            ],
        },
    )
    _write_json(
        live_folder / "datastore.json",
        {
            "artifact_kind": "make_live_data_stores",
            "resources": [
                {
                    "resource_key": "requests ",
                    "name": "Requests Data Store ",
                    "datastructure_ref": "requests",
                    "maxSizeMB": 1,
                    "bind_placeholder": "{{runtime.datastore.requests}}",
                }
            ],
        },
    )
    _write_json(
        live_folder / "webhook.json",
        {
            "artifact_kind": "make_live_webhooks",
            "resources": [
                {
                    "resource_key": "incoming ",
                    "name": "Incoming Webhook ",
                    "typeName": "gateway-webhook",
                    "data": {
                        "headers": False,
                        "method": False,
                        "stringify": False,
                    },
                    "bind_placeholder": "{{runtime.webhook.incoming}}",
                }
            ],
        },
    )
    _write_json(
        live_folder / "connections.json",
        {
            "artifact_kind": "client_app_connection_requirements",
            "resources": [
                {
                    "provider": "slack ",
                    "source": "{{runtime.connection.slack_ops}}",
                    "example_field_paths": ["flow[2].parameters.__IMTCONN__"],
                },
                {
                    "provider": "google-email ",
                    "source": "{{runtime.connection.google_email_ops}}",
                    "example_field_paths": ["flow[3].parameters.__IMTCONN__"],
                },
            ],
        },
    )
    _write_json(
        live_folder / "runtime-values.json",
        {
            "artifact_kind": "client_runtime_value_requirements",
            "resources": [
                {
                    "provider": "slack ",
                    "source": "{{runtime.slack.channel.ops_alerts}}",
                }
            ],
        },
    )
    _write_json(
        live_folder / "upload-plan.json",
        {
            "artifact_kind": "make_live_upload_plan",
            "dependency_order": [
                "create_data_structures ",
                "create_data_stores_with_created_data_structure_ids ",
                "create_webhooks",
            ],
        },
    )
    return project_folder


def _write_json(path: Path, payload: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
