# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Smoke tests for the Make blueprint importability validation gate.

Boundary contract:
- Owns: focused tests for importability finding-code stability and validator
wiring.
- Must not: test repair behavior, renderer output, catalog compilation, or live
Make import.
- Allows: sanitized offline blueprint payloads and catalog-backed validation
assertions.
- Split when: importability rules grow beyond one smoke-test module.
- Merge when: another importability test duplicates this validator wiring
contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from blueprints.validation.importability import (
    IMPORTABILITY_FINDING_CODES,
    IMPORTABILITY_PLACEHOLDER_UNRESOLVED,
    IMPORTABILITY_RULE_EVIDENCE,
    IMPORTABILITY_RULE_EXTERNAL_BIBLIOGRAPHY,
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


def test_importability_gate_accepts_known_good_faeefe05() -> None:
    """A catalog-backed valid fixture should not receive importability.

    blockers.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "importable-http",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST",
                                "url": "https://example.invalid",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                },
                sort_keys=True,
            )
        ),
        catalog=load_catalog_fixture(),
    )

    importability_codes = tuple(
        code for code in report.codes() if code.startswith("importability.")
    )
    assert not (importability_codes), (
        f"Known-good fixture produced importability findings: {report.findings}"
    )


def test_importability_gate_uses_stable_finding_codes() -> None:
    """Unresolved handoff placeholders should emit a stable importability.

    blocker.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "unresolved-placeholder",
                    "flow": [
                        {
                            "id": 1,
                            "module": "http:MakeRequest",
                            "parameters": {
                                "method": "POST",
                                "url": "{{TODO:client-webhook-url}}",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                },
                sort_keys=True,
            )
        ),
        catalog=load_catalog_fixture(),
    )

    assert not (IMPORTABILITY_PLACEHOLDER_UNRESOLVED not in report.codes()), (
        f"Importability placeholder blocker was not reported: {report.codes()}"
    )


def test_importability_rule_evidence_covers_every_finding_code() -> None:
    """Importability rule claims should name local or reviewed external.

    evidence.
    """
    evidence_by_code = dict(IMPORTABILITY_RULE_EVIDENCE)
    bibliography_by_code = dict(IMPORTABILITY_RULE_EXTERNAL_BIBLIOGRAPHY)

    assert frozenset(evidence_by_code) == IMPORTABILITY_FINDING_CODES, (
        f"Importability evidence map drifted: {evidence_by_code}"
    )
    missing_evidence = tuple(
        code for code, sources in evidence_by_code.items() if not sources
    )
    assert not (missing_evidence), (
        f"Importability rules lost evidence sources: {missing_evidence}"
    )
    external_sources = {
        source
        for sources in bibliography_by_code.values()
        for source in sources
    }
    assert external_sources == {
        "docs/bibliography/make-router-topology.md",
        "docs/bibliography/make-filter-expressions.md",
        "docs/bibliography/make.com.md",
    }, f"Unexpected importability bibliography coverage: {external_sources}"


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
