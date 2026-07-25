# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001042#repo.make-catalog.catalog-only-fallback-utility
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Catalog-only candidate scoring.

Boundary contract:
- Owns: deterministic score weights and match reasons for catalog candidates.
- Must not: traverse snapshots, choose query limits, validate aliases, or do IO.
- Allows: term extraction from module fields and RPC dependency metadata.
- Split when: scoring needs learned ranking, embeddings, or external evidence.
- Merge when: another scorer implements the same catalog-only weight policy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from languages.make.priority_modules import priority_make_app_search_terms

from catalog.fallback.results import (
    FALLBACK_ADVISORY_CONFIDENCE_WEIGHT,
    FALLBACK_RESOLUTION_ADVISORY,
    SOURCE_LABEL_FIXTURE_SNAPSHOT,
    CatalogModuleCandidate,
    catalog_source_rank,
)
from catalog.fallback.text import flatten_tokens, normalize_text

if TYPE_CHECKING:
    from catalog.models import CatalogApp, CatalogField, CatalogModule

GENERIC_WEBHOOK_QUERY_TERMS = frozenset(
    ("webhook", "webhooks", "customwebhook")
)
WEBHOOK_RESPONSE_QUERY_TERMS = frozenset(("response", "respond", "reply"))
GATEWAY_CUSTOM_WEBHOOK_KEY = "gateway:customwebhook"
GATEWAY_WEBHOOK_RESPONSE_KEYS = frozenset(
    ("gateway:webhookresponse", "webhooks:webhookresponse")
)
LOW_SIGNAL_QUERY_TERMS = frozenset(
    ("company", "data", "google", "lead", "leads", "live", "source")
)
IGNORED_QUERY_TERMS = frozenset(
    (
        "a ",
        "an ",
        "and ",
        "as ",
        "by ",
        "for ",
        "from ",
        "not ",
        "of ",
        "or ",
        "present ",
        "the ",
        "then ",
        "to ",
        "when ",
        "with ",
        "without",
    )
)
DATASTORE_INTENT_DESTINATION_TERMS = frozenset(
    ("crm", "destination", "destinations")
)
DATASTORE_INTENT_ROUTE_TERMS = frozenset(("incomplete", "qualified"))
EMAIL_REQUEST_TERMS = frozenset(("email", "emails", "gmail", "mail"))
EMAIL_CANDIDATE_TERMS = frozenset(("email", "emails", "gmail", "mail", "smtp"))
EMAIL_SHORT_QUERY_TOKEN_LIMIT = 3
EMAIL_WORKFLOW_TERMS = frozenset(
    (
        "attachment ",
        "attachments ",
        "draft ",
        "gmail ",
        "imap ",
        "inbound ",
        "mail ",
        "mailhook ",
        "notify ",
        "outbound ",
        "outlook ",
        "receipt ",
        "reply ",
        "send ",
        "sending ",
        "smtp ",
        "watch",
    )
)
CORE_EMAIL_APP_RANKS = {
    "google-email": 700,
    "microsoft-email": 650,
    "gateway": 600,
}
GOOGLE_SHEETS_TERMS = frozenset(
    ("google-sheets", "sheet", "sheets", "spreadsheet")
)
GOOGLE_SHEETS_ROW_TERMS = frozenset(("row", "rows"))
GOOGLE_SHEETS_UPDATE_TERMS = frozenset(("update", "upsert", "edit"))
GOOGLE_SHEETS_LOOKUP_TERMS = frozenset(("find", "filter", "lookup", "search"))
MIN_CONTEXTUAL_APP_INTENT_COUNT = 2
WORKFLOW_CONTEXT_TERMS = frozenset(
    (
        "append ",
        "connect ",
        "create ",
        "email ",
        "from ",
        "notify ",
        "post ",
        "publish ",
        "receipt ",
        "route ",
        "send ",
        "sync ",
        "to ",
        "update ",
        "when",
    )
)
GENERIC_GRAPH_EDGE_TERMS = frozenset(
    (
        "adds ",
        "belongs ",
        "edge ",
        "generic ",
        "group ",
        "member ",
        "relationship",
    )
)
QUERY_APP_INTENT_ALIASES = {
    "airtable": frozenset(("airtable",)),
    "google-email": frozenset(("gmail", "google", "email", "mail")),
    "google-sheets": frozenset(("google", "sheet", "sheets", "spreadsheet")),
    "hubspot": frozenset(("hubspot",)),
    "mailchimp": frozenset(("mailchimp",)),
    "notion": frozenset(("notion",)),
    "salesforce": frozenset(("salesforce",)),
    "shopify": frozenset(("shopify",)),
    "slack": frozenset(("slack",)),
    "stripe": frozenset(("stripe",)),
}


