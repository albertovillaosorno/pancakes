# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for promoted Make linter observability and release-governance.

rules.

Boundary contract:
- Owns: focused release-governance fixtures promoted from the Make linter intake
  queue.
- Must not: infer live ownership, release approval, incident response, or
monitoring
  systems from blueprint silence.
- Allows: synthetic AST fixtures, explicit governance-profile metadata, promoted
  knowledge facts, and exact finding assertions.
- Split when: release metadata, notification governance, or incident readiness
need
  independent validator slices.
- Merge when: the main blueprint validation contract owns these exact fixtures.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from blueprints.ast import parse_make_ast_json_text
from blueprints.validation import validate_blueprint
from catalog import catalog_snapshot_from_json
from catalog.json_payloads import normalize_json_object
from catalog.knowledge import KnowledgeRuleFact, KnowledgeStoreQuery

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from collections.abc import Mapping

    from blueprints.validation import BlueprintValidationReport
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
CLIENT_PATH_TOKENS = ("\\", "/", "src/", "tests/", "Refactor", "C:")


def test_governed_scenario_requires_release_metadata_evidence() -> None:
    """Governed production scenarios warn when release metadata evidence is.

    absent.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "governed-release-missing-metadata",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhooks:CustomWebhook",
                            "parameters": {"name": "orders-api"},
                        }
                    ],
                    "metadata": {
                        "governance": {
                            "profile": "tier1 critical production release",
                        },
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=observability_release_governance_knowledge_query(),
    )

    codes = report.codes()

    for code in (
        "scenario.owner_missing",
        "scenario.change_reason_missing",
        "scenario.rollback_plan_missing",
        "scenario.incident_note_missing",
    ):
        assert code in codes, (
            f"Governance metadata warning {code!r} did not run: {codes}"
        )
    governance_findings = tuple(
        finding
        for finding in report.findings
        if finding.code.startswith("scenario.")
    )
    assert not (
        any(finding.severity != "warning" for finding in governance_findings)
    ), f"Governance metadata findings should warn: {governance_findings}"
    assert_client_messages_are_path_safe(report)


def test_governed_scenario_accepts_release_metadata_evidence() -> None:
    """Governed production scenarios stay quiet when release evidence is.

    visible.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "governed-release-with-metadata",
                    "flow": [
                        {
                            "id": 1,
                            "module": "webhooks:CustomWebhook",
                            "parameters": {"name": "orders-api"},
                        }
                    ],
                    "metadata": {
                        "governance": {
                            "profile": "tier1 critical production release",
                            "owner": "payments-platform",
                            "oncall": "primary-oncall",
                            "changeReason": (
                                "CHG-1234 adds retry classification"
                            ),
                            "rollbackPlan": (
                                "Restore previous blueprint hash abc123"
                            ),
                            "incidentNotes": (
                                "Runbook PB-42 covers pager severity routing"
                            ),
                        },
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=observability_release_governance_knowledge_query(),
    )

    governance_codes = tuple(
        code for code in report.codes() if code.startswith("scenario.")
    )

    assert not (governance_codes), (
        f"Governance evidence still produced scenario warnings: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_governed_production_scenario_warns_on_debug_markers() -> None:
    """Production-profiled scenarios warn when debug or test-channel markers.

    remain.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "governed-release-with-debug-marker",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:Logger",
                            "label": "Debug log",
                            "parameters": {
                                "level": "debug",
                                "message": "{{1.body}}",
                            },
                        }
                    ],
                    "metadata": {
                        "governance": {
                            "profile": "production release",
                            "owner": "payments-platform",
                            "changeReason": (
                                "CHG-1234 validates production cleanup"
                            ),
                            "rollbackPlan": (
                                "Restore previous blueprint hash abc123"
                            ),
                        },
                        "schedule": {"id": "schedule:daily"},
                    },
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=observability_release_governance_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "scenario.production_debug_marker"
    )

    assert findings, (
        f"Production debug-marker warning did not run: {report.codes()}"
    )
    assert not (any(finding.severity != "warning" for finding in findings)), (
        f"Production debug-marker findings should warn: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_non_governed_scenario_does_not_require_release_metadata() -> None:
    """Release-governance rules stay inactive without explicit governance.

    profile evidence.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "local-debug-utility",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:Logger",
                            "label": "Debug log",
                            "parameters": {
                                "level": "debug",
                                "message": "{{1.body}}",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=observability_release_governance_knowledge_query(),
    )

    governance_codes = tuple(
        code for code in report.codes() if code.startswith("scenario.")
    )

    assert not (governance_codes), (
        f"Non-governed blueprint produced governance warnings: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def observability_release_governance_knowledge_query() -> KnowledgeStoreQuery:
    """Return promoted observability/release governance facts for focused.

    fixtures.
    """
    return KnowledgeStoreQuery(
        fingerprint="knowledge:observability-release-governance",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="linter-0021-scenario-owner-missing",
                domain="release_governance",
                rule_code="scenario.owner_missing",
                severity="warning",
                description=(
                    "Governed production scenarios should declare owner"
                    "evidence."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
            KnowledgeRuleFact(
                rule_id="linter-0021-scenario-change-reason-missing",
                domain="release_governance",
                rule_code="scenario.change_reason_missing",
                severity="warning",
                description=(
                    "Governed production scenarios should declare change reason"
                    "evidence."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
            KnowledgeRuleFact(
                rule_id="linter-0021-scenario-rollback-plan-missing",
                domain="release_governance",
                rule_code="scenario.rollback_plan_missing",
                severity="warning",
                description=(
                    "Governed production scenarios should declare rollback"
                    "evidence."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
            KnowledgeRuleFact(
                rule_id="linter-0021-scenario-incident-note-missing",
                domain="release_governance",
                rule_code="scenario.incident_note_missing",
                severity="warning",
                description=(
                    "Critical governed scenarios should declare incident"
                    "evidence."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
            KnowledgeRuleFact(
                rule_id="linter-0021-scenario-production-debug-marker",
                domain="release_governance",
                rule_code="scenario.production_debug_marker",
                severity="warning",
                description=(
                    "Governed production scenarios should not retain debug"
                    "markers."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
        ),
        optimizer_hints=(),
    )


def load_catalog_fixture() -> CatalogSnapshot:
    """Load the sample catalog fixture.

    Returns:
        The loaded value.
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


def assert_client_messages_are_path_safe(
    report: BlueprintValidationReport,
) -> None:
    """Fail if any public validation message leaks repository path details."""
    for finding in report.findings:
        leaked_tokens = [
            token
            for token in CLIENT_PATH_TOKENS
            if token in finding.client_message
        ]
        assert not (leaked_tokens), (
            f"Client message leaked path tokens {leaked_tokens}: {finding}"
        )
