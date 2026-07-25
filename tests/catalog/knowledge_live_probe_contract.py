# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for operator-gated live_probe evidence staging.

Boundary contract:
- Owns: Make live roundtrip probe planning, fake transports, and SQL staging.
- Must not: contact Make.com, require credentials, or mutate SQLite directly.
- Allows: temporary knowledge snapshots and fake roundtrip transports.
- Split when: real Make transport adapters need separate coverage.
- Merge when: knowledge_store_contract owns live_probe evidence behavior
directly.
"""

from __future__ import annotations

from shutil import copytree
from typing import TYPE_CHECKING, cast

import pytest
from catalog.knowledge import (
    DEFAULT_DB_SNAPSHOT_DIR,
    LIVE_PROBE_SOURCE_CONFIDENCE,
    LiveProbeAuthorization,
    build_knowledge_store,
    list_needs_review_conflicts,
    live_probe_authorization_from_json,
    load_knowledge_store_query,
    run_live_roundtrip_probe,
)

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

    from languages.make.raw_specs.models import JsonObject

REPO_ROOT = repo_root()
FIXED_OBSERVED_AT = "2026-04-30T00:00:00+00:00"
CONFLICT_KEY = "webhook.response.timeout_seconds"


class FakeRoundtripTransport:
    """Fake Make roundtrip transport for live_probe tests."""

    def __init__(self, returned_scenario: JsonObject) -> None:
        """Store the returned scenario fixture and captured upload state."""
        self.uploaded_scenario: JsonObject | None = None
        self.returned_scenario = returned_scenario
        self.aligned_scenario_ids: list[str] = []

    def upload_scenario(self, scenario: JsonObject) -> str:
        """Capture the uploaded probe scenario.

        Returns:
            The fake live scenario id.
        """
        self.uploaded_scenario = scenario
        return "scenario-live-probe-1"

    def auto_align_scenario(self, scenario_id: str) -> bool:
        """Pretend Make accepted auto-align for the probe scenario.

        Returns:
            True when the expected fake scenario id is supplied.
        """
        assert scenario_id == "scenario-live-probe-1", (
            f"Unexpected scenario id: {scenario_id}"
        )
        self.aligned_scenario_ids.append(scenario_id)
        return True

    def download_scenario(self, scenario_id: str) -> JsonObject:
        """Return the fake Make-normalized scenario."""
        assert scenario_id == "scenario-live-probe-1", (
            f"Unexpected scenario id: {scenario_id}"
        )
        return self.returned_scenario


def test_live_probe_stages_reviewed_evidence_for_next_offline_build(
    tmp_path: Path,
) -> None:
    """Live probes write reviewed SQL evidence and the next build resolves.

    ties.
    """
    _prepare_snapshot_dir(tmp_path)
    _write_needs_review_claim_evidence(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    conflicts = list_needs_review_conflicts(repo_root=tmp_path)
    raw_conflict_items = conflicts["conflicts"]
    assert isinstance(raw_conflict_items, list), (
        f"Expected one needs_review conflict: {conflicts}"
    )
    conflict_items = cast("list[JsonObject]", raw_conflict_items)
    assert len(conflict_items) == 1, (
        f"Expected one needs_review conflict: {conflicts}"
    )
    conflict_id = str(conflict_items[0]["conflict_id"])

    returned_scenario: JsonObject = {
        "name": "live-probe-webhook.response.timeout_seconds",
        "flow": [],
        "metadata": {
            "live_probe": {
                "claim_key": CONFLICT_KEY,
                "normalized": True,
                "errors": [{"message": "Make accepted 180 seconds."}],
            }
        },
    }
    report = run_live_roundtrip_probe(
        repo_root=tmp_path,
        conflict_id=conflict_id,
        authorization=LiveProbeAuthorization(
            operator_approved=True,
            approved_by="test-operator",
            credential_ref="make-connection:test",
            purpose="resolve_claim_conflict",
        ),
        transport=FakeRoundtripTransport(returned_scenario),
        reviewed_value_json='{"seconds":180}',
        observed_at_utc=FIXED_OBSERVED_AT,
    )

    raw_evidence = report["evidence"]
    assert isinstance(raw_evidence, dict), (
        f"Live probe did not return evidence: {report}"
    )
    evidence = cast("JsonObject", raw_evidence)
    assert evidence.get("source_kind") == "live_probe", (
        f"Live probe evidence source kind drifted: {evidence}"
    )
    assert evidence.get("source_confidence") == LIVE_PROBE_SOURCE_CONFIDENCE, (
        f"Live probe evidence confidence drifted: {evidence}"
    )
    assert report.get("evidence_sql_path") == (
        "src/data/sql_snapshots/live_probe_evidence.sql"
    ), f"Live probe wrote evidence outside the reviewed snapshot: {report}"

    _ = build_knowledge_store(repo_root=tmp_path)
    query = load_knowledge_store_query(repo_root=tmp_path)
    rebuilt_conflicts = query.claim_conflicts_for_key(CONFLICT_KEY)
    assert rebuilt_conflicts, (
        "Expected live_probe evidence to participate in conflict arbitration."
    )
    assert all(
        conflict.resolution_status == "resolved"
        for conflict in rebuilt_conflicts
    ), f"Live probe should resolve remaining conflicts: {rebuilt_conflicts}"
    assert all(
        conflict.winning_source_kind == "live_probe"
        for conflict in rebuilt_conflicts
    ), f"Live probe should win by confidence: {rebuilt_conflicts}"


def test_live_probe_rejects_unapproved_or_secret_like_authorization(
    tmp_path: Path,
) -> None:
    """Live probes cannot run without explicit safe operator authorization."""
    _prepare_snapshot_dir(tmp_path)
    _write_needs_review_claim_evidence(tmp_path)
    _ = build_knowledge_store(repo_root=tmp_path)
    conflicts = list_needs_review_conflicts(repo_root=tmp_path)
    raw_conflict_items = conflicts["conflicts"]
    assert isinstance(raw_conflict_items, list), (
        f"Expected needs_review conflicts: {conflicts}"
    )
    assert raw_conflict_items, f"Expected needs_review conflicts: {conflicts}"
    conflict_items = cast("list[JsonObject]", raw_conflict_items)
    conflict_id = str(conflict_items[0]["conflict_id"])

    with pytest.raises(PermissionError, match="operator_approved=true"):
        _ = run_live_roundtrip_probe(
            repo_root=tmp_path,
            conflict_id=conflict_id,
            authorization=LiveProbeAuthorization(
                operator_approved=False,
                approved_by="test-operator",
                credential_ref="make-connection:test",
                purpose="resolve_claim_conflict",
            ),
            transport=FakeRoundtripTransport(
                {"name": "x", "flow": [], "metadata": {}}
            ),
            reviewed_value_json='{"seconds":180}',
            observed_at_utc=FIXED_OBSERVED_AT,
        )

    with pytest.raises(PermissionError, match="non-secret reference"):
        _ = run_live_roundtrip_probe(
            repo_root=tmp_path,
            conflict_id=conflict_id,
            authorization=LiveProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="sk-this-is-a-raw-token",
                purpose="resolve_claim_conflict",
            ),
            transport=FakeRoundtripTransport(
                {"name": "x", "flow": [], "metadata": {}}
            ),
            reviewed_value_json='{"seconds":180}',
            observed_at_utc=FIXED_OBSERVED_AT,
        )


def test_live_probe_rejects_missing_authorization_identity_fields(
    tmp_path: Path,
) -> None:
    """Live probe approval must name the reviewer and credential reference."""
    cases = (
        (
            LiveProbeAuthorization(
                operator_approved=True,
                approved_by=" ",
                credential_ref="make-connection:test",
                purpose="resolve_claim_conflict",
            ),
            "requires approved_by",
        ),
        (
            LiveProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref=" ",
                purpose="resolve_claim_conflict",
            ),
            "requires credential_ref",
        ),
    )
    for authorization, expected_error in cases:
        with pytest.raises(PermissionError, match=expected_error):
            _ = run_live_roundtrip_probe(
                repo_root=tmp_path,
                conflict_id="unused-conflict",
                authorization=authorization,
                transport=FakeRoundtripTransport(
                    {"name": "x", "flow": [], "metadata": {}}
                ),
                reviewed_value_json='{"seconds":180}',
                observed_at_utc=FIXED_OBSERVED_AT,
            )


def test_live_probe_rejects_authorization_shape_drift(tmp_path: Path) -> None:
    """Authorization control fields must keep exact reviewed JSON shapes."""
    cases = (
        (
            LiveProbeAuthorization(
                operator_approved=cast("bool", "true"),
                approved_by="test-operator",
                credential_ref="make-connection:test",
                purpose="resolve_claim_conflict",
            ),
            "operator_approved=true",
        ),
        (
            LiveProbeAuthorization(
                operator_approved=True,
                approved_by=cast("str", {"operator": "test"}),
                credential_ref="make-connection:test",
                purpose="resolve_claim_conflict",
            ),
            "requires approved_by",
        ),
        (
            LiveProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref=cast("str", ["make-connection:test"]),
                purpose="resolve_claim_conflict",
            ),
            "requires credential_ref",
        ),
        (
            LiveProbeAuthorization(
                operator_approved=True,
                approved_by="test-operator",
                credential_ref="make-connection:test",
                purpose=cast("str", ["resolve_claim_conflict"]),
            ),
            "purpose must be",
        ),
    )
    for authorization, expected_error in cases:
        with pytest.raises(PermissionError, match=expected_error):
            _ = run_live_roundtrip_probe(
                repo_root=tmp_path,
                conflict_id="unused-conflict",
                authorization=authorization,
                transport=FakeRoundtripTransport(
                    {"name": "x", "flow": [], "metadata": {}}
                ),
                reviewed_value_json='{"seconds":180}',
                observed_at_utc=FIXED_OBSERVED_AT,
            )


def test_live_probe_authorization_json_keeps_exact_field_shapes() -> None:
    """Authorization JSON parsing must not coerce arbitrary shapes to text."""
    with pytest.raises(TypeError, match="boolean operator_approved"):
        _ = live_probe_authorization_from_json(
            """
            {
              "operator_approved": "true",
              "approved_by": "test-operator",
              "credential_ref": "make-connection:test",
              "purpose": "resolve_claim_conflict"
            }
            """
        )

    with pytest.raises(ValueError, match="non-empty string approved_by"):
        _ = live_probe_authorization_from_json(
            """
            {
              "operator_approved": true,
              "approved_by": {"operator": "test"},
              "credential_ref": "make-connection:test",
              "purpose": "resolve_claim_conflict"
            }
            """
        )


def _prepare_snapshot_dir(tmp_path: Path) -> None:
    source = REPO_ROOT / DEFAULT_DB_SNAPSHOT_DIR
    destination = tmp_path / DEFAULT_DB_SNAPSHOT_DIR
    _ = copytree(source, destination)


def _write_needs_review_claim_evidence(tmp_path: Path) -> None:
    snapshot_path = (
        tmp_path / DEFAULT_DB_SNAPSHOT_DIR / "claim_evidence_needs_review.sql"
    )
    _ = snapshot_path.write_text(
        """
