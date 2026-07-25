# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for the Make-focused MCP tool scope.

Boundary contract:
- Owns: MCP scope policy coverage for Make scenario-focused tools.
- Must not: execute MCP tools, start transports, or validate OAuth behavior.
- Allows: registry description checks and ADR/README scope assertions.
- Split when: future non-Make commercial helper scopes get their own ADRs.
- Merge when: another MCP scope test duplicates these exact policy assertions.
"""

from __future__ import annotations

from pathlib import Path

from mcp import mcp_tool_registry

MCP_POLICY_ADR = Path("docs/adr/mcp-server-slice-policy.md")
MCP_README = Path("src/mcp/README.md")


def test_mcp_tool_scope_is_make_scenario_focused() -> None:
    """MCP tools stay focused on Make scenario work, not generic repo.

    operations.
    """
    normalized_adr_text = " ".join(
        MCP_POLICY_ADR.read_text(encoding="utf-8").split()
    )
    normalized_readme_text = " ".join(
        MCP_README.read_text(encoding="utf-8").split()
    )

    required_adr_fragments = (
        "repo.mcp.make-scenario-tool-scope ",
        "repo.mcp.scenario-builder-micro-tools ",
        "Make.com scenario generation and validation",
        (
            "Scenario-builder MCP tools may mutate only repository-local "
            "scratch "
            "workspace artifacts and finalized project scenario JSON files"
        ),
        '"final_artifact_root": "projects"',
        "not to expose generic technical repository operations ",
        "Upwork proposal support only after a future ADR ",
        "portfolio support only after a future ADR",
    )
    missing_adr_fragments = [
        fragment
        for fragment in required_adr_fragments
        if fragment not in normalized_adr_text
    ]
    assert not (missing_adr_fragments), (
        f"MCP scope policy is missing fragments: {missing_adr_fragments}"
    )

    required_readme_fragments = (
        "Make.com scenario-oriented",
        (
            "The only write-like tool families in this boundary are project "
            "node edits, "
            "local project draft creation, local Make artifact projection "
            "writes, local package "
            "writes, linter quarantine intake, guarded linter rule editor "
            "dispositions, backlog "
            "intake/end, and the development-only catalog semantic loop. "
            "Business lifecycle, "
            "delivery, dashboard, payment, and customer writes are not "
            "Pancakes "
            "MCP tools"
        ),
        (
            "Generic JSON read/write, JSON patch, scenario workspace, scenario "
            "command"
        ),
        "not a general repository administration API ",
        "Future Upwork proposal or portfolio helpers require a separate ADR",
    )
    missing_readme_fragments = [
        fragment
        for fragment in required_readme_fragments
        if fragment not in normalized_readme_text
    ]
    assert not (missing_readme_fragments), (
        f"MCP README is missing scope fragments: {missing_readme_fragments}"
    )

    domain_terms = (
        "Make ",
        "blueprint ",
        "scenario",
        "AST",
        "raw-spec ",
        "catalog ",
        "project",
    )
    forbidden_technical_terms = ("git", "shell", "filesystem administration")
    for tool in mcp_tool_registry():
        tool_text = " ".join(
            (
                tool.description,
                tool.output_description,
                " ".join(field.description for field in tool.input_fields),
            )
        )
        normalized_tool_text = tool_text.casefold()
        assert any(
            term.casefold() in normalized_tool_text for term in domain_terms
        ), f"MCP tool is not Make scenario focused: {tool.name} {tool_text}"
        forbidden_hits = [
            term
            for term in forbidden_technical_terms
            if term.casefold() in tool_text.casefold()
        ]
        assert not (forbidden_hits), (
            f"MCP tool exposes generic repo operations: {tool.name} "
            f"{forbidden_hits}"
        )


def test_mcp_ai_privacy_and_redaction_boundary_is_documented() -> None:
    """MCP docs state the AI assistance boundary without making public.

    claims.
    """
    normalized_adr_text = " ".join(
        MCP_POLICY_ADR.read_text(encoding="utf-8").split()
    )
    normalized_readme_text = " ".join(
        MCP_README.read_text(encoding="utf-8").split()
    )

    required_adr_fragments = (
        "repo.mcp.ai-assisted-privacy-and-redaction-boundary",
        (
            "AI assistance is allowed only as an operator-directed editing and "
            "review aid"
        ),
        "account privacy controls enabled when available",
        (
            "redact secrets, webhook URLs, account ids, emails, customer "
            "identifiers"
        ),
        "raw Make blueprint JSON as local evidence for narrow debugging ",
        "narrow local JSON slices may be inspected or fine-tuned manually",
        (
            "public copy about AI assistance, privacy options, or redaction "
            "requires legal review"
        ),
        (
            "do not claim local-only handling when ChatGPT.com, email, hosted "
            "storage"
        ),
    )
    missing_adr_fragments = [
        fragment
        for fragment in required_adr_fragments
        if fragment not in normalized_adr_text
    ]
    assert not (missing_adr_fragments), (
        f"MCP AI privacy ADR is missing fragments: {missing_adr_fragments}"
    )

    required_readme_fragments = (
        (
            "AI assistance is allowed as an operator-directed editing and "
            "review "
            "aid"
        ),
        "applicable account privacy controls enabled ",
        "secrets or personal identifiers redacted ",
        "raw Make blueprint JSON is local evidence for narrow debugging ",
        "Manual JSON fine tuning is an exception for small local slices ",
        "Public copy about AI assistance, privacy options, redaction",
    )
    missing_readme_fragments = [
        fragment
        for fragment in required_readme_fragments
        if fragment not in normalized_readme_text
    ]
    assert not (missing_readme_fragments), (
        f"MCP README is missing AI privacy fragments: "
        f"{missing_readme_fragments}"
    )
