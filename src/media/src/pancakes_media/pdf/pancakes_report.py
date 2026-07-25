# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

"""Pancakes report module."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from schoenwald_pdf import HandoffPdfDocument, PdfSection

REQUIRED_REPORT_KEYS = (
    "report_id ",
    "source_label ",
    "audience ",
    "importability_status ",
    "delivery_mode ",
    "live_make_called ",
    "blocker_count ",
    "warning_count ",
    "handoff_placeholder_count ",
    "client_ready_score ",
    "evidence_source_ids ",
    "disclosures ",
    "pdf_status ",
    "customer_pdf_enabled ",
    "is_truncated ",
    "truncation_reason",
)


def document_from_pancakes_report(
    report: Mapping[str, object],
) -> HandoffPdfDocument:
    """Handle document from pancakes report.

    Returns:
        The computed command value.
    """
    _assert_required_keys(report)
    _assert_pdf_source_is_renderable(report)

    report_id = _string_value(report, "report_id")
    evidence_ids = ", ".join(_string_sequence(report, "evidence_source_ids"))
    disclosures = _string_sequence(report, "disclosures")
    return HandoffPdfDocument.create(
        title=f"Pancakes Audit Handoff: {report_id}",
        subtitle=(
            "Client-safe offline report generated from validated Pancakes "
            "evidence."
        ),
        sections=[
            PdfSection.create(
                "Audit Summary",
                [
                    f"Source: {_string_value(report, 'source_label')}",
                    f"Delivery mode: {_string_value(report, 'delivery_mode')}",
                    (
                        f"Importability: "
                        f"{_string_value(report, 'importability_status')}"
                    ),
                    (
                        f"Client-ready score: "
                        f"{_number_text(report, 'client_ready_score')}"
                    ),
                ],
            ),
            PdfSection.create(
                "Evidence",
                [
                    f"Evidence source IDs: {evidence_ids}",
                    f"Warnings: {_integer_text(report, 'warning_count')}",
                    (
                        f"Handoff placeholders: "
                        f"{_integer_text(report, 'handoff_placeholder_count')}"
                    ),
                    "Live Make execution is not implied by this PDF.",
                ],
            ),
            PdfSection.create("Disclosures", tuple(disclosures)),
            PdfSection.create(
                "Deferred Media",
                [
                    (
                        "WAV voice, SRT captions, and MP4 walkthroughs are "
                        "deferred."
                    ),
                    (
                        "This PDF does not enable monitoring, managed-service "
                        "obligations, or live provider claims."
                    ),
                ],
            ),
        ],
    )


def _assert_required_keys(report: Mapping[str, object]) -> None:
    missing = [key for key in REQUIRED_REPORT_KEYS if key not in report]
    if missing:
        msg = f"Pancakes report is missing keys: {', '.join(missing)}"
        raise ValueError(msg)


def _assert_pdf_source_is_renderable(report: Mapping[str, object]) -> None:
    if report["live_make_called"] is not False:
        msg = "Pancakes Media PDF requires offline report evidence."
        raise ValueError(msg)
    if report["blocker_count"] != 0:
        msg = "Pancakes Media PDF cannot render reports with handoff blockers."
        raise ValueError(msg)
    if (
        report["is_truncated"] is not False
        or report["truncation_reason"] != "not_truncated"
    ):
        msg = "Pancakes Media PDF requires non-truncated report evidence."
        raise ValueError(msg)
    if (
        report["customer_pdf_enabled"] is not False
        or report["pdf_status"] != "deferred"
    ):
        msg = (
            "Pancakes core must remain JSON-first; Pancakes Media owns PDF "
            "rendering."
        )
        raise ValueError(msg)


def _string_value(report: Mapping[str, object], key: str) -> str:
    value = report[key]
    if not isinstance(value, str) or not value.strip():
        msg = f"Pancakes report key must be non-empty text: {key}"
        raise ValueError(msg)
    return value.strip()


def _string_sequence(report: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = report[key]
    if not isinstance(value, Sequence) or isinstance(value, str):
        msg = f"Pancakes report key must be a sequence of text: {key}"
        raise TypeError(msg)
    strings = tuple(
        item for item in value if isinstance(item, str) and item.strip()
    )
    if len(strings) != len(value):
        msg = f"Pancakes report key contains non-text entries: {key}"
        raise ValueError(msg)
    return strings


def _integer_text(report: Mapping[str, object], key: str) -> str:
    value = report[key]
    if not isinstance(value, int):
        msg = f"Pancakes report key must be an integer: {key}"
        raise TypeError(msg)
    return str(value)


def _number_text(report: Mapping[str, object], key: str) -> str:
    value = report[key]
    if not isinstance(value, int | float):
        msg = f"Pancakes report key must be numeric: {key}"
        raise TypeError(msg)
    return f"{value:.2f}" if isinstance(value, float) else str(value)
