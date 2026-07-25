# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 001033#repo.paths.no-output-outside-repository
# - 001034#repo.paths.no-hardcoded-repository-paths
# - 001041#repo.make-scraper.raw-spec-refresh-policy
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Repository-confined paths for Make raw-spec artifacts.

Boundary contract:
- Owns: repo-relative raw-spec paths and safe filename tokens.
- Must not: read or write files, fetch specs, parse payloads, or inspect env.
- Allows: rejecting absolute or escaping paths before callers perform IO.
- Split when: path policy differs for cache, data, temp, or dependency roots.
- Merge when: another path helper owns the same raw-spec path rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

DEFAULT_RAW_SPEC_DIR: Final[Path] = Path("temp/raw-specs-json")
DEFAULT_RAW_SPEC_MANIFEST: Final[Path] = DEFAULT_RAW_SPEC_DIR / "manifest.json"
DEFAULT_RAW_SPEC_SQLITE_DATABASE: Final[Path] = Path("src/data/pancakes.sqlite")
SAFE_PATH_FALLBACK: Final = "spec"
ALLOWED_PATH_TOKEN_CHARACTERS: Final = frozenset(("-", "_", "."))


def resolve_repo_relative_path(repo_root: Path, relative_path: Path) -> Path:
    """Resolve one repository-relative path and reject escapes.

    Returns:
        The resolved value.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    if relative_path.is_absolute() or relative_path.drive:
        message = f"Repository output path must be relative: {relative_path}"
        raise ValueError(message)

    resolved_root = repo_root.resolve()
    resolved_path = (resolved_root / relative_path).resolve()
    if not resolved_path.is_relative_to(resolved_root):
        message = (
            f"Repository output path escapes the repository: {relative_path}"
        )
        raise ValueError(message)
    return resolved_path


def relative_to_repo(repo_root: Path, path: Path) -> str:
    """Return a stable POSIX-style path relative to the repository root.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    resolved_root = repo_root.resolve()
    if path.drive and not path.is_absolute():
        message = f"Path is outside the repository: {path}"
        raise ValueError(message)
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        message = f"Path is outside the repository: {path}"
        raise ValueError(message)
    return resolved_path.relative_to(resolved_root).as_posix()


def safe_path_token(value: str) -> str:
    """Return a Windows-safe token for one Make app or version component."""
    token = "".join(
        character
        for character in value.strip()
        if character.isalnum() or character in ALLOWED_PATH_TOKEN_CHARACTERS
    )
    if set(token) <= {"."}:
        return SAFE_PATH_FALLBACK
    return token or SAFE_PATH_FALLBACK


def raw_spec_file_name(app_slug: str, app_version: str) -> str:
    """Return the canonical raw-spec file name for one app/version pair."""
    return f"{safe_path_token(app_slug)}__{safe_path_token(app_version)}.json"
