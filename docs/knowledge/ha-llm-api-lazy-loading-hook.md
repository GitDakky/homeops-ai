---
type: Architecture
title: HA LLM API Lazy-Loading Hook
description: Home Assistant's async_get_tools is evaluated per request and can vary its tool set, enabling custom agents to lazy-load context.
resource: https://developers.home-assistant.io/docs/core/llm/
tags: [home-assistant, llm-api, lazy-loading]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: https://developers.home-assistant.io/docs/core/llm/
  verification: agent-checked
  confidence: high
  aliases: [async_get_tools, custom llm api, per-request tools]
  relations:
    relates_to: [entity-context-bloat-problem]
---

Home Assistant's LLM developer API provides the architectural escape hatch
from the [context bloat problem](/entity-context-bloat-problem.md): a
custom integration's tools platform is "imported lazily and queried only
when an LLM request needs its tools", and its `async_get_tools(hass,
llm_context)` callback is "evaluated for each request… can return a
different set of tools depending on the context".

Three consequences shape HomeOps AI's design:

1. A custom conversation agent is not obliged to carry the full entity
   table — it can vary what the model sees per request.
2. An agent holding its own Home Assistant API access (add-on Supervisor
   token or a long-lived token) bypasses the exposed-entities gate
   entirely via REST/WebSocket, decoupling context size from control
   reach.
3. HA's `mcp_server` integration is NOT a fix by itself: its access is
   still gated by the exposed-entities page, so it only changes the
   transport, not the trade-off.

HomeOps AI implements the pattern outside HA core — in the
[router](/fast-lane-voice-router.md) — because a loopback OpenAI-compatible
proxy works with any conversation integration without requiring a custom
HA component install.
