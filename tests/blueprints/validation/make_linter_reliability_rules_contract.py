# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for promoted Make linter reliability rules.

Boundary contract:
- Owns: focused reliability-rule fixtures promoted from the Make linter intake
  queue.
- Must not: call Make.com, infer live provider guarantees, or test unrelated
  validation families.
- Allows: synthetic AST fixtures, promoted knowledge facts, and exact finding
  assertions.
- Split when: reliability rules need independent subfamilies for state,
  concurrency, or retry behavior.
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


def test_datastore_ephemeral_state_requires_ttl_evidence() -> None:
    """Temporary datastore lock/session state warns when no TTL evidence is.

    visible.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "datastore-lock-missing-ttl",
                    "flow": [
                        {
                            "id": 1,
                            "module": "datastore:AddRecord",
                            "parameters": {
                                "key": "{{1.order_id}}",
                                "value": {
                                    "lockOwner": "{{execution.id}}",
                                    "state": "session lock",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=reliability_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_store.ttl_missing"
    )

    assert findings, f"Datastore TTL warning did not run: {report.codes()}"
    assert not (any(finding.severity != "warning" for finding in findings)), (
        f"Datastore TTL findings should warn: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_datastore_ephemeral_state_accepts_ttl_evidence() -> None:
    """Temporary datastore state stays quiet when TTL or expiry evidence.

    exists.
    """
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "datastore-lock-with-ttl",
                    "flow": [
                        {
                            "id": 1,
                            "module": "datastore:AddRecord",
                            "parameters": {
                                "key": "{{1.order_id}}",
                                "ttlSeconds": 900,
                                "value": {
                                    "lockOwner": "{{execution.id}}",
                                    "state": "session lock",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=reliability_knowledge_query(),
    )

    assert "data_store.ttl_missing" not in report.codes(), (
        f"Datastore TTL evidence still produced warnings: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_datastore_write_warns_on_secret_like_storage() -> None:
    """Datastore writes should not visibly persist secret-scoped values."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "datastore-secret-storage",
                    "flow": [
                        {
                            "id": 1,
                            "module": "datastore:AddRecord",
                            "parameters": {
                                "key": "{{1.account_id}}",
                                "value": {
                                    "apiToken": "{{1.auth.token}}",
                                    "owner": "{{1.owner}}",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=reliability_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "data_store.secret_storage"
    )

    assert findings, (
        f"Datastore secret storage warning did not run: {report.codes()}"
    )
    assert not (any(finding.severity != "warning" for finding in findings)), (
        f"Datastore secret storage findings should warn: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_datastore_write_allows_ordinary_record_values() -> None:
    """Ordinary datastore writes stay quiet for the secret-storage rule."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "datastore-ordinary-storage",
                    "flow": [
                        {
                            "id": 1,
                            "module": "datastore:AddRecord",
                            "parameters": {
                                "key": "{{1.account_id}}",
                                "value": {
                                    "owner": "{{1.owner}}",
                                    "status": "{{1.status}}",
                                },
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=reliability_knowledge_query(),
    )

    assert "data_store.secret_storage" not in report.codes(), (
        f"Ordinary datastore values produced a warning: {report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def reliability_knowledge_query() -> KnowledgeStoreQuery:
    """Return promoted reliability facts for focused linter fixtures."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:reliability-state",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="linter-0017-data-store-ttl-missing",
                domain="data_stores",
                rule_code="data_store.ttl_missing",
                severity="warning",
                description=(
                    "Temporary data-store state should declare TTL or cleanup "
                    "evidence."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
            KnowledgeRuleFact(
                rule_id="linter-0017-data-store-secret-storage",
                domain="data_stores",
                rule_code="data_store.secret_storage",
                severity="warning",
                description=(
                    "Data-store writes should not persist secret-scoped values."
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
