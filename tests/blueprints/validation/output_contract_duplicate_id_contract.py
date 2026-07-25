# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Output-contract validation tests for duplicate source node IDs.

Boundary contract:
- Owns: duplicate-node safety for output-reference validation.
- Must not: duplicate general node ID validation or contact live Make services.
- Allows: sanitized inline blueprints that exercise expression reference
ambiguity.
- Split when: output-reference ambiguity expands beyond duplicate node IDs.
- Merge when: another validation contract owns the same duplicate-target
behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import validate_blueprint
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


def test_output_reference_to_duplicate_node_id_reports_ambiguous_target() -> (
    None
):
    """References to duplicate source node IDs must not pass through one.

    overwritten lookup.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(duplicate_source_reference_blueprint())
        ),
        catalog=load_catalog_fixture(),
    )
    codes = report.codes()

    assert not ("ast.node_id_duplicate" not in codes), (
        f"Duplicate node ID validator finding was suppressed: {report.findings}"
    )
    assert not ("output.reference_duplicate_node_id" not in codes), (
        f"Duplicate output-reference target was not reported: {report.findings}"
    )
    assert "semantic.output_field_unknown" not in codes, (
        f"Ambiguous duplicate target was misreported as an unknown field: "
        f"{report}"
    )


def duplicate_source_reference_blueprint() -> JsonObject:
    """Return a sanitized blueprint with a downstream reference to a duplicated.

    source ID.
    """
    return {
        "name": "duplicate-output-reference-target",
        "flow": [
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "version": 1,
                "interface": [{"name": "email", "type": "text"}],
            },
            {
                "id": 1,
                "module": "gateway:CustomWebHook",
                "version": 1,
                "interface": [{"name": "email", "type": "text"}],
            },
            {
                "id": 2,
                "module": "http:MakeRequest",
                "version": 1,
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
                "parameters": {
                    "method": "POST",
                    "url": "https://example.invalid/{{1.email}}",
                },
            },
        ],
        "metadata": {"schedule": {"id": "schedule:daily"}},
    }


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample catalog fixture.

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
