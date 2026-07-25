# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Make adapter boundary tests.

Boundary contract:
- Owns: static checks that Make export behavior stays inside
`src/languages/make/**`.
- Must not: test live Make APIs, catalog scraping, or generic AST behavior.
- Allows: repository text checks for import boundaries and compatibility
wrappers.
- Split when: a general architecture-boundary test suite owns all adapter
boundaries.
- Merge when: another Make adapter test enforces the same vendor-boundary
contract.
"""

from __future__ import annotations

from pathlib import Path

from tests.support.paths import repo_root

REPO_ROOT = repo_root()


def test_make_native_export_shape_is_not_implemented_in_ast_wrappers() -> None:
    """Make-specific export details must live in the Make language adapter."""
    make_export = read_repo_text(Path("src/languages/make/blueprint_export.py"))
    ast_renderer = read_repo_text(Path("src/blueprints/ast/renderer.py"))
    ast_render_validation = read_repo_text(
        Path("src/blueprints/ast/render_validation.py")
    )

    for required_fragment in (
        "MAKE_NATIVE_NODE_METADATA_KEYS",
        "PANCAKES_PRIVATE_METADATA_KEYS",
        "DEFAULT_MAKE_MODULE_VERSION",
        "_render_native_parameters",
        "_render_module_version",
        "_render_node_metadata",
    ):
        assert required_fragment in make_export, (
            f"Make export lost adapter-owned behavior: {required_fragment!r}"
        )
        assert required_fragment not in ast_renderer, (
            f"AST renderer reintroduced Make export behavior: "
            f"{required_fragment!r}"
        )
        assert required_fragment not in ast_render_validation, (
            f"AST render validation reintroduced Make export behavior: "
            f"{required_fragment!r}"
        )


def test_runtime_callers_use_make_adapter_imports_for_make_export() -> None:
    """Runtime Make rendering must not be exposed through the public MCP.

    server.
    """
    assert not (REPO_ROOT / "src/mcp/scenario_builder.py").exists()

    make_export = read_repo_text(Path("src/languages/make/blueprint_export.py"))
    make_render_validation = read_repo_text(
        Path("src/languages/make/render_validation.py")
    )

    assert "class MakeBlueprintRenderError" in make_export
    assert "def render_and_validate_blueprint" in make_render_validation


def test_make_parameter_aliases_stay_in_make_adapter() -> None:
    """Native Make parameter aliases must not move into generic AST.

    rendering.
    """
    parameter_aliases = read_repo_text(
        Path("src/languages/make/parameter_aliases.py")
    )
    ast_renderer = read_repo_text(Path("src/blueprints/ast/renderer.py"))

    assert "MAKE_CONNECTION_PARAMETER_ALIASES" in parameter_aliases
    assert "__IMTCONN__" in parameter_aliases
    assert "MAKE_CONNECTION_PARAMETER_ALIASES" not in ast_renderer
    assert "__IMTCONN__" not in ast_renderer


def test_legacy_ast_renderer_paths_are_compatibility_only() -> None:
    """Compatibility paths may re-export but must not own Make-specific.

    logic.
    """
    ast_renderer = read_repo_text(Path("src/blueprints/ast/renderer.py"))
    ast_render_validation = read_repo_text(
        Path("src/blueprints/ast/render_validation.py")
    )

    assert "Compatibility import path" in ast_renderer
    assert "from languages.make.blueprint_export import" in ast_renderer
    assert "def render_make_blueprint_payload" not in ast_renderer
    assert "class MakeBlueprintRenderReport" not in ast_renderer

    assert "Compatibility import path" in ast_render_validation
    assert (
        "from languages.make.render_validation import" in ast_render_validation
    )
    assert "def render_and_validate_blueprint" not in ast_render_validation
    assert (
        "class MakeBlueprintRenderValidationReport" not in ast_render_validation
    )


def read_repo_text(relative_path: Path) -> str:
    """Return one repository text file."""
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")
