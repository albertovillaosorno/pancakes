# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001041#repo.make-scraper.raw-specs.command-query-boundary
# - 001041#repo.make-scraper.raw-specs.live-scraping-disabled-by-default
# - 001041#repo.make-scraper.raw-specs.repo-local-cache
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Command-line entrypoint for raw-spec status and live refresh.

Boundary contract:
- Owns: service-facing raw-spec status and live refresh command parsing.
- Must not: implement HTTP transport, parse manifests, or compile catalogs.
- Allows: JSON operator output and repo-local environment loading.
- Split when: status and refresh commands need independent executable surfaces.
- Merge when: another CLI exposes the same raw-spec command contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from catalog.knowledge import build_knowledge_store, knowledge_report_to_json

from languages.make.raw_specs.config import MakeScraperConfig
from languages.make.raw_specs.live import MakeApiError
from languages.make.raw_specs.refresh import refresh_raw_specs_from_live_config
from languages.make.raw_specs.status import raw_spec_refresh_status

if TYPE_CHECKING:
    from languages.make.raw_specs.models import (
        JsonObject,
        RawSpecRefreshStatus,
        RawSpecSyncReport,
    )


class RawSpecCommandNamespace(argparse.Namespace):
    """Typed namespace for raw-spec CLI commands."""

    command: str
    env_file: str
    limit: int | None
    repo_root: Path
    search: str | None


def main(argv: list[str] | None = None) -> int:
    """Run the raw-spec CLI.

    Returns:
        The process exit status.
    """
    args = _parse_args(argv)
    try:
        payload = _run(args)
    except RuntimeError as exc:
        _write_json(_error_payload("configuration_error", str(exc)))
        return 3
    except (MakeApiError, OSError, TypeError, ValueError) as exc:
        _write_json(_error_payload(type(exc).__name__, str(exc)))
        return 1
    _write_json(payload)
    return 0


def _run(args: RawSpecCommandNamespace) -> JsonObject:
    """Run one parsed CLI command.

    Returns:
        The command JSON payload.

    Raises:
        ValueError: If the command is unknown.
    """
    config = MakeScraperConfig.from_repo_env(
        args.repo_root,
        env_file_name=args.env_file,
    )
    if args.command == "status":
        return _json_object(raw_spec_refresh_status(config))
    if args.command == "refresh":
        report = refresh_raw_specs_from_live_config(
            config=config,
            search=args.search,
            limit=args.limit,
        )
        payload = _json_object(report)
        payload["knowledge_store"] = knowledge_report_to_json(
            build_knowledge_store(repo_root=config.repo_root)
        )
        payload["status"] = "refreshed"
        return payload
    message = f"Unknown raw-spec command: {args.command}"
    raise ValueError(message)


def _parse_args(argv: list[str] | None) -> RawSpecCommandNamespace:
    """Parse CLI arguments into a typed namespace.

    Returns:
        The parsed CLI namespace.

    Raises:
        TypeError: If argparse returns an unexpected namespace.
    """
    namespace = RawSpecCommandNamespace()
    parsed_namespace = _argument_parser().parse_args(argv, namespace=namespace)
    if parsed_namespace is not namespace:
        message = "argparse returned an unexpected namespace instance."
        raise TypeError(message)
    return namespace


def _argument_parser() -> argparse.ArgumentParser:
    """Build the raw-spec CLI parser.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -B -m languages.make.raw_specs"
    )
    _ = parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    _ = parser.add_argument("--env-file", default=".env")
    subcommands = parser.add_subparsers(dest="command", required=True)
    _ = subcommands.add_parser(
        "status", help="print local SQLite raw-spec status"
    )
    refresh_parser = subcommands.add_parser(
        "refresh",
        help="download all live Make raw specs into src/data/pancakes.sqlite",
    )
    _ = refresh_parser.add_argument("--search", default=None)
    _ = refresh_parser.add_argument(
        "--limit", type=_non_negative_int, default=None
    )
    return parser


def _non_negative_int(value: str) -> int:
    """Parse a non-negative integer argument.

    Returns:
        The parsed non-negative integer.

    Raises:
        argparse.ArgumentTypeError: If the value is negative.
    """
    try:
        parsed = int(value)
    except ValueError as exc:
        message = (
            "Expected a non-negative integer; raw argument value is redacted."
        )
        raise argparse.ArgumentTypeError(message) from exc
    if parsed < 0:
        message = (
            "Expected a non-negative integer; raw argument value is redacted."
        )
        raise argparse.ArgumentTypeError(message)
    return parsed


def _json_object(value: RawSpecRefreshStatus | RawSpecSyncReport) -> JsonObject:
    """Convert one typed record payload into a JSON object.

    Returns:
        The JSON object.
    """
    return cast("JsonObject", dict(value._asdict()))


def _error_payload(error_type: str, message: str) -> JsonObject:
    """Return a non-secret error payload for operators and services."""
    return {
        "status": "failed",
        "error_type": error_type,
        "message": message,
    }


def _write_json(payload: JsonObject) -> None:
    """Write one JSON object to stdout."""
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    _ = sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
