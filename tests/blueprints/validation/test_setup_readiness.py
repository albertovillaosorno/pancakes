# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001046#repo.blueprint-validation.validator-policy
# - 001061#repo.delivery.client-ready-handoff-contract
# - 001068#repo.operator-commands.command-registry
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Setup-readiness tests for Golden and Blueprint validation evidence.

Boundary contract:
- Owns: focused setup-required diagnostic checks for local readiness reports.
- Must not: call Make.com, refresh catalogs, inspect browser UI, or test privacy
parity.
- Allows: synthetic designer diagnostics, existing validation findings, and
Golden gating.
- Split when: live setup probing or repair planning requires separate fixtures.
- Merge when: another validation test owns the same setup-readiness contract.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from blueprints.validation.findings import build_validation_finding
from blueprints.validation.setup_readiness import check_setup_readiness
from catalog.json_payloads import normalize_json_object
from golden.comparison import compare_golden_blueprint_texts

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

REPO_ROOT = repo_root()
SETUP_FIXTURE_ROOT = (
    REPO_ROOT / "tests" / "blueprints" / "fixtures" / "setup_readiness"
)
SETUP_REQUIRED_DIAGNOSTICS = (
    SETUP_FIXTURE_ROOT / "setup_required_diagnostics.json"
)
NO_SETUP_REQUIRED_DIAGNOSTICS = (
    SETUP_FIXTURE_ROOT / "no_setup_required_diagnostics.json"
)
VALID_BLUEPRINT = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "importability"
    / "valid_lead_routing_router.json"
)


def test_setup_required_designer_diagnostic_fails_readiness() -> None:
    """A Make setupreq error blocks local client-readiness."""
    report = check_setup_readiness(
        designer_diagnostics=load_diagnostics(SETUP_REQUIRED_DIAGNOSTICS)
    )

    assert not (report.client_ready), (
        f"Setup-required diagnostics must fail readiness: {report}"
    )
    assert report.checked_without_live_make, (
        f"Setup readiness must stay local-only: {report}"
    )
    assert report.dimension == "setup_readiness", (
        f"Setup readiness must expose its own dimension: {report}"
    )

    finding = report.findings[0]
    assert finding.affected_module == "google-sheets:addRow", (
        f"Finding lost the affected module: {finding}"
    )
    assert finding.category == "setupreq", (
        f"Finding did not preserve setupreq error evidence: {finding}"
    )
    assert finding.severity == "error", (
        f"Finding did not preserve setupreq error evidence: {finding}"
    )
    assert finding.evidence_path == "$.flow[1].metadata.designer.messages[0]", (
        f"Finding lost evidence path: {finding}"
    )
    assert not (finding.model_dependent_uncertainty), (
        f"Complete fixture should not add uncertainty: {finding}"
    )


def test_make_native_setup_and_epoch_categories_fail_readiness() -> None:
    """Make setup, setupreq, and epochreq errors are native setup blockers."""
    report = check_setup_readiness(
        designer_diagnostics=(
            {
                "affected_module": "notion:watchDatabaseItems",
                "category": "setup",
                "severity": "error",
                "message": "Connection: Value must not be empty.",
                "evidence_path": "$.flow[0].metadata.designer.messages[0]",
            },
            {
                "affected_module": "google-email:triggerWatchNewEmails",
                "category": "epochreq",
                "severity": "error",
                "message": "You must first choose from which point to start.",
                "evidence_path": (
                    "$.metadata.designer.orphans[0][0].metadata.designer.messages[3]"
                ),
            },
            {
                "affected_module": "google-sheets:addRow",
                "category": "setupreq",
                "severity": "error",
                "message": "The module is not set up.",
                "evidence_path": "$.flow[1].metadata.designer.messages[0]",
            },
            {
                "affected_module": "google-email:triggerWatchNewEmails",
                "category": "link",
                "severity": "warning",
                "message": "This module is not connected to the flow.",
                "evidence_path": (
                    "$.metadata.designer.orphans[0][0].metadata.designer.messages[0]"
                ),
            },
        )
    )

    assert not (report.client_ready), (
        f"Native Make setup errors must block: {report}"
    )
    assert tuple(finding.category for finding in report.findings) == (
        "setup",
        "epochreq",
        "setupreq",
    ), f"Native Make setup categories were not preserved: {report.findings}"


