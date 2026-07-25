# Pancakes Media

Private media-delivery repository for Pancakes audit and repair services.

The only active implementation surface is PDF handoff generation. WAV, SRT, and MP4 stay deferred until an explicit task approves their utility libraries, provider policy, tests, and commercial delivery boundaries.

## Structure

- `src/pancakes_media/pdf/`: Pancakes-specific PDF adapter from validated Pancakes report JSON to the reusable `libraries/pdf` renderer.
- `pdf/`: PDF delivery data boundary and future generated output root.
- `wav/`, `srt/`, `mp4/`: deferred media domains with no executable implementation.
- `tests/pdf/`: deterministic contract tests for the PDF handoff path.
- `docs/adr/`: repository-local media delivery decisions.

## Validation

Run through the Schoenwald command layer:

```powershell
python -B tests/pdf/pancakes_media_pdf_contract.py
```

Direct development command from the Schoenwald root:

```powershell
python -B src/media/tests/pdf/pancakes_media_pdf_contract.py
```

## Boundary

Pancakes core remains the source of validated report JSON. This repository may render client-safe PDF handoff artifacts from that JSON, but it must not parse blueprints, run Make.com, inspect private source evidence, or expose Schoenwald control-plane material.
