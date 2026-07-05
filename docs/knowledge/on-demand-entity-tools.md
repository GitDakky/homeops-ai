---
type: Pattern
title: On-Demand Entity Tools
description: Three router tools that let the fast model reach the full Home Assistant entity graph lazily instead of carrying it in context.
tags: [tools, lazy-loading, router]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:homeops_ai/homeops_router.py
  verification: agent-checked
  confidence: high
  aliases: [search_entities, get_state, call_service, lazy entity tools]
  relations:
    relates_to: [fast-lane-voice-router]
---

The fast lane carries only a small candidate entity set, so the model needs
an escape hatch when the target device is not in context. The
[router](/fast-lane-voice-router.md) attaches three OpenAI function tools:

- `search_entities(query, domain?, limit?)` — scores the parsed entity
  table first; if empty, falls back to a live `GET /states` against the
  Home Assistant REST API, reaching the **full** entity graph, not just
  exposed entities.
- `get_state(entity_id)` — live state plus a slimmed attribute whitelist
  (brightness, temperature, position, media title, etc.) to keep tool
  results small.
- `call_service(domain, service, entity_id?, data?)` — performs the
  action. Disabled unless the add-on option `enable_ha_service_calls` is
  on, and every domain/service/entity string must match strict regexes
  before any API call, preventing injection through model output.

The tool loop is capped (default 5 rounds); exhaustion returns a graceful
spoken apology rather than hanging the voice pipeline. The fast system
prompt explicitly instructs the model to call `search_entities` before
claiming a device does not exist.
