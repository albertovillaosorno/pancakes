# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001064#repo.make-knowledge.build-command
# - 001064#repo.make-knowledge.snapshot-dump-command
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Command-line entrypoint for Make knowledge-store build, dump, and status.

Boundary contract:
- Owns: parsing CLI arguments and writing JSON command reports.
- Must not: implement SQLite persistence, raw-spec parsing, or live scraping.
- Allows: small command dispatch over repository-confined knowledge operations.
- Split when: build, dump, and status need separate executable entrypoints.
- Merge when: another CLI exposes the same command contract.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from catalog.json_payloads import normalize_json_object
from catalog.knowledge.catalog_plan_ssot import connect_catalog_plan_ssot
from catalog.knowledge.catalog_quality_reset import (
    DEFAULT_CATALOG_RESET_RUN_ID,
    DEFAULT_CATALOG_RESET_SOURCE_REF,
    catalog_reset_units_from_raw_specs,
    start_catalog_quality_reset_run,
)
from catalog.knowledge.schema import read_engine_schema_sql
from catalog.knowledge.storage import (
    DEFAULT_GENERATED_FACTS_PATH,
    build_knowledge_store,
    dump_knowledge_store,
    knowledge_report_to_json,
    knowledge_store_status,
)

if TYPE_CHECKING:
    from catalog.models import JsonObject


class KnowledgeCommandNamespace(argparse.Namespace):
    """Typed namespace for knowledge-store CLI commands."""

    command: str
    database_path: Path
    output_path: Path
    repo_root: Path
    reseed_active: bool
    run_id: str
    snapshot_dir: Path


