# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Priority Make module planning contracts.

Boundary contract:
- Owns: planner scoring behavior for operator-priority Make connector public
names.
- Must not: compile the full catalog, call Make.com, or depend on generated
credentials.
- Allows: small synthetic catalog models that isolate alias scoring behavior.
- Split when: broad requirement decomposition owns cross-module workflow
ranking.
"""

from __future__ import annotations

from catalog.fallback.scoring import score_module
from catalog.fallback.text import normalize_text, tokenize
from catalog.models import CatalogApp, CatalogModule


def test_priority_public_names_score_legacy_raw_spec_slugs() -> None:
    """Public connector names should recover Make raw-spec slugs during.

    planning.
    """
    brevo = score_module(
        app=_app(app_slug="sendinblue", label="Sendinblue"),
        module=_module(app_slug="sendinblue", internal_name="CreateContact"),
        query_terms=_query_terms("Brevo create contact"),
    )
    go_high_level = score_module(
        app=_app(app_slug="highlevel", label="HighLevel"),
        module=_module(app_slug="highlevel", internal_name="createAContact"),
        query_terms=_query_terms("GoHighLevel create contact"),
    )
    make_code = score_module(
        app=_app(app_slug="code", label="Code"),
        module=_module(
            app_slug="code",
            internal_name="ExecuteCode",
            display_name="Run code",
        ),
        query_terms=_query_terms("Make Code run code"),
    )

    assert brevo.score >= 50
    assert "exact:brevo" in brevo.match_reasons
    assert go_high_level.score >= 50
    assert "exact:gohighlevel" in go_high_level.match_reasons
    assert make_code.score >= 50
    assert "token:make" in make_code.match_reasons


def _query_terms(query: str) -> frozenset[str]:
    return frozenset(tokenize(normalize_text(query)))


def _app(*, app_slug: str, label: str) -> CatalogApp:
    return CatalogApp(
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        label=label,
        external_id=app_slug,
        deprecated=False,
        versions=(),
        fingerprint=f"fingerprint:{app_slug}",
    )


def _module(
    *,
    app_slug: str,
    internal_name: str,
    display_name: str = "Create a contact",
) -> CatalogModule:
    return CatalogModule(
        module_id=f"module:{app_slug}:1.0.0:action:{internal_name}",
        app_version_id=f"app-version:{app_slug}:1.0.0",
        app_slug=app_slug,
        app_version="1.0.0",
        module_kind="action",
        internal_name=internal_name,
        display_name=display_name,
        external_id=internal_name,
        deprecated=False,
        parameters=(),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256="0" * 64,
        fingerprint=f"fingerprint:{app_slug}:{internal_name}",
    )
