# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Lead-routing offline handoff validation chain tests.

Boundary contract:
- Owns: one offline parse/render/validate/handoff chain for lead
  routing.
- Must not: call Make.com, read credentials, generate PDFs, or create
  media artifacts.
- Allows: sanitized fixture reads and typed handoff manifest assertions.
- Split when: live roundtrip proof or generated handoff artifacts need
  their own suite.
- Merge when: another integration test owns this exact offline handoff chain.
"""

from __future__ import annotations

import json
import os
from collections import UserDict
from typing import TYPE_CHECKING, NamedTuple, cast

from blueprints.ast import JsonObject, parse_make_ast_json_text
from blueprints.validation.delivery_coverage import (
    build_blueprint_delivery_coverage,
)
from blueprints.validation.generation_gate import guard_blueprint_for_handoff
from blueprints.validation.handoff_manifest import (
    HandoffEvidenceSource,
    build_handoff_placeholder_manifest,
    build_handoff_readiness_manifest,
)
from blueprints.validation.validator import validate_blueprint
from catalog.json_payloads import normalize_json_object
from languages.make.blueprint_export import (
    MakeBlueprintRenderMode,
    render_make_blueprint_payload,
)
from tests.catalog.test_module_token_resolution import native_module_snapshot

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from _pytest.monkeypatch import MonkeyPatch
    from blueprints.ast.models import MakeAstRoot
    from blueprints.validation.delivery_coverage import (
        BlueprintDeliveryCoverage,
    )
    from blueprints.validation.generation_gate import BlueprintHandoffGateReport
    from blueprints.validation.handoff_manifest import (
        BlueprintHandoffReadinessManifest,
    )
    from blueprints.validation.models import BlueprintValidationReport
    from languages.make.blueprint_export import MakeBlueprintRenderReport

REPO_ROOT = repo_root()
IMPORTABLE_CANDIDATE = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "importability"
    / "valid_lead_routing_importable_candidate.json"
)
SOURCE_PROJECT_ASSET = (
    REPO_ROOT
    / "tests"
    / "blueprints"
    / "fixtures"
    / "portfolio_projects"
    / "lead-routing-data-store-mvp"
    / "scenario.json"
)
EXPECTED_PLACEHOLDER_KEYS = frozenset(
    (
        "runtime_datastore_incomplete_leads",
        "runtime_datastore_qualified_leads",
        "runtime_webhook_lead_intake_hook",
    )
)
EXPECTED_SOURCE_BLOCKERS = frozenset(
    (
        "route.routes_on_non_router",
        "importability.placeholder_registry_incomplete",
        "importability.placeholder_unregistered",
    )
)
EXPECTED_EVIDENCE_IDS = frozenset(
    (
        "ast.parse",
        "ast.render",
        "validation.importability",
        "handoff.strict_gate",
        "handoff.placeholder_manifest",
    )
)
CREDENTIAL_ENV_MARKERS = frozenset(
    (
        "api",
        "auth",
        "bearer",
        "credential",
        "key",
        "make",
        "password",
        "secret",
        "token",
    )
)


class OfflineHandoffChain(NamedTuple):
    """One cached result from the offline lead-routing validation chain."""

    payload: JsonObject
    root: MakeAstRoot
    render_result: MakeBlueprintRenderReport
    validation_report: BlueprintValidationReport
    strict_gate: BlueprintHandoffGateReport
    coverage: BlueprintDeliveryCoverage
    manifest: BlueprintHandoffReadinessManifest


def test_lead_routing_candidate_offline_chain_is_importable_candidate() -> None:
    """The fixture is importable offline without live Make claims."""
    chain = _run_offline_chain(IMPORTABLE_CANDIDATE)

    assert not (chain.validation_report.has_errors), (
        f"Candidate chain produced validation errors: {chain.validation_report}"
    )
    assert chain.strict_gate.status == "allowed", (
        f"Strict gate did not accept the offline candidate: {chain.strict_gate}"
    )
    assert chain.strict_gate.importable, (
        f"Strict gate did not accept the offline candidate: {chain.strict_gate}"
    )
    assert chain.render_result.importable, (
        f"Renderer did not preserve importable status: {chain.render_result}"
    )
    assert chain.manifest.importability_status == "importable_candidate", (
        f"Candidate was not classified honestly: {chain.manifest}"
    )
    assert not (chain.manifest.live_make_called), (
        f"Offline chain must not claim a live scenario: {chain.manifest}"
    )


def test_lead_routing_source_draft_chain_reports_known_blockers() -> None:
    """The source project remains blocked until known issues are fixed."""
    chain = _run_offline_chain(SOURCE_PROJECT_ASSET)
    blocker_codes = frozenset(
        blocker.code for blocker in chain.manifest.blockers
    )
    missing = EXPECTED_SOURCE_BLOCKERS - blocker_codes

    assert chain.strict_gate.status == "blocked", (
        f"Source draft must stay blocked: {chain.strict_gate}"
    )
    assert not (chain.strict_gate.importable), (
        f"Source draft must stay blocked: {chain.strict_gate}"
    )
    assert chain.manifest.importability_status == "source_draft", (
        f"Source project was not classified as source draft: {chain.manifest}"
    )
    assert not (missing), (
        f"Source draft blockers drifted: missing={sorted(missing)}"
    )
    assert not (chain.coverage.error_count <= 0), (
        "Delivery coverage must expose the blocked source draft: "
        f"{chain.coverage}"
    )


def test_handoff_manifest_contains_placeholder_and_evidence_summary() -> None:
    """Manifest output carries placeholders, warnings, and evidence."""
    chain = _run_offline_chain(IMPORTABLE_CANDIDATE)

    placeholder_keys = frozenset(
        placeholder.key for placeholder in chain.manifest.placeholders
    )
    evidence_ids = frozenset(
        source.source_id for source in chain.manifest.evidence_sources
    )
    warning_codes = tuple(warning.code for warning in chain.manifest.warnings)

    assert placeholder_keys == EXPECTED_PLACEHOLDER_KEYS, (
        f"Candidate placeholder manifest drifted: {chain.manifest.placeholders}"
    )
    assert EXPECTED_EVIDENCE_IDS.issubset(evidence_ids), (
        "Manifest evidence sources are incomplete: "
        f"{chain.manifest.evidence_sources}"
    )
    assert not (chain.manifest.blockers), (
        "Candidate manifest should not carry blockers: "
        f"{chain.manifest.blockers}"
    )
    assert not ("webhook.response_missing" not in warning_codes), (
        f"Offline advisory warning disappeared from manifest: {chain.manifest}"
    )
    assert not (
        any(
            warning.severity != "warning" for warning in chain.manifest.warnings
        )
    ), f"Designer advisories must stay nonblocking warnings: {chain.manifest}"


def test_offline_chain_does_not_read_environment_credentials(
    monkeypatch: MonkeyPatch,
) -> None:
    """The handoff chain uses fixture and catalog evidence only."""
    monkeypatch.setattr(os, "getenv", _fail_environment_read)
    monkeypatch.setattr(os, "environ", CredentialReadTrap())

    chain = _run_offline_chain(IMPORTABLE_CANDIDATE)

    assert not (chain.manifest.live_make_called), (
        "Credential-free offline chain must not call live Make: "
        f"{chain.manifest}"
    )


def _run_offline_chain(path: Path) -> OfflineHandoffChain:
    payload = _load_json_object(path)
    root = parse_make_ast_json_text(json.dumps(payload, sort_keys=True))
    catalog = native_module_snapshot()
    validation_report = validate_blueprint(root=root, catalog=catalog)
    strict_gate = guard_blueprint_for_handoff(root=root, catalog=catalog)
    render_mode: MakeBlueprintRenderMode = (
        "importable" if strict_gate.importable else "draft"
    )
    render_result = render_make_blueprint_payload(
        root=root,
        catalog=catalog,
        mode=render_mode,
    )
    placeholders = build_handoff_placeholder_manifest(
        root=root, catalog=catalog
    )
    return OfflineHandoffChain(
        payload=payload,
        root=root,
        render_result=render_result,
        validation_report=validation_report,
        strict_gate=strict_gate,
        coverage=build_blueprint_delivery_coverage(root=root, catalog=catalog),
        manifest=build_handoff_readiness_manifest(
            report=validation_report,
            placeholders=placeholders,
            importable=strict_gate.importable,
            live_make_called=False,
            evidence_sources=_offline_evidence_sources(),
        ),
    )


def _offline_evidence_sources() -> tuple[HandoffEvidenceSource, ...]:
    return (
        HandoffEvidenceSource(
            source_id="ast.parse",
            label="AST parser",
            detail="Parsed with blueprints.ast.parse_make_ast_json_text.",
        ),
        HandoffEvidenceSource(
            source_id="ast.render",
            label="Make blueprint exporter",
            detail=(
                "Rendered with languages.make.blueprint_export."
                "render_make_blueprint_payload."
            ),
        ),
        HandoffEvidenceSource(
            source_id="validation.importability",
            label="Importability validation",
            detail=(
                "Validated through blueprints.validation.validate_blueprint."
            ),
        ),
        HandoffEvidenceSource(
            source_id="handoff.strict_gate",
            label="Strict handoff gate",
            detail="Checked with guard_blueprint_for_handoff in strict mode.",
        ),
        HandoffEvidenceSource(
            source_id="handoff.placeholder_manifest",
            label="Placeholder manifest",
            detail=(
                "Built from runtime placeholder registry and catalog fields."
            ),
        ),
    )


def _load_json_object(path: Path) -> JsonObject:
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return normalize_json_object(cast("Mapping[str, object]", payload))


def _fail_environment_read(key: str, default: object = None) -> object:
    assert not (_credential_like_env_key(key)), (
        f"Offline handoff chain unexpectedly read environment key {key!r}."
    )
    return default


class CredentialReadTrap(UserDict[str, str]):
    """Mapping that fails if the offline chain asks for environment values."""

    def __getitem__(self, key: str) -> str:
        """Fail credential-like lookups and report other keys as missing.

        Raises:
            KeyError: For non-credential environment keys.
        """
        assert not (_credential_like_env_key(key)), (
            f"Offline handoff chain unexpectedly read environment key {key!r}."
        )
        raise KeyError(key)

    def __setitem__(self, key: str, item: str) -> None:
        """Allow non-credential test-runner bookkeeping writes."""
        assert not (_credential_like_env_key(key)), (
            f"Offline handoff chain unexpectedly wrote environment key {key!r}."
        )
        self.data[key] = item

    def __delitem__(self, key: str) -> None:
        """Allow non-credential test-runner cleanup deletes."""
        assert not (_credential_like_env_key(key)), (
            "Offline handoff chain unexpectedly deleted environment "
            f"key {key!r}."
        )
        _ = self.data.pop(key, None)

    def __contains__(self, key: object) -> bool:
        """Fail credential-like membership checks and miss other keys.

        Returns:
            False for non-credential environment keys.
        """
        if isinstance(key, str):
            assert not _credential_like_env_key(key), (
                "Offline handoff chain unexpectedly checked environment "
                f"key {key!r}."
            )
        return False


def _credential_like_env_key(key: str) -> bool:
    return any(marker in key.casefold() for marker in CREDENTIAL_ENV_MARKERS)
