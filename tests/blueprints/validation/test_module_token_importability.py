# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Importability tests for catalog-backed module token validation.

Boundary contract:
- Owns: focused tests for unknown module token importability blockers.
- Must not: test catalog compilation, module ranking, or live Make imports.
- Allows: sanitized offline blueprint fixtures and synthetic catalog snapshots.
- Split when: importability token checks expand into separate path or version
rules.
- Merge when: another importability test duplicates unknown-token blocker
behavior.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.importability import validate_importability
from catalog.json_payloads import normalize_json_object

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

REPO_ROOT = repo_root()
UNKNOWN_MODULE_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "importability"
    / "invalid_unknown_module_reference.json"
)


def test_unknown_module_token_reports_importability_07ae8a4a() -> None:
    """Unknown Make module tokens produce actionable importability blockers."""
    payload = load_fixture(UNKNOWN_MODULE_FIXTURE)
    findings = validate_importability(
        iter_ast_nodes(
            parse_make_ast_json_text(json.dumps(payload, sort_keys=True))
        ),
        native_module_snapshot(),
    )

    unknown_findings = [
        finding
        for finding in findings
        if finding.code == "importability.module.unknown"
    ]
    assert len(unknown_findings) == 1, (
        f"Expected one unknown-token importability blocker: {findings}"
    )
    finding = unknown_findings[0]
    assert finding.source_path == ("flow", 0), (
        f"Unknown-token finding did not name the module path: {finding}"
    )
    assert not ("unknown:ImaginaryModule" not in finding.internal_message), (
        f"Unknown-token finding lost the raw module token: {finding}"
    )


def load_fixture(path: Path) -> JsonObject:
    """Load one sanitized JSON object fixture.

    Returns:
        The loaded JSON object.
    """
    payload = cast(
        "object",
        json.loads(path.read_text(encoding="utf-8")),
    )
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))
