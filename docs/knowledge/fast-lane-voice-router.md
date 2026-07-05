---
type: Architecture
title: Fast-Lane Voice Router
description: Loopback OpenAI-compatible proxy that diets the entity context and lazy-loads the rest, fixing voice latency on large Home Assistant installs.
resource: https://github.com/GitDakky/homeops-ai/blob/main/homeops_ai/homeops_router.py
tags: [router, voice, latency, architecture]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:homeops_ai/homeops_router.py
  verification: agent-checked
  confidence: high
  aliases: [voice router, fast lane, context diet, homeops router]
  relations:
    depends_on: [entity-context-bloat-problem]
    relates_to: [routing-lane-classification, on-demand-entity-tools]
---

The HomeOps router (`homeops_ai/homeops_router.py`) is a stdlib-only Python
HTTP proxy listening on loopback port 8643 that speaks the OpenAI
`/v1/chat/completions` protocol. Home Assistant conversation integrations
point at the router instead of the raw Hermes gateway when `agent_mode` is
`router`.

Per request it: (1) extracts the entity table Home Assistant embedded in the
system prompt, (2) scores every entity against the user's utterance using
token overlap, domain keywords, and exact-name bonuses, (3) rebuilds a slim
system prompt containing at most `max_fast_entities` candidates (default 20),
(4) sends that to the configured fast model with three
[on-demand entity tools](/on-demand-entity-tools.md) attached, and
(5) escalates complex or streaming requests verbatim to the full Hermes
gateway — see [lane classification](/routing-lane-classification.md).

The router is fail-open: any internal error escalates the original request
rather than dropping it, addressing the
[entity context bloat problem](/entity-context-bloat-problem.md) without
ever reducing capability. Read-only observability lives at `/router/health`
and `/router/stats` (no secrets ever appear in stats), surfaced in the
add-on's Voice tab.
