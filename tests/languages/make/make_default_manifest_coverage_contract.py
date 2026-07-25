# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for the Make default-manifest coverage ledger.

Boundary contract:
- Owns: deterministic validation for operator-reviewed Make built-in/default
exports.
- Must not: call Make.com, read browser cookies, or depend on generated SQLite
artifacts.
- Allows: local JSON evidence checks and identity-only catalog fallback
assertions.
- Split when: the ledger becomes a generated knowledge-store seed.
- Merge when: raw-spec refresh contracts own this exact coverage source.
"""

from __future__ import annotations

from languages.make.default_manifest_coverage import (
    MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SHA256,
    MAKE_DEFAULT_MANIFEST_EXPECTED_MODULE_COUNT,
    MAKE_DEFAULT_MANIFEST_EXPECTED_SOURCE_NODE_COUNT,
    load_make_default_manifest_coverage_payload,
    make_default_manifest_coverage_fact_for_token,
    make_default_manifest_coverage_facts,
)

from tests.support.paths import repo_root

REPO_ROOT = repo_root()
REGEXP_PARSER_MODULE_REF = "regexp:Parser"


def test_make_default_manifest_coverage_loader_validates_operator_sources() -> (
    None
):
    """The default manifest ledger records every embedded Make source export."""
    payload = load_make_default_manifest_coverage_payload(REPO_ROOT)
    coverage = payload["coverage"]
    assert isinstance(coverage, dict), f"Coverage must be an object: {payload}"

    assert (
        coverage["source_node_count"]
        == MAKE_DEFAULT_MANIFEST_EXPECTED_SOURCE_NODE_COUNT
    )
    assert (
        coverage["unique_module_count"]
        == MAKE_DEFAULT_MANIFEST_EXPECTED_MODULE_COUNT
    )
    assert (
        coverage["raw_spec_backed_count"]
        == MAKE_DEFAULT_MANIFEST_EXPECTED_MODULE_COUNT
    )
    assert (
        payload["source_file_sha256"]
        == MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SHA256
    )
    assert payload["source_files"] == [
        "make_built_in_1.json",
        "make_built_in_2.json",
        "make_built_in_ai.json",
    ]


def test_make_default_manifest_coverage_facts_ecd11aaa() -> None:
    """Default manifest facts include parser, AI, and platform utility.

    families.
    """
    facts = make_default_manifest_coverage_facts(REPO_ROOT)
    module_refs = {fact.module_ref for fact in facts}

    assert len(facts) == MAKE_DEFAULT_MANIFEST_EXPECTED_MODULE_COUNT
    assert {
        "regexp:Parser",
        "ai-tools:Ask",
        "ai-local-agent:RunLocalAIAgent",
        "json:ParseJSON",
        "xml:ParseXML",
        "csv:ParseCSV",
        "archive:PackAggregator",
        "crypto:AESEncrypt",
        "image:Convert",
        "email:ActionSendEmail",
        "rss:TriggerNewArticle",
        "http:MakeRequest",
    } <= module_refs


def test_make_default_manifest_coverage_token_lookup_is_identity_only() -> None:
    """Token lookup returns module identity without inventing field-level.

    rules.
    """
    fact = make_default_manifest_coverage_fact_for_token(
        repo_root=REPO_ROOT,
        module_token=REGEXP_PARSER_MODULE_REF,
    )

    assert fact is not None
    assert fact.module.module_id == "module:regexp:1.10.5:transformer:Parser"
    assert fact.module.display_name == "Match pattern"
    assert fact.source_files == ("make_built_in_1.json",)
