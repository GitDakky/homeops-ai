---
type: Architecture
title: Ingress Operator UI
description: The tabbed operator console served under Home Assistant Ingress, including the Voice tab's live router stats.
resource: https://github.com/GitDakky/homeops-ai/blob/main/homeops_ai/landing.html.tpl
tags: [ui, ingress, operator, voice]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:homeops_ai/landing.html.tpl
  verification: agent-checked
  confidence: high
  aliases: [landing page, voice tab, operator console]
  relations:
    relates_to: [addon-runtime-lifecycle, fast-lane-voice-router]
---

The add-on page inside Home Assistant is a single templated HTML console
(`landing.html.tpl`, rendered by `render_nginx.py` as part of the
[add-on runtime lifecycle](/addon-runtime-lifecycle.md), served by nginx
on the ingress port) with tabs: Overview, Help, Workspace, Runtime,
**Voice**, Insights, Integrations, Memory.

The Voice tab is the cockpit for the
[fast-lane voice router](/fast-lane-voice-router.md): it polls
`./router/stats`
(read-only, proxied by nginx to the loopback router) and shows fast-lane
vs escalated turn counts, the entity diet (entities seen in the last
prompt vs entities actually sent to the model), p50/p95 latency, the
active fast model, and whether service calls are enabled. A copy button
provides the offline dogfood command.

Hard-won UI rules encoded here: all ingress links must be relative
(`./terminal/`, `./dashboard/`, `./router/stats`) or derived from
`window.location.pathname` — absolute paths break under HA Ingress
path-prefixing. The Workspace button gets a concrete `http(s)://host:port`
URL, never `href="#"`. Any new `__PLACEHOLDER__` in a template requires a
matching substitution in `render_nginx.py` in the same change.
