"""PROCESIO DTO sub-tools.

Deterministic, reusable builders that turn a small validated `config` into a full
PROCESIO DTO by merging it onto a captured golden template, then create/edit the
resource over the Web API. See DTO-SUBTOOLS-NOTE.md for the design.

Layout per component: tools/procesio/dto/<component>/
  description.md       - what it is / when to use / gotchas
  config.schema.json   - the JSON Schema the (LLM-produced) config must satisfy
  template.dto.json    - a real captured golden DTO with placeholders
  builder.py           - PURE config -> DTO (no I/O); + a Component spec
  fixtures/            - golden config->DTO pairs (regression) + drift captures
"""
