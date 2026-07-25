# ruff: noqa: S404, S603
# Archive boundary: legacy snapshot retained for migration evidence.
# Rewrite requires a dedicated archive-to-domain migration pass.
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Current Make data layout contract tests.

Boundary contract:
- Owns: tests for Make raw-spec, catalog, and knowledge path authority.
- Must not: move data files, fetch live Make services, or test blueprint
behavior.
- Allows: static path constants, repo-local docs, and ignore-pattern checks.
- Split when: source language layout or generated artifact policy gets separate
ownership.
- Merge when: another raw-spec test owns this exact layout regression coverage.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Final

from catalog.knowledge import (
    DEFAULT_DB_SNAPSHOT_DIR,
    DEFAULT_GENERATED_FACTS_PATH,
    DEFAULT_KNOWLEDGE_DB_PATH,
    DEFAULT_LIVE_PROBE_EVIDENCE_PATH,
    MAKE_DESIGNER_MESSAGE_RAW_DIR,
)
from catalog.storage import DEFAULT_CATALOG_SNAPSHOT_PATH
from languages.make.raw_specs.paths import (
    DEFAULT_RAW_SPEC_DIR,
    DEFAULT_RAW_SPEC_MANIFEST,
    DEFAULT_RAW_SPEC_SQLITE_DATABASE,
)

from tests.support.paths import repo_root

CANONICAL_MAKE_DATA_ROOT: Final = Path("src/languages/make/data")
CANONICAL_RAW_SPEC_DIR: Final = Path("temp/raw-specs-json")
CANONICAL_RAW_SPEC_MANIFEST: Final = CANONICAL_RAW_SPEC_DIR / "manifest.json"
CANONICAL_CATALOG_SNAPSHOT: Final = (
    CANONICAL_MAKE_DATA_ROOT / "catalog" / "catalog.json"
)
CANONICAL_DB_SNAPSHOT_DIR: Final = Path("src/data/sql_snapshots")
CANONICAL_KNOWLEDGE_DB: Final = Path("src/data/pancakes.sqlite")
CANONICAL_GENERATED_FACTS_PATH: Final = Path("src/data/sql_snapshots/make.sql")
CANONICAL_DESIGNER_MESSAGE_RAW_DIR: Final = (
    CANONICAL_MAKE_DATA_ROOT / "designer-messages" / "raw"
)
FORBIDDEN_OLD_MAKE_DUMP: Final = Path("cache/make.sql")
TRACKED_SQL_SNAPSHOT_NAMES: Final = frozenset(
    {
        "aliases.sql",
        "course_rules.sql",
        "designer_message_evidence.sql",
        "live_probe_evidence.sql",
        "native_module_expectations.sql",
        "schema.sql",
        "transaction_profiles.sql",
    }
)
GENERATED_DATA_IGNORE_PATTERNS: Final = frozenset(
    {
        "src/data/*.sqlite",
        "src/data/*.sqlite*",
        "src/data/*.sqlite3",
        "src/data/*.sqlite3*",
        "src/data/*.db",
        "src/data/*.db-*",
        "src/data/sql_snapshots/make.sql",
        "src/data/sql_snapshots/*.dump.sql",
        "src/data/sql_snapshots/*.full.sql",
        "src/data/sql_snapshots/*.backup.sql",
        "src/data/sql_snapshots/*.generated.sql",
        "src/data/sql_snapshots/*.sqlite",
        "src/data/sql_snapshots/*.sqlite*",
    }
)
FORBIDDEN_TRACKED_DATA_SUFFIXES: Final = (
    ".sqlite",
    ".sqlite3",
    ".db",
    ".dump.sql",
    ".full.sql",
    ".backup.sql",
    ".generated.sql",
)
FORBIDDEN_TRACKED_DATA_PATHS: Final = frozenset(
    {
        CANONICAL_KNOWLEDGE_DB.as_posix(),
        CANONICAL_GENERATED_FACTS_PATH.as_posix(),
    }
)
TRACKED_SQL_SNAPSHOT_MAX_BYTES: Final = 1_000_000
OBSOLETE_LAYOUT_FRAGMENTS: Final = (
    "src/catalog/data/make",
    "src/catalog/raw_specs",
    "catalog.raw_specs",
    "python -B -m catalog.raw_specs",
)