def score_module(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
    source_label: str = SOURCE_LABEL_FIXTURE_SNAPSHOT,
) -> CatalogModuleCandidate:
    """Score one module against normalized query tokens.

    Returns:
        The result produced by score one module against normalized query tokens.
    """
    score, reasons = _term_match_score(
        app=app, module=module, query_terms=query_terms
    )
    for boost, reason in _score_boosts(
        app=app,
        module=module,
        query_terms=query_terms,
        source_label=source_label,
    ):
        if not boost:
            continue
        score += boost
        if reason:
            reasons.append(reason)
    return CatalogModuleCandidate(
        module_id=module.module_id,
        app_slug=app.app_slug,
        app_label=app.label,
        app_version=module.app_version,
        module_kind=module.module_kind,
        internal_name=module.internal_name,
        display_name=module.display_name,
        deprecated=module.deprecated,
        score=score,
        match_reasons=tuple(reasons),
        source_label=source_label,
        source_rank=catalog_source_rank(source_label),
        resolution_kind=FALLBACK_RESOLUTION_ADVISORY,
        confidence_weight=FALLBACK_ADVISORY_CONFIDENCE_WEIGHT,
    )


def _term_match_score(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
) -> tuple[int, list[str]]:
    """Return direct query-term score and reasons for one module candidate."""
    primary_terms = module_primary_terms(app=app, module=module)
    field_terms = module_field_terms(module)
    primary_tokens = flatten_tokens(primary_terms)
    field_tokens = flatten_tokens(field_terms)
    searchable_terms = primary_terms | field_terms
    score = 0
    reasons: list[str] = []
    for term in sorted(query_terms - IGNORED_QUERY_TERMS):
        exact_weight, token_weight, field_weight, contains_weight = (
            _term_weights(term)
        )
        if term in primary_terms:
            score += exact_weight
            reasons.append(f"exact:{term}")
        elif term in primary_tokens:
            score += token_weight
            reasons.append(f"token:{term}")
        elif term in field_tokens:
            score += field_weight
            reasons.append(f"field:{term}")
        elif any(term in searchable for searchable in searchable_terms):
            score += contains_weight
            reasons.append(f"contains:{term}")
    return (score, reasons)


def _score_boosts(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
    source_label: str,
) -> tuple[tuple[int, str], ...]:
    """Return deterministic intent and provider-specific score boosts."""
    datastore_boost, datastore_reason = datastore_score_boost(
        app=app,
        module=module,
        query_terms=query_terms,
    )
    webhook_boost = webhook_score_boost(module=module, query_terms=query_terms)
    contextual_boost, contextual_reason = contextual_workflow_score_boost(
        app=app,
        module=module,
        query_terms=query_terms,
    )
    provenance_boost, provenance_reason = provenance_score_boost(
        source_label=source_label
    )
    return (
        (datastore_boost, datastore_reason or ""),
        (
            webhook_boost,
            "webhook:generic-receiver"
            if webhook_boost > 0
            else "webhook:management-module",
        ),
        (
            email_score_boost(app=app, module=module, query_terms=query_terms),
            "intent:core-email-family",
        ),
        (
            google_sheets_score_boost(
                app=app, module=module, query_terms=query_terms
            ),
            "intent:google-sheets-row-chain",
        ),
        (contextual_boost, contextual_reason or ""),
        (provenance_boost, provenance_reason or ""),
    )


