# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001033#repo.paths.generated-output-must-stay-inside-repo
# - 001044#repo.make-ast.contract-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Repository-local Make blueprint bundle persistence.

Boundary contract:
- Owns: repository-local persistence and validation of blueprint bundle files.
- Must not: render AST payloads, call live services, or write outside the repo.
- Allows: data/blueprints paths, JSON writes, manifests, and bundle validation.
- Split when: persistence, naming, or validation rules need separate ownership.
- Merge when: another artifact file writes the same bundle contract identically.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NamedTuple, TypeGuard, cast

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject

BLUEPRINT_BUNDLE_ROOT: Final[Path] = Path("data") / "blueprints"
LOGGER: Final[logging.Logger] = logging.getLogger(__name__)
SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")
MAX_JSON_BYTES: Final[int] = 10 * 1024 * 1024
SHA256_HEX_LENGTH: Final[int] = 64
JSON_READ_FAILED: Final[object] = object()
SOURCE_AST_REQUIRED_ARRAY_KEYS: Final[tuple[str, ...]] = ("flow",)
REQUIRED_BUNDLE_FILES: Final[tuple[str, ...]] = ("source_ast",)
OPTIONAL_BUNDLE_FILES: Final[tuple[str, ...]] = (
    "validated_ast ",
    "repair_report ",
    "migration_report ",
    "live_verification_report ",
    "observability_report",
)
KNOWN_BUNDLE_FILE_STEMS: Final[tuple[str, ...]] = (
    REQUIRED_BUNDLE_FILES + OPTIONAL_BUNDLE_FILES
)
type BlueprintArtifactPhase = Literal[
    "source_draft ",
    "compiled_blueprint ",
    "importable_candidate ",
    "live_make_scenario",
]
BLUEPRINT_ARTIFACT_PHASES: Final[tuple[BlueprintArtifactPhase, ...]] = (
    "source_draft ",
    "compiled_blueprint ",
    "importable_candidate ",
    "live_make_scenario",
)
IMPORTABLE_OR_LIVE_ARTIFACT_PHASES: Final[
    tuple[BlueprintArtifactPhase, ...]
] = (
    "importable_candidate ",
    "live_make_scenario",
)
ARTIFACT_PHASE_CLAIM_MISMATCH: Final[str] = "artifact_phase.claim_mismatch"
SOURCE_DRAFT_RUNTIME_MARKER: Final[str] = "{{runtime."
SOURCE_DRAFT_MESSAGE_TOKENS: Final[tuple[str, ...]] = (
    "replace runtime placeholders ",
    "offline portfolio draft",
)


class BlueprintPersistenceError(RuntimeError):
    """Raised when blueprint bundle persistence cannot complete."""


class _NonStandardJsonConstantError(ValueError):
    """Raised for non-standard JSON constants during parsing."""


class MakeBlueprintBundlePayloads(NamedTuple):
    """Payloads persisted for one Make blueprint bundle."""

    source_ast: JsonObject
    validated_ast: JsonObject | None = None
    repair_report: JsonObject | None = None
    migration_report: JsonObject | None = None
    live_verification_report: JsonObject | None = None
    observability_report: JsonObject | None = None

    def by_file_stem(self) -> dict[str, JsonObject]:
        """Return non-empty bundle payloads keyed by output file stem."""
        payloads_map: dict[str, JsonObject | None] = {
            "source_ast": self.source_ast,
            "validated_ast": self.validated_ast,
            "repair_report": self.repair_report,
            "migration_report": self.migration_report,
            "live_verification_report": self.live_verification_report,
            "observability_report": self.observability_report,
        }
        return {
            name: payload
            for name, payload in payloads_map.items()
            if payload is not None
        }


class BlueprintArtifactPhaseAssessment(NamedTuple):
    """Assessment for a claimed blueprint artifact phase."""

    artifact_phase: BlueprintArtifactPhase
    claimed_phase: BlueprintArtifactPhase
    diagnostic: JsonObject | None = None

    @property
    def claim_allowed(self) -> bool:
        """Check if the artifact can be represented as the claimed phase."""
        return self.diagnostic is None


def classify_blueprint_artifact_phase(
    payload: JsonObject,
) -> BlueprintArtifactPhase:
    """Classify repository-local blueprint artifact lifecycle phase.

    Returns:
        The classified artifact phase.
    """
    explicit_phase = _explicit_blueprint_artifact_phase(payload)
    if explicit_phase is not None:
        return explicit_phase
    if _contains_source_draft_signal(payload):
        return "source_draft"
    return "compiled_blueprint"


