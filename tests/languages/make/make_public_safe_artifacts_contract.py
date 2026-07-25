# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for public-safe Make JSON artifacts.

Boundary contract:
- Owns: Make artifact allowlists, runtime placeholder shapes, and
  private-trace rejection.
- Must not: call Make.com, inspect credentials, or test MCP response packaging.
- Allows: synthetic JSON fixtures that prove customer/import JSON is
  fail-closed.
- Split when: another provider gains a separate public artifact boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from languages.make.public_safe_artifacts import (
    ACCEPTED_RUNTIME_PLACEHOLDER_SHAPES,
    make_public_safe_blueprint_json,
    make_public_safe_live_resource_manifest,
    validate_make_public_safe_artifact,
)

if TYPE_CHECKING:
    from tests.support.json_payloads import JsonObject


def test_public_safe_blueprint_json_writes_make_importable_root() -> None:
    """Customer files contain the Make blueprint root."""
    projection: JsonObject = {
        "artifact_format": "make_blueprint_json",
        "scenario": {
            "name": "Lead intake",
            "flow": [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {"hook": "{{runtime.webhook.lead_intake}}"},
                    "mapper": {"email": "{{1.email}}"},
                }
            ],
            "metadata": {"version": 1, "designer": {"orphans": []}},
        },
    }

    public_payload = make_public_safe_blueprint_json(projection)
    report = validate_make_public_safe_artifact(
        projection,
        artifact_kind="make_blueprint_projection",
    )

    assert report.safe, report
    assert public_payload["name"] == "Lead intake"
    assert "flow" in public_payload
    assert "scenario" not in public_payload
    assert "artifact_format" not in public_payload
    assert (
        report.accepted_runtime_placeholder_shapes
        == ACCEPTED_RUNTIME_PLACEHOLDER_SHAPES
    )


def test_public_safe_boundary_blocks_private_trace() -> None:
    """Private workflow terms and secret-looking strings fail."""
    projection: JsonObject = {
        "artifact_format": "make_blueprint_json",
        "scenario": {
            "name": "Schoenwald local draft",
            "flow": [
                {
                    "id": 1,
                    "module": "gateway:CustomWebHook",
                    "parameters": {
                        "hook": "{{runtime webhook.invalid}}",
                        "authorization": "Bearer sk_test_secret_like_value",
                    },
                    "metadata": {
                        "designer": {
                            "message": (
                                "source_draft C:\\Users\\humbe\\draft.json"
                            )
                        }
                    },
                }
            ],
            "metadata": {"pancakes_trace": "internal"},
        },
    }

    report = validate_make_public_safe_artifact(
        projection,
        artifact_kind="make_blueprint_projection",
    )

    codes = {issue.code for issue in report.issues}
    assert not report.safe
    assert "public_artifact.private_trace_text" in codes
    assert "public_artifact.private_key" in codes
    assert "public_artifact.secret_like_text" in codes
    assert "public_artifact.invalid_runtime_placeholder" in codes


def test_public_safe_live_resource_manifest_keeps_public_fields() -> None:
    """Written live manifests strip local setup internals."""
    manifest: JsonObject = {
        "artifact_kind": "make_live_data_stores",
        "resources": [
            {
                "resource_key": "requests",
                "name": "Requests Data Store",
                "datastructure_ref": "requests",
                "maxSizeMB": 1,
                "bind_placeholder": "{{runtime.datastore.requests}}",
                "target_blueprint_field": "parameters.datastore",
                "example_field_paths": ["flow[1].parameters.datastore"],
                "batch_upsert_plan": {"internal": True},
            }
        ],
    }

    public_manifest = make_public_safe_live_resource_manifest(manifest)
    resource = cast("list[JsonObject]", public_manifest["resources"])[0]
    report = validate_make_public_safe_artifact(
        public_manifest,
        artifact_kind="make_live_resource_manifest",
    )

    assert report.safe, report
    assert resource == {
        "bind_placeholder": "{{runtime.datastore.requests}}",
        "datastructure_ref": "requests",
        "maxSizeMB": 1,
        "name": "Requests Data Store",
        "resource_key": "requests",
    }


def test_public_safe_upload_plan_strips_local_fields() -> None:
    """Upload plans do not carry commands or local IDs."""
    plan: JsonObject = {
        "artifact_kind": "make_live_upload_plan",
        "status": "ready",
        "project_id": "local-project",
        "dependency_order": ("create_data_structures", "create_webhooks"),
        "resource_creation_order": ("data_structure", "webhook", "scenario"),
        "resource_creation_order_human": (
            "Data Structure -> Webhook -> Scenario"
        ),
        "one_command_upload_entrypoint": "python -m languages.make.live_upload",
        "dynamic_api_key_policy": {"artifact_storage_allowed": False},
        "scenario_activation_allowed": False,
        "run_once_allowed": False,
    }

    public_plan = make_public_safe_live_resource_manifest(plan)
    report = validate_make_public_safe_artifact(
        public_plan,
        artifact_kind="make_live_resource_manifest",
    )

    assert report.safe, report
    assert "project_id" not in public_plan
    assert "one_command_upload_entrypoint" not in public_plan
    assert "dynamic_api_key_policy" not in public_plan
