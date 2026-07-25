# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for deferred Make-to-Python and platform-adapter strategy.

Boundary contract:
- Owns: static proof that portability strategy is documented as deferred.
- Must not: implement adapters, translate payloads, or validate market claims.
- Allows: fast documentation and path-boundary checks.
- Split when: an actual translation target or source-language adapter exists.
- Merge when: the language AST IR boundary contract owns this exact policy.
"""

from __future__ import annotations

from pathlib import Path

from tests.support.paths import repo_root

REPO_ROOT = repo_root()


def test_make_to_python_strategy_is_deferred_and_bounded() -> None:
    """Repository-visible strategy names portability without claiming.

    support.
    """
    text = read_repo_text(
        Path("docs/adr/make-to-python-platform-adapter-boundary-policy.md")
    )

    for required_fragment in (
        "future portability strategy ",
        "no translation target or second automation platform ",
        "current executable adapter remains Make ",
        "language-neutral IR core ",
        "Python is not a source automation language ",
        "Python may later become a translation target",
        (
            "Zapier, n8n, and other automation platforms may later become "
            "source-language adapters"
        ),
        (
            "Do not claim migration, portability, or vendor lock-in reduction "
            "as a current supported capability"
        ),
    ):
        assert required_fragment in text, (
            f"Missing deferred adapter boundary fragment: {required_fragment!r}"
        )


def test_platform_adapter_strategy_depends_on_ir_evidence() -> None:
    """The adapter policy must depend on real language and IR evidence."""
    adr_text = read_repo_text(
        Path("docs/adr/make-to-python-platform-adapter-boundary-policy.md")
    )
    ir_text = read_repo_text(Path("src/ir/README.md"))
    language_boundary_text = read_repo_text(
        Path("docs/adr/language-ast-ir-boundary-policy.md")
    )

    for required_fragment in (
        "second source automation language has real fixtures ",
        "promoted into or proven against `src/ir/**`",
        "Platform-specific behavior remains isolated in language adapters ",
        "Translation round trips have deterministic tests",
    ):
        assert required_fragment in adr_text, (
            f"Missing adapter promotion gate: {required_fragment!r}"
        )

    assert "language-neutral Pancakes IR boundary" in ir_text
    assert (
        "No Zapier, n8n, or second source-language implementation is approved"
        in (language_boundary_text)
    )


def test_no_deferred_adapter_runtime_paths_exist_yet() -> None:
    """Deferred adapter strategy must not add speculative runtime packages."""
    forbidden_runtime_paths = (
        REPO_ROOT / "src" / "translation",
        REPO_ROOT / "src" / "make_to_python",
    )
    existing_runtime_paths = [
        path for path in forbidden_runtime_paths if path.exists()
    ]
    assert not existing_runtime_paths, (
        "Deferred platform-adapter runtime paths must not exist yet: "
        f"{existing_runtime_paths}"
    )

    empty_reserved_sources = (
        REPO_ROOT / "src" / "languages" / "zapier",
        REPO_ROOT / "src" / "languages" / "n8n",
    )
    for source_path in empty_reserved_sources:
        source_children = (
            tuple(source_path.iterdir()) if source_path.exists() else ()
        )
        assert not source_children, (
            f"Deferred source-language adapters must stay empty: {source_path}"
        )

    python_children = tuple(
        (REPO_ROOT / "src" / "languages" / "python").iterdir()
    )
    assert python_children == (
        REPO_ROOT / "src" / "languages" / "python" / "README.md",
    ), (
        "Deferred Python translation target must stay documentation-only: "
        f"{python_children}"
    )


def read_repo_text(relative_path: Path) -> str:
    """Return one repository text file."""
    return " ".join(
        (REPO_ROOT / relative_path).read_text(encoding="utf-8").split()
    )
