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

"""Environment-backed configuration for the Make raw-spec scraper slice.

Boundary contract:
- Owns: repository-confined scraper configuration and live-readiness checks.
- Must not: fetch upstream data, write manifests, parse specs, or perform IO.
- Allows: environment-style value normalization and repo path resolution.
- Split when: configuration gains source-specific adapter setup.
- Merge when: another config module resolves the same scraper settings.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

from languages.make.raw_specs.external_ids import (
    normalize_optional_make_external_id,
)
from languages.make.raw_specs.paths import (
    DEFAULT_RAW_SPEC_DIR,
    DEFAULT_RAW_SPEC_MANIFEST,
    DEFAULT_RAW_SPEC_SQLITE_DATABASE,
    resolve_repo_relative_path,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_APPS_PER_MINUTE: Final = 15
DEFAULT_ENV_FILE_NAME: Final = ".env"
QUOTED_ENV_VALUE_MIN_LENGTH: Final = 2


class MakeScraperConfig(NamedTuple):
    """Resolved Make scraper configuration without embedding secrets."""

    repo_root: Path
    raw_spec_dir: Path = DEFAULT_RAW_SPEC_DIR
    manifest_path: Path = DEFAULT_RAW_SPEC_MANIFEST
    sqlite_database_path: Path = DEFAULT_RAW_SPEC_SQLITE_DATABASE
    live_enabled: bool = False
    api_token: str | None = None
    zone: str | None = None
    organization_id: str | None = None
    apps_per_minute: int = DEFAULT_APPS_PER_MINUTE

    @classmethod
    def from_env(
        cls,
        repo_root: Path,
        env: Mapping[str, str] | None = None,
    ) -> MakeScraperConfig:
        """Build configuration from environment-style key/value pairs.

        Returns:
            The constructed value.
        """
        values = os.environ if env is None else env
        return cls(
            repo_root=repo_root,
            raw_spec_dir=Path(
                values.get("MAKE_RAW_SPEC_DIR", str(DEFAULT_RAW_SPEC_DIR))
            ),
            manifest_path=Path(
                values.get(
                    "MAKE_RAW_SPEC_MANIFEST", str(DEFAULT_RAW_SPEC_MANIFEST)
                )
            ),
            sqlite_database_path=Path(
                values.get(
                    "PANCAKES_SQLITE_PATH",
                    str(DEFAULT_RAW_SPEC_SQLITE_DATABASE),
                )
            ),
            live_enabled=_env_flag(values.get("MAKE_LIVE_SCRAPER_ENABLED")),
            api_token=_blank_to_none(values.get("MAKE_API_TOKEN")),
            zone=_blank_to_none(values.get("MAKE_ZONE")),
            organization_id=normalize_optional_make_external_id(
                _blank_to_none(values.get("MAKE_ORGANIZATION_ID")),
                field_name="MAKE_ORGANIZATION_ID",
            ),
            apps_per_minute=_positive_int(
                values.get("MAKE_IMT_APPS_PER_MINUTE"),
                default=DEFAULT_APPS_PER_MINUTE,
            ),
        )

    @classmethod
    def from_repo_env(
        cls,
        repo_root: Path,
        env: Mapping[str, str] | None = None,
        env_file_name: str = DEFAULT_ENV_FILE_NAME,
    ) -> MakeScraperConfig:
        """Build configuration from process env and the repo env file.

        Returns:
            The constructed value.
        """
        return cls.from_env(
            repo_root,
            repo_env_values(
                repo_root=repo_root, env=env, env_file_name=env_file_name
            ),
        )

    def resolved_raw_spec_dir(self) -> Path:
        """Return the repo-confined raw-spec directory."""
        return resolve_repo_relative_path(self.repo_root, self.raw_spec_dir)

    def resolved_manifest_path(self) -> Path:
        """Return the repo-confined raw-spec manifest path."""
        return resolve_repo_relative_path(self.repo_root, self.manifest_path)

    def resolved_sqlite_database_path(self) -> Path:
        """Return the repo-confined Pancakes SQLite SSOT path."""
        return resolve_repo_relative_path(
            self.repo_root, self.sqlite_database_path
        )


def require_live_ready(config: MakeScraperConfig) -> None:
    """Reject live scraping until it is explicitly enabled and credentialed.

    Raises:
        RuntimeError: If required repository state cannot be resolved.
    """
    if not config.live_enabled:
        message = (
            "Live Make scraping is disabled; use a mocked source for tests."
        )
        raise RuntimeError(message)
    if (
        config.api_token is None
        or config.zone is None
        or config.organization_id is None
    ):
        message = (
            "Live Make scraping requires token, zone, and organization id."
        )
        raise RuntimeError(message)


def repo_env_values(
    *,
    repo_root: Path,
    env: Mapping[str, str] | None = None,
    env_file_name: str = DEFAULT_ENV_FILE_NAME,
) -> dict[str, str]:
    """Return environment values with repo-local defaults loaded first.

    Process environment values override the ignored repo `.env` file so an
    operator can rotate secrets without editing repository files.

    Returns:
        The merged environment values.
    """
    file_values = _read_env_file(repo_root / env_file_name)
    process_values = dict(os.environ if env is None else env)
    return file_values | process_values


def _read_env_file(path: Path) -> dict[str, str]:
    """Read a simple KEY=VALUE environment file if it exists.

    Returns:
        Parsed environment key/value pairs.

    Raises:
        ValueError: If a non-comment line has an empty environment key.
    """
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if not key:
            message = f"Invalid empty env key in {path} line {line_number}."
            raise ValueError(message)
        values[key] = value
    return values


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    """Parse one simple env assignment line.

    Returns:
        The parsed key/value pair, or None for blank/comment lines.

    Raises:
        ValueError: If the line is not a KEY=VALUE assignment.
    """
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].strip()
    if "=" not in stripped:
        message = "Expected KEY=VALUE env assignment; raw env line is redacted."
        raise ValueError(message)
    key, raw_value = stripped.split("=", maxsplit=1)
    return key.strip(), _strip_env_quotes(raw_value.strip())


def _strip_env_quotes(value: str) -> str:
    """Strip matching single or double quotes from one env value.

    Returns:
        The unquoted value when quotes match, otherwise the original value.
    """
    if (
        len(value) >= QUOTED_ENV_VALUE_MIN_LENGTH
        and value[0] == value[-1]
        and value[0] in {"'", '"'}
    ):
        return value[1:-1]
    return value


def _blank_to_none(value: str | None) -> str | None:
    """Normalize blank environment values.

    Returns:
        The normalized value.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_flag(value: str | None) -> bool:
    """Return whether one environment flag is enabled."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _positive_int(value: str | None, *, default: int) -> int:
    """Parse a positive integer with a deterministic fallback.

    Returns:
        The parsed value.

    Raises:
        ValueError: If an input value violates the documented contract.
    """
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        message = "Expected a positive integer; raw env value is redacted."
        raise ValueError(message) from exc
    if parsed <= 0:
        message = "Expected a positive integer; raw env value is redacted."
        raise ValueError(message)
    return parsed