def assess_blueprint_artifact_phase_claim(
    *,
    payload: JsonObject,
    claimed_phase: BlueprintArtifactPhase | str,
) -> BlueprintArtifactPhaseAssessment:
    """Return diagnostics for representing a blueprint as a claimed phase.

    Returns:
        The phase assessment for the claimed representation.
    """
    artifact_phase = classify_blueprint_artifact_phase(payload)
    normalized_claim = normalize_blueprint_artifact_phase(claimed_phase)
    if (
        normalized_claim in IMPORTABLE_OR_LIVE_ARTIFACT_PHASES
        and artifact_phase != normalized_claim
    ):
        return BlueprintArtifactPhaseAssessment(
            artifact_phase=artifact_phase,
            claimed_phase=normalized_claim,
            diagnostic={
                "code": ARTIFACT_PHASE_CLAIM_MISMATCH,
                "severity": "error",
                "artifact_phase": artifact_phase,
                "claimed_phase": normalized_claim,
                "message": (
                    "Artifact phase does not support the requested "
                    "importable/live representation."
                ),
            },
        )
    return BlueprintArtifactPhaseAssessment(
        artifact_phase=artifact_phase,
        claimed_phase=normalized_claim,
    )


def normalize_blueprint_artifact_phase(value: object) -> BlueprintArtifactPhase:
    """Normalize a raw phase value to the typed artifact phase vocabulary.

    Returns:
        The normalized artifact phase.

    Raises:
        ValueError: If the phase is not part of the canonical vocabulary.
    """
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in BLUEPRINT_ARTIFACT_PHASES:
            return normalized
    message = f"Unknown blueprint artifact phase: {value!r}"
    raise ValueError(message)


def slugify_blueprint_name(name: str) -> str:
    """Return a deterministic filesystem-safe blueprint bundle slug."""
    collapsed = SLUG_PATTERN.sub("-", name.strip().casefold()).strip("-")
    return collapsed or "unnamed-blueprint"


def make_blueprint_bundle_root(repo_root: Path) -> Path:
    """Return the repository-local blueprint bundle root under data/."""
    root = repo_root.resolve()
    return _safe_repo_child(
        repo_root=root, target_path=root / BLUEPRINT_BUNDLE_ROOT
    )


def persist_make_blueprint_bundle(
    *,
    repo_root: Path,
    blueprint_name: str,
    payloads: MakeBlueprintBundlePayloads,
) -> dict[str, str]:
    """Persist one blueprint bundle under data/blueprints.

    Returns:
        The persisted blueprint bundle under data/blueprints.

    Raises:
        BlueprintPersistenceError: If persistence contract checks fail.
    """
    bundle_dir = make_blueprint_bundle_root(repo_root) / slugify_blueprint_name(
        blueprint_name
    )
    try:
        bundle_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        message = f"Unable to create blueprint bundle directory: {bundle_dir}"
        raise BlueprintPersistenceError(message) from exc

    written: dict[str, str] = {}
    checksums: dict[str, str] = {}
    for name, payload in payloads.by_file_stem().items():
        relative_path, payload_sha256 = _write_json(
            repo_root=repo_root,
            path=bundle_dir / f"{name}.json",
            payload=payload,
        )
        written[name] = relative_path
        checksums[name] = payload_sha256

    manifest: JsonObject = {
        "blueprint_name": blueprint_name,
        "slug": bundle_dir.name,
        "files": dict(written),
        "checksums_sha256": dict(checksums),
    }
    manifest_path, _ = _write_json(
        repo_root=repo_root,
        path=bundle_dir / "manifest.json",
        payload=manifest,
    )
    written["manifest"] = manifest_path
    return written


def validate_make_blueprint_bundle_collection(bundle_root: Path) -> JsonObject:
    """Validate one blueprint bundle collection layout.

    Returns:
        The validated value.
    """
    if not bundle_root.exists():
        return {"valid": True, "bundle_count": 0, "bundles": [], "errors": []}
    if not bundle_root.is_dir():
        return {
            "valid": False,
            "bundle_count": 0,
            "bundles": [],
            "errors": ["Blueprint bundle collection root must be a directory."],
        }
    return _bundle_collection_report(_bundle_validation_entries(bundle_root))


def _bundle_validation_entries(bundle_root: Path) -> tuple[JsonObject, ...]:
    """Return per-bundle validation entries for one bundle collection."""
    return tuple(
        _bundle_validation_entry(bundle_dir)
        for bundle_dir in sorted(
            path for path in bundle_root.iterdir() if path.is_dir()
        )
    )


