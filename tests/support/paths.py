# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Repository path helpers for nested tests.

Boundary contract:
- Owns: locating the repository root from nested test files.
- Must not: mutate sys.path, create directories, execute Git,
  or inspect file payloads.
- Allows: deterministic upward search and source-archive path inventories.
- Split when: fixture path helpers need domain-specific ownership.
- Merge when: another test helper owns identical repository-root discovery.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final


def repo_root() -> Path:
    """Return the repository root for nested test modules."""
    return repo_root_from(Path(__file__))


IGNORED_SOURCE_NAMES: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".pytest-tmp",
        ".ruff_cache",
        ".basedpyright",
        "cache",
        "dependencies",
        "logs",
        "temp",
        "bin",
        "node_modules",
        "obj",
    }
)
IGNORED_SOURCE_PATH_PREFIXES: Final[frozenset[str]] = frozenset(
    {
        "src/languages/make/data/designer-messages/raw",
        "temp/raw-specs-json",
        "src/mcp/data/oauth",
        "docs/todo/completed",
    }
)
IGNORED_SOURCE_FILE_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".bin",
        ".db",
        ".log",
        ".npy",
        ".npz",
        ".pyc",
        ".pyd",
        ".pyo",
        ".sqlite",
        ".sqlite3",
        ".tar.gz",
        ".zip",
    }
)


def repo_root_from(path: Path) -> Path:
    """Return the repository root containing a nested path.

    Raises:
        RuntimeError: If required repository state cannot be resolved.
    """
    resolved_path = path.resolve(strict=False)
    start = resolved_path.parent if resolved_path.suffix else resolved_path
    for candidate in (start, *start.parents):
        if (
            (candidate / "src").is_dir()
            and (candidate / "tests").is_dir()
            and (candidate / "LICENSE").is_file()
        ):
            return candidate
    message = "Repository root not found."
    raise RuntimeError(message)


def repository_source_paths(root: Path) -> tuple[str, ...]:
    """Return source-archive paths without requiring Git metadata."""
    resolved_root = root.resolve(strict=False)
    paths: list[str] = []
    for current_dir, dir_names, file_names in os.walk(
        resolved_root, topdown=True
    ):
        current_path = Path(current_dir)
        current_relative_path = _relative_source_path(
            current_path, resolved_root
        )
        dir_names[:] = sorted(
            directory_name
            for directory_name in dir_names
            if not ignored_source_directory(
                current_relative_path, directory_name
            )
        )

        for file_name in sorted(file_names):
            path = current_path / file_name
            relative_path = path.relative_to(resolved_root).as_posix()
            if ignored_source_file_name(path):
                continue
            if ignored_source_path(relative_path):
                continue
            paths.append(relative_path)
    return tuple(sorted(paths))


def ignored_source_directory(
    parent_relative_path: str, directory_name: str
) -> bool:
    """Return whether a directory can be pruned before recursive descent."""
    if directory_name.casefold() in IGNORED_SOURCE_NAMES:
        return True
    relative_path = (
        directory_name
        if not parent_relative_path
        else f"{parent_relative_path}/{directory_name}"
    )
    return ignored_source_path(relative_path)


def _relative_source_path(path: Path, root: Path) -> str:
    if path == root:
        return ""
    return path.relative_to(root).as_posix()


def ignored_source_path(relative_path: str) -> bool:
    """Return whether a repository-relative path is ignored source state."""
    relative_path_key = relative_path.casefold()
    return any(
        relative_path_key == ignored_path
        or relative_path_key.startswith(f"{ignored_path}/")
        for ignored_path in IGNORED_SOURCE_PATH_PREFIXES
    )


def ignored_source_file_name(path: Path) -> bool:
    """Return whether one source file name is generated local state."""
    normalized_file_name = path.name.lower()
    if normalized_file_name == ".env.example":
        return False
    if normalized_file_name in {
        ".coverage",
        ".ds_store",
        ".env example",
        "coverage.xml",
        "pytest.junit.xml",
        "thumbs.db",
    }:
        return True
    if normalized_file_name.startswith(
        (".coverage.", ".env.", "npm-debug.log")
    ):
        return True
    if any(
        marker in normalized_file_name for marker in (".db-", ".", ".sqlite3-")
    ):
        return True
    return any(
        normalized_file_name.endswith(suffix)
        for suffix in IGNORED_SOURCE_FILE_SUFFIXES
    )
