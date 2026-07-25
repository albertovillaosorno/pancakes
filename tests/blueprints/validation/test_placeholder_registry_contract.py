# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Runtime placeholder registry validation tests.

Boundary contract:
- Owns: project placeholder registry importability and handoff manifest
coverage.
- Must not: call live Make services, require credentials, or validate secret
values.
- Allows: sanitized offline fixtures, exact path assertions, and manifest
checks.
- Split when: placeholder registry parsing becomes a standalone validation
slice.
- Merge when: another test module owns this exact runtime placeholder contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import (
    build_handoff_placeholder_manifest,
    validate_blueprint,
)
from blueprints.validation.handoff_manifest import (
    build_handoff_blocker_manifest,
)
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.validation import (
        BlueprintValidationFinding,
        BlueprintValidationReport,
    )

UNREGISTERED_PLACEHOLDER_CODE = "importability.placeholder_unregistered"
UNUSED_PLACEHOLDER_CODE = "importability.placeholder_registry_unused"
INCOMPLETE_REGISTRY_CODE = "importability.placeholder_registry_incomplete"
TARGET_MISMATCH_CODE = "importability.placeholder_registry_target_mismatch"
FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
INVALID_UNREGISTERED_FIXTURE = (
    FIXTURE_ROOT / "invalid_unregistered_runtime_placeholder.json"
)
INVALID_UNUSED_FIXTURE = (
    FIXTURE_ROOT / "invalid_unused_placeholder_registry_entry.json"
)


def test_registered_runtime_placeholder_used_in_parameters_is_accepted() -> (
    None
):
    """A complete registry entry covers a runtime placeholder used in.

    parameters.
    """
    report = validate_payload(registered_placeholder_payload())

    blocked_codes = {
        UNREGISTERED_PLACEHOLDER_CODE,
        UNUSED_PLACEHOLDER_CODE,
        INCOMPLETE_REGISTRY_CODE,
    }
    actual = blocked_codes.intersection(report.codes())
    assert not (actual), (
        f"Registered runtime placeholder was rejected: {report.findings}"
    )


def test_unregistered_runtime_placeholder_reports_path_ef45640() -> None:
    """A runtime placeholder without registry evidence reports its exact.

    payload.

    path.
    """
    report = validate_fixture(INVALID_UNREGISTERED_FIXTURE)
    finding = require_finding(report, UNREGISTERED_PLACEHOLDER_CODE)

    assert finding.source_path == ("flow", 0, "parameters", "hook"), (
        f"Unregistered placeholder path drifted: {finding}"
    )
    assert not ("suggested registry entry" not in finding.internal_message), (
        f"Missing suggested registry entry guidance: {finding}"
    )
    assert not (
        "runtime.webhook.lead_intake_hook" not in finding.internal_message
    ), f"Missing placeholder token in diagnostic: {finding}"


def test_runtime_placeholder_blocker_is_operator_083fa6cf() -> None:
    """Runtime placeholder registry blockers are routed to the operator in.

    handoff output.
    """
    report = validate_fixture(INVALID_UNREGISTERED_FIXTURE)

    blockers = build_handoff_blocker_manifest(report=report)
    placeholder_blockers = tuple(
        blocker
        for blocker in blockers
        if blocker.code == UNREGISTERED_PLACEHOLDER_CODE
    )
    assert placeholder_blockers, (
        f"Missing runtime placeholder blocker in handoff manifest: {blockers}"
    )
    assert placeholder_blockers[0].suggested_owner == "operator", (
        f"Runtime placeholder blocker owner drifted: {placeholder_blockers[0]}"
    )


def test_unused_placeholder_registry_entry_is_3b5e892b() -> None:
    """Registry entries that do not correspond to a runtime placeholder stay.

    visible.
    """
    report = validate_fixture(INVALID_UNUSED_FIXTURE)
    finding = require_finding(report, UNUSED_PLACEHOLDER_CODE)

    assert not (finding.severity not in {"warning", "error"}), (
        f"Unused registry entries must be visible warnings or blockers: "
        f"{finding}"
    )
    assert finding.source_path == ("metadata", "placeholder_registry", 0), (
        f"Unused registry entry path drifted: {finding}"
    )


