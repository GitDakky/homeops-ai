---
type: Glossary
title: Model Lanes
description: The four configurable model lanes (fast, complex, deep, local) and what each is for.
tags: [configuration, models, lanes]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:homeops_ai/config.yaml
  verification: agent-checked
  confidence: high
  aliases: [fast lane model, agent_mode, routed lanes]
  relations:
    relates_to: [fast-lane-voice-router, routing-lane-classification]
---

HomeOps AI options define four model lanes, each with a provider + model
pair, persisted under Hermes `homeops.*` config keys at startup:

- **Fast** (`fast_llm_*`, default `google/gemini-3.1-flash-lite`) — the
  voice lane the [router](/fast-lane-voice-router.md) calls with the
  dieted context. Needs a genuinely fast, tool-capable model; Groq-hosted
  or local OpenAI-compatible servers are good fits.
- **Complex** (`complex_llm_*`, default `openai/gpt-5.5`) — normal Hermes
  diagnostics and multi-step reasoning.
- **Deep** (`deep_llm_*`) — audits, repairs, long/overnight operations.
- **Local** (`local_llm_*` + `local_llm_base_url`) — ultra-fast local
  experiments via any OpenAI-compatible endpoint.

`agent_mode` selects the architecture: `router` (recommended) starts the
fast-lane router in front of the gateway; `fast`, `complex`, or `deep`
skip the router and let Home Assistant call the gateway directly. Which
requests actually use the fast lane is decided by
[lane classification](/routing-lane-classification.md).
`max_fast_entities` (1–100, default 20) caps the per-turn candidate set —
the context-diet knob. Only enable device *control* on the fast lane after
the model passes tool-calling tests
([dogfood workflow](/dogfood-and-validation-workflow.md)).
