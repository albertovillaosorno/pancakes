# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-specs.repo-local-cache
# - 001042#repo.make-catalog.raw-specs-and-catalog-authority
# - 001064#repo.make-knowledge.structural-ssot
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Private Make default-manifest coverage ledger.

Boundary contract:
- Owns: deterministic loading of operator-reviewed Make default module coverage.
- Must not: call Make.com, scrape browsers, expose credentials, or claim
field-level parity.
- Allows: local module identity fallback for MCP search, expansion, and
generation audit.
- Split when: default manifest coverage becomes a generated knowledge-store
seed.
- Merge when: the Make knowledge store always ships a source-controlled
structural snapshot.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple, cast

from catalog.fallback.results import SOURCE_LABEL_MAKE_DEFAULT_MANIFEST_COVERAGE
from catalog.knowledge.models import KnowledgeModuleFact
from catalog.models import (
    CATALOG_SCHEMA_VERSION,
    CatalogApp,
    CatalogAppVersion,
    CatalogModule,
    CatalogSnapshot,
)

from languages.make.raw_specs.paths import resolve_repo_relative_path
from languages.make.tokens import module_token_resolution_key

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from catalog.models import CatalogModuleKind

type JsonObject = dict[str, object]

MAKE_DEFAULT_MANIFEST_COVERAGE_PATH: Final = Path(
    "src/languages/make/data/default_manifest_coverage.json"
)
MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SET: Final = (
    "operator_make_built_in_default_exports"
)
MAKE_DEFAULT_MANIFEST_COVERAGE_GENERATED_AT: Final = (
    "make-default-manifest-coverage"
)
MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SHA256: Final[dict[str, str]] = {
    "make_built_in_1.json": (
        "bfc312399a77b534d6405c145d8c3161a8e9b2c25c6082d337222600029227a9"
    ),
    "make_built_in_2.json": (
        "5fa5ffe611d83aaea86b40c826bc557115642bcde281b7c8f67ea0e3995c79cf"
    ),
    "make_built_in_ai.json": (
        "8ed95cea683718544cbea110c0bc00e8380faf45ded4802a1b0a038ea0130e14"
    ),
}
MAKE_DEFAULT_MANIFEST_EXPECTED_SOURCE_NODE_COUNT: Final = 198
MAKE_DEFAULT_MANIFEST_EXPECTED_MODULE_COUNT: Final = 197


class MakeDefaultManifestCoverageFact(NamedTuple):
    """One module identity from the private Make default-manifest coverage.

    ledger.
    """

    module_ref: str
    source_files: tuple[str, ...]
    occurrence_count: int
    scenario_names: tuple[str, ...]
    module: KnowledgeModuleFact

    @property
    def module_id(self) -> str:
        """Return the normalized catalog module id."""
        return self.module.module_id


def load_make_default_manifest_coverage_payload(repo_root: Path) -> JsonObject:
    """Return the validated Make default-manifest coverage payload."""
    path = _coverage_path(repo_root)
    stat = path.stat()
    return _load_payload_cached(str(path), stat.st_mtime_ns, stat.st_size)


def make_default_manifest_coverage_facts(
    repo_root: Path,
) -> tuple[MakeDefaultManifestCoverageFact, ...]:
    """Return validated default-manifest module facts."""
    payload = load_make_default_manifest_coverage_payload(repo_root)
    records = _object_list(payload, "records")
    facts = tuple(_fact_from_record(record) for record in records)
    _validate_unique_module_ids(facts)
    return facts


def make_default_manifest_coverage_fact_for_module_id(
    *,
    repo_root: Path,
    module_id: str,
) -> MakeDefaultManifestCoverageFact | None:
    """Return one default-manifest fact by module id."""
    normalized = module_id.casefold().strip()
    for fact in make_default_manifest_coverage_facts(repo_root):
        if fact.module_id.casefold() == normalized:
            return fact
    return None


