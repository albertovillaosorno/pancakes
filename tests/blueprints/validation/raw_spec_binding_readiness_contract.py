# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Raw-spec binding hash readiness validation contracts.

Boundary contract:
- Owns: catalog-backed readiness claim tests for AST raw-spec binding hashes.
- Must not: scrape Make, refresh raw specs, or validate project persistence.
- Allows: small synthetic AST payloads and catalog-backed validation assertions.
- Split when: raw-spec binding status becomes a standalone validator slice.
- Merge when: another validation test owns the same readiness claim behavior.
"""

from __future__ import annotations

import json
from typing import Final

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation import BlueprintValidationReport, validate_blueprint

from tests.catalog.test_module_token_resolution import native_module_snapshot

RAW_SPEC_HASH_MISSING: Final = "raw_spec.binding_hash_missing"
UNRESOLVED_MODULE: Final = "module.unresolved"
DATASTORE_ADD_RECORD_MODULE_ID: Final = (
    "module:datastore:2.0.5:action:AddRecord"
)


def test_catalog_backed_readiness_accepts_resolved_binding_with_hash() -> None:
    """Readiness claims pass when resolved bindings carry raw-spec hash.

    evidence.
    """
    report = _validate(
        _scenario(
            claim_level="catalog_backed_import_ready",
            raw_spec={
                "catalog_module_id": DATASTORE_ADD_RECORD_MODULE_ID,
                "issues": [],
                "raw_spec_sha256": "a" * 64,
                "status": "resolved",
            },
        )
    )

    assert RAW_SPEC_HASH_MISSING not in report.codes(), (
        f"Hash-backed binding should satisfy readiness evidence: {report}"
    )


def test_catalog_backed_readiness_blocks_resolved_binding_missing_hash() -> (
    None
):
    """Resolved-looking raw-spec bindings cannot support import-ready claims.

    without hashes.
    """
    report = _validate(
        _scenario(
            claim_level="catalog_backed_import_ready",
            raw_spec={
                "catalog_module_id": DATASTORE_ADD_RECORD_MODULE_ID,
                "issues": [],
                "status": "resolved",
            },
        )
    )

    _assert_single_hash_blocker(report.codes())


def test_catalog_backed_readiness_blocks_missing_binding_hash_evidence() -> (
    None
):
    """Catalog-resolved modules still need node-local raw-spec hash evidence."""
    report = _validate(
        _scenario(
            claim_level="catalog_backed_import_ready",
            raw_spec=None,
        )
    )

    _assert_single_hash_blocker(report.codes())


def test_source_draft_parsing_allows_missing_binding_hash_evidence() -> None:
    """Project drafts without readiness claims keep missing hash evidence.

    nonblocking.
    """
    report = _validate(
        _scenario(
            claim_level=None,
            raw_spec={
                "catalog_module_id": DATASTORE_ADD_RECORD_MODULE_ID,
                "issues": [],
                "status": "resolved",
            },
        )
    )

    assert RAW_SPEC_HASH_MISSING not in report.codes(), (
        f"Draft parsing should not require hash evidence: {report}"
    )


def test_unresolved_module_keeps_existing_resolution_blocker() -> None:
    """Unresolved modules should not also emit raw-spec hash readiness.

    blockers.
    """
    report = _validate(
        _scenario(
            claim_level="catalog_backed_import_ready",
            module_name="datastore:ImaginaryModule",
            raw_spec=None,
        )
    )

    codes = report.codes()
    assert not (UNRESOLVED_MODULE not in codes), (
        f"Unresolved module should keep the existing blocker: {report}"
    )
    assert RAW_SPEC_HASH_MISSING not in codes, (
        f"Unresolved modules should not duplicate hash blockers: {report}"
    )


def test_importable_candidate_phase_claim_requires_binding_hash_evidence() -> (
    None
):
    """Importable artifact-phase claims are stronger than catalog-backed.

    readiness.
    """
    report = _validate(
        _scenario(
            artifact_phase="importable_candidate",
            raw_spec={
                "catalog_module_id": DATASTORE_ADD_RECORD_MODULE_ID,
                "issues": [],
                "status": "resolved",
            },
        )
    )

    _assert_single_hash_blocker(report.codes())


def _validate(payload: JsonObject) -> BlueprintValidationReport:
    return validate_blueprint(
        root=parse_make_ast_json_text(json.dumps(payload, sort_keys=True)),
        catalog=native_module_snapshot(),
    )


def _scenario(
    *,
    claim_level: str | None = None,
    artifact_phase: str | None = None,
    module_name: str = "datastore:AddRecord",
    raw_spec: JsonObject | None,
) -> JsonObject:
    metadata: JsonObject = {"schedule": {"id": "schedule:manual"}}
    if claim_level is not None:
        metadata["claim_level"] = claim_level
    if artifact_phase is not None:
        metadata["artifact_phase"] = artifact_phase
    node: JsonObject = {
        "id": 1,
        "module": module_name,
        "parameters": {},
    }
    if raw_spec is not None:
        node["metadata"] = {"raw_spec": raw_spec}
    return {
        "name": "raw-spec-readiness",
        "flow": [node],
        "metadata": metadata,
    }


def _assert_single_hash_blocker(codes: tuple[str, ...]) -> None:
    assert codes.count(RAW_SPEC_HASH_MISSING) == 1, (
        f"Readiness claim should have exactly one hash blocker: {codes}"
    )