def test_make_data_path_constants_use_language_owned_layout() -> None:
    """Make raw-spec, catalog, and knowledge constants use the current language.

    data root.
    """
    actual_paths = {
        "raw_spec_dir": DEFAULT_RAW_SPEC_DIR,
        "raw_spec_manifest": DEFAULT_RAW_SPEC_MANIFEST,
        "raw_spec_sqlite_database": DEFAULT_RAW_SPEC_SQLITE_DATABASE,
        "catalog_snapshot": DEFAULT_CATALOG_SNAPSHOT_PATH,
        "db_snapshots": DEFAULT_DB_SNAPSHOT_DIR,
        "knowledge_db": DEFAULT_KNOWLEDGE_DB_PATH,
        "generated_facts": DEFAULT_GENERATED_FACTS_PATH,
        "designer_message_raw": MAKE_DESIGNER_MESSAGE_RAW_DIR,
        "live_probe_evidence": DEFAULT_LIVE_PROBE_EVIDENCE_PATH,
    }
    expected_paths = {
        "raw_spec_dir": CANONICAL_RAW_SPEC_DIR,
        "raw_spec_manifest": CANONICAL_RAW_SPEC_MANIFEST,
        "raw_spec_sqlite_database": CANONICAL_KNOWLEDGE_DB,
        "catalog_snapshot": CANONICAL_CATALOG_SNAPSHOT,
        "db_snapshots": CANONICAL_DB_SNAPSHOT_DIR,
        "knowledge_db": CANONICAL_KNOWLEDGE_DB,
        "generated_facts": CANONICAL_GENERATED_FACTS_PATH,
        "designer_message_raw": CANONICAL_DESIGNER_MESSAGE_RAW_DIR,
        "live_probe_evidence": CANONICAL_DB_SNAPSHOT_DIR
        / "live_probe_evidence.sql",
    }

    assert actual_paths == expected_paths, (
        f"Make data path constants drifted: {actual_paths}"
    )


def test_large_make_sql_dump_is_not_old_cache_authority() -> None:
    """Generated Make SQL dumps cannot remain in the old cache location."""
    forbidden_path = repo_root() / FORBIDDEN_OLD_MAKE_DUMP
    assert not forbidden_path.exists(), (
        f"Remove generated Make SQL dump from old cache path: "
        f"{FORBIDDEN_OLD_MAKE_DUMP}"
    )


