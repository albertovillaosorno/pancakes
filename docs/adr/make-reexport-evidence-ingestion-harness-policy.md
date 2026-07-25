# Make Re-Export Evidence Ingestion Harness Policy

## Status

Accepted

## Scope

repository/make-adapter

## Context

Make-native parity improves when Pancakes can compare a locally generated blueprint with a local
Make re-export. That workflow must not become a live Make integration by accident, and it must not
activate compiler changes from one observed diff.

## Decision

Re-export evidence ingestion is a local, non-mutating harness:

- accepts repository-local generated blueprint files;
- accepts repository-local Make re-export blueprint files;
- canonicalizes and classifies deltas through the internal local blueprint delta harness;
- separates volatile Make noise, native shape deltas, runtime binding gaps, zero-trace violations,
  and semantic breakage;
- proposes manifest, matrix, projector, canonicalizer, or readiness follow-up candidates;
- marks every candidate as inactive until tests or operator review accept it.

The harness must not call Make.com, fetch provider data, require provider credentials, write raw
provider state, or change compiler behavior by default.

## Safety

Raw evidence remains caller-owned local files. The report may name local repository-relative paths
and counts, but it must not print credential values. Evidence ingestion runs zero-trace checks and
secret-like marker checks before any candidate can be promoted.

## Validation

`src/mcp/reexport_evidence.py` owns the local harness. This is not a public MCP tool.
`tests/languages/make/make_roundtrip_reexport_parity_corpus_contract.py` verifies safe reports,
inactive candidates, diff classification, and blocking behavior for private or secret-like
evidence.
