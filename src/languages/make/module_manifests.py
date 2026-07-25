# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001040#repo.runtime.target-modular-layout.bounded-contexts
# - 001060#repo.architecture.ports-adapters.boundary-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Manifest-backed Make-native module projector contracts.

Boundary contract:
- Owns: deterministic local loading of Make-specific module projector manifests.
- Must not: call Make.com, mutate manifests, define generic AST semantics, or
expose private
  manifest details in customer-facing blueprint artifacts.
- Allows: Make exporter helpers, tests, and internal diagnostics to trace
module-shape decisions to
  explicit target-language contracts.
- Split when: generated typed projector manifests replace JSON manifest loading.
- Merge when: another Make manifest loader duplicates this exact contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from blueprints.ast.models import JsonObject

MAKE_MODULE_PROJECTOR_MANIFEST_SCHEMA_VERSION: Final = 1
MAKE_MODULE_PROJECTOR_MANIFEST_BASE_PATH: Final = Path(__file__).parent
MAKE_MODULE_PROJECTOR_MANIFEST_ROOTS: Final = (
    MAKE_MODULE_PROJECTOR_MANIFEST_BASE_PATH / "modules",
    MAKE_MODULE_PROJECTOR_MANIFEST_BASE_PATH / "builtins",
)
MAKE_MODULE_PROJECTOR_MANIFEST_GLOB: Final = "*.manifest.json"


def make_module_projector_manifest_paths() -> tuple[Path, ...]:
    """Return all local Make module projector manifest paths."""
    paths: list[Path] = []
    for root in MAKE_MODULE_PROJECTOR_MANIFEST_ROOTS:
        if root.exists():
            paths.extend(
                sorted(root.rglob(MAKE_MODULE_PROJECTOR_MANIFEST_GLOB))
            )
    return tuple(paths)


def make_module_projector_manifests() -> tuple[JsonObject, ...]:
    """Return all Make module projector manifests."""
    return tuple(
        _load_manifest(path) for path in make_module_projector_manifest_paths()
    )


def make_module_projector_manifest_for_native_token(
    module: str,
) -> JsonObject | None:
    """Return the projector manifest for a Make-native module token or known.

    alias.
    """
    normalized = module.casefold().strip()
    for manifest in make_module_projector_manifests():
        tokens = {str(manifest.get("native_token", "")).casefold().strip()}
        aliases = manifest.get("aliases")
        if isinstance(aliases, list):
            tokens.update(
                str(alias).casefold().strip()
                for alias in cast("list[object]", aliases)
            )
        if normalized in tokens:
            return manifest
    return None


def make_module_projector_kind(manifest: JsonObject) -> str | None:
    """Return the manifest projector kind, if declared."""
    projector = manifest.get("projector")
    if not isinstance(projector, dict):
        return None
    kind = cast("dict[object, object]", projector).get("kind")
    return kind if isinstance(kind, str) and kind else None


def make_module_manifest_fixed_version(manifest: JsonObject) -> int | None:
    """Return a fixed Make-native module version declared by a manifest."""
    policy = manifest.get("version_policy")
    if not isinstance(policy, dict):
        return None
    typed_policy = cast("dict[object, object]", policy)
    if typed_policy.get("kind") != "fixed":
        return None
    version = typed_policy.get("version")
    if isinstance(version, int) and version > 0:
        return version
    return None


def make_module_manifest_policy_required_keys(
    manifest: JsonObject,
    policy_name: str,
) -> tuple[str, ...]:
    """Return required keys declared under a manifest policy object."""
    policy = manifest.get(policy_name)
    if not isinstance(policy, dict):
        return ()
    required_keys = cast("dict[object, object]", policy).get("required_keys")
    if not isinstance(required_keys, list):
        return ()
    return tuple(
        str(key)
        for key in cast("list[object]", required_keys)
        if isinstance(key, str) and key
    )


def make_module_manifest_connection_families(
    manifest: JsonObject,
) -> tuple[str, ...]:
    """Return Make connection families declared by a module manifest."""
    policy = manifest.get("connection_projection_policy")
    if not isinstance(policy, dict):
        return ()
    families = cast("dict[object, object]", policy).get("families")
    if not isinstance(families, list):
        return ()
    return tuple(
        str(family)
        for family in cast("list[object]", families)
        if isinstance(family, str) and family
    )


def _load_manifest(path: Path) -> JsonObject:
    raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict):
        message = (
            f"Make module projector manifest must be a JSON object: {path}"
        )
        raise TypeError(message)
    manifest = _json_object(cast("dict[object, object]", raw))
    schema_version = manifest.get("schema_version")
    if schema_version != MAKE_MODULE_PROJECTOR_MANIFEST_SCHEMA_VERSION:
        message = (
            f"Unsupported Make module projector manifest schema"
            f"{schema_version!r}: {path}"
        )
        raise ValueError(message)
    return manifest


def _json_object(value: dict[object, object]) -> JsonObject:
    return {str(key): item for key, item in value.items()}