def _bundle_validation_entry(bundle_dir: Path) -> JsonObject:
    """Return one bundle validation entry."""
    bundle_errors = _validate_bundle(bundle_dir)
    return {
        "bundle": bundle_dir.name,
        "valid": not bundle_errors,
        "errors": list(bundle_errors),
    }


def _bundle_collection_report(entries: tuple[JsonObject, ...]) -> JsonObject:
    """Return the aggregate validation report for bundle entries."""
    errors: list[str] = []
    for entry in entries:
        bundle_name = entry.get("bundle")
        bundle_errors = _bundle_entry_error_messages(entry)
        if not isinstance(bundle_name, str) or bundle_errors is None:
            errors.append("Bundle validation entry has an invalid shape.")
            continue
        errors.extend(f"{bundle_name}: {message}" for message in bundle_errors)
    return {
        "valid": not errors,
        "bundle_count": len(entries),
        "bundles": list(entries),
        "errors": errors,
    }


def _bundle_entry_error_messages(entry: JsonObject) -> tuple[str, ...] | None:
    """Return typed validation messages from one aggregate entry."""
    value = entry.get("errors")
    if not isinstance(value, list):
        return None
    messages: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str):
            return None
        messages.append(item)
    return tuple(messages)


def _validate_bundle(bundle_dir: Path) -> tuple[str, ...]:
    errors: list[str] = []
    manifest_path = bundle_dir / "manifest.json"
    source_ast_path = bundle_dir / "source_ast.json"
    manifest = _read_json_object(manifest_path)
    source_ast = _read_json_object(source_ast_path)
    if not manifest_path.exists():
        errors.append("manifest.json is required.")
    elif manifest is None:
        errors.append("manifest.json must contain an object.")
    else:
        errors.extend(
            _checksum_errors(manifest=manifest, bundle_dir=bundle_dir)
        )
    if not source_ast_path.exists():
        errors.append("source_ast.json is required.")
    elif source_ast is None:
        errors.append("source_ast.json must contain an object.")
    else:
        errors.extend(_source_ast_shape_errors(source_ast))
    for file_key in OPTIONAL_BUNDLE_FILES:
        file_path = bundle_dir / f"{file_key}.json"
        if file_path.exists() and _read_json_object(file_path) is None:
            errors.append(f"{file_key}.json must contain an object.")
    live_report = _read_json_object(
        bundle_dir / "live_verification_report.json"
    )
    if live_report is not None and _live_report_has_drift(live_report):
        errors.append("live_verification_report.json reports AST drift.")
    return tuple(errors)


def _live_report_has_drift(report: JsonObject) -> bool:
    ast_delta = report.get("ast_delta")
    if not _is_json_object(ast_delta):
        return False
    return ast_delta.get("has_changes") is True


def _read_json_object(path: Path) -> JsonObject | None:
    """Return a JSON object when a bundle file is small and object-shaped."""
    if not path.exists():
        return None
    payload = _read_json_payload(path)
    if payload is JSON_READ_FAILED:
        return None
    if not _is_json_object(payload):
        LOGGER.warning("Blueprint bundle JSON root is not an object: %s", path)
        return None
    return payload


def _read_json_payload(path: Path) -> object:
    """Return a JSON payload when a bundle file can be decoded."""

    def reject_non_standard_constant(raw_value: str) -> object:
        message = f"non-standard JSON constant {raw_value}"
        raise _NonStandardJsonConstantError(message)

    try:
        file_size = path.stat().st_size
        if file_size > MAX_JSON_BYTES:
            LOGGER.warning(
                "Blueprint bundle JSON exceeds the %d byte limit: %s",
                MAX_JSON_BYTES,
                path,
            )
            return JSON_READ_FAILED
        payload = cast(
            "object",
            json.loads(
                path.read_text(encoding="utf-8"),
                parse_constant=reject_non_standard_constant,
            ),
        )
    except (json.JSONDecodeError, _NonStandardJsonConstantError):
        LOGGER.warning("Blueprint bundle JSON is malformed: %s", path)
        return JSON_READ_FAILED
    except UnicodeDecodeError:
        LOGGER.warning("Blueprint bundle JSON is not valid UTF-8: %s", path)
        return JSON_READ_FAILED
    except OSError:
        LOGGER.warning("Blueprint bundle JSON could not be read: %s", path)
        return JSON_READ_FAILED
    return payload