def _term_weights(term: str) -> tuple[int, int, int, int]:
    """Return deterministic weights for one query term."""
    if term in LOW_SIGNAL_QUERY_TERMS:
        return (8, 5, 3, 1)
    return (30, 20, 12, 6)


def webhook_score_boost(
    *, module: CatalogModule, query_terms: frozenset[str]
) -> int:
    """Prefer Make's generic webhook receiver for common webhook search text.

    Returns:
        The deterministic boost or penalty for webhook-related candidates.
    """
    if not query_terms.intersection(GENERIC_WEBHOOK_QUERY_TERMS):
        return 0
    module_key = f"{module.app_slug}:{module.internal_name}".casefold()
    if module_key == GATEWAY_CUSTOM_WEBHOOK_KEY:
        return 1000
    if (
        query_terms.intersection(WEBHOOK_RESPONSE_QUERY_TERMS)
        and module_key in GATEWAY_WEBHOOK_RESPONSE_KEYS
    ):
        return 900
    management_terms = tuple(
        term.casefold()
        for term in (
            "createWebhook ",
            "deleteWebhook ",
            "listWebhook ",
            "updateWebhook",
        )
    )
    if any(
        term in module.internal_name.casefold() for term in management_terms
    ):
        return -25
    return 0


def email_score_boost(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
) -> int:
    """Prefer core mail families when requirements ask for email workflow.

    semantics.

    Returns:
        The deterministic email-family score boost.
    """
    if not _email_intent_active(query_terms):
        return 0
    app_slug = app.app_slug.casefold()
    base_boost = CORE_EMAIL_APP_RANKS.get(app_slug, 0)
    if not base_boost:
        return 0
    module_text = flatten_tokens((module.internal_name, module.display_name))
    if app_slug == "gateway" and not {"mailhook", "mail", "hook"}.intersection(
        module_text
    ):
        return 0
    workflow_boost = 0
    if {"send", "sending", "receipt", "notify"}.intersection(query_terms) and {
        "send ",
        "email ",
        "message",
    }.intersection(module_text):
        workflow_boost += 90
    if {"attachment", "attachments"}.intersection(query_terms) and {
        "attachment ",
        "attachments ",
        "feedattachments ",
        "listattachments",
    }.intersection(module_text):
        workflow_boost += 90
    if {"inbound", "receive", "received", "watch"}.intersection(
        query_terms
    ) and {
        "watch ",
        "trigger ",
        "mailhook",
    }.intersection(module_text):
        workflow_boost += 80
    if {"smtp", "imap"}.intersection(query_terms) and {
        "smtp ",
        "imap",
    }.intersection(module_text):
        workflow_boost += 80
    return base_boost + workflow_boost


def google_sheets_score_boost(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
) -> int:
    """Prefer Google Sheets row lookup/update modules for row-update.

    requirements.

    Returns:
        The deterministic Google Sheets row-chain score boost.
    """
    if app.app_slug.casefold() != "google-sheets":
        return 0
    if not GOOGLE_SHEETS_TERMS.intersection(query_terms):
        return 0
    if not GOOGLE_SHEETS_ROW_TERMS.intersection(query_terms):
        return 0
    module_terms = flatten_tokens((module.internal_name, module.display_name))
    boost = 400
    if GOOGLE_SHEETS_UPDATE_TERMS.intersection(query_terms) and (
        {"update", "updaterow", "row"}.intersection(module_terms)
    ):
        boost += 500
    if GOOGLE_SHEETS_LOOKUP_TERMS.intersection(query_terms) and (
        {"filter", "search", "rows", "report"}.intersection(module_terms)
    ):
        boost += 450
    return boost