def main(argv: list[str] | None = None) -> int:
    """Run the Make knowledge-store CLI.

    Returns:
        The process exit status.
    """
    args = _parse_args(argv)
    try:
        payload = _run(args)
    except (
        FileNotFoundError,
        OSError,
        sqlite3.Error,
        TypeError,
        ValueError,
    ) as exc:
        _write_json(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
        return 1
    _write_json(payload)
    return 0


def _run(args: KnowledgeCommandNamespace) -> JsonObject:
    """Run one parsed command.

    Returns:
        The JSON command payload.

    Raises:
        ValueError: If the command is unknown.
    """
    if args.command == "build":
        return knowledge_report_to_json(
            build_knowledge_store(
                repo_root=args.repo_root,
                database_path=args.database_path,
                snapshot_dir=args.snapshot_dir,
            )
        )
    if args.command == "ensure":
        return _ensure_payload(args)
    if args.command == "dump":
        return knowledge_report_to_json(
            dump_knowledge_store(
                repo_root=args.repo_root,
                database_path=args.database_path,
                output_path=args.output_path,
            )
        )
    if args.command == "reset":
        return _reset_payload(args)
    if args.command == "status":
        return knowledge_report_to_json(
            knowledge_store_status(
                repo_root=args.repo_root, database_path=args.database_path
            )
        )
    message = f"Unknown knowledge command: {args.command}"
    raise ValueError(message)


def _ensure_payload(args: KnowledgeCommandNamespace) -> JsonObject:
    """Rebuild generated SQLite when status proves it is absent or stale.

    Returns:
        The JSON payload for the ensure command.
    """
    before = knowledge_store_status(
        repo_root=args.repo_root, database_path=args.database_path
    )
    if before.status in {
        "empty_database",
        "missing_database",
        "stale_manifest",
        "stale_schema",
    }:
        build = build_knowledge_store(
            repo_root=args.repo_root,
            database_path=args.database_path,
            snapshot_dir=args.snapshot_dir,
        )
        after = knowledge_store_status(
            repo_root=args.repo_root, database_path=args.database_path
        )
        return {
            "status": after.status,
            "before_status": before.status,
            "rebuilt": True,
            "database_path": after.database_path,
            "raw_spec_manifest_path": after.raw_spec_manifest_path,
            "build_report": knowledge_report_to_json(build),
            "status_report": knowledge_report_to_json(after),
        }
    return {
        "status": before.status,
        "before_status": before.status,
        "rebuilt": False,
        "database_path": before.database_path,
        "raw_spec_manifest_path": before.raw_spec_manifest_path,
        "status_report": knowledge_report_to_json(before),
    }


def _reset_payload(args: KnowledgeCommandNamespace) -> JsonObject:
    """Start the canonical catalog run from current SQLite raw-spec records.

    Returns:
        The JSON reset receipt.

    Raises:
        ValueError: If the current SQLite file has no raw-spec records to seed.
    """
    with closing(
        connect_catalog_plan_ssot(
            repo_root=args.repo_root, database_path=args.database_path
        )
    ) as connection:
        _ = connection.executescript(read_engine_schema_sql())
        active_run_id = _active_catalog_run_id(connection)
        if active_run_id is not None and not args.reseed_active:
            return {
                "status": "already_active",
                "run_id": active_run_id,
                "database_path": args.database_path.as_posix(),
                "reset_started": False,
            }
        if (
            active_run_id is not None
            and _non_queued_active_unit_count(connection) > 0
        ):
            message = (
                "Refusing to reseed an active catalog run after units were "
                "leased or saved."
            )
            raise ValueError(message)
        units = catalog_reset_units_from_raw_specs(connection=connection)
        if not units:
            message = (
                "No current SQLite raw-spec records are available for "
                "catalog reset."
            )
            raise ValueError(message)
        report = start_catalog_quality_reset_run(
            connection=connection,
            run_id=args.run_id,
            units=units,
            source_ref=DEFAULT_CATALOG_RESET_SOURCE_REF,
            observed_at_utc=datetime.now(UTC).isoformat(),
        )
    return {
        **normalize_json_object(dict(report._asdict())),
        "status": "reset_started",
        "database_path": args.database_path.as_posix(),
        "reseed_active": args.reseed_active,
        "reset_started": True,
    }


def _active_catalog_run_id(connection: sqlite3.Connection) -> str | None:
    row = cast(
        "sqlite3.Row | None",
        connection.execute(
            """
            SELECT run_id
            FROM catalog_runs
            WHERE run_status = 'active'
            ORDER BY created_at_utc DESC, run_id
            LIMIT 1
            """
        ).fetchone(),
    )
    if row is None:
        return None
    return cast("str", row["run_id"])


def _non_queued_active_unit_count(connection: sqlite3.Connection) -> int:
    row = cast(
        "tuple[int]",
        connection.execute(
            """
            SELECT COUNT(*)
            FROM catalog_units AS units
            JOIN catalog_runs AS runs ON runs.run_id = units.run_id
            WHERE runs.run_status = 'active'
              AND units.status != 'queued'
            """
        ).fetchone(),
    )
    return row[0]


def _parse_args(argv: list[str] | None) -> KnowledgeCommandNamespace:
    """Parse CLI arguments into a typed namespace.

    Returns:
        The parsed CLI namespace.

    Raises:
        TypeError: If argparse returns an unexpected namespace.
    """
    namespace = KnowledgeCommandNamespace()
    parsed = _argument_parser().parse_args(argv, namespace=namespace)
    if parsed is not namespace:
        message = "argparse returned an unexpected namespace instance."
        raise TypeError(message)
    return namespace


def _argument_parser() -> argparse.ArgumentParser:
    """Build the knowledge-store CLI parser.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(prog="python -B -m catalog.knowledge")
    _ = parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    _ = parser.add_argument(
        "--database-path",
        type=Path,
        default=Path("src/data/pancakes.sqlite"),
    )
    _ = parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=Path("src/data/sql_snapshots"),
    )
    _ = parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_GENERATED_FACTS_PATH,
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    _ = subcommands.add_parser(
        "build", help="rebuild the generated SQLite knowledge store"
    )
    _ = subcommands.add_parser(
        "ensure", help="rebuild generated SQLite only when needed"
    )
    _ = subcommands.add_parser(
        "dump", help="dump SQLite facts into ignored cache SQL"
    )
    reset = subcommands.add_parser(
        "reset", help="start the canonical catalog run"
    )
    _ = reset.add_argument("--run-id", default=DEFAULT_CATALOG_RESET_RUN_ID)
    _ = reset.add_argument(
        "--reseed-active",
        action="store_true",
        help="rebuild the active reset queue only while no units are completed",
    )
    _ = subcommands.add_parser("status", help="print knowledge-store status")
    return parser


def _write_json(payload: JsonObject) -> None:
    """Write one JSON object to stdout."""
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    _ = sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
