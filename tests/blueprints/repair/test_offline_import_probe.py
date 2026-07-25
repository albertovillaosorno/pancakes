# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for offline Make import probe transports.

Boundary contract:
- Owns: fake Make import probe behavior over sanitized local fixtures.
- Must not: call live Make services, require credentials, or test MCP routing.
- Allows: fixture-backed responses and repair diagnostic assertions.
- Split when: live probe authorization tests become a separate gated workflow.
- Merge when: another repair test duplicates fake import probe transport
coverage.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from blueprints.repair.transports import FixtureImportProbe

if TYPE_CHECKING:
    from pathlib import Path as PathType

FIXTURE_ROOT = Path("tests/blueprints/fixtures/importability")
MAKE_ENV_VARS = (
    "MAKE_API_TOKEN",
    "MAKE_ZONE",
    "MAKE_ORGANIZATION_ID",
    "MAKE_LIVE_SCRAPER_ENABLED",
)


def test_fake_import_probe_returns_success_for_valid_fixture() -> None:
    """Successful fixture responses produce no diagnostics."""
    result = FixtureImportProbe.from_path(
        FIXTURE_ROOT / "mock_make_import_success.json"
    ).probe_import({})

    assert result.status == "accepted", (
        f"Success fixture should not emit findings: {result}"
    )
    assert not (result.findings), (
        f"Success fixture should not emit findings: {result}"
    )
    assert not (result.diagnostics.candidates), (
        f"Success fixture should not emit repair diagnostics: {result}"
    )


def test_fake_import_probe_maps_router_failure_to_actionable_diagnostic() -> (
    None
):
    """Router topology failures should map to incomplete-execution repair.

    guidance.
    """
    result = FixtureImportProbe.from_path(
        FIXTURE_ROOT / "mock_make_import_router_failure.json"
    ).probe_import({})

    categories = result.diagnostics.categories()
    assert not ("incomplete_execution_risk" not in categories), (
        f"Router failure did not map to actionable diagnostics: {result}"
    )
    assert result.findings[0].code == "importability.router_topology", (
        f"Router finding code drifted: {result.findings}"
    )


def test_fake_import_probe_does_not_require_environment_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixture-backed import probes must not depend on Make credential.

    environment.
    """
    for name in MAKE_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    result = FixtureImportProbe.from_path(
        FIXTURE_ROOT / "mock_make_import_placeholder_failure.json"
    ).probe_import({})

    assert result.status == "rejected", (
        f"Placeholder failure fixture should be rejected: {result}"
    )
    assert result.findings[0].code == "importability.placeholder_unresolved", (
        f"Placeholder finding code drifted: {result.findings}"
    )


def test_fake_import_probe_rejects_non_standard_json_constants(
    tmp_path: PathType,
) -> None:
    """Import probe fixtures must be strict JSON, not Python parser.

    extensions.
    """
    fixture_path = tmp_path / "probe.json"
    _ = fixture_path.write_text('{"status": NaN}', encoding="utf-8")

    with pytest.raises(ValueError, match="non-standard JSON constant NaN"):
        _ = FixtureImportProbe.from_path(fixture_path)
