# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for product-safe enterprise handoff readiness.

Boundary contract:
- Owns: repository-visible handoff policy for an external technical owner.
- Must not: expose private strategy, weaken validation gates, or define sales
copy.
- Allows: static checks over the handoff-readiness ADR.
- Split when: bootstrap, waiver, or audit guides get executable checks.
- Merge when: another repository-readiness contract owns the same policy.
"""

from __future__ import annotations

from tests.support.paths import repo_root

HANDOFF_ADR = (
    repo_root() / "docs" / "adr" / "enterprise-handoff-readiness-policy.md"
)


def test_enterprise_handoff_policy_requires_operational_materials() -> None:
    """Handoff readiness needs enough docs for an external technical owner."""
    text = read_handoff_adr()

    for required_fragment in (
        "Architecture overview for the IR-centered engine and Make adapter",
        "Validation gate profile and command entry points",
        "Fresh-clone bootstrap path",
        "Rule authoring guide",
        "Safe gate-waiver procedure",
        "Product-critical gate inventory",
        "Reusable versus product-specific tool boundary",
        "Agent operation guide for repository-local work",
        "Human audit guide for reviewing agent-authored changes",
    ):
        assert required_fragment in text, (
            f"Missing handoff-readiness material: {required_fragment!r}"
        )


def test_enterprise_handoff_policy_keeps_agent_native_value() -> None:
    """The repository should become explainable without weakening its gates."""
    text = read_handoff_adr()

    for required_fragment in (
        "remain agent-native and deterministically validated",
        "become explainable",
        "what it owns, how it is validated",
        "Human-governed, agent-executed, deterministically validated",
        "Do not lower validation strictness",
        "Do not remove deterministic gates",
        "Do not hide agent-native workflows",
    ):
        assert required_fragment in text, (
            f"Missing agent-native handoff boundary: {required_fragment!r}"
        )


def test_enterprise_handoff_policy_excludes_private_strategy() -> None:
    """Public-safe handoff documentation cannot contain private strategy.

    markers.
    """
    normalized = read_handoff_adr().casefold()

    forbidden_fragments = (
        "acquisition",
        "auction",
        "celonis",
        "founder strategy",
        "negotiation",
        "tax planning",
        "subasta",
    )
    for forbidden_fragment in forbidden_fragments:
        assert forbidden_fragment not in normalized, (
            f"Private strategy marker leaked into handoff policy: "
            f"{forbidden_fragment!r}"
        )


def read_handoff_adr() -> str:
    """Return normalized handoff ADR text."""
    assert HANDOFF_ADR.is_file(), f"Missing handoff ADR: {HANDOFF_ADR}"
    return " ".join(HANDOFF_ADR.read_text(encoding="utf-8").split())
