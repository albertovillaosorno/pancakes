# Scraper

This bounded context owns the Make.com raw-spec refresh boundary.

## File Boundary

This README owns the `languages.make.raw_specs` package behavior summary,
source-injection contract, and repository-local output roots. Catalog
compilation and live credential policy remain outside this package boundary.

Tests and dry runs pass an object that implements `MakeRawSpecSource`; live Make
API scraping stays disabled by default and requires explicit credentialed
configuration before the service-facing CLI can download raw specs.

ADR 001074 classifies raw specs and authenticated API responses as source
material for internal functional transformation only. Raw spec refreshes must
preserve provenance, truncation, and deletion evidence without publishing raw
payloads or turning generated Make data into a customer-facing catalog.

Default refresh output is repository-local SQLite:

- `src/data/pancakes.sqlite` for `make_raw_spec_payloads` and
  `make_raw_spec_manifest_records`
- `make_raw_spec_update_reviews` rows for new, changed, or removed raw specs
  that need downstream catalog, semantics, native semantics, projector, and
  roundtrip review
- `temp/` for disposable work files

Raw-spec payloads are not repository source files. Durable payloads and manifest
state live in SQLite; temporary fetch artifacts may exist only under ignored
cache or temp roots during a run.
Exact duplicate raw-spec payloads collapse to the existing current SQLite rows.
Changed payloads close the previous current row with `valid_to` and insert a new
current row, preserving point-in-time history without deleting older evidence.
Only sanitized functional facts may flow into tracked catalog snapshots. Copied
documentation prose, screenshots, credentials, private account identifiers, and
full raw authenticated responses must stay out of tracked source and
customer-facing output.

Minimal manual dry run shape:

```python
from pathlib import Path

from languages.make.raw_specs import (
    MakeScraperConfig,
    MakeRawSpecTarget,
    SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
    sync_raw_specs,
)

config = MakeScraperConfig.from_env(Path.cwd())
report = sync_raw_specs(
    config=config,
    source=my_source,
    source_metadata=SYNTHETIC_RAW_SPEC_SOURCE_METADATA,
)
```

`my_source` must implement `list_app_versions()` and `fetch_app_spec(target)`.

Service-facing live refresh shape:

```powershell
python -B -m languages.make.raw_specs --repo-root . refresh
```

The live command loads process environment plus the explicitly supplied private
operator env file. It requires live scraping to be enabled by the launching
service or command, plus `MAKE_API_TOKEN`, `MAKE_ZONE`, and
`MAKE_ORGANIZATION_ID`, then writes all discovered raw specs to
`src/data/pancakes.sqlite`. Pancakes does not own private service install
configuration.

Full live refreshes also seed Make-owned platform/native raw specs when the IMT
app index omits them. The guarded seed list covers AI-agent families,
`app-runtime`, `builtin`, `csv`, `datastore`, `http`, `json`, `regexp`, `util`,
and `xml` so routers, aggregators, transformers, triggers, AI modules, and text
parser modules stay available to the retained catalog. Search-constrained
diagnostic runs stay limited to the operator search term.

Live configuration parsing keeps Make external identifiers as text. This avoids
precision loss for large organization IDs while still rejecting blank, boolean,
non-decimal, or non-positive values before a live adapter can use them.

`MakeLiveRawSpecSource` is the reviewed live adapter boundary for explicit runs.
It is not used by tests or default validation; tests must inject fake transports
and deterministic sources.

Every raw-spec sync must pass explicit source metadata. Synthetic tests use the
fixture metadata constant; live refresh wiring uses authorized authenticated API
metadata and keeps raw ingest ignored by default.

## Refresh Status Contract

`catalog.status`, `scraper.refresh_status`, and
`python -B -m languages.make.raw_specs --repo-root . status` are read-only
freshness surfaces. They must report the local manifest path, generated time,
record counts, source provenance counts, sanitization posture, missing or
invalid records, and complete-refresh blockers without contacting Make.

The repeatable refresh path is:

1. Sync raw specs through `sync_raw_specs` with an injected source for tests or
   through the explicit live command in an operator-controlled service context.
2. Keep raw payloads and manifest state in `src/data/pancakes.sqlite`.
3. Rebuild or ensure generated projections from SQLite rows and tracked SQL
   snapshots.
4. Promote only generalized evidence into Make module manifests, the native
   semantics matrix, compiler projectors, or blueprint diff rules.

The live refresh command remains operator-gated. It requires
`MAKE_LIVE_SCRAPER_ENABLED`, `MAKE_API_TOKEN`, `MAKE_ZONE`, and
`MAKE_ORGANIZATION_ID` from private runtime environment, and it must not become
the default validation path. Pancakes must never store provider credential
values, OAuth or bearer tokens, manual one-off scenario patches, generated
SQLite binaries as source truth, or raw authenticated payloads in
customer-facing output.
