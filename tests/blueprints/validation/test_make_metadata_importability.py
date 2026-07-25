# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Importability tests for Make-native metadata payloads.

Boundary contract:
- Owns: node-local metadata shape checks for import-critical Make fields.
- Must not: validate live Make behavior, catalog resolution, or renderer output.
- Allows: small sanitized AST payloads and exact validation finding paths.
- Split when: root metadata and node metadata need separate policy modules.
- Merge when: importability tests already cover these exact metadata fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from blueprints.ast import JsonObject, ast_evidence_report, parse_make_ast
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.importability import (
    IMPORTABILITY_METADATA_INVALID,
    validate_importability,
)

from tests.support.assertions import assert_unexpected_success

if TYPE_CHECKING:
    from blueprints.validation.models import BlueprintValidationFinding


def test_restore_metadata_shape_is_preserved_for_node_evidence() -> None:
    """Restore metadata stays raw, recognized, and non-opaque in AST.

    evidence.
    """
    payload: JsonObject = {
        "name": "restore-metadata-evidence",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "metadata": {
                    "restore": {"mode": "connection", "source": "accountId"},
                    "custom_restore_note": "kept",
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:manual"}},
    }

    root = parse_make_ast(payload)
    node = iter_ast_nodes(root)[0]
    node_metadata = cast("JsonObject", node.raw_payload["metadata"])
    report = ast_evidence_report(root)
    findings = validate_importability(iter_ast_nodes(root), root=root)

    assert node_metadata.get("restore") == {
        "mode": "connection",
        "source": "accountId",
    }, f"Node restore metadata was not preserved: {node_metadata}"
    assert "$.flow[0].metadata.restore" not in report.opaque_field_paths, (
        f"Restore metadata should be recognized, not opaque: {report}"
    )
    assert not (
        "$.flow[0].metadata.custom_restore_note"
        not in report.opaque_field_paths
    ), f"Unknown metadata evidence should stay visible: {report}"
    assert not (
        any(
            finding.code == IMPORTABILITY_METADATA_INVALID
            for finding in findings
        )
    ), f"Valid restore metadata reported an importability finding: {findings}"


def test_malformed_expect_metadata_reports_importability_finding() -> None:
    """Malformed Make expect metadata emits a path-specific importability.

    finding.
    """
    findings = importability_findings(
        {
            "name": "malformed-expect-metadata",
            "flow": [
                {
                    "id": 1,
                    "module": "http:MakeRequest",
                    "metadata": {"expect": "not a field collection"},
                }
            ],
            "metadata": {"schedule": {"id": "schedule:manual"}},
        }
    )

    finding = require_finding(findings, IMPORTABILITY_METADATA_INVALID)

    assert finding.source_path == ("flow", 0, "metadata", "expect"), (
        f"Malformed expect metadata path drifted: {finding}"
    )
    assert finding.node_id == "1", (
        f"Malformed expect metadata should attach to node 1: {finding}"
    )


def test_unknown_metadata_field_is_preserved_unless_policy_blocks_it() -> None:
    """Unknown metadata fields remain raw evidence and do not fail.

    importability.
    """
    payload: JsonObject = {
        "name": "unknown-metadata-preservation",
        "flow": [
            {
                "id": 1,
                "module": "http:MakeRequest",
                "metadata": {
                    "expect": [{"name": "recordId", "type": "text"}],
                    "non_policy_metadata": {"kept": True},
                },
            }
        ],
        "metadata": {"schedule": {"id": "schedule:manual"}},
    }

    root = parse_make_ast(payload)
    node = iter_ast_nodes(root)[0]
    node_metadata = cast("JsonObject", node.raw_payload["metadata"])
    findings = validate_importability(iter_ast_nodes(root), root=root)
    report = ast_evidence_report(root)

    assert node_metadata.get("non_policy_metadata") == {"kept": True}, (
        f"Unknown metadata field was not preserved: {node_metadata}"
    )
    assert not (
        any(
            finding.code == IMPORTABILITY_METADATA_INVALID
            for finding in findings
        )
    ), f"Unknown metadata should not fail importability: {findings}"
    assert not (
        "$.flow[0].metadata.non_policy_metadata"
        not in report.opaque_field_paths
    ), f"Unknown metadata evidence should remain visible: {report}"


def importability_findings(
    payload: JsonObject,
) -> tuple[BlueprintValidationFinding, ...]:
    """Return importability findings for one sanitized payload."""
    root = parse_make_ast(payload)
    return validate_importability(iter_ast_nodes(root), root=root)


def require_finding(
    findings: tuple[BlueprintValidationFinding, ...],
    code: str,
) -> BlueprintValidationFinding:
    """Return one validation finding by code or fail."""
    for finding in findings:
        if finding.code == code:
            return finding
    failure_message = f"Expected finding code {code!r}; got {findings}"
    assert_unexpected_success(failure_message)
    return None
