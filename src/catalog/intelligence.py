# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001042#repo.make-catalog.schema-policy
# - 001048#repo.mapping-expression-intelligence.promoted-rules
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Catalog intelligence derived from retained Make raw-spec fields.

Boundary contract:
- Owns: deterministic planning hints inferred from catalog module fields.
- Must not: call AI providers, rank fallback candidates, mutate catalogs, or do
IO.
- Allows: conservative provider, option source, failure-mode, and cost hints.
- Split when: inference needs model calls, learning state, or workflow planning.
- Merge when: another module infers the same catalog intelligence hints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from catalog.models import CatalogField, CatalogModule, CatalogSnapshot

AI_PROVIDER_CANONICAL_NAMES: Final[dict[str, str]] = {
    "openai-gpt-3": "OpenAI ",
    "azure-openai": "OpenAI ",
    "anthropic-claude": "Anthropic ",
    "gemini-ai": "Gemini ",
    "google-vertex-ai": "Gemini ",
    "groq": "Groq ",
    "mistral-ai": "Mistral ",
    "cohere": "Cohere ",
    "amazon-bedrock": "Amazon Bedrock",
}


class CatalogModuleIntelligence(NamedTuple):
    """Derived planning hints for one catalog module."""

    module_id: str
    account_types: tuple[str, ...]
    option_sources: tuple[str, ...]
    ai_provider_names: tuple[str, ...]
    failure_modes: tuple[str, ...]
    supports_agent: bool
    credit_cost: int | None


def build_catalog_intelligence_profile(
    snapshot: CatalogSnapshot,
) -> tuple[CatalogModuleIntelligence, ...]:
    """Return the computed result for the caller."""
    profiles = [
        infer_module_intelligence(module)
        for app in snapshot.apps
        for version in app.versions
        for module in version.modules
    ]
    return tuple(sorted(profiles, key=lambda item: item.module_id))


def infer_module_intelligence(
    module: CatalogModule,
) -> CatalogModuleIntelligence:
    """Infer planning hints from one compiled catalog module.

    Returns:
        The result produced by infer planning hints from one compiled catalog
        module.
    """
    fields = (
        *module.parameters,
        *module.expect_schema,
        *module.interface_schema,
    )
    account_types = _account_types(fields)
    option_sources = _option_sources(fields)
    providers = _ai_provider_names(
        account_types=account_types,
        identity=(
            f"{module.app_slug} {module.display_name} {module.internal_name}"
        ),
    )
    supports_agent = module.module_kind == "agent" or bool(providers)
    return CatalogModuleIntelligence(
        module_id=module.module_id,
        account_types=tuple(sorted(account_types)),
        option_sources=tuple(sorted(option_sources)),
        ai_provider_names=tuple(sorted(providers)),
        failure_modes=_failure_modes(
            module=module, supports_agent=supports_agent
        ),
        supports_agent=supports_agent,
        credit_cost=_credit_cost(module),
    )


def _account_types(fields: tuple[CatalogField, ...]) -> set[str]:
    """Return account identifiers declared by field types."""
    accounts: set[str] = set()
    for field in fields:
        if field.field_type is None or not field.field_type.startswith(
            "account:"
        ):
            continue
        raw_values = field.field_type.removeprefix("account:")
        accounts.update(
            item.strip() for item in raw_values.split(",") if item.strip()
        )
    return accounts


def _option_sources(fields: tuple[CatalogField, ...]) -> set[str]:
    """Return option RPC sources declared by field dependencies."""
    return {
        dependency
        for field in fields
        for dependency in field.rpc_dependencies
        if dependency.startswith("rpc://")
    }


def _ai_provider_names(*, account_types: set[str], identity: str) -> set[str]:
    """Infer canonical AI provider names from account types and module identity.

    Returns:
        The inferred canonical AI provider names.
    """
    providers: set[str] = set()
    for account_type in account_types:
        canonical = AI_PROVIDER_CANONICAL_NAMES.get(account_type)
        if canonical is not None:
            providers.add(canonical)
        providers.update(_provider_tokens(account_type))
    providers.update(_provider_tokens(identity))
    return providers


def _provider_tokens(value: str) -> set[str]:
    """Return provider labels inferred from a text surface."""
    lowered = value.casefold()
    providers: set[str] = set()
    if "openai" in lowered:
        providers.add("OpenAI")
    if "anthropic" in lowered:
        providers.add("Anthropic")
    if "gemini" in lowered or "vertex" in lowered:
        providers.add("Gemini")
    if "groq" in lowered:
        providers.add("Groq")
    if "mistral" in lowered:
        providers.add("Mistral")
    return providers


def _failure_modes(
    *, module: CatalogModule, supports_agent: bool
) -> tuple[str, ...]:
    """Return conservative failure-mode hints for one module."""
    modes: set[str] = set()
    if module.deprecated:
        modes.add("deprecated")
    if supports_agent:
        modes.add("provider_unavailable")
        modes.add("timeout")
    if any(field.required for field in module.parameters):
        modes.add("missing_required_parameter")
    return tuple(sorted(modes))


def _credit_cost(module: CatalogModule) -> int | None:
    """Return positive operation cost when the compiled catalog retains it."""
    del module
    return None
