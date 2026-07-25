# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Pytest configuration for repository-wide tests.

Boundary contract:
- Owns: test import roots and root-owned Python bytecode cache routing.
- Must not: define feature fixtures or execute validation tools during import.
- Allows: deterministic sys.path setup for src and repository tool packages.
- Split when: a feature slice needs owned fixtures or test configuration.
- Merge when: another conftest duplicates repository-wide import setup.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _operator_workspace_root(repo_root: Path) -> Path:
    for candidate in repo_root.resolve().parents:
        if candidate.name == "repos":
            return candidate.parent.resolve()
    return repo_root.resolve().parent


PYTHON_CACHE_ROOT = (
    _operator_workspace_root(REPO_ROOT) / "cache" / "pancakes" / "python"
)
PYTHON_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
sys.pycache_prefix = str(PYTHON_CACHE_ROOT)

IMPORT_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "tools" / "AntiHardcoding",
    REPO_ROOT / "tools" / "ContinueSelector",
    REPO_ROOT / "tools" / "EnglishCodeComments",
    REPO_ROOT / "tools" / "GitGuard",
    REPO_ROOT / "tools" / "JsonPayloadTyping",
    REPO_ROOT / "tools" / "OnlineCiPolicy",
    REPO_ROOT / "tools" / "PythonSyntaxGuard",
    REPO_ROOT / "tools" / "RepositoryScan",
    REPO_ROOT / "tools" / "TestRigor",
    REPO_ROOT / "tools" / "TurboRunner",
    REPO_ROOT / "tools" / "UnionTypeGuard",
    REPO_ROOT / "tools" / "VersionCurrency",
)

for import_root in IMPORT_ROOTS:
    import_root_text = str(import_root)
    if import_root_text not in sys.path:
        sys.path.insert(0, import_root_text)


def pytest_sessionstart() -> None:
    """Remove pytest bootstrap bytecode after cache routing is active."""
    bootstrap_cache = Path(__file__).resolve().parent / "__pycache__"
    if bootstrap_cache.is_dir():
        shutil.rmtree(bootstrap_cache)
