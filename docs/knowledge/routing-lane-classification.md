---
type: Pattern
title: Routing Lane Classification
description: How the router decides between the fast lane and escalation to the full Hermes agent for each utterance.
tags: [routing, classification, router]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:homeops_ai/homeops_router.py
  verification: agent-checked
  confidence: high
  aliases: [fast vs escalate, lane choice, escalation rules]
  relations:
    relates_to: [fast-lane-voice-router]
---

Classification is deliberately conservative — when in doubt, escalate,
because the full agent can always answer a simple question while the fast
lane cannot handle a complex one.

An utterance escalates to the full Hermes gateway when any of these hold:

- it is empty, or longer than ~280 characters;
- it matches complexity patterns: automation/script/scene editing,
  diagnostics ("why", "debug", "error", "logs"), configuration, install/
  update/backup, scheduling/reminders, research/explain/compare/summarise;
- the request asks for streaming (only the escalation path streams);
- there is no entity table to diet AND the utterance has no device-domain
  keywords (lights, heating, blinds, locks, media, etc.).

Everything else — short device commands and state questions — runs the
fast lane with the dieted context from the
[router](/fast-lane-voice-router.md).

Escalated requests are forwarded **verbatim** (original body, original fat
prompt) so the full agent loses nothing. Escalation is also the error path:
any fast-lane exception falls through to the gateway (fail-open), which the
dogfood harness asserts explicitly.
