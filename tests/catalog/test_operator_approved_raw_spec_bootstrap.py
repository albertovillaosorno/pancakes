# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Operator-approved raw-spec bootstrap tests.

Boundary contract:
- Owns: focused tests for local operator-approved raw-spec stub behavior.
- Must not: scrape Make, call live services, compile catalogs, or test MCP
flows.
- Allows: sanitized offline fixtures and synthetic catalog snapshots.
- Split when: stub persistence or knowledge-store promotion gets separate tests.
- Merge when: another catalog test owns the same local stub validation contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.ast.traversal import iter_ast_nodes
from blueprints.validation.importability import (
    IMPORTABILITY_MODULE_OPERATOR_APPROVED_STUB,
    validate_importability,
)
from catalog.json_payloads import normalize_json_object
from catalog.lineage import build_operator_approved_stub_lineage
from catalog.validation import resolve_module_token
from languages.make.raw_specs.local_stubs import (
    operator_approved_raw_spec_stub_from_json,
)

from tests.catalog.test_module_token_resolution import native_module_snapshot
from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from blueprints.ast.models import MakeAstNode
    from blueprints.validation.models import BlueprintValidationFinding
    from catalog.models import CatalogSnapshot
    from languages.make.raw_specs.local_stubs import OperatorApprovedRawSpecStub

STUB_FIXTURE = (
    repo_root()
    / "tests"
    / "fixtures"
    / "catalog"
    / "operator_approved_datastore_add_record_stub.json"
)


def test_operator_approved_stub_requires_provenance_fields() -> None:
    """Operator-approved local stubs must carry explicit provenance limits."""
    payload = load_stub_payload()
    del payload["unsupported_fields"]

    with pytest.raises(ValueError, match="unsupported_fields"):
        _ = operator_approved_raw_spec_stub_from_json(payload)


def test_operator_approved_stub_is_allowed_in_offline_development_mode() -> (
    None
):
    """Offline development may acknowledge a stub without.

    catalog-confirming it.
    """
    stub = load_stub_fixture()
    snapshot = snapshot_without_datastore()

    resolution = resolve_module_token(
        snapshot,
        "datastore:AddRecord",
        operator_approved_stubs=(stub,),
        offline_development=True,
    )

    assert not (resolution.known), (
        f"Operator-approved stubs must not be catalog-confirmed: {resolution}"
    )
    assert resolution.issue == "operator_approved_stub", (
        f"Stub resolution did not preserve provenance status: {resolution}"
    )
    assert not (resolution.catalog_module_id is not None), (
        f"Stub resolution fabricated catalog evidence: {resolution}"
    )
    assert not (resolution.raw_spec_sha256 is not None), (
        f"Stub resolution fabricated catalog evidence: {resolution}"
    )

    lineage = build_operator_approved_stub_lineage((stub,))
    assert lineage.stubs[0].module_token == stub.module_token, (
        f"Stub lineage lost the module token: {lineage}"
    )

    findings = validate_importability(
        datastore_add_record_nodes(),
        catalog=snapshot,
        operator_approved_stubs=(stub,),
        delivery_mode="offline_development",
    )
    stub_findings = _stub_findings(findings)
    assert len(stub_findings) == 1, (
        f"Offline stub should be a nonblocking finding: {findings}"
    )
    assert stub_findings[0].severity == "warning", (
        f"Offline stub should be a nonblocking finding: {findings}"
    )


def test_operator_approved_stub_blocks_strict_client_handoff() -> None:
    """Strict handoff treats local stubs as unresolved raw-spec evidence."""
    stub = load_stub_fixture()

    findings = validate_importability(
        datastore_add_record_nodes(),
        catalog=snapshot_without_datastore(),
        operator_approved_stubs=(stub,),
        delivery_mode="strict_client_handoff",
    )

    stub_findings = _stub_findings(findings)
    assert len(stub_findings) == 1, (
        f"Strict handoff must block operator-approved stubs: {findings}"
    )
    assert stub_findings[0].severity == "error", (
        f"Strict handoff must block operator-approved stubs: {findings}"
    )
    assert "Make-confirmed" not in stub_findings[0].client_message, (
        f"Stub handoff message must not claim Make confirmation: "
        f"{stub_findings[0]}"
    )


def test_real_raw_spec_takes_precedence_over_stub() -> None:
    """Catalog-backed raw-spec evidence outranks a matching local stub."""
    stub = load_stub_fixture()
    snapshot = native_module_snapshot()

    resolution = resolve_module_token(
        snapshot,
        "datastore:AddRecord",
        operator_approved_stubs=(stub,),
        offline_development=True,
    )

    assert resolution.known, (
        f"Catalog evidence should take precedence over stubs: {resolution}"
    )
    assert not (resolution.issue is not None), (
        f"Catalog evidence should take precedence over stubs: {resolution}"
    )
    assert (
        resolution.catalog_module_id
        == "module:datastore:2.0.5:action:AddRecord"
    ), f"Catalog-backed module ID was not preserved: {resolution}"

    findings = validate_importability(
        datastore_add_record_nodes(),
        catalog=snapshot,
        operator_approved_stubs=(stub,),
        delivery_mode="strict_client_handoff",
    )
    assert not (_stub_findings(findings)), (
        f"Strict handoff should not block catalog-confirmed modules: {findings}"
    )


def load_stub_fixture() -> OperatorApprovedRawSpecStub:
    """Load the sanitized local raw-spec stub fixture.

    Returns:
        The loaded local raw-spec stub.
    """
    return operator_approved_raw_spec_stub_from_json(load_stub_payload())


def load_stub_payload() -> JsonObject:
    """Load the raw JSON fixture payload.

    Returns:
        The loaded JSON object.
    """
    return load_json_object(STUB_FIXTURE)


def snapshot_without_datastore() -> CatalogSnapshot:
    """Return the synthetic catalog without Data Store raw-spec evidence."""
    snapshot = native_module_snapshot()
    return snapshot._replace(
        apps=tuple(app for app in snapshot.apps if app.app_slug != "datastore"),
    )


def datastore_add_record_nodes() -> tuple[MakeAstNode, ...]:
    """Return AST nodes for a local Data Store AddRecord draft."""
    root = parse_make_ast_json_text(
        json.dumps(
            {
                "name": "operator-approved-stub",
                "flow": [
                    {
                        "id": 1,
                        "module": "datastore:AddRecord",
                        "parameters": {
                            "datastore": "{{runtime.datastore.test}}"
                        },
                    }
                ],
                "metadata": {"schedule": {"id": "schedule:manual"}},
            },
            sort_keys=True,
        )
    )
    return iter_ast_nodes(root)


def _stub_findings(
    findings: tuple[BlueprintValidationFinding, ...],
) -> tuple[BlueprintValidationFinding, ...]:
    return tuple(
        finding
        for finding in findings
        if finding.code == IMPORTABILITY_MODULE_OPERATOR_APPROVED_STUB
    )


def load_json_object(path: Path) -> JsonObject:
    """Load one JSON object fixture.

    Returns:
        The loaded JSON object.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))
