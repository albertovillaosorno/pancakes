INSERT OR REPLACE INTO module_aliases (
  alias_text,
  canonical_token,
  canonical_module_id,
  confidence,
  source_kind,
  source_ref,
  valid_from,
  valid_to,
  fingerprint,
  adr_anchor
) VALUES
  (
    'trigger',
    'trigger_imt',
    NULL,
    'reviewed',
    'course',
    'src/catalog/data/make/courses/raw/Introduction to Modules.md',
    '2026-04-30T00:00:00+00:00',
    NULL,
    '99a7e3077ec483a780522b580963f59722ed2f24f931fc4a49cd1962c783f850',
    '001064#repo.make-knowledge.promoted-aliases'
  ),
  (
    'scenario trigger',
    'trigger_imt',
    NULL,
    'reviewed',
    'course',
    'src/catalog/data/make/courses/raw/Setting up my first scenario.md',
    '2026-04-30T00:00:00+00:00',
    NULL,
    '670d7e53686558b4eb080c64be4d79d43f8a82ee7720e47c85ca37bec923f0aa',
    '001064#repo.make-knowledge.promoted-aliases'
  ),
  (
    'webhook response',
    'webhooks.respond',
    NULL,
    'reviewed',
    'course',
    'src/catalog/data/make/courses/raw/Advanced Webhooks.md',
    '2026-04-30T00:00:00+00:00',
    NULL,
    '01db7a495d76c860141b76b07343d73b1a9f08e77bd74edb3f4b3fbd955cba63',
    '001064#repo.make-knowledge.promoted-aliases'
  ),
  (
    'iterator',
    'builtin.iterator',
    NULL,
    'reviewed',
    'course',
    'src/catalog/data/make/courses/raw/Introduction to Iterators and Array Aggregators.md',
    '2026-04-30T00:00:00+00:00',
    NULL,
    '8bb3299fcd54c978489fd7583613b0c33dc25da4e83e266a4078fa9cb792d742',
    '001064#repo.make-knowledge.promoted-aliases'
  ),
  (
    'array aggregator',
    'builtin.array_aggregator',
    NULL,
    'reviewed',
    'course',
    'src/catalog/data/make/courses/raw/Introduction to Iterators and Array Aggregators.md',
    '2026-04-30T00:00:00+00:00',
    NULL,
    'e4e3aa9dbb5547bf6c814b458937848296461415df401f169b46e9cb5b2aa0ee',
    '001064#repo.make-knowledge.promoted-aliases'
  ),
  (
    'data store',
    'datastore',
    NULL,
    'reviewed',
    'course',
    'src/catalog/data/make/courses/raw/Data stores and data structures.md',
    '2026-04-30T00:00:00+00:00',
    NULL,
    '29f27f448037c2eb073a37403787616f910cb3df4c8fd44f1200714236c205fc',
    '001064#repo.make-knowledge.promoted-aliases'
  );

