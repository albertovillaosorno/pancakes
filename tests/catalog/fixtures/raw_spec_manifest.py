# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Synthetic raw-spec manifest fixtures for catalog-adjacent tests.

Boundary contract:
- Owns: deterministic test-only raw-spec manifest materialization.
- Must not: read data/make raw-spec caches, call Make.com, or store secrets.
- Allows: synthetic fixture payloads under tests/catalog/fixtures/raw_specs.
- Split when: fixture families need separate app domains or scenario ownership.
- Merge when: another test fixture builder owns these exact manifest records.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, NamedTuple

from catalog.identifiers import module_id
from languages.make.raw_specs.manifest import (
    build_raw_spec_manifest,
    load_raw_spec_manifest,
    write_raw_spec_file,
    write_raw_spec_manifest,
)
from languages.make.raw_specs.models import SYNTHETIC_RAW_SPEC_SOURCE_METADATA

if TYPE_CHECKING:
    from collections.abc import Mapping

    from languages.make.raw_specs.models import (
        JsonObject,
        RawSpecManifest,
        RawSpecRecord,
    )

FIXTURE_GENERATED_AT: Final = "2026-05-05T00:00:00+00:00"
RAW_SPEC_FIXTURE_DIR: Final = Path("tests/catalog/fixtures/raw_specs")
MINIMAL_MANIFEST_RELATIVE_PATH: Final = (
    RAW_SPEC_FIXTURE_DIR / "minimal_manifest.json"
)
DATASTORE_APP_SLUG: Final = "datastore"
DATASTORE_LEGACY_VERSION: Final = "1.15.1"
DATASTORE_CURRENT_VERSION: Final = "2.0.5"
DATASTORE_ADD_RECORD_INTERNAL_NAME: Final = "AddRecord"
DATASTORE_ADD_RECORD_LEGACY_KEY: Final = "datastore_add_record_legacy"
DATASTORE_ADD_RECORD_CURRENT_KEY: Final = "datastore_add_record_current"
DATASTORE_ADD_RECORD_MODULE_REF: Final = "datastore:AddRecord"
HASH_MANIFEST_KEY: Final = "manifest_sha256"
HASH_RAW_SPEC_LEGACY_KEY: Final = "datastore_1_15_1_raw_spec_sha256"
HASH_RAW_SPEC_CURRENT_KEY: Final = "datastore_2_0_5_raw_spec_sha256"
_FIXTURE_SOURCE_MANIFEST = (
    Path(__file__).resolve().parent / "raw_specs" / "minimal_manifest.json"
)


class MinimalRawSpecManifestFixture(NamedTuple):
    """Materialized synthetic raw-spec manifest fixture."""

    repo_root: Path
    manifest_path: Path
    module_id_map: Mapping[str, str]
    token_map: Mapping[str, str]
    expected_hashes: Mapping[str, str]


