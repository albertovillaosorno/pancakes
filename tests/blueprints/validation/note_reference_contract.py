# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Contract tests for technical PDF note references.

Boundary contract:
- Owns: note numbering, color evidence, and missing-reference failure behavior.
- Must not: render PDFs, contact Make.com, or create customer artifacts.
- Allows: synthetic note-reference drafts and deterministic output assertions.
- Split when: Pancakes Web owns generated PDF layout tests.
"""

from __future__ import annotations

import pytest
from blueprints.validation import (
    NoteReferenceSurface,
    TechnicalPdfNoteReferenceDraft,
    build_technical_pdf_note_references,
    technical_pdf_note_reference_code_map,
)


def test_note_references_have_stable_manual_codes_without_external_links() -> (
    None
):
    """The same manual note codes can be reused across customer artifacts."""
    references = build_technical_pdf_note_references(
        drafts=(
            draft("route-fallback", "filter_label", label="Fallback route"),
            draft("handler-retry", "error_handler_note", label="Retry handler"),
            draft("module-contract", "make_note", label="Module contract"),
        ),
        required_reference_ids=(
            "handler-retry",
            "module-contract",
            "route-fallback",
        ),
    )

    assert technical_pdf_note_reference_code_map(references) == {
        "route-fallback": "NOTE-001",
        "handler-retry": "NOTE-002",
        "module-contract": "NOTE-003",
    }
    for reference in references:
        assert not reference.reference_code.startswith(
            ("http://", "https://")
        ), f"Reference codes must be manual, not external links: {reference}"
        assert reference.reference_code.count("-") == 1, (
            f"Reference code should stay compact and portable: {reference}"
        )


def test_note_reference_colors_require_make_exported_hex_evidence() -> None:
    """Normalize Make-exported note colors only with explicit evidence."""
    references = build_technical_pdf_note_references(
        drafts=(
            TechnicalPdfNoteReferenceDraft(
                reference_id="colored-note",
                source_surface="make_note",
                source_label="Designer note",
                text="A note with Make-exported color evidence.",
                color_hex="#aabbcc",
                color_evidence="make_export_hex",
            ),
        )
    )

    assert references[0].color_hex == "#AABBCC"


def test_note_reference_colors_reject_unknown_or_synthetic_color_evidence() -> (
    None
):
    """Synthetic gray or guessed colors cannot enter customer artifacts."""
    with pytest.raises(ValueError, match="Make-exported hex evidence"):
        _ = build_technical_pdf_note_references(
            drafts=(
                TechnicalPdfNoteReferenceDraft(
                    reference_id="guessed-color",
                    source_surface="filter_label",
                    source_label="Filter label",
                    text="A guessed color should not be accepted.",
                    color_hex="#808080",
                    color_evidence="unknown",
                ),
            )
        )


def test_note_references_fail_when_required_pdf_anchor_is_missing() -> None:
    """Required PDF anchors fail closed instead of producing broken links."""
    with pytest.raises(
        ValueError, match="Missing technical PDF note references"
    ):
        _ = build_technical_pdf_note_references(
            drafts=(draft("present", "make_note"),),
            required_reference_ids=("missing", "present"),
        )


def test_note_references_reject_duplicate_ids_and_blank_text() -> None:
    """Reference IDs and text must be explicit for stable customer handoff."""
    with pytest.raises(
        ValueError, match="Duplicate technical PDF note reference"
    ):
        _ = build_technical_pdf_note_references(
            drafts=(draft("same", "make_note"), draft("same", "filter_label"))
        )

    with pytest.raises(ValueError, match="text must not be blank"):
        _ = build_technical_pdf_note_references(
            drafts=(
                TechnicalPdfNoteReferenceDraft(
                    reference_id="blank-text",
                    source_surface="make_note",
                    source_label="Blank text",
                    text=" ",
                    color_hex=None,
                    color_evidence="not_supported",
                ),
            )
        )


def test_note_reference_color_values_must_match_make_hex_shape() -> None:
    """Color strings must be Make-style six-digit hex values."""
    with pytest.raises(ValueError, match="Invalid Make note color hex"):
        _ = build_technical_pdf_note_references(
            drafts=(
                TechnicalPdfNoteReferenceDraft(
                    reference_id="bad-color",
                    source_surface="make_note",
                    source_label="Bad color",
                    text="Bad color shape.",
                    color_hex="gray",
                    color_evidence="make_export_hex",
                ),
            )
        )


def draft(
    reference_id: str,
    source_surface: NoteReferenceSurface,
    *,
    label: str = "Synthetic note",
) -> TechnicalPdfNoteReferenceDraft:
    """Return a colorless synthetic note-reference draft."""
    return TechnicalPdfNoteReferenceDraft(
        reference_id=reference_id,
        source_surface=source_surface,
        source_label=label,
        text=f"{label} text.",
        color_hex=None,
        color_evidence="not_supported",
    )
