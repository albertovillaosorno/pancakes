# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Catalog-backed Make module token resolution tests.

Boundary contract:
- Owns: focused tests for resolving Make module tokens from typed catalog
evidence.
- Must not: scrape Make, refresh raw specs, or validate blueprint importability.
- Allows: small synthetic catalog snapshots with sanitized native module rows.
- Split when: raw-spec manifest binding or knowledge-store lookup gets separate
tests.
- Merge when: another catalog test owns the same module-token resolution
behavior.
"""

from __future__ import annotations

from typing import NamedTuple

from catalog.models import (
    CatalogApp,
    CatalogAppVersion,
    CatalogModule,
    CatalogSnapshot,
)
from catalog.validation import resolve_module_token

FIXED_GENERATED_AT = "2026-05-06T00:00:00+00:00"
HEX_1 = "1" * 64
HEX_2 = "2" * 64
HEX_3 = "3" * 64
HEX_4 = "4" * 64
HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64
HEX_D = "d" * 64
HEX_E = "e" * 64
HEX_F = "f" * 64


class NativeModuleSeed(NamedTuple):
    """Synthetic catalog module values for one native Make module."""

    app_slug: str
    app_version: str
    module_kind: str
    internal_name: str
    display_name: str
    raw_spec_sha256: str
    fingerprint: str


def test_known_make_module_token_resolves_from_catalog_fixture() -> None:
    """Known Make tokens resolve from catalog rows and expose version.

    evidence.
    """
    snapshot = native_module_snapshot()

    resolutions = {
        token: resolve_module_token(snapshot, token)
        for token in (
            "gateway:CustomWebHook",
            "builtin:BasicRouter",
            "datastore:AddRecord",
        )
    }

    expected_module_ids = {
        "gateway:CustomWebHook": "module:gateway:1.14.1:trigger:CustomWebHook",
        "builtin:BasicRouter": "module:builtin:current:router:BasicRouter",
        "datastore:AddRecord": "module:datastore:2.0.5:action:AddRecord",
    }
    for token, expected_module_id in expected_module_ids.items():
        resolution = resolutions[token]
        assert resolution.known, (
            f"Catalog token {token!r} did not resolve: {resolution}"
        )
        assert resolution.catalog_module_id == expected_module_id, (
            f"Catalog token {token!r} did not resolve: {resolution}"
        )
        assert resolution.app_version, (
            f"Catalog token {token!r} lost version evidence: {resolution}"
        )
        assert resolution.raw_spec_sha256, (
            f"Catalog token {token!r} lost version evidence: {resolution}"
        )


def test_legacy_prefixed_make_module_token_resolves_from_catalog_fixture() -> (
    None
):
    """Catalog token resolution accepts legacy action and trigger internal-name.

    prefixes.
    """
    snapshot = native_module_snapshot()

    resolutions = {
        token: resolve_module_token(snapshot, token)
        for token in (
            "gateway:triggerCustomWebHook",
            "datastore:actionAddRecord",
        )
    }

    expected_module_ids = {
        "gateway:triggerCustomWebHook": (
            "module:gateway:1.14.1:trigger:CustomWebHook"
        ),
        "datastore:actionAddRecord": "module:datastore:2.0.5:action:AddRecord",
    }
    for token, expected_module_id in expected_module_ids.items():
        resolution = resolutions[token]
        assert resolution.known, (
            f"Legacy-prefixed token {token!r} did not resolve: {resolution}"
        )
        assert resolution.catalog_module_id == expected_module_id, (
            f"Legacy-prefixed token {token!r} resolved to the wrong module: "
            f"{resolution}"
        )


def test_version_resolution_does_not_guess_aa8f95f0() -> None:
    """Unknown module tokens do not fabricate module IDs or raw-spec.

    versions.
    """
    resolution = resolve_module_token(
        native_module_snapshot(), "gateway:ImaginaryModule"
    )

    assert not (resolution.known), (
        f"Unknown token should not resolve: {resolution}"
    )
    assert not (resolution.catalog_module_id is not None), (
        f"Unknown token must not fabricate module evidence: {resolution}"
    )
    assert not (resolution.raw_spec_sha256 is not None), (
        f"Unknown token must not fabricate module evidence: {resolution}"
    )
    assert resolution.available_versions == ("1.14.1",), (
        f"Known app versions should remain evidence-only: {resolution}"
    )


def test_unknown_make_module_token_reports_f580fb28() -> None:
    """Unknown module diagnostics should list semantic versions in descending.

    order.
    """
    modules = (
        native_module(
            NativeModuleSeed(
                app_slug="gateway",
                app_version="1.9.0",
                module_kind="trigger",
                internal_name="LegacyWebhook",
                display_name="Legacy webhook",
                raw_spec_sha256=HEX_A,
                fingerprint=HEX_1,
            )
        ),
        native_module(
            NativeModuleSeed(
                app_slug="gateway",
                app_version="1.10.0",
                module_kind="trigger",
                internal_name="CurrentWebhook",
                display_name="Current webhook",
                raw_spec_sha256=HEX_B,
                fingerprint=HEX_2,
            )
        ),
        native_module(
            NativeModuleSeed(
                app_slug="gateway",
                app_version="2.0.0",
                module_kind="trigger",
                internal_name="NextWebhook",
                display_name="Next webhook",
                raw_spec_sha256=HEX_C,
                fingerprint=HEX_3,
            )
        ),
    )
    snapshot = CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc=FIXED_GENERATED_AT,
        raw_spec_manifest_sha256=HEX_D,
        apps=(app_with_versions("gateway", "Gateway", modules, HEX_E),),
        fingerprint=HEX_F,
    )

    resolution = resolve_module_token(snapshot, "gateway:ImaginaryModule")

    assert resolution.available_versions == ("2.0.0", "1.10.0", "1.9.0"), (
        f"Available versions should be newest first: {resolution}"
    )


def test_unknown_make_module_token_reports_current_version_first() -> None:
    """Unknown module diagnostics should treat Make current specs as newest."""
    modules = (
        native_module(
            NativeModuleSeed(
                app_slug="builtin",
                app_version="1.0.0",
                module_kind="router",
                internal_name="LegacyRouter",
                display_name="Legacy router",
                raw_spec_sha256=HEX_A,
                fingerprint=HEX_1,
            )
        ),
        native_module(
            NativeModuleSeed(
                app_slug="builtin",
                app_version="current",
                module_kind="router",
                internal_name="CurrentRouter",
                display_name="Current router",
                raw_spec_sha256=HEX_B,
                fingerprint=HEX_2,
            )
        ),
        native_module(
            NativeModuleSeed(
                app_slug="builtin",
                app_version="2.0.0",
                module_kind="router",
                internal_name="NextRouter",
                display_name="Next router",
                raw_spec_sha256=HEX_C,
                fingerprint=HEX_3,
            )
        ),
    )
    snapshot = CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc=FIXED_GENERATED_AT,
        raw_spec_manifest_sha256=HEX_D,
        apps=(app_with_versions("builtin", "Make builtin", modules, HEX_E),),
        fingerprint=HEX_F,
    )

    resolution = resolve_module_token(snapshot, "builtin:ImaginaryRouter")

    assert resolution.available_versions == ("current", "2.0.0", "1.0.0"), (
        f"Current Make specs should sort ahead of numbered versions: "
        f"{resolution}"
    )


def native_module_snapshot() -> CatalogSnapshot:
    """Return a sanitized catalog with native Make module token examples."""
    gateway = native_module(
        NativeModuleSeed(
            app_slug="gateway",
            app_version="1.14.1",
            module_kind="trigger",
            internal_name="CustomWebHook",
            display_name="Custom webhook",
            raw_spec_sha256=HEX_A,
            fingerprint=HEX_1,
        )
    )
    builtin = native_module(
        NativeModuleSeed(
            app_slug="builtin",
            app_version="current",
            module_kind="router",
            internal_name="BasicRouter",
            display_name="Basic router",
            raw_spec_sha256=HEX_B,
            fingerprint=HEX_2,
        )
    )
    datastore = native_module(
        NativeModuleSeed(
            app_slug="datastore",
            app_version="2.0.5",
            module_kind="action",
            internal_name="AddRecord",
            display_name="Add/replace a record",
            raw_spec_sha256=HEX_C,
            fingerprint=HEX_3,
        )
    )
    return CatalogSnapshot(
        catalog_schema_version=1,
        generated_at_utc=FIXED_GENERATED_AT,
        raw_spec_manifest_sha256=HEX_D,
        apps=(
            app_with_module("builtin", "Make builtin", builtin, HEX_4),
            app_with_module("datastore", "Data Store", datastore, HEX_E),
            app_with_module("gateway", "Gateway", gateway, HEX_F),
        ),
        fingerprint=HEX_A,
    )


def native_module(seed: NativeModuleSeed) -> CatalogModule:
    """Return one minimal catalog module."""
    module = CatalogModule(
        module_id="module:placeholder:current:action:placeholder",
        app_version_id="app-version:placeholder:current",
        app_slug=seed.app_slug,
        app_version=seed.app_version,
        module_kind="action",
        internal_name=seed.internal_name,
        display_name=seed.display_name,
        external_id="placeholder",
        deprecated=False,
        parameters=(),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256=seed.raw_spec_sha256,
        fingerprint=seed.fingerprint,
    )
    return module._replace(
        module_id=(
            f"module:{seed.app_slug}:{seed.app_version}:{seed.module_kind}:{seed.internal_name}"
        ),
        app_version_id=f"app-version:{seed.app_slug}:{seed.app_version}",
        module_kind=seed.module_kind,
        external_id=(
            f"{seed.app_slug}:{seed.app_version}:{seed.module_kind}:{seed.internal_name}"
        ),
    )


def app_with_module(
    app_slug: str,
    label: str,
    module: CatalogModule,
    fingerprint: str,
) -> CatalogApp:
    """Return one catalog app containing a single version and module."""
    version = CatalogAppVersion(
        app_version_id=f"app-version:{app_slug}:{module.app_version}",
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        version=module.app_version,
        latest=True,
        manifest_version=1,
        modules=(module,),
        raw_spec_sha256=module.raw_spec_sha256,
        fingerprint=fingerprint,
    )
    return CatalogApp(
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        label=label,
        external_id=app_slug,
        deprecated=False,
        versions=(version,),
        fingerprint=fingerprint,
    )


def app_with_versions(
    app_slug: str,
    label: str,
    modules: tuple[CatalogModule, ...],
    fingerprint: str,
) -> CatalogApp:
    """Return one catalog app containing one module per app version."""
    versions = tuple(
        CatalogAppVersion(
            app_version_id=f"app-version:{app_slug}:{module.app_version}",
            app_id=f"app:{app_slug}",
            app_slug=app_slug,
            version=module.app_version,
            latest=module.app_version == "2.0.0",
            manifest_version=1,
            modules=(module,),
            raw_spec_sha256=module.raw_spec_sha256,
            fingerprint=module.fingerprint,
        )
        for module in modules
    )
    return CatalogApp(
        app_id=f"app:{app_slug}",
        app_slug=app_slug,
        label=label,
        external_id=app_slug,
        deprecated=False,
        versions=versions,
        fingerprint=fingerprint,
    )
