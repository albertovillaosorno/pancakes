# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Portfolio readiness matrix tests for tracked Make project fixtures.

Boundary contract:
- Owns: offline readiness matrix assertions for project fixture assets.
- Must not: call Make.com, mutate project JSON, read credentials, or publish
reports.
- Allows: deterministic fixture discovery, validation summaries, and handoff
counts.
- Split when: a generated report or live verification matrix becomes approved.
- Merge when: another integration test owns this exact project readiness matrix.
"""

from __future__ import annotations

import os
from collections import UserDict
from typing import TYPE_CHECKING, Final

from blueprints.validation.portfolio_readiness import (
    build_portfolio_readiness_matrix,
)
from tests.catalog.test_module_token_resolution import native_module_snapshot

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

REPO_ROOT = repo_root()
PROJECTS_ROOT = (
    REPO_ROOT / "tests" / "blueprints" / "fixtures" / "portfolio_projects"
)
LEAD_PROJECT_ID: Final = "lead-routing-data-store-mvp"
CREDENTIAL_ENV_MARKERS: Final = frozenset(
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


def test_portfolio_readiness_matrix_includes_lead_routing_asset() -> None:
    """The matrix discovers the tracked lead-routing project fixture."""
    matrix = build_portfolio_readiness_matrix(
        projects_root=PROJECTS_ROOT,
        catalog=native_module_snapshot(),
    )
    row = matrix.row_for_project(LEAD_PROJECT_ID)

    assert row is not None, (
        f"Matrix did not include {LEAD_PROJECT_ID}: {matrix}"
    )
    assert row.project_name == "Lead Routing Data Store MVP", (
        f"Lead project name drifted: {row}"
    )
    expected_path = (
        "portfolio_projects/lead-routing-data-store-mvp/scenario.json"
    )
    assert row.relative_scenario_path == expected_path, (
        f"Lead project path drifted: {row}"
    )
    assert not (any(item.project_id.startswith("_") for item in matrix.rows)), (
        f"Template folders must not be reported as portfolio assets: {matrix}"
    )


def test_portfolio_readiness_matrix_uses_offline_validation_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The matrix uses local fixtures and catalog evidence without reading.

    credentials.
    """
    monkeypatch.setattr(os, "getenv", _fail_environment_read)
    monkeypatch.setattr(os, "environ", CredentialReadTrap())

    matrix = build_portfolio_readiness_matrix(
        projects_root=PROJECTS_ROOT,
        catalog=native_module_snapshot(),
    )

    assert matrix.rows, (
        "Portfolio readiness matrix should include at least one tracked asset."
    )
    assert not (any(row.live_make_called for row in matrix.rows)), (
        f"Portfolio readiness matrix must remain offline-only: {matrix}"
    )
    assert {row.evidence_status for row in matrix.rows} == {
        "offline_validation_only"
    }, f"Unexpected evidence status values: {matrix}"


def test_portfolio_readiness_matrix_reports_phase_21a70b17() -> None:
    """The matrix reports phase, status, blockers, warnings, and placeholder.

    counts.
    """
    matrix = build_portfolio_readiness_matrix(
        projects_root=PROJECTS_ROOT,
        catalog=native_module_snapshot(),
    )
    row = matrix.row_for_project(LEAD_PROJECT_ID)

    assert row is not None, (
        f"Matrix did not include {LEAD_PROJECT_ID}: {matrix}"
    )
    assert row.artifact_phase == "source_draft", (
        f"Lead project status must stay honest while blocked: {row}"
    )
    assert row.importability_status == "blocked", (
        f"Lead project status must stay honest while blocked: {row}"
    )
    assert not (row.blocker_count <= 0), (
        f"Blocked project must expose blocker count: {row}"
    )
    assert {
        "route.routes_on_non_router",
        "importability.placeholder_registry_incomplete",
        "importability.placeholder_unregistered",
    }.issubset(row.blocker_codes), f"Lead project blocker codes drifted: {row}"
    assert not (row.warning_count < 0), (
        f"Matrix counts must be nonnegative: {row}"
    )
    assert not (row.placeholder_count < 0), (
        f"Matrix counts must be nonnegative: {row}"
    )
    assert row.placeholder_count == len(row.placeholder_keys), (
        f"Placeholder count must match placeholder keys: {row}"
    )


def test_portfolio_readiness_matrix_rejects_non_standard_json_constants(
    tmp_path: Path,
) -> None:
    """Scenario discovery treats NaN and Infinity as malformed JSON."""
    project_root = tmp_path / "bad-project"
    project_root.mkdir()
    _ = (project_root / "scenario.json").write_text(
        '{"name":"Bad","flow":[],"metadata":{"score":NaN}}\n',
        encoding="utf-8",
    )

    matrix = build_portfolio_readiness_matrix(
        projects_root=tmp_path,
        catalog=native_module_snapshot(),
    )
    row = matrix.row_for_project("bad-project")

    assert row is not None, f"Bad project row was not reported: {matrix}"
    assert row.evidence_status == "offline_parse_failed", (
        f"Malformed JSON scenario should be parse-failed: {row}"
    )
    assert row.blocker_codes == (
        "portfolio.scenario_parse_failed:ValueError",
    ), f"Malformed JSON should fail before AST parsing: {row}"


def _fail_environment_read(key: str, default: object = None) -> object:
    assert not (_credential_like_env_key(key)), (
        f"Offline readiness matrix unexpectedly read environment key {key!r}."
    )
    return default


class CredentialReadTrap(UserDict[str, str]):
    """Mapping that fails if readiness code asks for credential-like.

    environment.

    values.
    """

    def __getitem__(self, key: str) -> str:
        """Fail credential-like lookups and report other keys as missing.

        Raises:
            KeyError: For non-credential environment keys.
        """
        assert not (_credential_like_env_key(key)), (
            f"Offline readiness matrix unexpectedly read environment key "
            f"{key!r}."
        )
        raise KeyError(key)

    def __setitem__(self, key: str, item: str) -> None:
        """Allow non-credential test-runner bookkeeping writes."""
        assert not (_credential_like_env_key(key)), (
            f"Offline readiness matrix unexpectedly wrote environment key "
            f"{key!r}."
        )
        self.data[key] = item

    def __delitem__(self, key: str) -> None:
        """Allow non-credential test-runner cleanup deletes."""
        assert not (_credential_like_env_key(key)), (
            f"Offline readiness matrix unexpectedly deleted environment key "
            f"{key!r}."
        )
        _ = self.data.pop(key, None)

    def __contains__(self, key: object) -> bool:
        """Fail credential-like membership checks and miss other keys.

        Returns:
            False for non-credential environment keys.
        """
        if isinstance(key, str):
            assert not _credential_like_env_key(key), (
                f"Offline readiness matrix unexpectedly checked environment "
                f"key {key!r}."
            )
        return False


def _credential_like_env_key(key: str) -> bool:
    return any(marker in key.casefold() for marker in CREDENTIAL_ENV_MARKERS)