def _write_json(
    *, repo_root: Path, path: Path, payload: JsonObject
) -> tuple[str, str]:
    root = repo_root.resolve()
    resolved_path = _safe_repo_child(repo_root=root, target_path=path)
    content = (
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n"
    ).encode("utf-8")
    payload_sha256 = hashlib.sha256(content).hexdigest()
    temp_path = _safe_repo_child(
        repo_root=root,
        target_path=resolved_path.with_name(f"{resolved_path.name}.tmp"),
    )
    try:
        _ = temp_path.write_bytes(content)
        _ = temp_path.replace(resolved_path)
    except OSError as exc:
        temp_path.unlink(missing_ok=True)
        message = f"Unable to write blueprint bundle JSON: {resolved_path}"
        raise BlueprintPersistenceError(message) from exc
    return resolved_path.relative_to(root).as_posix(), payload_sha256


def _safe_repo_child(*, repo_root: Path, target_path: Path) -> Path:
    root = repo_root.resolve()
    source = target_path if target_path.is_absolute() else root / target_path
    candidate = source.resolve()
    if root not in {candidate, *candidate.parents}:
        message = f"Refusing to write outside repository: {candidate}"
        raise ValueError(message)
    refactor_root = (root / "Refactor").resolve()
    if candidate == refactor_root or refactor_root in candidate.parents:
        message = f"Refusing to write inside Refactor: {candidate}"
        raise ValueError(message)
    return candidate


def _is_json_object(value: object) -> TypeGuard[JsonObject]:
    if not isinstance(value, dict):
        return False
    mapping = cast("dict[object, object]", value)
    return all(isinstance(key, str) for key in mapping)


def _explicit_blueprint_artifact_phase(
    payload: JsonObject,
) -> BlueprintArtifactPhase | None:
    """Return explicit root artifact phase metadata when present."""
    root_phase = payload.get("artifact_phase")
    if root_phase is not None:
        return normalize_blueprint_artifact_phase(root_phase)
    metadata = payload.get("metadata")
    if not _is_json_object(metadata):
        return None
    metadata_phase = metadata.get("artifact_phase")
    if metadata_phase is not None:
        return normalize_blueprint_artifact_phase(metadata_phase)
    artifact = metadata.get("artifact")
    if not _is_json_object(artifact):
        return None
    artifact_phase = artifact.get("phase")
    if artifact_phase is None:
        return None
    return normalize_blueprint_artifact_phase(artifact_phase)


def _contains_source_draft_signal(value: object) -> bool:
    """Return whether a payload still carries source-draft evidence."""
    if isinstance(value, str):
        return _is_source_draft_text(value)
    if isinstance(value, list):
        return any(
            _contains_source_draft_signal(item)
            for item in cast("list[object]", value)
        )
    if not _is_json_object(value):
        return False
    if _has_placeholder_registry(value):
        return True
    return any(_contains_source_draft_signal(item) for item in value.values())


def _has_placeholder_registry(value: JsonObject) -> bool:
    registry = value.get("placeholder_registry")
    if not isinstance(registry, list):
        return False
    registry_items = cast("list[object]", registry)
    return len(registry_items) > 0


def _is_source_draft_text(value: str) -> bool:
    normalized = value.strip().casefold()
    return SOURCE_DRAFT_RUNTIME_MARKER in normalized or any(
        token in normalized for token in SOURCE_DRAFT_MESSAGE_TOKENS
    )


def _source_ast_shape_errors(source_ast: JsonObject) -> tuple[str, ...]:
    return tuple(
        f"source_ast.json must contain {key}[]."
        for key in SOURCE_AST_REQUIRED_ARRAY_KEYS
        if not isinstance(source_ast.get(key), list)
    )


def _checksum_errors(
    *, manifest: JsonObject, bundle_dir: Path
) -> tuple[str, ...]:
    checksums = manifest.get("checksums_sha256")
    files = manifest.get("files")
    if not _is_json_object(files) or not _is_json_object(checksums):
        return (
            "manifest.json checksums_sha256 must match files object entries.",
        )

    entry_errors = _manifest_entry_key_errors(
        files=files,
        checksums=checksums,
        bundle_dir=bundle_dir,
    )
    if entry_errors:
        return entry_errors

    errors: list[str] = []
    for file_stem, expected_hash in checksums.items():
        if not isinstance(expected_hash, str) or not _is_sha256(expected_hash):
            errors.append(
                f"manifest checksum for {file_stem} must be a SHA-256 hex "
                f"digest."
            )
            continue
        relative_path = files.get(file_stem)
        if not isinstance(relative_path, str):
            errors.append(f"manifest files entry for {file_stem} is required.")
            continue
        if not _manifest_file_path_matches_bundle(
            relative_path=relative_path,
            bundle_dir=bundle_dir,
            file_stem=file_stem,
        ):
            expected_path = _expected_manifest_file_path(
                bundle_dir=bundle_dir, file_stem=file_stem
            )
            errors.append(
                f"manifest files entry for {file_stem} must point at "
                f"{expected_path}."
            )
            continue
        file_path = bundle_dir / f"{file_stem}.json"
        if not file_path.is_file():
            errors.append(f"{file_stem}.json is required by manifest checksum.")
            continue
        actual_hash = _file_sha256(file_path)
        if actual_hash is None:
            errors.append(
                f"{file_stem}.json could not be read for checksum validation."
            )
            continue
        if actual_hash != expected_hash:
            errors.append(f"{file_stem}.json checksum does not match manifest.")
    return tuple(errors)


