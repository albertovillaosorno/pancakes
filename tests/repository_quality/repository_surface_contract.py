# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Repository active-surface documentation contracts.

Boundary contract:
- Owns: repository entrypoint claims about active command and backlog
  surfaces.
- Must not: validate ADR history, rewrite completed evidence, or inspect
  provider state.
- Allows: reading authored repository Markdown that defines the current local
  surface.
- Split when: command-surface docs gain their own repository-owned manifest.
- Merge when: another repository-quality contract owns this exact entrypoint
  claim.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
README_PATH = REPO_ROOT / "README.md"
TESTS_README_PATH = REPO_ROOT / "tests" / "README.md"


def test_readme_does_not_present_docs_todo_as_active_scheduler() -> None:
    """Require Schoenwald ownership of active executable work."""
    text = README_PATH.read_text(encoding="utf-8")

    assert "executable backlog\nstate stays in `docs/todo/`" not in text
    assert "external Schoenwald `todo/` control plane" in text
    assert (
        "`docs/todo/**` references in ADR evidence are archive pointers" in text
    )


def test_tests_readme_uses_schoenwald_command_profile() -> None:
    """Require command-layer test entrypoint documentation."""
    text = TESTS_README_PATH.read_text(encoding="utf-8")

    assert "dependencies\\python" not in text
    assert "python.exe -m pytest" not in text
    assert "python -B" in text
    assert "-Command pancakes.test" in text
    assert "-Execute" in text
    assert "legacy\npackage scripts" in text
    assert "as command authority" in text