def make_default_manifest_coverage_fact_for_token(
    *,
    repo_root: Path,
    module_token: str,
) -> MakeDefaultManifestCoverageFact | None:
    """Return the computed result for the caller."""
    normalized = module_token_resolution_key(module_token)
    for fact in make_default_manifest_coverage_facts(repo_root):
        module = fact.module
        if normalized in {
            module_token_resolution_key(fact.module_ref),
            module_token_resolution_key(module.internal_name),
            module_token_resolution_key(module.display_name),
        }:
            return fact
    return None


def make_default_manifest_coverage_module_ids_for_token(
    *,
    repo_root: Path,
    module_token: str,
) -> tuple[str, ...]:
    """Return default-manifest module ids matching one Make module token."""
    fact = make_default_manifest_coverage_fact_for_token(
        repo_root=repo_root,
        module_token=module_token,
    )
    return () if fact is None else (fact.module_id,)


def make_default_manifest_coverage_requested_module_ids(
    *,
    repo_root: Path,
    module_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """Return requested module ids present in the default-manifest coverage.

    ledger.
    """
    requested = _dedupe(module_ids)
    available = {
        fact.module_id
        for fact in make_default_manifest_coverage_facts(repo_root)
        if fact.module_id in requested
    }
    return tuple(module_id for module_id in requested if module_id in available)


def make_default_manifest_coverage_catalog_snapshot(
    *,
    repo_root: Path,
    module_ids: tuple[str, ...] = (),
) -> CatalogSnapshot:
    """Return the computed result for the caller."""
    facts = _selected_facts(repo_root=repo_root, module_ids=module_ids)
    return CatalogSnapshot(
        catalog_schema_version=CATALOG_SCHEMA_VERSION,
        generated_at_utc=MAKE_DEFAULT_MANIFEST_COVERAGE_GENERATED_AT,
        raw_spec_manifest_sha256=_fingerprint(
            _source_sha256_payload(repo_root)
        ),
        apps=_catalog_apps_for_facts(facts),
        fingerprint=_fingerprint(
            {"module_ids": [fact.module_id for fact in facts]}
        ),
        diagnostics=(),
    )


def with_make_default_manifest_coverage_modules(
    snapshot: CatalogSnapshot,
    *,
    repo_root: Path,
    module_ids: tuple[str, ...] = (),
) -> CatalogSnapshot:
    """Return a catalog snapshot augmented with default-manifest module.

    identities.
    """
    try:
        selected_facts = _selected_facts(
            repo_root=repo_root, module_ids=module_ids
        )
    except FileNotFoundError:
        return snapshot
    facts = tuple(
        fact
        for fact in selected_facts
        if fact.module_id not in _snapshot_module_ids(snapshot)
    )
    if not facts:
        return snapshot
    apps = _merge_catalog_apps_with_facts(snapshot.apps, facts)
    return snapshot._replace(
        apps=apps,
        fingerprint=_fingerprint(
            {
                "base": snapshot.fingerprint,
                "make_default_manifest_module_ids": [
                    fact.module_id for fact in facts
                ],
            }
        ),
    )


def make_default_manifest_coverage_payload(
    fact: MakeDefaultManifestCoverageFact,
) -> JsonObject:
    """Return a JSON-ready default-manifest module summary."""
    module = fact.module
    return {
        "module_id": module.module_id,
        "token": fact.module_ref,
        "app_slug": module.app_slug,
        "app_version": module.app_version,
        "module_kind": module.module_kind,
        "internal_name": module.internal_name,
        "display_name": module.display_name,
        "deprecated": module.deprecated,
        "source_files": list(fact.source_files),
        "occurrence_count": fact.occurrence_count,
        "scenario_names": list(fact.scenario_names),
        "confidence": "raw_spec_backed_default_manifest_coverage",
        "source_label": SOURCE_LABEL_MAKE_DEFAULT_MANIFEST_COVERAGE,
    }


def _coverage_path(repo_root: Path) -> Path:
    return resolve_repo_relative_path(
        repo_root, MAKE_DEFAULT_MANIFEST_COVERAGE_PATH
    )


@lru_cache(maxsize=4)
def _load_payload_cached(
    path_text: str, mtime_ns: int, size: int
) -> JsonObject:
    del mtime_ns, size
    path = Path(path_text)
    raw_payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    payload = _json_object(raw_payload, source=str(path))
    _validate_payload(payload)
    return payload


def _validate_payload(payload: Mapping[str, object]) -> None:
    source_files = tuple(_string_list(payload, "source_files"))
    expected_source_files = tuple(MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SHA256)
    if source_files != expected_source_files:
        message = f"Default manifest source files drifted: {source_files}"
        raise ValueError(message)
    source_hashes = _object(payload, "source_file_sha256")
    observed_hashes = {
        name: _required_text(source_hashes, name) for name in source_files
    }
    if observed_hashes != MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SHA256:
        message = "Default manifest source file hashes drifted."
        raise ValueError(message)
    if (
        _required_text(payload, "source_set")
        != MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SET
    ):
        message = "Default manifest coverage source set drifted."
        raise ValueError(message)
    coverage = _object(payload, "coverage")
    _require_int(
        coverage,
        "source_node_count",
        MAKE_DEFAULT_MANIFEST_EXPECTED_SOURCE_NODE_COUNT,
    )
    _require_int(
        coverage,
        "unique_module_count",
        MAKE_DEFAULT_MANIFEST_EXPECTED_MODULE_COUNT,
    )
    _require_int(
        coverage,
        "raw_spec_backed_count",
        MAKE_DEFAULT_MANIFEST_EXPECTED_MODULE_COUNT,
    )
    _require_int(coverage, "missing_local_catalog_manifest_count", 0)
    if _string_list(coverage, "missing_modules"):
        message = "Default manifest coverage unexpectedly has missing modules."
        raise ValueError(message)
    redaction = _object(payload, "redaction")
    if _required_text(redaction, "provider_credentials") != "not_recorded":
        message = (
            "Default manifest coverage must not record provider credentials."
        )
        raise ValueError(message)
    browser_evidence = _object(payload, "browser_evidence")
    if (
        _required_text(browser_evidence, "status")
        != "manual_login_ready_read_only"
    ):
        message = "Default manifest browser evidence status drifted."
        raise ValueError(message)


def _fact_from_record(
    record: Mapping[str, object],
) -> MakeDefaultManifestCoverageFact:
    if _required_text(record, "status") != "raw_spec_backed":
        message = f"Default manifest module is not raw-spec backed: {record}"
        raise ValueError(message)
    evidence = _object(record, "catalog_evidence")
    module_ref = _required_text(record, "module")
    app_slug = _required_text(evidence, "app_slug")
    internal_name = _required_text(evidence, "internal_name")
    expected_module_ref = f"{app_slug}:{internal_name}"
    if module_ref != expected_module_ref:
        message = f"Default manifest module token drifted: {module_ref}"
        raise ValueError(message)
    module = KnowledgeModuleFact(
        module_id=_required_text(evidence, "module_id"),
        app_slug=app_slug,
        app_version=_required_text(evidence, "app_version"),
        module_kind=_required_text(evidence, "module_kind"),
        internal_name=internal_name,
        display_name=_required_text(evidence, "display_name"),
        deprecated=False,
        fingerprint=_fingerprint(
            {
                "catalog_evidence": evidence,
                "module": module_ref,
                "source_files": _string_list(record, "source_files"),
            }
        ),
        adr_anchor="make_default_manifest_coverage",
    )
    return MakeDefaultManifestCoverageFact(
        module_ref=module_ref,
        source_files=tuple(_string_list(record, "source_files")),
        occurrence_count=_required_positive_int(record, "occurrences"),
        scenario_names=tuple(_string_list(record, "scenario_names")),
        module=module,
    )


def _selected_facts(
    *,
    repo_root: Path,
    module_ids: tuple[str, ...],
) -> tuple[MakeDefaultManifestCoverageFact, ...]:
    facts = make_default_manifest_coverage_facts(repo_root)
    if not module_ids:
        return facts
    requested = set(
        make_default_manifest_coverage_requested_module_ids(
            repo_root=repo_root,
            module_ids=module_ids,
        )
    )
    return tuple(fact for fact in facts if fact.module_id in requested)


def _catalog_apps_for_facts(
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> tuple[CatalogApp, ...]:
    grouped: dict[str, list[MakeDefaultManifestCoverageFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.module.app_slug, []).append(fact)
    return tuple(
        _catalog_app_for_facts(tuple(group))
        for _, group in sorted(grouped.items())
    )


def _catalog_app_for_facts(
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> CatalogApp:
    first = facts[0].module
    versions = _catalog_app_versions_for_facts(facts)
    return CatalogApp(
        app_id=f"app:{first.app_slug}",
        app_slug=first.app_slug,
        label=_app_label(first.app_slug),
        external_id=f"make:{first.app_slug}",
        deprecated=False,
        versions=versions,
        fingerprint=_fingerprint(
            {
                "make_default_manifest_app_slug": first.app_slug,
                "versions": [version.fingerprint for version in versions],
            }
        ),
    )


def _catalog_app_versions_for_facts(
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> tuple[CatalogAppVersion, ...]:
    grouped: dict[tuple[str, str], list[MakeDefaultManifestCoverageFact]] = {}
    for fact in facts:
        grouped.setdefault(
            (fact.module.app_slug, fact.module.app_version), []
        ).append(fact)
    return tuple(
        _catalog_app_version_for_facts(tuple(group))
        for _, group in sorted(grouped.items())
    )


def _catalog_app_version_for_facts(
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> CatalogAppVersion:
    first = facts[0].module
    modules = tuple(_catalog_module(fact) for fact in facts)
    fingerprint = _fingerprint(
        {"modules": [module.fingerprint for module in modules]}
    )
    return CatalogAppVersion(
        app_version_id=f"app-version:{first.app_slug}:{first.app_version}",
        app_id=f"app:{first.app_slug}",
        app_slug=first.app_slug,
        version=first.app_version,
        latest=True,
        manifest_version=1,
        modules=modules,
        raw_spec_sha256=_fingerprint(
            {"module_ids": [fact.module_id for fact in facts]}
        ),
        fingerprint=fingerprint,
    )


def _catalog_module(fact: MakeDefaultManifestCoverageFact) -> CatalogModule:
    module = fact.module
    return CatalogModule(
        module_id=module.module_id,
        app_version_id=f"app-version:{module.app_slug}:{module.app_version}",
        app_slug=module.app_slug,
        app_version=module.app_version,
        module_kind=cast("CatalogModuleKind", module.module_kind),
        internal_name=module.internal_name,
        display_name=module.display_name,
        external_id=f"make:{fact.module_ref}",
        deprecated=module.deprecated,
        parameters=(),
        expect_schema=(),
        interface_schema=(),
        rpc_dependencies=(),
        raw_spec_sha256=module.fingerprint,
        fingerprint=module.fingerprint,
    )


def _merge_catalog_apps_with_facts(
    apps: tuple[CatalogApp, ...],
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> tuple[CatalogApp, ...]:
    remaining = list(facts)
    merged_apps: list[CatalogApp] = []
    for app in apps:
        app_facts = tuple(
            fact
            for fact in remaining
            if fact.module.app_slug == app.app_slug
            or f"app:{fact.module.app_slug}" == app.app_id
        )
        if not app_facts:
            merged_apps.append(app)
            continue
        merged_apps.append(_merge_catalog_app_with_facts(app, app_facts))
        consumed = {fact.module_id for fact in app_facts}
        remaining = [
            fact for fact in remaining if fact.module_id not in consumed
        ]
    return (*merged_apps, *_catalog_apps_for_facts(tuple(remaining)))


def _merge_catalog_app_with_facts(
    app: CatalogApp,
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> CatalogApp:
    remaining = list(facts)
    versions: list[CatalogAppVersion] = []
    for version in app.versions:
        version_facts = tuple(
            fact
            for fact in remaining
            if fact.module.app_slug == version.app_slug
            and fact.module.app_version == version.version
        )
        if not version_facts:
            versions.append(version)
            continue
        versions.append(
            _merge_catalog_app_version_with_facts(version, version_facts)
        )
        consumed = {fact.module_id for fact in version_facts}
        remaining = [
            fact for fact in remaining if fact.module_id not in consumed
        ]
    versions.extend(_catalog_app_versions_for_facts(tuple(remaining)))
    return app._replace(
        versions=tuple(versions),
        fingerprint=_fingerprint(
            {
                "base": app.fingerprint,
                "make_default_manifest_module_ids": [
                    fact.module_id for fact in facts
                ],
            }
        ),
    )


def _merge_catalog_app_version_with_facts(
    version: CatalogAppVersion,
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> CatalogAppVersion:
    existing_module_ids = {module.module_id for module in version.modules}
    modules = (
        *version.modules,
        *(
            _catalog_module(fact)
            for fact in facts
            if fact.module_id not in existing_module_ids
        ),
    )
    return version._replace(
        modules=modules,
        raw_spec_sha256=_fingerprint(
            {
                "base": version.raw_spec_sha256,
                "make_default_manifest_module_ids": [
                    fact.module_id for fact in facts
                ],
            }
        ),
        fingerprint=_fingerprint(
            {
                "base": version.fingerprint,
                "module_ids": [module.module_id for module in modules],
            }
        ),
    )


def _snapshot_module_ids(snapshot: CatalogSnapshot) -> frozenset[str]:
    return frozenset(
        module.module_id
        for app in snapshot.apps
        for version in app.versions
        for module in version.modules
    )


def _source_sha256_payload(repo_root: Path) -> JsonObject:
    payload = load_make_default_manifest_coverage_payload(repo_root)
    return {
        "source_set": payload["source_set"],
        "source_files": payload["source_files"],
        "source_file_sha256": payload.get(
            "source_file_sha256",
            MAKE_DEFAULT_MANIFEST_COVERAGE_SOURCE_SHA256,
        ),
    }


def _validate_unique_module_ids(
    facts: tuple[MakeDefaultManifestCoverageFact, ...],
) -> None:
    module_ids = [fact.module_id for fact in facts]
    if len(module_ids) != len(set(module_ids)):
        message = "Default manifest coverage contains duplicate module ids."
        raise ValueError(message)


def _json_object(value: object, *, source: str) -> JsonObject:
    if not isinstance(value, dict):
        message = f"Expected JSON object: {source}"
        raise TypeError(message)
    return {
        str(key): item
        for key, item in cast("Mapping[object, object]", value).items()
    }


def _object(payload: Mapping[str, object], key: str) -> JsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        message = f"Expected object member: {key}"
        raise TypeError(message)
    return _json_object(cast("object", value), source=key)


def _object_list(
    payload: Mapping[str, object], key: str
) -> tuple[JsonObject, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Expected object list member: {key}"
        raise TypeError(message)
    return tuple(
        _json_object(item, source=key) for item in cast("list[object]", value)
    )


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Expected non-empty text member: {key}"
        raise TypeError(message)
    return value.strip()


def _string_list(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Expected string list member: {key}"
        raise TypeError(message)
    items = cast("list[object]", value)
    strings = tuple(str(item) for item in items if isinstance(item, str))
    if len(strings) != len(items):
        message = f"Expected string list member: {key}"
        raise TypeError(message)
    return strings


def _required_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value <= 0:
        message = f"Expected positive integer member: {key}"
        raise TypeError(message)
    return value


def _require_int(
    payload: Mapping[str, object], key: str, expected: int
) -> None:
    value = payload.get(key)
    if value != expected:
        message = f"Default manifest coverage {key} drifted: {value!r}"
        raise ValueError(message)


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return tuple(deduped)


def _app_label(app_slug: str) -> str:
    return app_slug.replace("-", " ").replace("_", " ").title()


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
