# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contracts for contextual catalog graph candidate ranking.

Boundary contract:
- Owns: workflow-intent retrieval ranking for app/capability/edge/
  provenance context.
- Must not: call providers, author catalog answers, or inspect live
  Make.com state.
- Allows: synthetic catalog snapshots and deterministic benchmark query
  assertions.
- Split when: graph query service owns contextual edge ranking directly.
- Merge when: fallback scoring tests own the same query-intent ranking contract.
"""

from __future__ import annotations

import pytest
from catalog.fallback.query import retrieve_catalog_modules
from catalog.fallback.scoring import (
    contextual_workflow_score_boost,
    provenance_score_boost,
    query_app_intents,
)
from catalog.models import (
    CatalogApp,
    CatalogAppVersion,
    CatalogModule,
    CatalogSnapshot,
)

BENCHMARK_QUERIES = [
    ("connect Slack to Gmail", ("slack", "google-email")),
    ("sync Google Sheets rows to Slack", ("google-sheets", "slack")),
    ("create Salesforce lead from Gmail", ("salesforce", "google-email")),
    ("send HubSpot contact update to Slack", ("hubspot", "slack")),
    ("append Airtable record from Gmail", ("airtable", "google-email")),
    ("publish Notion page to Slack", ("notion", "slack")),
    ("create Stripe payment receipt email", ("stripe", "google-email")),
    ("send Shopify order to Google Sheets", ("shopify", "google-sheets")),
    ("add Mailchimp subscriber from Gmail", ("mailchimp", "google-email")),
    ("notify Slack when Google Sheets row updates", ("slack", "google-sheets")),
]


@pytest.mark.parametrize(("query_text", "expected_apps"), BENCHMARK_QUERIES)
def test_contextual_queries_prioritize_requested_apps(
    query_text: str,
    expected_apps: tuple[str, str],
) -> None:
    """Ten workflow queries rank requested context above generic edges."""
    report = retrieve_catalog_modules(
        snapshot=_benchmark_snapshot(),
        query_text=query_text,
        limit=6,
        source_label="knowledge_db",
    )
    ranked_apps = tuple(candidate.app_slug for candidate in report.candidates)
    generic_index = _index_or_none(ranked_apps, "directory")

    assert expected_apps[0] in ranked_apps[:3], (
        f"{query_text!r} did not prioritize {expected_apps[0]}: {ranked_apps}"
    )
    assert expected_apps[1] in ranked_apps[:4], (
        f"{query_text!r} did not prioritize {expected_apps[1]}: {ranked_apps}"
    )
    assert generic_index is None or generic_index > max(
        ranked_apps.index(expected_apps[0]),
        ranked_apps.index(expected_apps[1]),
    ), f"{query_text!r} ranked generic graph edge too high: {ranked_apps}"
    assert any(
        "intent:query-app" in reason
        for candidate in report.candidates
        for reason in candidate.match_reasons
    ), (
        f"{query_text!r} did not record query-app intent reasons: "
        f"{report.candidates}"
    )


def test_connect_slack_to_gmail_demotes_adds_member_to_generic_edge() -> None:
    """The Slack/Gmail workflow outranks an unrelated generic edge."""
    report = retrieve_catalog_modules(
        snapshot=_benchmark_snapshot(),
        query_text="connect Slack to Gmail",
        limit=8,
        source_label="knowledge_db",
    )
    ranked_apps = tuple(candidate.app_slug for candidate in report.candidates)

    assert "slack" in ranked_apps
    assert "google-email" in ranked_apps
    if "directory" in ranked_apps:
        assert ranked_apps.index("slack") < ranked_apps.index("directory")
        assert ranked_apps.index("google-email") < ranked_apps.index(
            "directory"
        )


def test_contextual_ranking_uses_context_signals() -> None:
    """Scoring exposes each contextual ranking signal."""
    snapshot = _benchmark_snapshot()
    apps_by_slug = {app.app_slug: app for app in snapshot.apps}
    slack_app = apps_by_slug["slack"]
    directory_app = apps_by_slug["directory"]
    query_terms = frozenset(("connect", "slack", "gmail"))

    boost, reason = contextual_workflow_score_boost(
        app=slack_app,
        module=slack_app.versions[0].modules[0],
        query_terms=query_terms,
    )
    generic_boost, generic_reason = contextual_workflow_score_boost(
        app=directory_app,
        module=directory_app.versions[0].modules[0],
        query_terms=query_terms,
    )
    provenance_boost, provenance_reason = provenance_score_boost(
        source_label="knowledge_db"
    )

    assert query_app_intents(query_terms) == frozenset(
        ("google-email", "slack")
    )
    assert boost > 0
    assert reason is not None and "intent:query-app" in reason
    assert generic_boost < 0
    assert (
        generic_reason is not None and "edge:generic-demoted" in generic_reason
    )
    assert provenance_boost > 0
    assert provenance_reason == "provenance:knowledge_db"


def _benchmark_snapshot() -> CatalogSnapshot:
    apps = (
        _app("slack", "Slack", ("Create message", "Post to channel")),
        _app("google-email", "Google Email", ("Send email", "Watch emails")),
        _app("google-sheets", "Google Sheets", ("Update row", "Search rows")),
        _app("salesforce", "Salesforce", ("Create lead",)),
        _app("hubspot", "HubSpot", ("Update contact",)),
        _app("airtable", "Airtable", ("Create record",)),
        _app("notion", "Notion", ("Create page",)),
        _app("stripe", "Stripe", ("Create payment receipt",)),
        _app("shopify", "Shopify", ("Create order",)),
        _app("mailchimp", "Mailchimp", ("Add subscriber",)),
        _app("directory", "Generic graph edges", ("Adds member to group",)),
    )
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc="2026-05-26T00:00:00+00:00",
        raw_spec_manifest_sha256="synthetic-context-ranking",
        apps=apps,
        fingerprint="synthetic-context-ranking",
    )


def _app(
    app_slug: str, app_label: str, display_names: tuple[str, ...]
) -> CatalogApp:
    modules = tuple(
        _module(app_slug=app_slug, display_name=display_name, index=index)
        for index, display_name in enumerate(display_names, start=1)
    )
    app_version = CatalogAppVersion(
        app_version_id=f"app-version:{app_slug}:1.0",
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        version="1.0",
        latest=True,
        manifest_version=1,
        modules=modules,
        raw_spec_sha256=f"raw-spec:{app_slug}",
        fingerprint=f"app-version:{app_slug}:1.0",
    )
    return CatalogApp(
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        label=app_label,
        external_id=app_slug,
        deprecated=False,
        versions=(app_version,),
        fingerprint=f"app:{app_slug}",
    )


def _module(app_slug: str, display_name: str, index: int) -> CatalogModule:
    internal_name = display_name.replace(" ", "")
    return CatalogModule(
        module_id=f"module:{app_slug}:1.0:action:{internal_name}",
        app_version_id=f"app-version:{app_slug}:1.0",
        app_slug=app_slug,
        app_version="1.0",
        module_kind="action",
        internal_name=internal_name,
        display_name=display_name,
        external_id=f"{app_slug}:{index}",
        deprecated=False,
        parameters=(),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256=f"raw-spec:{app_slug}",
        fingerprint=f"module:{app_slug}:{index}",
    )


def _index_or_none(values: tuple[str, ...], item: str) -> int | None:
    try:
        return values.index(item)
    except ValueError:
        return None
