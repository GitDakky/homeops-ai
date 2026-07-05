---
type: Architecture
title: Add-on Runtime Lifecycle
description: What run.sh starts inside the HomeOps AI container, in what order, and the ports each service owns.
resource: https://github.com/GitDakky/homeops-ai/blob/main/homeops_ai/run.sh
tags: [runtime, lifecycle, ports, architecture]
timestamp: 2026-07-05
aokf:
  provenance:
    method: agent-authored
    source: repo:homeops_ai/run.sh
  verification: agent-checked
  confidence: high
  aliases: [run.sh, startup order, port map]
  relations:
    relates_to: [fast-lane-voice-router, ingress-operator-ui]
---

`run.sh` is PID 1 (with `set -euo pipefail`). It reads user options from
`/data/options.json` (validating anything injected into shell/nginx/hermes
config), maps them to Hermes configuration, then starts services in order,
killing stale listeners on each port first so restarts are idempotent:

1. **Hermes gateway** — the full agent, loopback `:8642`
   (`GATEWAY_INTERNAL_PORT`), API-server platform enabled.
2. **Voice router** — loopback `:8643`, only when `agent_mode: router`;
   see [Fast-Lane Voice Router](/fast-lane-voice-router.md).
3. **Dashboard API** — loopback `:48110`, read-mostly operator data for
   the ingress page.
4. **Hermes dashboard UI** — loopback `:9119`, proxied under ingress
   `/dashboard/`.
5. **Hermes Workspace** — `:3000` (configurable), opened in a new tab
   rather than embedded.
6. **nginx** — ingress entrypoint `:48109`, routing `/`, `/terminal/`,
   `/dashboard/`, `/super/api/`, `/router/`.
7. **ttyd web terminal** — `:7682` (configurable), optional.

Persistent state lives under `/config` (`/config/.hermes`,
`/config/homeops`) and is never wiped by restarts. All template
placeholders in `nginx.conf.tpl`/`landing.html.tpl` — the
[ingress operator UI](/ingress-operator-ui.md) — are substituted by
`render_nginx.py`, which must be updated in the same change as any new
placeholder.
