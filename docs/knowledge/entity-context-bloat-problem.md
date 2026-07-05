---
type: Decision
title: Entity Context Bloat Problem
description: Home Assistant serialises every exposed entity into the LLM prompt each turn, making voice slow and expensive on large installs.
tags: [latency, context, home-assistant, voice]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: live HA diagnosis 2026-07-05 + HA developer docs
  verification: agent-checked
  confidence: high
  aliases: [slow voice assistant, exposed entities latency, prompt bloat]
  relations:
    relates_to: [ha-llm-api-lazy-loading-hook]
---

Home Assistant's built-in Assist LLM integration serialises every *exposed*
entity (name, state, aliases) into the system prompt on every utterance.
On a large install this was measured at thousands of exposed entities —
tens of thousands of tokens per voice turn — producing multi-second
latency and high per-turn cost, mostly describing devices irrelevant to
the request.

The critical architectural constraint: with the stock built-in agent,
"Assist can only control entities exposed to it" — exposure is
simultaneously the context-loader AND the access-gate. You cannot get
small-context plus full-control from the built-in agent; curating exposure
shrinks both together.

This is the problem the [fast-lane voice router](/fast-lane-voice-router.md)
exists to solve: a custom conversation endpoint holding its own Home
Assistant API access is not bound by the exposure gate (see the
[HA LLM API lazy-loading hook](/ha-llm-api-lazy-loading-hook.md)), so it
can send a tiny candidate set to the model while reaching the full entity
graph through [on-demand tools](/on-demand-entity-tools.md).