def test_placeholder_registry_rejects_empty_runtime_identifier() -> None:
    """A bare runtime namespace is not a valid registered placeholder."""
    payload = registered_placeholder_payload()
    node = cast("JsonObject", cast("list[object]", payload["flow"])[0])
    parameters = cast("JsonObject", node["parameters"])
    parameters["hook"] = "{{runtime.}}"
    metadata = cast("JsonObject", payload["metadata"])
    registry = cast("list[object]", metadata["placeholder_registry"])
    registry_entry = cast("JsonObject", registry[0])
    registry_entry["placeholder"] = "runtime."

    report = validate_payload(payload)
    incomplete = require_finding(report, INCOMPLETE_REGISTRY_CODE)
    unregistered = require_finding(report, UNREGISTERED_PLACEHOLDER_CODE)

    assert incomplete.source_path == ("metadata", "placeholder_registry", 0), (
        f"Invalid placeholder registry path drifted: {incomplete}"
    )
    assert not ("runtime." not in unregistered.internal_message), (
        f"Invalid placeholder usage was not reported: {unregistered}"
    )


def test_placeholder_registry_rejects_stale_target_path() -> None:
    """Registry target_path must match an executable runtime placeholder.

    location.
    """
    payload = registered_placeholder_payload()
    metadata = cast("JsonObject", payload["metadata"])
    registry = cast("list[object]", metadata["placeholder_registry"])
    registry_entry = cast("JsonObject", registry[0])
    registry_entry["target_path"] = "/flow/0/parameters/wrong"

    report = validate_payload(payload)
    finding = require_finding(report, TARGET_MISMATCH_CODE)

    assert finding.source_path == ("metadata", "placeholder_registry", 0), (
        f"Target path mismatch source path drifted: {finding}"
    )
    assert not ("/flow/0/parameters/hook" not in finding.internal_message), (
        f"Target path mismatch did not report actual usage: {finding}"
    )


def test_handoff_manifest_includes_project_placeholder_instructions() -> None:
    """Project registry entries become handoff manifest placeholders."""
    root = parse_make_ast_json_text(
        json.dumps(registered_placeholder_payload(), sort_keys=True)
    )
    manifest = build_handoff_placeholder_manifest(
        root=root, catalog=native_module_snapshot()
    )
    by_key = {placeholder.key: placeholder for placeholder in manifest}

    placeholder = by_key.get("runtime_webhook_lead_intake_hook")
    assert placeholder is not None, (
        f"Project placeholder was missing from handoff manifest: {manifest}"
    )
    assert (
        placeholder.description
        == "Create a custom webhook in Make, then paste its hook ID."
    ), f"Project instructions were not preserved: {placeholder}"
    assert placeholder.expected_type == "hook_id", (
        f"Project placeholder schema did not reach the manifest: {placeholder}"
    )
    assert placeholder.required, (
        f"Project placeholder schema did not reach the manifest: {placeholder}"
    )
    assert (
        placeholder.replacement_paths[0].json_pointer
        == "/flow/0/parameters/hook"
    ), f"Project replacement path drifted: {placeholder}"


def registered_placeholder_payload() -> JsonObject:
    """Return the computed result for the caller."""
    return {
        "flow": [
            {
                "id": 1,
                "interface": [{"name": "email", "type": "text"}],
                "metadata": {
                    "raw_spec": {
                        "catalog_module_id": (
                            "module:gateway:1.14.1:trigger:CustomWebHook"
                        ),
                        "issues": [],
                        "raw_spec_sha256": "a" * 64,
                        "status": "resolved",
                    }
                },
                "module": "gateway:CustomWebHook",
                "parameters": {"hook": "{{runtime.webhook.lead_intake_hook}}"},
            }
        ],
        "metadata": {
            "placeholder_registry": [
                {
                    "expected_type": "hook_id",
                    "handoff_instructions": (
                        "Create a custom webhook in Make, then paste its hook "
                        "ID."
                    ),
                    "kind": "runtime_setup ",
                    "placeholder": "runtime.webhook.lead_intake_hook",
                    "required": True,
                    "target_path": "/flow/0/parameters/hook",
                }
            ],
            "schedule": {"id": "schedule:manual"},
        },
        "name": "registered-runtime-placeholder",
    }


def validate_fixture(path: Path) -> BlueprintValidationReport:
    """Validate one sanitized placeholder fixture.

    Returns:
        The validation report.
    """
    return validate_payload(load_fixture(path))


def validate_payload(payload: JsonObject) -> BlueprintValidationReport:
    """Validate one sanitized placeholder payload.

    Returns:
        The validation report.
    """
    return validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )


def require_finding(
    report: BlueprintValidationReport,
    code: str,
) -> BlueprintValidationFinding:
    """Return one validation finding by code.

    Returns:
        The matching validation finding.
    """
    for finding in report.findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected finding code {code!r}; got {report.findings}"
    assert_unexpected_success(failure_message)
    return None


def load_fixture(path: Path) -> JsonObject:
    """Load one sanitized JSON object fixture.

    Returns:
        The loaded fixture payload.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))
