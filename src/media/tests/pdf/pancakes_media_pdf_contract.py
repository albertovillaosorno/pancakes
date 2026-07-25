# Copyright (c) 2026 Alberto Villa Osorno.
# Licensed under the MIT License. See LICENSE in the project root.

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

MEDIA_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = MEDIA_ROOT.parents[2]
sys.path.insert(0, str(MEDIA_ROOT / "src"))
sys.path.insert(0, str(WORKSPACE_ROOT / "libraries" / "pdf" / "src"))
sys.path.insert(
    0, str(WORKSPACE_ROOT / "repos" / "proprietary" / "pancakes" / "src")
)

from blueprints.validation.client_report import (
    build_client_safe_audit_report,
    client_safe_audit_report_as_dict,
)
from blueprints.validation.delivery_coverage import (
    BlueprintDeliveryCoverage,
)
from blueprints.validation.handoff_manifest import (
    BlueprintHandoffReadinessManifest,
    HandoffEvidenceSource,
)
from pancakes_media.pdf import (
    document_from_pancakes_report,
    write_pancakes_report_pdf,
)


def test_pancakes_report_json_renders_deterministic_pdf() -> None:
    report = _pancakes_report()
    document = document_from_pancakes_report(report)

    assert document.title == "Pancakes Audit Handoff: lead-routing-audit", (
        f"Unexpected PDF document title: {document}"
    )

    with TemporaryDirectory() as directory:
        output_root = Path(directory)
        first = write_pancakes_report_pdf(
            report=report,
            output_root=output_root,
            relative_path="reports/lead-routing-audit.pdf",
        )
        second = write_pancakes_report_pdf(
            report=report,
            output_root=output_root,
            relative_path="reports/lead-routing-audit-copy.pdf",
        )

        first_bytes = first.path.read_bytes()
        second_bytes = second.path.read_bytes()
        assert first_bytes == second_bytes, (
            "Pancakes Media PDF bytes must be deterministic."
        )
        assert b"Pancakes Audit Handoff" in first_bytes, (
            "Pancakes title missing from PDF."
        )
        assert (
            b"WAV voice, SRT captions, and MP4 walkthroughs are deferred."
            in first_bytes
        ), "Deferred media boundary missing from PDF."


def test_pancakes_media_rejects_private_source_report_text() -> None:
    report = dict(_pancakes_report())
    report["source_label"] = "raw source evidence package"

    with TemporaryDirectory() as directory:
        try:
            _ = write_pancakes_report_pdf(
                report=report,
                output_root=Path(directory),
                relative_path="reports/private.pdf",
            )
        except ValueError as exc:
            assert "private_or_raw_source_marker_present" in str(exc), str(exc)
        else:
            msg = "Private source text must block media PDF rendering."
            raise AssertionError(msg)


def test_wav_srt_and_mp4_are_documented_as_deferred() -> None:
    for folder in ("wav", "srt", "mp4"):
        readme = (MEDIA_ROOT / folder / "README.md").read_text(encoding="utf-8")
        assert "deferred" in readme.casefold(), (
            f"{folder} README must defer implementation."
        )


def test_media_delivery_scope_keeps_automation_deferred() -> None:
    adr = (
        MEDIA_ROOT / "docs" / "adr" / "media-addons-and-delivery-scope.md"
    ).read_text(encoding="utf-8")
    lower_adr = adr.casefold()

    assert "delivery automation remains deferred" in lower_adr, (
        "Media ADR must keep delivery automation deferred."
    )
    assert "no delivery link generation" in lower_adr, (
        "Media ADR must forbid delivery links until provider approval."
    )
    assert "no raw customer artifact storage" in lower_adr, (
        "Media ADR must forbid raw customer artifact storage."
    )
    assert "validated, sanitized pancakes report json" in lower_adr, (
        "Media ADR must keep PDF input scoped to sanitized report JSON."
    )
    assert "provider-specific commercial-use review" in lower_adr, (
        "Media ADR must require provider-specific commercial-use review."
    )
    assert "synthetic media disclosure boundary" in lower_adr, (
        "Media ADR must require synthetic media disclosure review."
    )
    assert "retention and deletion review" in lower_adr, (
        "Media ADR must require retention and deletion review."
    )
    assert "client blueprint content" in lower_adr, (
        "Media ADR must forbid client blueprint content in generated media."
    )
    for deferred_surface in (
        "generated voice",
        "cloned voice",
        "avatar narration",
    ):
        assert deferred_surface in lower_adr, (
            f"Media ADR must defer {deferred_surface}."
        )


def _pancakes_report() -> dict[str, object]:
    manifest = BlueprintHandoffReadinessManifest(
        importability_status="importable_candidate",
        live_make_called=False,
        blockers=(),
        warnings=(),
        secondary_diagnostics=(),
        placeholders=(),
        evidence_sources=(
            HandoffEvidenceSource(
                source_id="ast.parse",
                label="AST parser",
                detail="Parsed a sanitized synthetic Make fixture.",
            ),
            HandoffEvidenceSource(
                source_id="validation.importability",
                label="Importability validation",
                detail="Validated with local catalog evidence.",
            ),
        ),
    )
    coverage = BlueprintDeliveryCoverage(
        catalog_fingerprint="catalog:fingerprint:synthetic",
        delivery_mode="deploy_ready",
        error_count=0,
        warning_count=0,
        optimization_count=0,
        explanation_count=0,
        handoff_placeholder_count=0,
        client_ready_score=1.0,
    )
    report = build_client_safe_audit_report(
        report_id="Lead Routing Audit",
        source_label="Synthetic lead routing blueprint",
        manifest=manifest,
        coverage=coverage,
        audience="operator_review",
    )
    return client_safe_audit_report_as_dict(report)


def main() -> None:
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            function()
    print("PANCAKES_MEDIA_PDF_CONTRACT_OK")


if __name__ == "__main__":
    main()