def materialize_minimal_raw_spec_manifest_fixture(
    repo_root: Path,
) -> MinimalRawSpecManifestFixture:
    """Write the synthetic raw-spec fixture into a repository-shaped root.

    Returns:
        The materialized manifest path plus deterministic lookup metadata.
    """
    raw_spec_dir = repo_root / RAW_SPEC_FIXTURE_DIR
    records = tuple(
        write_raw_spec_file(
            repo_root=repo_root,
            raw_spec_dir=raw_spec_dir,
            payload=payload,
            source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
        )
        for payload in (
            _legacy_datastore_payload(),
            _current_datastore_payload(),
        )
    )
    manifest = build_raw_spec_manifest(
        repo_root=repo_root,
        raw_spec_dir=raw_spec_dir,
        records=records,
        generated_at_utc=FIXTURE_GENERATED_AT,
    )
    _require_fixture_manifest_snapshot(manifest)
    manifest_path = repo_root / MINIMAL_MANIFEST_RELATIVE_PATH
    write_raw_spec_manifest(manifest=manifest, manifest_path=manifest_path)
    return _fixture_from_manifest(
        repo_root=repo_root,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def _require_fixture_manifest_snapshot(manifest: RawSpecManifest) -> None:
    """Reject fixture code when it drifts from the committed manifest snapshot.

    Raises:
        ValueError: If the generated fixture no longer matches the
            committed manifest.
    """
    expected_manifest = load_raw_spec_manifest(_FIXTURE_SOURCE_MANIFEST)
    if manifest != expected_manifest:
        message = (
            "Synthetic raw-spec manifest fixture drifted from "
            "minimal_manifest.json."
        )
        raise ValueError(message)


def _fixture_from_manifest(
    *,
    repo_root: Path,
    manifest_path: Path,
    manifest: RawSpecManifest,
) -> MinimalRawSpecManifestFixture:
    """Return fixture metadata derived from the loaded manifest."""
    _require_fixture_local_manifest(manifest)
    legacy_record = _datastore_record(
        manifest.records, DATASTORE_LEGACY_VERSION
    )
    current_record = _datastore_record(
        manifest.records, DATASTORE_CURRENT_VERSION
    )
    legacy_module_id = _datastore_module_id(DATASTORE_LEGACY_VERSION)
    current_module_id = _datastore_module_id(DATASTORE_CURRENT_VERSION)
    return MinimalRawSpecManifestFixture(
        repo_root=repo_root,
        manifest_path=manifest_path,
        module_id_map=MappingProxyType(
            {
                DATASTORE_ADD_RECORD_LEGACY_KEY: legacy_module_id,
                DATASTORE_ADD_RECORD_CURRENT_KEY: current_module_id,
            }
        ),
        token_map=MappingProxyType(
            {DATASTORE_ADD_RECORD_MODULE_REF: current_module_id}
        ),
        expected_hashes=MappingProxyType(
            {
                HASH_MANIFEST_KEY: manifest.manifest_sha256,
                HASH_RAW_SPEC_LEGACY_KEY: legacy_record.sha256,
                HASH_RAW_SPEC_CURRENT_KEY: current_record.sha256,
            }
        ),
    )


def _require_fixture_local_manifest(manifest: RawSpecManifest) -> None:
    """Assert fixture manifest paths stay under tests/catalog/fixtures.

    Raises:
        ValueError: If any manifest path escapes the fixture directory.
    """
    expected_dir = RAW_SPEC_FIXTURE_DIR.as_posix()
    if manifest.raw_spec_dir != expected_dir:
        message = f"Raw-spec fixture directory must be {expected_dir!r}."
        raise ValueError(message)
    for record in manifest.records:
        if not record.relative_path.startswith(f"{expected_dir}/"):
            message = (
                "Raw-spec fixture record escaped fixture directory: "
                f"{record.relative_path}"
            )
            raise ValueError(message)
        if record.relative_path.startswith("data/make/"):
            message = (
                "Raw-spec fixture record must not use data/make: "
                f"{record.relative_path}"
            )
            raise ValueError(message)


def _datastore_record(
    records: tuple[RawSpecRecord, ...], app_version: str
) -> RawSpecRecord:
    """Return one Data Store manifest record by version.

    Raises:
        LookupError: If the requested synthetic app version is absent.
    """
    for record in records:
        if (
            record.app_slug == DATASTORE_APP_SLUG
            and record.app_version == app_version
        ):
            return record
    message = f"Missing synthetic Data Store raw-spec record for {app_version}."
    raise LookupError(message)


def _datastore_module_id(app_version: str) -> str:
    """Return the stable Data Store AddRecord catalog module ID."""
    return module_id(
        app_slug=DATASTORE_APP_SLUG,
        app_version=app_version,
        module_kind="action",
        internal_name=DATASTORE_ADD_RECORD_INTERNAL_NAME,
    )


def _legacy_datastore_payload() -> JsonObject:
    """Return the synthetic legacy Data Store raw-spec payload."""
    return _datastore_payload(
        app_version=DATASTORE_LEGACY_VERSION,
        latest=False,
        mode_label="Legacy import mode",
    )


def _current_datastore_payload() -> JsonObject:
    """Return the synthetic current Data Store raw-spec payload."""
    return _datastore_payload(
        app_version=DATASTORE_CURRENT_VERSION,
        latest=True,
        mode_label="Current import mode",
    )


def _datastore_payload(
    *, app_version: str, latest: bool, mode_label: str
) -> JsonObject:
    """Return one synthetic Data Store raw-spec app payload."""
    return {
        "app": {
            "name": DATASTORE_APP_SLUG,
            "version": app_version,
            "label": "Synthetic Data Store",
            "latest": latest,
            "manifest": {"version": 1},
            "actions": [
                {
                    "name": DATASTORE_ADD_RECORD_INTERNAL_NAME,
                    "label": "Add/replace a record",
                    "parameters": [
                        {
                            "name": "datastore",
                            "label": "Data store",
                            "required": True,
                            "type": "text",
                        },
                        {
                            "name": "record",
                            "label": "Record",
                            "type": "collection",
                            "spec": [
                                {
                                    "name": "leadId",
                                    "label": "Lead ID",
                                    "required": True,
                                    "type": "text",
                                },
                                {
                                    "name": "email",
                                    "label": "Lead email",
                                    "type": "email",
                                },
                            ],
                        },
                        {
                            "name": "mode",
                            "label": mode_label,
                            "type": "select",
                            "default": "upsert",
                            "options": [
                                {"label": "Add", "value": "add"},
                                {"label": "Upsert", "value": "upsert"},
                            ],
                        },
                    ],
                    "interface": [
                        {
                            "name": "recordId",
                            "label": "Record ID",
                            "type": "text",
                        }
                    ],
                }
            ],
        }
    }
