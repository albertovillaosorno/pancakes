# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Behavior tests for repository path helpers.

Boundary contract:
- Owns: source-path inventory pruning and ignored generated directory behavior.
- Must not: execute Git, read provider state, or depend on the active repository
cache layout.
- Allows: synthetic filesystem fixtures and monkeypatched local directory walks.
- Split when: source archive packaging gains its own production module.
- Merge when: another tests/support contract owns path-helper recursion
behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    import pytest

from tests.support import paths


def test_repository_source_paths_prunes_ignored_directories_before_descent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ignored cache directories are removed from the recursive walk.

    frontier.
    """
    root = tmp_path.resolve()
    walked_directories: list[tuple[str, ...]] = []

    def fake_walk(
        top: Path,
        *,
        topdown: bool,
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        assert Path(top) == root
        assert topdown is True
        root_dir_names = ["cache", ".pytest_cache", "src"]
        yield str(root), root_dir_names, ["README.md"]
        walked_directories.append(tuple(root_dir_names))
        assert root_dir_names == ["src"], (
            f"Ignored generated directories were not pruned: {root_dir_names}"
        )
        yield str(root / "src"), [], ["app.py", "runtime.sqlite"]

    monkeypatch.setattr(paths.os, "walk", fake_walk)

    assert paths.repository_source_paths(root) == ("README.md", "src/app.py")
    assert walked_directories == [("src",)]


def test_repository_source_paths_filters_ignored_prefixes_and_file_names(
    tmp_path: Path,
) -> None:
    """Path-prefix ignores and generated file suffixes stay out of source.

    inventories.
    """
    (tmp_path / "src" / "mcp" / "data" / "oauth").mkdir(parents=True)
    (tmp_path / "src" / "mcp" / "data" / "visible").mkdir(parents=True)
    _ = (
        tmp_path / "src" / "mcp" / "data" / "oauth" / "tokens.json"
    ).write_text(
        "{}\n",
        encoding="utf-8",
    )
    _ = (
        tmp_path / "src" / "mcp" / "data" / "visible" / "safe.json"
    ).write_text(
        "{}\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "src" / "runtime.sqlite").write_text(
        "not source\n", encoding="utf-8"
    )

    assert paths.repository_source_paths(tmp_path) == (
        "src/mcp/data/visible/safe.json",
    )
