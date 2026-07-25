# Media Add-Ons And Delivery Scope

Status: accepted

## Decision

This repository owns Pancakes-specific media deliverables for audit and repair services. The first
active surface is PDF-style handoff material. Video, captions, timestamped links, translated
versions, voice, and narrated walkthroughs remain deferred until the corresponding utility
repositories and validation contracts are ready.

The current package posture is PDF-first: a PDF report add-on may package approved, sanitized
findings for internal circulation, while video walkthroughs, generated voice, cloned voice, avatar
narration, and automated media generation remain deferred.

Deferred media surfaces:

- video walkthrough;
- generated voice;
- cloned voice;
- avatar narration;
- automated media generation.

## Scope

Allowed future add-on surfaces:

- PDF documentation upgrade;
- premium async handoff;
- recorded walkthrough video;
- SRT subtitles;
- timestamped PDF links;
- additional language version;
- access cleanup checklist;
- scenario monitoring explanation;
- support-window or maintenance-retainer packaging after separate approval.

The media repository coordinates product-specific deliverables. General generation mechanics belong
in the relevant private libraries:

- `libraries/pdf` for general PDF generation;
- `libraries/mp4` for video generation;
- `libraries/srt` for SRT or timestamp JSON generation;
- `libraries/wav` for generated voice/audio workflows.

## Data Boundary

Media deliverables must be generated from fake, synthetic, public, or sanitized customer-safe inputs
unless an explicit customer delivery task approves the exact evidence package.

Do not place raw customer blueprint files, credentials, webhook URLs, private source paths, private
prompts, platform cookies, or operator-only strategy into media artifacts.

Client blueprint content, execution logs, screenshots, customer names, account identifiers, voice
samples, or personal data must not be used in generated video, avatar, cloned voice, or narrated
media until provider, consent, disclosure, retention, deletion, and contract gates are approved.

## Commercial Boundary

Media add-ons are commercial packaging candidates, not current implementation permission. They may
be described as future or optional only after the public copy is reviewed for claim safety, delivery
scope, refunds, taxes, and customer terms.

Continuous monitoring and managed-service obligations are not enabled by this ADR.

Future video, avatar, caption, voice, or narrated walkthrough packages require all of these gates:

- provider-specific commercial-use review;
- provider-specific data-use and training review;
- retention and deletion review;
- customer consent and media release boundary;
- synthetic media disclosure boundary;
- client artifact inventory;
- generated media storage and deletion plan;
- delivery provider and access lifetime;
- refund, tax, contract, and support boundaries;
- operator approval before any provider mutation.

## Delivery Automation Boundary

Media delivery remains PDF-first and package-local. This repository may render a client-safe PDF
from validated, sanitized Pancakes report JSON, but delivery automation remains deferred.

Current media delivery non-goals:

- no delivery link generation;
- no provider mutation;
- no customer upload or intake;
- no raw customer artifact storage;
- no parsing of blueprints or execution logs;
- no unattended customer file processing;
- no video, voice, or caption generation until those utility boundaries are approved.
- no generated media package using client blueprint content until privacy and provider gates are
  approved.

An approved future delivery provider must define capability lifetime, retention, deletion evidence,
access review, and client-safe package contents before this repository creates deliverable links or
provider packages.

## Source Material

Converted from the legacy Upwork and commercial docs triage material covering:

- PDF documentation upgrade;
- premium async handoff;
- recorded walkthrough video;
- SRT subtitles;
- timestamped PDF links;
- additional language versions;
- service tier prompt templates;
- service catalog and add-ons;
- Level 3 video pipeline notes;
- maintenance-retainer packaging notes.

## Validation

- Confirm media artifacts are generated from sanitized inputs.
- Confirm future video, caption, and voice work has an owning utility ADR before implementation.
- Confirm future media packages have provider, consent, disclosure, retention, deletion, contract,
  and client-artifact gates before implementation.
- Confirm public copy does not promise media add-ons before delivery and support boundaries are
  approved.