def contextual_workflow_score_boost(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
) -> tuple[int, str | None]:
    """Boost app-specific workflow candidates and demote unrelated generic.

    graph.

    edges.

    Returns:
        The contextual boost and optional reason label.
    """
    requested_apps = query_app_intents(query_terms)
    if not _workflow_context_active(
        query_terms=query_terms, requested_apps=requested_apps
    ):
        return (0, None)
    app_slug = app.app_slug.casefold()
    module_terms = module_primary_terms(
        app=app, module=module
    ) | module_field_terms(module)
    boost = 0
    reasons: list[str] = []
    if app_slug in requested_apps:
        boost += 850
        reasons.append("intent:query-app")
        if len(requested_apps) > 1:
            boost += 150
            reasons.append("intent:multi-app-workflow")
    capability_terms = query_terms.intersection(WORKFLOW_CONTEXT_TERMS)
    if capability_terms.intersection(module_terms):
        boost += 120
        reasons.append("intent:capability")
    if _generic_graph_edge_candidate(module) and app_slug not in requested_apps:
        boost -= 220
        reasons.append("edge:generic-demoted")
    if not reasons:
        return (0, None)
    return (boost, "+".join(reasons))


def query_app_intents(query_terms: frozenset[str]) -> frozenset[str]:
    """Return app slugs explicitly implied by one workflow query."""
    requested: set[str] = set()
    for app_slug, aliases in QUERY_APP_INTENT_ALIASES.items():
        if _query_terms_match_app_alias(
            query_terms=query_terms,
            app_slug=app_slug,
            aliases=aliases,
        ):
            requested.add(app_slug)
    return frozenset(requested)


def provenance_score_boost(*, source_label: str) -> tuple[int, str | None]:
    """Return a small provenance score boost for stronger catalog sources.

    Returns:
        The provenance boost and optional reason label.
    """
    source_rank = catalog_source_rank(source_label)
    if source_rank <= catalog_source_rank("raw_spec_manifest"):
        return (30, f"provenance:{source_label}")
    if source_rank <= catalog_source_rank("fallback_alias"):
        return (10, f"provenance:{source_label}")
    return (0, None)


def _workflow_context_active(
    *,
    query_terms: frozenset[str],
    requested_apps: frozenset[str],
) -> bool:
    if len(requested_apps) >= MIN_CONTEXTUAL_APP_INTENT_COUNT:
        return True
    return bool(
        requested_apps and query_terms.intersection(WORKFLOW_CONTEXT_TERMS)
    )


def _query_terms_match_app_alias(
    *,
    query_terms: frozenset[str],
    app_slug: str,
    aliases: frozenset[str],
) -> bool:
    if app_slug in query_terms:
        return True
    if app_slug == "google-email":
        return "gmail" in query_terms or {"google", "email"}.issubset(
            query_terms
        )
    if app_slug == "google-sheets":
        return bool({"sheets", "spreadsheet"}.intersection(query_terms)) or (
            {"google", "sheet"}.issubset(query_terms)
        )
    return bool(query_terms.intersection(aliases))


def _generic_graph_edge_candidate(module: CatalogModule) -> bool:
    module_terms = flatten_tokens(
        (module.module_id, module.internal_name, module.display_name)
    )
    return bool(GENERIC_GRAPH_EDGE_TERMS.intersection(module_terms))


def datastore_score_boost(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
) -> tuple[int, str | None]:
    """Prefer Make Data Store record writes when requirements indicate that.

    intent.

    Returns:
        The score boost and optional reason label.
    """
    if not datastore_intent_active(query_terms):
        return (0, None)
    if app.app_slug.casefold() == "datastore" and _module_is_add_record(module):
        return (1400, "intent:datastore-add-record")
    if app.app_slug.casefold() == "datastore":
        return (180, "intent:datastore-family")
    if _module_is_requested_companion_action(
        app=app, module=module, query_terms=query_terms
    ):
        return (0, None)
    if _module_is_native_planner_companion(app=app, module=module):
        return (0, None)
    return (-80, "intent:prefer-make-datastore")


