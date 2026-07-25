# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for Make platform legal and product framing.

Boundary contract:
- Owns: repository-visible Make platform source posture and public wording
limits.
- Must not: provide legal advice, claim Make affiliation, or assert unsupported
  cross-platform support.
- Allows: static checks over ADR and bibliography wording.
- Split when: public website copy or customer contracts gain their own
repository.
- Merge when: product positioning tests fully own the same source-rights
boundary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.support.paths import repo_root

if TYPE_CHECKING:
    from pathlib import Path

POSITIONING_ADR = (
    repo_root()
    / "docs"
    / "adr"
    / "automation-governance-product-positioning-policy.md"
)
MAKE_BIBLIOGRAPHY = repo_root() / "docs" / "bibliography" / "make.com.md"
INTEROPERABILITY_BIBLIOGRAPHY = (
    repo_root()
    / "docs"
    / "bibliography"
    / "software-interoperability-ip-law.md"
)


def test_make_platform_positioning_records_current_source_review() -> None:
    """The product-positioning ADR records the current Make source review."""
    text = _normalized(POSITIONING_ADR)

    for required_fragment in (
        "Source review was refreshed on 2026-05-13 ",
        "official Make terms ",
        "Make API documentation ",
        "Make Custom Apps review ",
        "Community Apps approval ",
        "docs/bibliography/make.com.md ",
        "docs/bibliography/software-interoperability-ip-law.md",
    ):
        assert required_fragment in text, (
            f"Make platform source-review boundary is missing: "
            f"{required_fragment!r}"
        )


def test_make_platform_framing_keeps_make_as_language_adapter() -> None:
    """Make is a source adapter, not the product model or provider authority."""
    text = _normalized(POSITIONING_ADR)

    for required_fragment in (
        (
            "Make.com is a named source platform and the first implemented "
            "language "
            "adapter"
        ),
        "It is not the Pancakes product model ",
        "Make-compatible artifact validation ",
        "language adapter",
        (
            "separate adapter, fixture corpus, translation contract, and "
            "validation "
            "suite"
        ),
    ):
        assert required_fragment in text, (
            f"Make adapter framing drifted or disappeared: "
            f"{required_fragment!r}"
        )


def test_make_platform_framing_forbids_public_provider_overclaims() -> None:
    """Provider, legal, and cross-platform overclaims stay blocked."""
    text = _normalized(POSITIONING_ADR)

    for required_boundary in (
        "Do not claim affiliation, endorsement, sponsorship, partnership ",
        "app-review approval ",
        "Marketplace listing ",
        "Community Apps approval ",
        "official extension status",
        (
            "Do not claim Zapier, n8n, Python translation, or "
            "cross-platform IR "
            "support"
        ),
        "Do not present Pancakes as a substitute for Make support",
    ):
        assert required_boundary in text, (
            f"Product-positioning overclaim boundary is missing: "
            f"{required_boundary!r}"
        )


def test_make_platform_bibliography_notices_are_non_governing_records() -> None:
    """Make and interoperability notices exist and keep legal notice shape."""
    for notice_path in (MAKE_BIBLIOGRAPHY, INTEROPERABILITY_BIBLIOGRAPHY):
        text = _normalized(notice_path)
        raw_text = notice_path.read_text(encoding="utf-8")

        assert not raw_text.startswith("---"), (
            f"Bibliography notices must not use YAML front matter: "
            f"{notice_path}"
        )
        for required_section in (
            "## Covered Material",
            "## Repository Use And Scope",
            "## License Or Terms Basis",
            "## Compliance Posture",
        ):
            assert required_section in raw_text, (
                f"Bibliography notice is missing {required_section}: "
                f"{notice_path}"
            )
        assert "Third-party legal notice only" in text, (
            f"Bibliography notice must remain non-governing: {notice_path}"
        )
        assert (
            "not legal advice" in text
            or "Do not use this notice to claim legal" in text
        ), (
            f"Bibliography notice must reject legal-advice posture: "
            f"{notice_path}"
        )


def test_make_platform_bibliography_covers_official_make_sources() -> None:
    """The Make notice preserves official source URLs needed for current.

    review.
    """
    text = MAKE_BIBLIOGRAPHY.read_text(encoding="utf-8")

    for source_url in (
        "https://www.make.com/en/terms-and-conditions ",
        "https://www.make.com/master-service-agreement.pdf ",
        "https://developers.make.com/api-documentation ",
        "https://developers.make.com/custom-apps-documentation",
        (
            "https://developers.make.com/custom-apps-documentation/"
            "community-apps/terms-and-conditions"
        ),
        "https://www.make.com/en/brand-guidelines.pdf ",
        "https://www.make.com/en/disclaimer",
    ):
        assert source_url in text, (
            f"Make bibliography missing official source: {source_url}"
        )


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())
