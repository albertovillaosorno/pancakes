# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 000010#repo.config.python.active-src-package-boundary
# - 000017#repo.code.architecture.vertical-slices-and-cqrs.repo-wide
# - 001044#repo.make-ast.contract
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Contract tests for the language, AST, and IR boundary.

Boundary contract:
- Owns: static proof that Make, AST, and IR ownership stays documented.
- Must not: implement Zapier, parse blueprints, call live services, or move
data.
- Allows: fast documentation, path existence, and public IR model checks.
- Split when: translation round-trip tests become executable.
- Merge when: another architecture contract owns this exact boundary.
"""

from __future__ import annotations

from pathlib import Path

from tests.support.paths import repo_root

REPO_ROOT = repo_root()


def test_language_ast_ir_boundary_documents_ir_centered_product_core() -> None:
    """Current docs keep Make as a language adapter and IR as the product.

    core.
    """
    required_fragments = {
        Path("src/languages/README.md"): (
            "source automation platform language boundaries ",
            "src/languages/make/",
            "Make is one language adapter ",
            "not the product core ",
            "Future Zapier ",
            "n8n ",
            "peer adapters ",
            "Python is not a source automation language",
        ),
        Path("src/languages/make/README.md"): (
            "Make.com language adapter boundary ",
            "Make JSON interpretation ",
            "only executable source language adapter today ",
            "not treat Make as the product core ",
            "src/ir/**",
            "src/blueprints/**",
        ),
        Path("src/blueprints/README.md"): (
            "current compatibility runtime ",
            "Make-named records ",
            "src/languages/make/**",
            "src/ir/**",
            "product-level semantic contract",
        ),
        Path("src/ir/README.md"): (
            "language-neutral Pancakes IR boundary ",
            "product-level semantic core ",
            "general directed acyclic graph ",
            "Make is the first implemented source language adapter ",
            "must not claim Zapier ",
            "general DAG representation",
        ),
        Path("src/blueprints/ast/README.md"): (
            "Pancakes AST ",
            "Product-facing code should prefer the `PancakesAst*` aliases ",
            "Make as a language adapter ",
            "src/languages/make/**",
        ),
        Path("docs/adr/language-ast-ir-boundary-policy.md"): (
            "src/languages/**",
            "src/blueprints/ast/**",
            "src/ir/**",
            "IR-centered automation analysis core ",
            "Make as the first implemented source-language adapter",
            (
                "No Zapier, n8n, or second source-language implementation is "
                "approved"
            ),
        ),
    }

    for relative_path, fragments in required_fragments.items():
        text = read_repo_text(relative_path)
        missing = [fragment for fragment in fragments if fragment not in text]
        assert not missing, (
            f"{relative_path} is missing boundary fragments: {missing}"
        )


def test_language_tree_keeps_future_sources_empty_while_ir_is_executable() -> (
    None
):
    """Future source languages stay empty while IR has a minimal executable.

    core.
    """
    assert (REPO_ROOT / "src" / "languages" / "make").is_dir(), (
        "Make must remain the active source language boundary."
    )
    for future_language in ("zapier", "n8n"):
        language_path = REPO_ROOT / "src" / "languages" / future_language
        language_children = (
            tuple(language_path.iterdir()) if language_path.exists() else ()
        )
        assert not language_children, (
            f"{future_language} may be an empty reserved peer only until real "
            f"evidence exists: {language_children}"
        )

    ir_children = {path.name for path in (REPO_ROOT / "src" / "ir").iterdir()}
    assert {
        "README.md",
        "__init__.py ",
        "models.py ",
        "graph.py",
    } <= ir_children, (
        f"IR must expose a minimal language-neutral runtime core: {ir_children}"
    )


def read_repo_text(relative_path: Path) -> str:
    """Return one repository text file."""
    return " ".join(
        (REPO_ROOT / relative_path).read_text(encoding="utf-8").split()
    )
