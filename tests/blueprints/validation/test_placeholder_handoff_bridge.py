# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Placeholder registry to handoff manifest bridge tests.

Boundary contract:
- Owns: registry-backed handoff placeholder manifest behavior.
- Must not: render PDFs, call Make.com, or resolve live runtime resources.
- Allows: sanitized offline fixture mutation and exact manifest/finding
assertions.
- Split when: placeholder registry parsing or client handoff rendering needs its
own suite.
- Merge when: another validation test owns this exact registry-to-manifest
bridge.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import (
    BlueprintValidationFinding,
    BlueprintValidationReport,
    HandoffPlaceholder,
    build_handoff_placeholder_manifest,
    validate_blueprint,
)
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.assertions import assert_unexpected_success
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

FIXTURE_ROOT = (
    repo_root() / "tests" / "blueprints" / "fixtures" / "importability"
)
BRIDGE_FIXTURE = FIXTURE_ROOT / "placeholder_registry_handoff_bridge.json"
PLACEHOLDER_CONFLICT_CODE = "importability.placeholder_registry_conflict"
PLACEHOLDER_DUPLICATE_CODE = "importability.placeholder_registry_duplicate"
PLACEHOLDER_UNREGISTERED_CODE = "importability.placeholder_unregistered"


def test_project_placeholder_registry_entry_appears_in_handoff_manifest() -> (
    None
):
    """A project-declared runtime placeholder becomes a handoff manifest.

    item.
    """
    manifest = manifest_by_key(load_fixture(BRIDGE_FIXTURE))

    placeholder = manifest.get("runtime_webhook_lead_intake_hook")
    assert placeholder is not None, (
        f"Webhook runtime placeholder was missing from manifest: {manifest}"
    )
    assert placeholder.description == (
        "Create a Custom webhook in Make, then paste its hook ID before"
        "activation."
    ), f"Project handoff instructions were not preserved: {placeholder}"
    assert placeholder.expected_type == "hook_id", (
        f"Project placeholder schema drifted: {placeholder}"
    )
    assert placeholder.required, (
        f"Project placeholder schema drifted: {placeholder}"
    )
    assert_replacement_paths(placeholder, ("/flow/0/parameters/hook",))


def test_catalog_and_project_placeholder_requirements_are_deduplicated() -> (
    None
):
    """Repeated registry evidence for one runtime placeholder stays one.

    requirement.
    """
    payload = load_fixture(BRIDGE_FIXTURE)
    registry = placeholder_registry(payload)
    registry.append(copy.deepcopy(registry[0]))

    report = validate_payload(payload)
    blocked_codes = {
        PLACEHOLDER_CONFLICT_CODE,
        PLACEHOLDER_DUPLICATE_CODE,
    }.intersection(report.codes())
    if blocked_codes:
        message = (
            f"Equivalent placeholder registry entries should deduplicate:"
            f"{report.findings}"
        )
        assert not (blocked_codes), message

    manifest = manifest_by_key(payload)
    placeholder = manifest.get("runtime_webhook_lead_intake_hook")
    assert placeholder is not None, (
        f"Deduplicated project placeholder was missing: {manifest}"
    )
    assert_replacement_paths(placeholder, ("/flow/0/parameters/hook",))


def test_conflicting_placeholder_registry_entries_report_8d599() -> None:
    """Conflicting registry entries for one runtime placeholder are explicit.

    blockers.
    """
    payload = load_fixture(BRIDGE_FIXTURE)
    registry = placeholder_registry(payload)
    conflicting_entry = copy.deepcopy(registry[0])
    conflicting_entry["kind"] = "connection"
    conflicting_entry["target_path"] = "/flow/0/parameters/connection"
    registry.append(conflicting_entry)

    report = validate_payload(payload)
    finding = require_finding(report, PLACEHOLDER_CONFLICT_CODE)

    assert finding.source_path == ("metadata", "placeholder_registry", 2), (
        f"Placeholder conflict path drifted: {finding}"
    )
    assert not (
        "runtime.webhook.lead_intake_hook" not in finding.internal_message
    ), f"Placeholder conflict did not name the placeholder: {finding}"


def test_unresolved_parameter_placeholder_links_to_handoff_requirement() -> (
    None
):
    """Runtime parameter placeholders expose their exact replacement path in.

    handoff.
    """
    manifest = manifest_by_key(load_fixture(BRIDGE_FIXTURE))

    placeholder = manifest.get("runtime_datastore_qualified_leads")
    assert placeholder is not None, (
        f"Data Store runtime placeholder was missing from manifest: {manifest}"
    )
    assert placeholder.seed_value == "{{runtime.datastore.qualified_leads}}", (
        f"Runtime placeholder seed value drifted: {placeholder}"
    )
    assert placeholder.bind_in_make, (
        f"Runtime placeholder must remain operator-supplied: {placeholder}"
    )
    assert placeholder.client_supplies_value, (
        f"Runtime placeholder must remain operator-supplied: {placeholder}"
    )
    assert_replacement_paths(placeholder, ("/flow/1/parameters/datastore",))


def load_fixture(path: Path) -> JsonObject:
    """Load a sanitized JSON object fixture.

    Returns:
        The loaded fixture payload.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def validate_payload(payload: JsonObject) -> BlueprintValidationReport:
    """Validate one placeholder bridge payload.

    Returns:
        The validation report for the payload.
    """
    return validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )


def manifest_by_key(payload: JsonObject) -> dict[str, HandoffPlaceholder]:
    """Build handoff manifest placeholders by key.

    Returns:
        The handoff manifest indexed by placeholder key.
    """
    root = parse_make_ast_json_text(json.dumps(payload, sort_keys=True))
    manifest = build_handoff_placeholder_manifest(
        root=root, catalog=native_module_snapshot()
    )
    return {placeholder.key: placeholder for placeholder in manifest}


def placeholder_registry(payload: JsonObject) -> list[JsonObject]:
    """Return the mutable placeholder registry from a fixture payload.

    Returns:
        The root metadata.placeholder_registry list.
    """
    metadata = payload.get("metadata")
    assert isinstance(metadata, dict), (
        f"Fixture metadata must be an object: {payload}"
    )
    metadata_object = cast("JsonObject", metadata)
    registry = metadata_object.get("placeholder_registry")
    assert isinstance(registry, list), (
        f"Fixture placeholder_registry must be a list: {metadata_object}"
    )
    registry_items = cast("list[object]", registry)
    entries: list[JsonObject] = []
    for entry in registry_items:
        assert isinstance(entry, dict), (
            f"Fixture placeholder registry entries must be objects: {entry}"
        )
        entries.append(
            normalize_json_object(cast("Mapping[str, object]", entry))
        )
    registry_items[:] = entries
    return cast("list[JsonObject]", registry_items)


def require_finding(
    report: BlueprintValidationReport,
    code: str,
) -> BlueprintValidationFinding:
    """Return one finding by code.

    Returns:
        The matching validation finding.
    """
    for finding in report.findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected finding code {code!r}; got {report.findings}"
    assert_unexpected_success(failure_message)
    return None


def assert_replacement_paths(
    placeholder: HandoffPlaceholder,
    expected_paths: tuple[str, ...],
) -> None:
    """Assert exact replacement path pointers for one placeholder."""
    actual_paths = tuple(
        path.json_pointer for path in placeholder.replacement_paths
    )
    assert actual_paths == expected_paths, (
        f"Placeholder replacement paths drifted: {placeholder}"
    )
