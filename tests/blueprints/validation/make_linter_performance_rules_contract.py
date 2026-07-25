# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for promoted Make linter performance rules.

Boundary contract:
- Owns: focused performance-rule fixtures promoted from the Make linter intake
  queue.
- Must not: estimate live traffic, provider pricing, or exact operation savings.
- Allows: synthetic AST fixtures, promoted knowledge facts, and exact finding
  assertions for local cost-proxy evidence.
- Split when: performance rules need independent subfamilies for iterator,
  aggregator, fan-out, or payload growth behavior.
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
CLIENT_PATH_TOKENS = (
    "\\",
    "/",
    "src/",
    "tests/",
    "Refactor",
    "C:",
)


def test_iterator_expansion_requires_item_limit_evidence() -> None:
    """Iterator expansion warns without item-limit evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "iterator-missing-item-limit",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:Iterator",
                            "parameters": {"array": "{{1.items}}"},
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=performance_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "iterator.item_limit_missing"
    )

    assert findings, (
        f"Iterator item-limit warning did not run: {report.codes()}"
    )
    assert not (any(finding.severity != "warning" for finding in findings)), (
        f"Iterator item-limit findings should warn: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_iterator_expansion_accepts_item_limit_evidence() -> None:
    """Iterator expansion stays quiet when local item-limit evidence exists."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "iterator-with-item-limit",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:Iterator",
                            "parameters": {
                                "array": "{{1.items}}",
                                "maxItems": 250,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=performance_knowledge_query(),
    )

    assert "iterator.item_limit_missing" not in report.codes(), (
        "Iterator item-limit evidence still produced warnings: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_aggregator_consumption_requires_bundle_limit_evidence() -> None:
    """Aggregator consumption warns without bundle-limit evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "aggregator-missing-bundle-limit",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:TextAggregator",
                            "parameters": {
                                "sourceModule": "2",
                                "rowSeparator": "\n",
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=performance_knowledge_query(),
    )

    findings = tuple(
        finding
        for finding in report.findings
        if finding.code == "aggregator.bundle_limit_missing"
    )

    assert findings, (
        f"Aggregator bundle-limit warning did not run: {report.codes()}"
    )
    assert not (any(finding.severity != "warning" for finding in findings)), (
        f"Aggregator bundle-limit findings should warn: {findings}"
    )
    assert_client_messages_are_path_safe(report)


def test_aggregator_consumption_accepts_bundle_limit_evidence() -> None:
    """Aggregator consumption stays quiet with bundle-limit evidence."""
    report = validate_blueprint(
        root=parse_make_ast_json_text(
            json.dumps(
                {
                    "name": "aggregator-with-bundle-limit",
                    "flow": [
                        {
                            "id": 1,
                            "module": "tools:TextAggregator",
                            "parameters": {
                                "sourceModule": "2",
                                "rowSeparator": "\n",
                                "maxBundles": 250,
                            },
                        }
                    ],
                    "metadata": {"schedule": {"id": "schedule:daily"}},
                }
            )
        ),
        catalog=load_catalog_fixture(),
        knowledge=performance_knowledge_query(),
    )

    assert "aggregator.bundle_limit_missing" not in report.codes(), (
        "Aggregator bundle-limit evidence still produced warnings: "
        f"{report.findings}"
    )
    assert_client_messages_are_path_safe(report)


def performance_knowledge_query() -> KnowledgeStoreQuery:
    """Return promoted performance facts for focused linter fixtures."""
    return KnowledgeStoreQuery(
        fingerprint="knowledge:performance-memory-cost",
        aliases=(),
        rule_facts=(
            KnowledgeRuleFact(
                rule_id="linter-0018-iterator-item-limit-missing",
                domain="operation_volume",
                rule_code="iterator.item_limit_missing",
                severity="warning",
                description=(
                    "Iterator expansion should declare item-limit evidence."
                ),
                adr_anchor="001079#repo.make-linter.rule-intake-manual-gate",
            ),
            KnowledgeRuleFact(
                rule_id="linter-0018-aggregator-bundle-limit-missing",
                domain="operation_volume",
                rule_code="aggregator.bundle_limit_missing",
                severity="warning",
                description=(
                    "Aggregator consumption should declare "
                    "bundle-limit evidence."
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
