# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001033#repo.paths.no-output-outside-repository
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Manifest storage for Make raw-spec refresh artifacts.

Boundary contract:
- Owns: deterministic raw-spec file and manifest persistence.
- Must not: fetch upstream data, resolve credentials, or compile catalogs.
- Allows: repository-confined writes, manifest loading, and checksum validation.
- Split when: storage needs new artifact types or nonlocal backends.
- Merge when: another module writes the same raw-spec manifest format.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

from languages.make.raw_specs.models import (
    JsonObject,
    RawSpecManifest,
    RawSpecRecord,
    RawSpecSanitizationStatus,
    RawSpecSourceMetadata,
    RawSpecSourceType,
)
from languages.make.raw_specs.parser import parse_make_raw_spec
from languages.make.raw_specs.paths import (
    DEFAULT_RAW_SPEC_SQLITE_DATABASE,
    raw_spec_file_name,
    relative_to_repo,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class _RawSpecBundleLike(Protocol):
    """Loaded SQLite raw-spec bundle shape used by manifest loading."""

    manifest: RawSpecManifest


class _LoadSqliteRawSpecBundle(Protocol):
    """SQLite raw-spec bundle loader callable."""

    def __call__(self, *, database_path: Path) -> _RawSpecBundleLike | None: ...


RAW_SPEC_SQLITE_MANIFEST_REF = "sqlite:make_raw_spec_manifest_records"


def canonical_json_bytes(payload: JsonObject) -> bytes:
    """Return deterministic JSON bytes for one raw payload."""
    return (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def write_raw_spec_file(
    *,
    repo_root: Path,
    raw_spec_dir: Path,
    payload: JsonObject,
    source_metadata: RawSpecSourceMetadata,
) -> RawSpecRecord:
    """Write one raw spec file and return its manifest record.

    Returns:
        The documented result.

    Raises:
        OSError: If the documented operation cannot be completed.
    """
    parsed = parse_make_raw_spec(payload)
    output_path = raw_spec_dir / raw_spec_file_name(
        parsed.app_slug, parsed.app_version
    )
    _reject_linked_artifact_path(output_path)
    raw_spec_dir.mkdir(parents=True, exist_ok=True)
    _reject_linked_artifact_path(output_path)
    payload_bytes = canonical_json_bytes(payload)
    written_bytes = output_path.write_bytes(payload_bytes)
    if written_bytes != len(payload_bytes):
        message = f"Could not write full raw spec payload to {output_path}."
        raise OSError(message)
    digest = hashlib.sha256(payload_bytes).hexdigest()
    return RawSpecRecord(
        app_slug=parsed.app_slug,
        app_version=parsed.app_version,
        app_label=parsed.app_label,
        latest=parsed.latest,
        manifest_version=parsed.manifest_version,
        source_metadata=source_metadata,
        relative_path=relative_to_repo(repo_root, output_path),
        sha256=digest,
        size_bytes=len(payload_bytes),
        module_count=len(parsed.modules),
        module_kinds=tuple(
            sorted({module.module_kind for module in parsed.modules})
        ),
    )


def build_raw_spec_manifest(
    *,
    repo_root: Path,
    raw_spec_dir: Path,
    records: tuple[RawSpecRecord, ...],
    generated_at_utc: str,
) -> RawSpecManifest:
    """Build the deterministic manifest for a raw-spec sync.

    Returns:
        The deterministic manifest for a raw-spec sync.
    """
    ordered_records = tuple(
        sorted(
            records, key=lambda record: (record.app_slug, record.app_version)
        )
    )
    manifest_payload = _manifest_payload(
        generated_at_utc=generated_at_utc,
        raw_spec_dir=relative_to_repo(repo_root, raw_spec_dir),
        records=ordered_records,
        manifest_sha256="",
    )
    digest = hashlib.sha256(canonical_json_bytes(manifest_payload)).hexdigest()
    return RawSpecManifest(
        generated_at_utc=generated_at_utc,
        raw_spec_dir=relative_to_repo(repo_root, raw_spec_dir),
        records=ordered_records,
        manifest_sha256=digest,
    )


def build_raw_spec_manifest_for_store(
    *,
    raw_spec_dir: str,
    records: tuple[RawSpecRecord, ...],
    generated_at_utc: str,
) -> RawSpecManifest:
    """Build a deterministic manifest for a non-file raw-spec store.

    Returns:
        The deterministic manifest for a raw-spec sync.
    """
    ordered_records = tuple(
        sorted(
            records, key=lambda record: (record.app_slug, record.app_version)
        )
    )
    manifest_payload = _manifest_payload(
        generated_at_utc=generated_at_utc,
        raw_spec_dir=raw_spec_dir,
        records=ordered_records,
        manifest_sha256="",
    )
    digest = hashlib.sha256(canonical_json_bytes(manifest_payload)).hexdigest()
    return RawSpecManifest(
        generated_at_utc=generated_at_utc,
        raw_spec_dir=raw_spec_dir,
        records=ordered_records,
        manifest_sha256=digest,
    )


def write_raw_spec_manifest(
    *,
    manifest: RawSpecManifest,
    manifest_path: Path,
) -> None:
    """Persist one raw-spec manifest as deterministic JSON.

    Raises:
        OSError: If the documented operation cannot be completed.
    """
    _reject_linked_artifact_path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_linked_artifact_path(manifest_path)
    payload = _manifest_payload(
        generated_at_utc=manifest.generated_at_utc,
        raw_spec_dir=manifest.raw_spec_dir,
        records=manifest.records,
        manifest_sha256=manifest.manifest_sha256,
    )
    payload_bytes = canonical_json_bytes(payload)
    written_bytes = manifest_path.write_bytes(payload_bytes)
    if written_bytes != len(payload_bytes):
        message = f"Could not write full raw spec manifest to {manifest_path}."
        raise OSError(message)


def load_raw_spec_manifest(path: Path) -> RawSpecManifest:
    """Load a raw-spec manifest from disk.

    Returns:
        The loaded raw-spec manifest from disk.
    """
    if path.name == RAW_SPEC_SQLITE_MANIFEST_REF:
        return _load_sqlite_raw_spec_manifest(path)
    payload = _load_json_object(path)
    records = tuple(
        _record_from_payload(item) for item in _object_list(payload, "records")
    )
    generated_at = _required_text(payload, "generated_at_utc")
    raw_spec_dir = _required_text(payload, "raw_spec_dir")
    manifest_sha256 = _required_text(payload, "manifest_sha256")
    _verify_manifest_sha256(payload, manifest_sha256)
    return RawSpecManifest(
        generated_at_utc=generated_at,
        raw_spec_dir=raw_spec_dir,
        records=records,
        manifest_sha256=manifest_sha256,
    )


def _load_sqlite_raw_spec_manifest(path: Path) -> RawSpecManifest:
    """Load the current raw-spec manifest from the SQLite SSOT sentinel path.

    Returns:
        The current raw-spec manifest stored in SQLite.

    Raises:
        FileNotFoundError: If the SQLite manifest rows are missing.
    """
    sqlite_store = import_module("languages.make.raw_specs.sqlite_store")
    load_sqlite_raw_spec_bundle = cast(
        "_LoadSqliteRawSpecBundle",
        vars(sqlite_store)["load_sqlite_raw_spec_bundle"],
    )

    bundle = load_sqlite_raw_spec_bundle(
        database_path=path.parent / DEFAULT_RAW_SPEC_SQLITE_DATABASE
    )
    if bundle is None:
        message = f"SQLite raw spec manifest is missing for {path}."
        raise FileNotFoundError(message)
    return bundle.manifest


def _manifest_payload(
    *,
    generated_at_utc: str,
    raw_spec_dir: str,
    records: tuple[RawSpecRecord, ...],
    manifest_sha256: str,
) -> JsonObject:
    """Return a JSON object for one manifest."""
    return {
        "generated_at_utc": generated_at_utc,
        "raw_spec_dir": raw_spec_dir,
        "manifest_sha256": manifest_sha256,
        "records": [_record_payload(record) for record in records],
    }


def _record_payload(record: RawSpecRecord) -> JsonObject:
    """Return a JSON object for one manifest record."""
    return {
        "app_slug": record.app_slug,
        "app_version": record.app_version,
        "app_label": record.app_label,
        "latest": record.latest,
        "manifest_version": record.manifest_version,
        "source_metadata": _source_metadata_payload(record.source_metadata),
        "relative_path": record.relative_path,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "module_count": record.module_count,
        "module_kinds": list(record.module_kinds),
    }


def _verify_manifest_sha256(payload: JsonObject, manifest_sha256: str) -> None:
    """Reject manifests whose stored digest no longer matches their payload.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    digest_payload = dict(payload)
    digest_payload["manifest_sha256"] = ""
    digest = hashlib.sha256(canonical_json_bytes(digest_payload)).hexdigest()
    if digest != manifest_sha256:
        message = "Raw spec manifest hash mismatch."
        raise ValueError(message)


def _load_json_object(path: Path) -> JsonObject:
    """Load one JSON object from disk.

    Returns:
        The loaded JSON object from disk.

    Raises:
        TypeError: If a value has an invalid type.
    """
    payload = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(payload, dict):
        message = f"{path} must contain a JSON object."
        raise TypeError(message)
    return {
        str(key): value
        for key, value in cast("Mapping[object, object]", payload).items()
    }


def _object_member(payload: JsonObject, key: str) -> JsonObject:
    """Return one required object member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, dict):
        message = f"Manifest member {key!r} must be an object."
        raise TypeError(message)
    return {
        str(item_key): item_value
        for item_key, item_value in cast(
            "Mapping[object, object]", value
        ).items()
    }


def _object_list(payload: JsonObject, key: str) -> tuple[JsonObject, ...]:
    """Return one required object list member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Manifest member {key!r} must be a list."
        raise TypeError(message)
    records: list[JsonObject] = []
    for item in cast("list[object]", value):
        if not isinstance(item, dict):
            message = f"Manifest member {key!r} must contain only objects."
            raise TypeError(message)
        records.append(
            {
                str(item_key): item_value
                for item_key, item_value in cast(
                    "Mapping[object, object]", item
                ).items()
            }
        )
    return tuple(records)


def _record_from_payload(payload: JsonObject) -> RawSpecRecord:
    """Return one manifest record from JSON."""
    return RawSpecRecord(
        app_slug=_required_text(payload, "app_slug"),
        app_version=_required_text(payload, "app_version"),
        app_label=_required_text(payload, "app_label"),
        latest=_required_bool(payload, "latest"),
        manifest_version=_required_int(payload, "manifest_version"),
        source_metadata=_source_metadata_from_payload(
            _object_member(payload, "source_metadata")
        ),
        relative_path=_required_text(payload, "relative_path"),
        sha256=_required_text(payload, "sha256"),
        size_bytes=_required_int(payload, "size_bytes"),
        module_count=_required_int(payload, "module_count"),
        module_kinds=_string_tuple(payload, "module_kinds"),
    )


def _reject_linked_artifact_path(path: Path) -> None:
    """Reject existing symlink or junction components before artifact writes.

    Raises:
        ValueError: If the artifact path crosses a filesystem link.
    """
    checked_paths = tuple(_existing_artifact_path_components(path))
    for candidate in checked_paths:
        if _path_is_filesystem_link(candidate):
            message = (
                f"Raw spec artifact path uses a symlink or junction: {path}"
            )
            raise ValueError(message)


def _existing_artifact_path_components(path: Path) -> tuple[Path, ...]:
    """Return existing path components that would be traversed by a write."""
    candidates: list[Path] = []
    current = path
    while True:
        if current.exists() or current.is_symlink():
            candidates.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return tuple(reversed(candidates))


def _path_is_filesystem_link(path: Path) -> bool:
    """Return whether one path is a symlink or Windows reparse-point link."""
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        mode = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return bool(
        getattr(mode, "st_file_attributes", 0)
        & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _source_metadata_payload(metadata: RawSpecSourceMetadata) -> JsonObject:
    """Return a JSON object for source metadata."""
    return {
        "source_type": metadata.source_type,
        "is_truncated": metadata.is_truncated,
        "truncation_reason": metadata.truncation_reason,
        "sanitization_status": metadata.sanitization_status,
    }


def _source_metadata_from_payload(payload: JsonObject) -> RawSpecSourceMetadata:
    """Return required source metadata from JSON."""
    return RawSpecSourceMetadata(
        source_type=_raw_spec_source_type(payload),
        is_truncated=_required_bool(payload, "is_truncated"),
        truncation_reason=_required_text(payload, "truncation_reason"),
        sanitization_status=_raw_spec_sanitization_status(payload),
    )


def _raw_spec_source_type(payload: JsonObject) -> RawSpecSourceType:
    """Return one validated raw-spec source type.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = _required_text(payload, "source_type")
    if value not in {
        "client_authorized_authenticated_api_response",
        "public_make_docs",
        "derived_fixture",
        "third_party_connector_material",
    }:
        message = f"Manifest source_type {value!r} is not supported."
        raise ValueError(message)
    return cast("RawSpecSourceType", value)


def _raw_spec_sanitization_status(
    payload: JsonObject,
) -> RawSpecSanitizationStatus:
    """Return one validated raw-spec sanitization status.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = _required_text(payload, "sanitization_status")
    if value not in {
        "internal_raw_ignored",
        "synthetic_fixture",
        "sanitized_functional_facts",
    }:
        message = f"Manifest sanitization_status {value!r} is not supported."
        raise ValueError(message)
    return cast("RawSpecSanitizationStatus", value)


def _required_text(payload: JsonObject, key: str) -> str:
    """Return one required text member.

    Raises:
        ValueError: If a value violates the expected contract.
    """
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        message = f"Manifest member {key!r} must be non-empty text."
        raise ValueError(message)
    return value


def _required_int(payload: JsonObject, key: str) -> int:
    """Return one required integer member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        message = f"Manifest member {key!r} must be an integer."
        raise TypeError(message)
    return value


def _required_bool(payload: JsonObject, key: str) -> bool:
    """Return one required boolean member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, bool):
        message = f"Manifest member {key!r} must be a boolean."
        raise TypeError(message)
    return value


def _string_tuple(payload: JsonObject, key: str) -> tuple[str, ...]:
    """Return one required string-list member.

    Raises:
        TypeError: If a value has an invalid type.
    """
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"Manifest member {key!r} must be a string list."
        raise TypeError(message)
    items: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str):
            message = f"Manifest member {key!r} must be a string list."
            raise TypeError(message)
        items.append(item)
    return tuple(items)