INSERT OR REPLACE INTO claim_evidence (
  evidence_id,
  claim_key,
  domain,
  value_json,
  claim_text,
  source_confidence,
  evidence_observed_at,
  source_kind,
  source_ref,
  claim_ref,
  valid_from,
  valid_to,
  fingerprint,
  adr_anchor
) VALUES
  (
    'course-webhook-timeout-120',
    'webhook.response.timeout_seconds',
    'webhooks',
    '{"seconds":120}',
    'Course evidence says webhook responses have a 120-second timeout.',
    80,
    '2026-04-29T00:00:00+00:00',
    'course',
    'docs/fixtures/sample-source.md#timeout-120',
    'claim-webhook-response-timeout',
    '2026-04-29T00:00:00+00:00',
    NULL,
    'claim-evidence-course-webhook-timeout-120',
    '001064#repo.make-knowledge.claim-conflict-arbitration'
  ),
  (
    'raw-spec-webhook-timeout-180',
    'webhook.response.timeout_seconds',
    'webhooks',
    '{"seconds":180}',
    'Raw-spec evidence says webhook responses have a 180-second timeout.',
    80,
    '2026-04-29T00:00:00+00:00',
    'raw_spec',
    'temp/raw-specs-json/webhooks/current.json#timeout-180',
    NULL,
    '2026-04-29T00:00:00+00:00',
    NULL,
    'claim-evidence-raw-spec-webhook-timeout-180',
    '001064#repo.make-knowledge.claim-conflict-arbitration'
  );
""".lstrip(),
        encoding="utf-8",
    )
