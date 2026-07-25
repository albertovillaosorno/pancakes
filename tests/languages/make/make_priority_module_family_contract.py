# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Priority Make module family coverage contracts.

Boundary contract:
- Owns: offline coverage checks for the operator-priority Make connector
families.
- Must not: call Make.com, open browsers, store credentials, or assert dynamic
  RPC semantics.
- Allows: local raw-spec manifest reads and private alias-registry checks.
- Split when: browser-confirmed dynamic RPC behavior gets its own generated
  evidence ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from languages.make.priority_modules import (
    iter_priority_make_module_families,
    priority_make_app_search_terms,
    priority_make_module_coverage,
)
from languages.make.raw_specs.paths import DEFAULT_RAW_SPEC_SQLITE_DATABASE
from languages.make.raw_specs.sqlite_store import load_sqlite_raw_spec_bundle

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from languages.make.priority_modules import (
        PriorityMakeModuleCoverage,
        PriorityMakeModuleFamily,
    )
    from languages.make.raw_specs.models import RawSpecManifest

ABSOLUTE_PRIORITY_LABELS = {
    "Airtable",
    "Discord",
    "Gmail",
    "Google Calendar",
    "Google Drive",
    "Google Sheets",
    "Make AI Agents",
    "Make AI Toolkit",
    "Make Code",
    "Notion",
    "OpenAI (ChatGPT, Sora, Whisper)",
    "Shopify",
    "Slack",
    "Stripe",
    "Telegram Bot",
    "Twilio",
}


def test_priority_module_family_registry_preserves_f75c73f3() -> None:
    """Priority connector names are private engine input."""
    families = iter_priority_make_module_families()
    by_label = _families_by_label(families)

    assert len(families) == 42
    assert {
        label
        for label, family in by_label.items()
        if family.priority == "absolute"
    } == (ABSOLUTE_PRIORITY_LABELS)
    assert by_label["Verified"].status == "catalog_badge"
    assert by_label["New"].status == "catalog_badge"
    assert by_label["Make AI Agents"].source_occurrences == 2
    assert by_label["Brevo"].app_slugs == ("sendinblue",)
    assert by_label["GoHighLevel"].app_slugs == ("highlevel",)
    assert by_label["Make Code"].app_slugs == ("code",)


def test_priority_module_families_are_backed_by_local_raw_specs() -> None:
    """Every priority connector family can be audited offline from raw-spec.

    evidence.
    """
    coverage = priority_make_module_coverage(_raw_spec_manifest())
    by_label = _coverage_by_label(coverage)
    module_families = tuple(
        row for row in coverage if row.status == "module_family"
    )

    assert all(
        row.coverage_status == "raw_spec_backed" for row in module_families
    ), f"Priority module families lost local raw-spec coverage: {coverage}"
    assert all(row.module_count > 0 for row in module_families), (
        f"Priority module family coverage lost module counts: {coverage}"
    )
    assert by_label["Verified"].coverage_status == "not_a_module_family"
    assert by_label["New"].coverage_status == "not_a_module_family"
    assert by_label["OpenAI (ChatGPT, Sora, Whisper)"].latest_versions == (
        "openai-gpt-3@1.43.6",
    )
    assert by_label["Make AI Toolkit"].module_kinds == ("action",)
    assert by_label["Telegram Bot"].module_count >= 30
    assert by_label["HubSpot CRM"].module_count >= 100


def test_priority_module_aliases_recover_public_names_for_legacy_slugs() -> (
    None
):
    """Planner search can bridge Make public names to older raw-spec app.

    slugs.
    """
    assert "Brevo" in priority_make_app_search_terms("sendinblue")
    assert "GoHighLevel" in priority_make_app_search_terms("highlevel")
    assert "Make Code" in priority_make_app_search_terms("code")
    assert _has_search_term("microsoft-email", "outlook")
    assert _has_search_term("openai-gpt-3", "whisper")
    assert priority_make_app_search_terms("definitely-missing") == ()


def _raw_spec_manifest() -> RawSpecManifest:
    bundle = load_sqlite_raw_spec_bundle(
        database_path=repo_root() / DEFAULT_RAW_SPEC_SQLITE_DATABASE
    )
    assert bundle is not None, (
        "Expected SQLite raw-spec manifest rows in pancakes.sqlite."
    )
    return bundle.manifest


def _families_by_label(
    families: tuple[PriorityMakeModuleFamily, ...],
) -> dict[str, PriorityMakeModuleFamily]:
    return {family.label: family for family in families}


def _coverage_by_label(
    coverage: tuple[PriorityMakeModuleCoverage, ...],
) -> dict[str, PriorityMakeModuleCoverage]:
    return {row.label: row for row in coverage}


def _has_search_term(app_slug: str, expected: str) -> bool:
    return any(
        term.casefold() == expected
        for term in priority_make_app_search_terms(app_slug)
    )
