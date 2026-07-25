# Golden Make Scenario Corpus


This directory holds manually curated Make scenario exports for local Golden
health checks and future reconstruction work.

## File Boundary

This directory owns curated Make.com Golden workflow fixtures and their local
coverage ledger. It stores only the source corpus: `coverage.json` plus exported
Make blueprint JSON files under `data/`.

Public template fixtures live under `data/public/`. The first reviewed seed lives
under `data/public/priority/` and stays ahead of the larger API seed in the
single `coverage.json` ledger. The official API seed is capped at the 100
most-used public templates and lives under `data/public/top100/`; do not add a
second coverage ledger for it.

Generated batch output, comparison reports, scraper output, and command UX do
not belong here unless a focused TODO explicitly promotes an artifact into the
Golden corpus.

## Health Contract

`coverage.json` must be strict JSON and must contain ledger entries with these
required fields:

- `title`: non-empty string
- `description`: non-empty string
- `additional_information`: list of non-empty strings
- `file`: safe `data/**/*.json` relative path
- `completed`: explicit boolean

When `completed` is `true`, the entry must also include `manual_analysis` with
all of these required fields:

- `reviewed_by`: non-empty string naming the manual reviewer or review role
- `reviewed_at`: non-empty review timestamp string
- `parity_verdict`: non-empty string describing the accepted parity result
- `privacy_verdict`: non-empty string describing private-value handling
- `logic_candidate_review`: non-empty string confirming reusable logic
  candidates were reviewed before marking the entry complete. When review finds
  a reusable candidate, cite the local `golden.promotion` evaluation result and
  whether it was promoted, deferred, or rejected.
- `golden_tool_evidence`: list of non-empty strings naming local Golden tool
  output, comparison summaries, or report paths used to assist the manual review

Every JSON file under `data/` must appear exactly once in `coverage.json`.
Every ledger `file` value must resolve under `data/`, must exist, and must parse
as strict JSON.

For public templates, review `data/public/priority/` before
`data/public/top100/`. The top-100 files are public API fixtures only; they are
not a mandate to validate or collect every public Make template.

The read-only Python entry point is
`golden.coverage.check_golden_coverage(Path("src/languages/make/data/golden"))`.
A report with any finding is a failed health check.

## Terminal Summary

Run the read-only operator summary with:

```powershell
python -m golden.coverage_summary --root src/languages/make/data/golden
```

Successful output has this shape:

```text
Golden coverage summary
root: src\languages\make\data\golden
health: ok
total entries: 2
completed: true entries: 0
completed: false entries: 2
```

`completed: true` means a Golden scenario has been generated, manually reviewed,
accepted as matching the source fixture except for forbidden personal values,
and checked for reusable missing logic candidates. `completed: false` means the
exported source fixture exists but its accepted generated counterpart or manual
analysis is still pending.

If the health check finds missing files, extra files, duplicate ledger
references, malformed JSON, non-standard JSON constants, or unsafe paths, the
command prints `health: failed`, lists each finding code and location, and exits
non-zero. It never repairs, normalizes, or rewrites corpus files.

Any commit that changes `coverage.json` must include matching commit-body
evidence copied from the current summary:

```text
completed: true entries: N
completed: false entries: M
```

GitGuard rejects staged or outgoing coverage-ledger commits when those two
counts are missing or do not match the ledger content.

## Manual Maintenance

While the remaining TODO queue is being completed, the operator may manually
download scenario JSON exports, add them under `data/`, and update
`coverage.json`. Do not run automated Golden reconstruction yet.

Official Make public template blueprints may be promoted into
`data/public/top100/` only through the approved Templates API boundary, with a
hard cap of 100 most-used public templates unless a future operator instruction
changes the cap. After that seed, the background template scraper stays disabled
until further notice.

Raw golden exports are reference inputs. Do not rewrite, sanitize, or normalize
them through automation while they are being collected manually.

Template exports are not source-of-truth business logic. They may be used to
verify Make-readable JSON format, blueprint shape, notes, AI-agent tool fields,
and missing local raw-spec evidence. They must not be used to copy workflow
logic, prompt text, route behavior, error-handling policy, or linter rules into
the repository unless a separate official Make API response, raw spec,
documentation source, or manual LLM validity review proves the behavior is
generalizable.

Golden completion does not require an exact reconstruction of a template. The
deterministic comparison tools are assistants for manual review. A reviewer can
accept intentional differences when the important generated output remains
importable/compilable as Make blueprint JSON, preserves required tool surfaces,
and avoids private values. The review evidence belongs in
`manual_analysis.logic_candidate_review` and `manual_analysis.golden_tool_evidence`.

Raw exports may contain personal or account-specific labels. Generated scenarios
must never reproduce those values. A generated scenario still counts as
completed when it matches the golden scenario except for those personal values;
reproducing them is a critical generation error, not a golden-file problem.

## Commit Note

For now, commit corpus updates as manual Golden data changes. Any commit that
changes `coverage.json` or `data/` must state the current `completed: true` and
`completed: false` counts and must run the Golden coverage health contract.