def test_generated_sqlite_and_dump_artifacts_are_ignored() -> None:
    """Large generated SQLite and SQL dump classes remain local-only."""
    gitignore_lines = (
        (repo_root() / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
    missing_patterns = sorted(
        GENERATED_DATA_IGNORE_PATTERNS.difference(gitignore_lines)
    )
    assert not missing_patterns, (
        f"Generated SQLite and SQL dump patterns are not ignored: "
        f"{missing_patterns}"
    )


def test_generated_sqlite_and_dump_artifacts_are_not_tracked() -> None:
    """Local SQLite databases and generated dumps must not become tracked.

    artifacts.
    """
    tracked_data_artifacts = sorted(
        tracked_path
        for tracked_path in tracked_files()
        if is_forbidden_tracked_data_artifact(tracked_path)
    )

    assert not tracked_data_artifacts, (
        f"Generated SQLite or SQL dump artifacts are tracked: "
        f"{tracked_data_artifacts}"
    )


def test_sql_snapshot_inventory_documents_retention_policy() -> None:
    """Snapshot inventory lists tracked snapshots, generated classes, and.

    restore policy.
    """
    inventory = (
        repo_root() / CANONICAL_DB_SNAPSHOT_DIR / "README.md"
    ).read_text(encoding="utf-8")
    missing_tracked_snapshots = sorted(
        snapshot_name
        for snapshot_name in TRACKED_SQL_SNAPSHOT_NAMES
        if snapshot_name not in inventory
    )
    required_policy_terms = {
        "SQLite SSOT",
        "Ignored Local Artifacts",
        "Regeneration",
        "Retention Policy",
        "Restore Policy",
        "Review Budget",
        "make.sql",
        "pancakes.sqlite",
        "*.dump.sql",
        "*.full.sql",
        "*.backup.sql",
        "*.generated.sql",
    }
    missing_policy_terms = sorted(
        term for term in required_policy_terms if term not in inventory
    )

    assert not missing_tracked_snapshots, (
        f"Snapshot inventory omits tracked snapshots: "
        f"{missing_tracked_snapshots}"
    )
    assert not missing_policy_terms, (
        f"Snapshot inventory omits retention policy terms: "
        f"{missing_policy_terms}"
    )


def test_tracked_sql_snapshots_stay_reviewable() -> None:
    """Tracked SQL restore snapshots stay small and code-reviewable."""
    oversized_snapshots = {
        snapshot_name: (repo_root() / CANONICAL_DB_SNAPSHOT_DIR / snapshot_name)
        .stat()
        .st_size
        for snapshot_name in TRACKED_SQL_SNAPSHOT_NAMES
        if (repo_root() / CANONICAL_DB_SNAPSHOT_DIR / snapshot_name)
        .stat()
        .st_size
        > TRACKED_SQL_SNAPSHOT_MAX_BYTES
    }

    assert not oversized_snapshots, (
        "Tracked SQL snapshots exceeded the review budget: "
        f"{oversized_snapshots}"
    )


def test_make_raw_spec_ingest_paths_are_local_generated_state() -> None:
    """Generated Make ingest outputs stay ignored and outside canonical source.

    files.
    """
    gitignore_lines = (
        (repo_root() / ".gitignore").read_text(encoding="utf-8").splitlines()
    )
    search_ignore_lines = (
        (repo_root() / ".ignore").read_text(encoding="utf-8").splitlines()
    )
    required_ignored_paths = {
        "cache/",
        "temp/",
        "data/make/",
        CANONICAL_DESIGNER_MESSAGE_RAW_DIR.as_posix() + "/",
        "src/data/*.sqlite",
        "src/data/*.sqlite*",
        "src/data/sql_snapshots/make.sql",
    }

    missing_paths = sorted(required_ignored_paths.difference(gitignore_lines))
    assert not missing_paths, (
        f"Generated Make data paths are not ignored: {missing_paths}"
    )

    missing_search_paths = sorted(
        GENERATED_DATA_IGNORE_PATTERNS.difference(search_ignore_lines)
    )
    assert not missing_search_paths, (
        "Generated Make data paths are not excluded from local search: "
        f"{missing_search_paths}"
    )


def test_operator_docs_use_current_make_language_data_layout() -> None:
    """Docs and examples must not point agents back to obsolete Make data.

    roots.
    """
    checked_paths = (
        ".env.example",
        "src/catalog/README.md",
        "src/catalog/knowledge/README.md",
        "src/languages/make/raw_specs/README.md",
        "src/languages/make/raw_specs/__main__.py",
    )
    stale_references: dict[str, list[str]] = {}

    for relative_path in checked_paths:
        text = (repo_root() / relative_path).read_text(encoding="utf-8")
        stale_fragments = [
            fragment
            for fragment in OBSOLETE_LAYOUT_FRAGMENTS
            if fragment in text
        ]
        if stale_fragments:
            stale_references[relative_path] = stale_fragments

    assert not stale_references, (
        f"Obsolete Make data paths remain: {stale_references}"
    )


def tracked_files() -> frozenset[str]:
    """Return tracked repository files without reading ignored large local.

    dumps.
    """
    completed = subprocess.run(
        [shutil.which("git") or "git", "ls-files"],
        cwd=repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return frozenset(completed.stdout.splitlines())


def is_forbidden_tracked_data_artifact(relative_path: str) -> bool:
    """Return if a tracked path is a generated database or dump artifact."""
    if relative_path in FORBIDDEN_TRACKED_DATA_PATHS:
        return True
    if not relative_path.startswith(CANONICAL_DB_SNAPSHOT_DIR.as_posix() + "/"):
        return False
    return relative_path.endswith(FORBIDDEN_TRACKED_DATA_SUFFIXES)
