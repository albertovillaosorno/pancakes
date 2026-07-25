# Make Custom Module Source Use Policy

## Status

Accepted

## Scope

repository/make-custom-module-intake

## Decision

Custom Make modules and custom tools must not enter the shared Make catalog merely because they
appear in a customer blueprint, customer account, private connector, or authenticated raw response.
Pancakes classifies custom evidence before storage, validation, tool-spec generation, or promotion.

## Classifications

### public_api_connector_candidate

Definition:

- a custom module that appears to model a generally available API or connector surface;
- not reusable until the reusable facts are re-derived from public or explicitly authorized
  provider material.

Allowed sources:

- public API documentation that can be cited without copying protected documentation bodies;
- public OpenAPI or schema material with redistribution-compatible terms;
- operator-authored sanitized examples that do not identify a customer or account;
- customer-provided leads to public sources, but not the customer's private schema itself.

Forbidden sources:

- customer blueprint JSON;
- authenticated customer account exports;
- private connector payloads;
- credential values, account IDs, customer records, or private business examples.

Retention behavior:

- retain only sanitized functional facts, source refs, and source hashes;
- do not retain raw copied documentation bodies;
- may become shared catalog truth only after explicit promotion approval;
- reject or delete raw private intake material after source classification.

Redaction requirements:

- remove account, organization, tenant, zone, workspace, team, connection, email, URL, token,
  bearer, cookie, secret, and customer identifier examples before storage;
- store public source URLs and hashes instead of copied documentation bodies;
- keep provider examples paraphrased unless a short quoted fragment is necessary for traceability.

Shared catalog promotion:

- allowed only after a reviewed public-source or authorized-provider-source record exists;
- promotion must create or update tests before the facts are used by generation or validation;
- customer-derived field names alone are not promotion evidence.

Deletion behavior:

- delete raw customer-provided discovery material after sanitized public-source evidence is
  extracted;
- keep only source refs, redaction status, sanitizer version, hash, and approval metadata.

Required metadata:

- `source_label=public_api_connector_candidate`;
- source rank from catalog source ranking;
- public source reference;
- approval reference when promoted;
- redaction status;
- deletion status;
- sanitizer version;
- source hash.

Required tests before ingestion:

- classification accepts only supported source labels;
- promotion remains blocked without explicit approval;
- raw customer examples do not enter shared catalog fixtures;
- generated custom tool specs contain only sanitized field names and source refs.

### client_business_custom_module

Definition:

- a customer-specific custom module that exists for one named engagement or internal workflow;
- useful for that engagement's analysis, but not reusable catalog truth.

Allowed sources:

- customer-authorized custom module descriptions for a named engagement;
- sanitized field inventories created from an authorized intake process;
- local analysis notes that contain no raw customer payload examples.

Forbidden sources:

- shared master catalogs;
- public fixtures;
- reusable examples;
- raw customer business JSON in source control.

Retention behavior:

- store sanitized facts only for the authorized engagement;
- delete or reject raw payloads after processing;
- never promote customer-specific schema into shared catalog truth.

Redaction requirements:

- remove mapped values, record examples, personal data, endpoint URLs, connection names, account
  IDs, customer identifiers, and credential-like strings;
- keep field names only when they are required to analyze that customer's blueprint;
- store hashes and deletion evidence instead of raw customer payloads.

Shared catalog promotion:

- forbidden;
- a later public API connector task must re-derive any reusable facts from public or separately
  authorized provider material.

Deletion behavior:

- raw payloads are rejected or deleted after sanitized intake;
- sanitized engagement facts expire according to the engagement retention record;
- pass-through blueprint module tokens may remain only as customer-scoped evidence.

Required metadata:

- `source_label=client_business_custom_module`;
- source rank from catalog source ranking;
- authorization reference;
- deletion status;
- redaction status;
- retention scope;
- engagement identifier;
- provenance refs for the sanitized inventory.

Required tests before ingestion:

- customer-specific records cannot be promoted to shared catalog truth;
- raw payload, secret-like, account-specific, URL, and email example text is rejected;
- deletion and authorization metadata are required;
- custom tool specs built from this class are marked engagement-local.

### private_third_party_or_customer_private_module

Definition:

- a private connector, private third-party schema, or customer-private module where reusable rights
  and retention are not proven;
- preserved as unresolved pass-through evidence rather than inferred or deleted.

Allowed sources:

- a customer-owned blueprint node that must be preserved as pass-through evidence;
- a private third-party connector reference that cannot be generalized safely.

Forbidden sources:

- shared catalog promotion;
- custom tool spec generation with functional fields;
- copied private schema or provider payload examples.

Retention behavior:

- preserve the unknown module token as unresolved pass-through evidence;
- do not infer reusable module fields;
- delete or reject raw payloads after processing.

Redaction requirements:

- do not store private schema fields, endpoint examples, mapped values, customer records, or
  credential-like text;
- store only the unresolved module token, pass-through reason, source hash, and redaction status;
- use generic limitation text in customer-facing output.

Shared catalog promotion:

- forbidden until a later task proves a public or authorized rights basis and reclassifies the
  source;
- unresolved visibility in a blueprint is not permission to build a shared connector spec.

Deletion behavior:

- delete or reject raw private connector payloads immediately after classification;
- retain only pass-through metadata needed to preserve blueprint structure and report limitations.

Required metadata:

- `source_label=private_third_party_or_customer_private_module`;
- source rank from catalog source ranking;
- pass-through reason;
- deletion status;
- redaction status;
- unresolved rights basis;
- source hash.

Required tests before ingestion:

- private custom modules remain pass-through only;
- custom tool spec generation is rejected for private third-party or customer-private modules;
- unresolved modules remain visible in reports without fabricated fields;
- raw private fields and provider payload examples are rejected.

## Enforcement

The implementation in `src/languages/make/custom_modules.py` accepts only sanitized field names,
authorization refs, and provenance refs. It rejects secret-like, account-specific, URL, or email
example text before any custom tool spec is built.

Shared catalog eligibility is possible only for `public_api_connector_candidate` records with
explicit promotion approval. Client business modules stay engagement-local. Private third-party or
customer-private modules remain pass-through only.

## Consequences

Pancakes can analyze and render customer-specific custom tools without leaking their schemas into
shared fixtures. Unknown custom modules remain visible and preserved instead of being deleted, but
they do not become catalog-backed modules without approved provenance.
