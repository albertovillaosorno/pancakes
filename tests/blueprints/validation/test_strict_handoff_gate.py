# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Strict handoff gate tests for Make blueprint delivery claims.

Boundary contract:
- Owns: focused tests for strict and draft handoff gate behavior.
- Must not: render PDFs, create media artifacts, or call live Make services.
- Allows: sanitized inline blueprint payloads and catalog-backed validation.
- Split when: handoff output rendering owns its own importability assertions.
- Merge when: another validation test owns this exact handoff gate contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation.generation_gate import guard_blueprint_for_handoff
from blueprints.validation.handoff_manifest import (
    build_handoff_blocker_manifest,
)
from blueprints.validation.importability import (
    IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
)
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from catalog import CatalogSnapshot

REPO_ROOT = repo_root()
CATALOG_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "catalog"
    / "fixtures"
    / "make_catalog"
    / "sample_catalog.json"
)


def test_strict_handoff_gate_blocks_unimportable_blueprint() -> None:
    """Strict handoff blocks importable claims when offline validation has.

    errors.
    """
    result = guard_blueprint_for_handoff(
        root=parse_make_ast_json_text(json.dumps(placeholder_payload())),
        catalog=load_catalog_fixture(),
    )

    assert result.status == "blocked", (
        f"Strict handoff must block unimportable payloads: {result}"
    )
    assert not (result.importable), (
        f"Strict handoff must block unimportable payloads: {result}"
    )
    assert result.blockers[0].code == IMPORTABILITY_PLACEHOLDER_UNRESOLVED, (
        f"Strict handoff did not expose the importability blocker: {result}"
    )
    assert not ("/flow/0/parameters/url" not in result.operator_message), (
        f"Strict handoff did not name the first field to fix: {result}"
    )


def test_draft_handoff_gate_allows_warnings_but_marks_not_importable() -> None:
    """Draft handoff remains producible for warning-only blueprints without.

    importable claims.
    """
    result = guard_blueprint_for_handoff(
        root=parse_make_ast_json_text(json.dumps(warning_only_payload())),
        catalog=load_catalog_fixture(),
        mode="draft",
    )

    assert result.status == "allowed", (
        f"Draft handoff must be allowed but not importable: {result}"
    )
    assert not (result.importable), (
        f"Draft handoff must be allowed but not importable: {result}"
    )
    assert not (result.blockers), (
        f"Warning-only draft handoff should not have blockers: "
        f"{result.blockers}"
    )
    assert any(
        finding.severity == "warning"
        for finding in result.validation_report.findings
    ), (
        f"Draft handoff should retain warning findings: "
        f"{result.validation_report}"
    )


def test_handoff_manifest_lists_blocker_code_path_and_owner() -> None:
    """Handoff blocker manifests include code, field path, severity, and.

    owner.
    """
    result = guard_blueprint_for_handoff(
        root=parse_make_ast_json_text(json.dumps(placeholder_payload())),
        catalog=load_catalog_fixture(),
    )
    manifest = build_handoff_blocker_manifest(report=result.validation_report)

    blocker = manifest[0]

    assert blocker.code == IMPORTABILITY_PLACEHOLDER_UNRESOLVED, (
        f"Blocker manifest lost the finding code: {manifest}"
    )
    assert blocker.json_pointer == "/flow/0/parameters/url", (
        f"Blocker manifest lost the source path: {manifest}"
    )
    assert blocker.severity == "error", (
        f"Blocker manifest did not expose severity and owner: {manifest}"
    )
    assert blocker.suggested_owner == "operator", (
        f"Blocker manifest did not expose severity and owner: {manifest}"
    )


def placeholder_payload() -> JsonObject:
    """Return a catalog-backed payload with one unresolved handoff placeholder.

    Returns:
        The sanitized blueprint payload.
    """
    return {
        "name": "placeholder-blocked",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "parameters": {
                    "method": "POST ",
                    "url": "{{TODO:client-webhook-url}}",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def warning_only_payload() -> JsonObject:
    """Return a valid payload that still produces nonblocking warnings.

    Returns:
        The sanitized blueprint payload.
    """
    return {
        "name": "warning-only-handoff",
        "flow": [
            {
                "id": 1,
                "metadata": {
                    "raw_spec": {
                        "catalog_module_id": (
                            "module:http:1.0:action:makeRequest"
                        ),
                        "issues": [],
                        "raw_spec_sha256": "1" * 64,
                        "status": "resolved",
                    }
                },
                "module": "http:MakeRequest",
                "parameters": {
                    "method": "POST ",
                    "url": "https://example.invalid",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample Make catalog fixture.

    Returns:
        The loaded catalog snapshot.
    """
    payload = cast(
        "object", json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8"))
    )
    assert isinstance(payload, dict), (
        f"{CATALOG_FIXTURE} must contain a JSON object."
    )
    return catalog_snapshot_from_json(
        normalize_json_object(cast("Mapping[str, object]", payload))
    )