def _manifest_entry_key_errors(
    *,
    files: JsonObject,
    checksums: JsonObject,
    bundle_dir: Path,
) -> tuple[str, ...]:
    """Return manifest key set errors before payload checksum validation."""
    file_keys = set(files)
    checksum_keys = set(checksums)
    present_file_keys = _present_bundle_file_stems(bundle_dir)
    errors: list[str] = []
    errors.extend(
        _required_manifest_entry_errors(
            file_keys=file_keys, checksum_keys=checksum_keys
        )
    )
    errors.extend(
        _unknown_manifest_entry_errors(
            file_keys=file_keys, checksum_keys=checksum_keys
        )
    )
    errors.extend(
        _missing_manifest_checksum_errors(
            file_keys=file_keys,
            checksum_keys=checksum_keys,
            present_file_keys=present_file_keys,
        )
    )
    errors.extend(
        _missing_manifest_file_errors(
            file_keys=file_keys,
            checksum_keys=checksum_keys,
            present_file_keys=present_file_keys,
        )
    )
    return tuple(errors)


def _required_manifest_entry_errors(
    *,
    file_keys: set[str],
    checksum_keys: set[str],
) -> tuple[str, ...]:
    errors: list[str] = []
    for file_stem in REQUIRED_BUNDLE_FILES:
        if file_stem not in file_keys:
            errors.append(f"manifest files entry for {file_stem} is required.")
        if file_stem not in checksum_keys:
            errors.append(f"manifest checksum for {file_stem} is required.")
    return tuple(errors)


def _unknown_manifest_entry_errors(
    *,
    file_keys: set[str],
    checksum_keys: set[str],
) -> tuple[str, ...]:
    return tuple(
        f"manifest entry for {file_stem} is not a known bundle file."
        for file_stem in sorted(file_keys | checksum_keys)
        if file_stem not in KNOWN_BUNDLE_FILE_STEMS
    )


def _missing_manifest_checksum_errors(
    *,
    file_keys: set[str],
    checksum_keys: set[str],
    present_file_keys: set[str],
) -> tuple[str, ...]:
    return tuple(
        f"manifest checksum for {file_stem} is required."
        for file_stem in sorted((file_keys | present_file_keys) - checksum_keys)
        if file_stem in KNOWN_BUNDLE_FILE_STEMS
        and file_stem not in REQUIRED_BUNDLE_FILES
    )


def _missing_manifest_file_errors(
    *,
    file_keys: set[str],
    checksum_keys: set[str],
    present_file_keys: set[str],
) -> tuple[str, ...]:
    return tuple(
        f"manifest files entry for {file_stem} is required."
        for file_stem in sorted((checksum_keys | present_file_keys) - file_keys)
        if file_stem in KNOWN_BUNDLE_FILE_STEMS
        and file_stem not in REQUIRED_BUNDLE_FILES
    )


def _present_bundle_file_stems(bundle_dir: Path) -> set[str]:
    return {
        file_stem
        for file_stem in KNOWN_BUNDLE_FILE_STEMS
        if (bundle_dir / f"{file_stem}.json").is_file()
    }


def _manifest_file_path_matches_bundle(
    *,
    relative_path: str,
    bundle_dir: Path,
    file_stem: str,
) -> bool:
    manifest_path = Path(relative_path)
    if manifest_path.is_absolute() or ".." in manifest_path.parts:
        return False
    return manifest_path.as_posix() == _expected_manifest_file_path(
        bundle_dir=bundle_dir,
        file_stem=file_stem,
    )


def _expected_manifest_file_path(*, bundle_dir: Path, file_stem: str) -> str:
    return (
        BLUEPRINT_BUNDLE_ROOT / bundle_dir.name / f"{file_stem}.json"
    ).as_posix()


def _is_sha256(value: str) -> bool:
    return len(value) == SHA256_HEX_LENGTH and all(
        character in "0123456789abcdef" for character in value
    )


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
