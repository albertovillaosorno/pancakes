# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for Pancakes product-safe governance positioning.

Boundary contract:
- Owns: neutral repository-visible product wording for automation governance.
- Must not: validate market strategy, expose private buyer strategy, or claim
  compliance, certification, platform affiliation, or cross-platform support.
- Allows: static checks over the product ADR wording.
- Split when: public web copy or sales collateral gets its own repository.
- Merge when: another validation test owns the same product-positioning guard.
"""

from __future__ import annotations

from tests.support.paths import repo_root

PRODUCT_POSITIONING_ADR = (
    repo_root()
    / "docs"
    / "adr"
    / "automation-governance-product-positioning-policy.md"
)


def test_automation_governance_positioning_uses_neutral_product_language() -> (
    None
):
    """The product ADR names current capability without becoming a sales.

    pitch.
    """
    text = read_positioning_adr()

    for required_fragment in (
        "IR-centered automation governance and hardening engine ",
        "Make as its first implemented language adapter ",
        "deterministic validation ",
        "repair guidance ",
        "client-safe handoff ",
        "Production-readiness for automation workflows ",
        "Governance for agent-authored automation ",
        "Static analysis and safety checks for automation blueprints",
    ):
        assert required_fragment in text, (
            f"Product-safe governance wording is missing: {required_fragment!r}"
        )


def test_automation_governance_positioning_forbids_overclaims() -> None:
    """The product ADR blocks unsupported compliance and platform-support.

    claims.
    """
    text = read_positioning_adr()

    for required_boundary in (
        "Do not claim legal compliance ",
        "certification ",
        "attestation readiness ",
        "audit completion ",
        "affiliation, endorsement, or certification by Make.com",
        (
            "Do not claim Zapier, n8n, Python translation, or "
            "cross-platform IR "
            "support"
        ),
    ):
        assert required_boundary in text, (
            f"Product positioning boundary is missing: {required_boundary!r}"
        )


def test_automation_governance_positioning_keeps_private_strategy_out() -> None:
    """Repository-visible product framing cannot contain private strategy.

    markers.
    """
    normalized = read_positioning_adr().casefold()

    forbidden_fragments = (
        "acquisition ",
        "auction ",
        "celonis ",
        "founder strategy ",
        "tax ",
        "negotiation ",
        "subasta",
    )
    for forbidden_fragment in forbidden_fragments:
        assert forbidden_fragment not in normalized, (
            f"Private strategy marker leaked into product ADR: "
            f"{forbidden_fragment!r}"
        )


def read_positioning_adr() -> str:
    """Return the product positioning ADR text."""
    assert PRODUCT_POSITIONING_ADR.is_file(), (
        f"Missing product positioning ADR: {PRODUCT_POSITIONING_ADR}"
    )
    return " ".join(PRODUCT_POSITIONING_ADR.read_text(encoding="utf-8").split())