def datastore_intent_active(query_terms: frozenset[str]) -> bool:
    """Return if the query is asking for a CRM-like Data Store destination."""
    has_datastore = "datastore" in query_terms or {"data", "store"}.issubset(
        query_terms
    )
    has_record_write = bool({"add", "record"}.intersection(query_terms)) or (
        "addrecord" in query_terms
    )
    has_destination = bool(
        DATASTORE_INTENT_DESTINATION_TERMS.intersection(query_terms)
    )
    has_route_context = bool(
        DATASTORE_INTENT_ROUTE_TERMS.intersection(query_terms)
    )
    has_lead_context = bool({"lead", "leads"}.intersection(query_terms))
    if has_datastore and (
        has_record_write or has_destination or has_route_context
    ):
        return True
    return has_destination and has_route_context and has_lead_context


def _email_intent_active(query_terms: frozenset[str]) -> bool:
    """Return whether email means mail workflow, not only a lookup key field."""
    if not EMAIL_REQUEST_TERMS.intersection(query_terms):
        return False
    if EMAIL_WORKFLOW_TERMS.intersection(query_terms):
        return True
    if query_terms <= EMAIL_REQUEST_TERMS:
        return True
    if "address" in query_terms and GOOGLE_SHEETS_TERMS.intersection(
        query_terms
    ):
        return False
    return len(query_terms) <= EMAIL_SHORT_QUERY_TOKEN_LIMIT


def _module_is_native_planner_companion(
    *, app: CatalogApp, module: CatalogModule
) -> bool:
    """Return if a non-datastore module can accompany a datastore workflow."""
    app_slug = app.app_slug.casefold()
    module_kind = module.module_kind.casefold()
    return module_kind in {
        "aggregator ",
        "router ",
        "transformer",
    } or app_slug in {"agent-ai", "ai-agent", "http"}


def _module_is_requested_companion_action(
    *,
    app: CatalogApp,
    module: CatalogModule,
    query_terms: frozenset[str],
) -> bool:
    """Return whether a provider action was explicitly requested with datastore.

    work.
    """
    app_slug = app.app_slug.casefold()
    if "slack" in query_terms and app_slug == "slack":
        return True
    if not EMAIL_REQUEST_TERMS.intersection(query_terms):
        return False
    module_terms = flatten_tokens(
        (
            app.app_slug,
            app.label,
            module.module_id,
            module.internal_name,
            module.display_name,
        )
    )
    return bool(EMAIL_CANDIDATE_TERMS.intersection(module_terms))


def _module_is_add_record(module: CatalogModule) -> bool:
    """Return whether one module represents the Data Store add-record writer."""
    internal_key = normalize_text(module.internal_name).replace(" ", "")
    if internal_key == "addrecord":
        return True
    display_tokens = flatten_tokens((module.display_name,))
    return {"add", "record"}.issubset(display_tokens)


def module_primary_terms(
    *, app: CatalogApp, module: CatalogModule
) -> frozenset[str]:
    """Return primary normalized terms for one module."""
    return frozenset(
        normalize_text(value)
        for value in (
            app.app_slug,
            app.label,
            *priority_make_app_search_terms(app.app_slug),
            module.module_id,
            module.external_id,
            module.module_kind,
            module.internal_name,
            module.display_name,
        )
        if value
    )


def module_field_terms(module: CatalogModule) -> frozenset[str]:
    """Return normalized field and dependency terms for one module."""
    raw_terms: list[str] = []
    for field in (
        *module.parameters,
        *module.expect_schema,
        *module.interface_schema,
    ):
        raw_terms.extend(field_terms(field))
    raw_terms.extend(module.rpc_dependencies)
    return frozenset(normalize_text(value) for value in raw_terms if value)


def field_terms(field: CatalogField) -> tuple[str, ...]:
    """Return raw searchable terms for one catalog field."""
    return (
        ".".join(field.path),
        field.label,
        field.field_type or "",
        field.external_id,
        *field.rpc_dependencies,
    )