def test_no_setup_required_designer_diagnostic_812724e3() -> None:
    """Non-setup designer diagnostics do not block setup-readiness."""
    report = check_setup_readiness(
        designer_diagnostics=load_diagnostics(NO_SETUP_REQUIRED_DIAGNOSTICS)
    )

    assert report.client_ready, (
        f"Non-setup diagnostics must pass setup-readiness: {report}"
    )
    assert not (report.findings), (
        f"Non-setup diagnostics produced setup findings: {report.findings}"
    )


def test_validation_finding_equivalent_to_setupreq_fails_readiness() -> None:
    """Existing validation findings can represent setup-required states."""
    finding = build_validation_finding(
        code="designer.setupreq",
        severity="error",
        node=("2", ("flow", 1, "metadata", "designer", "messages", 0)),
        catalog_module_id="module:google-sheets:1.0:addRow",
        messages=(
            "A Make module still requires runtime setup.",
            "The module is not set up.",
        ),
    )

    report = check_setup_readiness(validation_findings=(finding,))

    assert not (report.client_ready), (
        f"Setup-required validation finding must fail readiness: {report}"
    )
    setup_finding = report.findings[0]
    assert setup_finding.source == "validation_finding", (
        f"Validation finding source was not preserved: {setup_finding}"
    )
    assert (
        setup_finding.evidence_path == "/flow/1/metadata/designer/messages/0"
    ), f"Validation finding path did not become a JSON pointer: {setup_finding}"
    assert setup_finding.category == "setupreq", (
        f"Validation finding did not normalize setup category: {setup_finding}"
    )


def test_validation_finding_path_safe_guard_redacts_rejected_message() -> None:
    """Path-safety guard failures must not echo the unsafe client message."""
    unsafe_client_message = "C:\\customers\\private-blueprint.json"

    with pytest.raises(
        ValueError, match="raw client message is redacted"
    ) as error:
        _ = build_validation_finding(
            code="designer.setupreq",
            severity="error",
            node=("2", ("flow", 1, "metadata", "designer", "messages", 0)),
            catalog_module_id="module:google-sheets:1.0:addRow",
            messages=(
                unsafe_client_message,
                "Internal validation detail.",
            ),
        )

    message = str(error.value)
    assert unsafe_client_message not in message, (
        f"Path-safety guard leaked the rejected client message: {message}"
    )


def test_golden_completion_blocks_on_setup_f7c87a53() -> None:
    """Golden completion reports setup readiness separately from semantic.

    parity.
    """
    blueprint_text = VALID_BLUEPRINT.read_text(encoding="utf-8")
    report = compare_golden_blueprint_texts(
        reference_text=blueprint_text,
        generated_text=blueprint_text,
        label="setup-readiness",
        designer_diagnostics=load_diagnostics(SETUP_REQUIRED_DIAGNOSTICS),
    )

    assert report.semantic_parity, (
        f"Identical blueprints must keep semantic parity: {report}"
    )
    assert not (report.completion_allowed), (
        f"Golden completion must block setup-required diagnostics: {report}"
    )
    assert not ("setup_readiness" not in report.completion_blockers), (
        f"Golden blockers must name setup_readiness: "
        f"{report.completion_blockers}"
    )
    assert report.setup_readiness.dimension == "setup_readiness", (
        f"Golden report lost setup readiness dimension: "
        f"{report.setup_readiness}"
    )
    payload = report.as_dict()
    assert not ("setup_readiness" not in payload), (
        f"Golden report must expose setup readiness beside comparison: "
        f"{payload}"
    )
    assert not ("comparison" not in payload), (
        f"Golden report must expose setup readiness beside comparison: "
        f"{payload}"
    )


def load_diagnostics(path: Path) -> tuple[Mapping[str, object], ...]:
    """Load one synthetic designer diagnostic fixture.

    Returns:
        The diagnostic objects in fixture order.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, list), f"{path} must contain a JSON array."
    diagnostics: list[Mapping[str, object]] = []
    for item in cast("list[object]", payload):
        assert isinstance(item, dict), (
            f"{path} must contain diagnostic objects."
        )
        diagnostic = normalize_json_object(cast("Mapping[str, object]", item))
        diagnostics.append(diagnostic)
    return tuple(diagnostics)
