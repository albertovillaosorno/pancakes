# Repository header: begin
# Provenance source mode: source_refs
# Provenance source refs:
# - 001046#repo.blueprint-validation.validator-policy
# - 001064#repo.make-knowledge.course-promoted-rules
# License notice ref: 000015#repo.headers.license.mit-notice.exact-block
# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.
# Repository header: end

"""Technical PDF note-reference contract for Make scenario handoff.

Boundary contract:
- Owns: stable manual note codes, color evidence checks, and missing-reference
failures.
- Must not: render PDFs, contact Make.com, infer unsupported colors, or create
external links.
- Allows: deterministic reference rows from caller-supplied scenario traversal
order.
- Split when: Pancakes Web owns PDF layout rendering.
- Merge when: note generation directly owns this exact reference index.
"""

from __future__ import annotations

import re
from typing import Final, Literal, NamedTuple

type NoteReferenceColorEvidence = Literal[
    "make_export_hex ",
    "not_supported ",
    "unknown",
]
type NoteReferenceSurface = Literal[
    "error_handler_note ",
    "filter_label ",
    "make_note",
]

NOTE_REFERENCE_CODE_PREFIX: Final[str] = "NOTE"
MAKE_HEX_COLOR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^#[0-9A-Fa-f]{6}$"
)
COLOR_CAPABLE_SURFACES: Final[frozenset[NoteReferenceSurface]] = frozenset(
    ("error_handler_note", "filter_label", "make_note")
)


class TechnicalPdfNoteReferenceDraft(NamedTuple):
    """Caller-provided note reference before stable numbering."""

    reference_id: str
    source_surface: NoteReferenceSurface
    source_label: str
    text: str
    color_hex: str | None
    color_evidence: NoteReferenceColorEvidence


class TechnicalPdfNoteReference(NamedTuple):
    """Stable customer-facing note reference row."""

    reference_id: str
    reference_code: str
    source_surface: NoteReferenceSurface
    source_label: str
    text: str
    color_hex: str | None


def build_technical_pdf_note_references(
    *,
    drafts: tuple[TechnicalPdfNoteReferenceDraft, ...],
    required_reference_ids: tuple[str, ...] = (),
) -> tuple[TechnicalPdfNoteReference, ...]:
    """Build stable manual note-reference codes from deterministic scenario.

    order.

    Returns:
        Stable note references with manual customer-facing codes.

    Raises:
        ValueError: If IDs are blank, duplicated, missing, or carry unsupported
        color data.
    """
    _validate_required_references(
        drafts=drafts, required_reference_ids=required_reference_ids
    )

    seen_ids: set[str] = set()
    references: list[TechnicalPdfNoteReference] = []
    for index, draft in enumerate(drafts, start=1):
        reference_id = _required_text(
            draft.reference_id, field_name="reference_id"
        )
        if reference_id in seen_ids:
            msg = (
                f"Duplicate technical PDF note reference id: {reference_id!r}."
            )
            raise ValueError(msg)
        seen_ids.add(reference_id)
        references.append(
            TechnicalPdfNoteReference(
                reference_id=reference_id,
                reference_code=_manual_reference_code(index),
                source_surface=draft.source_surface,
                source_label=_required_text(
                    draft.source_label, field_name="source_label"
                ),
                text=_required_text(draft.text, field_name="text"),
                color_hex=_validated_color_hex(draft),
            )
        )
    return tuple(references)


def technical_pdf_note_reference_code_map(
    references: tuple[TechnicalPdfNoteReference, ...],
) -> dict[str, str]:
    """Return reference ID to manual code mapping for PDF, portal, and.

    changelog.

    reuse.
    """
    return {
        reference.reference_id: reference.reference_code
        for reference in references
    }


def _validate_required_references(
    *,
    drafts: tuple[TechnicalPdfNoteReferenceDraft, ...],
    required_reference_ids: tuple[str, ...],
) -> None:
    if not required_reference_ids:
        return
    draft_ids = {
        draft.reference_id.strip()
        for draft in drafts
        if draft.reference_id.strip()
    }
    missing_ids = tuple(
        sorted(
            reference_id
            for reference_id in required_reference_ids
            if reference_id not in draft_ids
        )
    )
    if missing_ids:
        msg = f"Missing technical PDF note references: {missing_ids}."
        raise ValueError(msg)


def _validated_color_hex(draft: TechnicalPdfNoteReferenceDraft) -> str | None:
    color_hex = draft.color_hex
    if color_hex is None:
        return None
    if draft.source_surface not in COLOR_CAPABLE_SURFACES:
        msg = (
            f"Surface does not support note color evidence:"
            f"{draft.source_surface!r}."
        )
        raise ValueError(msg)
    if draft.color_evidence != "make_export_hex":
        msg = "Note colors require Make-exported hex evidence."
        raise ValueError(msg)
    normalized_color = color_hex.strip().upper()
    if not MAKE_HEX_COLOR_PATTERN.fullmatch(normalized_color):
        msg = f"Invalid Make note color hex: {color_hex!r}."
        raise ValueError(msg)
    return normalized_color


def _manual_reference_code(index: int) -> str:
    return f"{NOTE_REFERENCE_CODE_PREFIX}-{index:03d}"


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        msg = f"Technical PDF note reference {field_name} must not be blank."
        raise ValueError(msg)
    return normalized
