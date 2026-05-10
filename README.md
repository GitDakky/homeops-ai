# HomeOps AI

**HomeOps AI** is a Home Assistant add-on that brings a Hermes-powered operations agent into HAOS properly — as a native add-on/app, not as a fragile side-load that HA can wipe on update.

The project is seeded from the GitDakky OpenClaw Home Assistant add-on work, but the direction is now Hermes-first: a clean, popular, installable Home Assistant AI operations layer.

## Product promise

HomeOps AI aims to become the most useful AI add-on for Home Assistant:

- diagnose Home Assistant issues from inside the supervised environment
- inspect live entities, devices, automations, services, templates, and bounded history
- keep a persistent operator workspace and Home Assistant skill pack
- expose a clean operator dashboard via Home Assistant ingress
- support voice-ready and OpenAI-compatible workflows where appropriate
- keep user data under add-on-managed persistent storage
- avoid unsupported HAOS hacks or non-native side-loaded services

## Current status

This repository has just been created from the proven Home Assistant add-on shell in `GitDakky/OpenClawHomeAssistant`. The first milestone is to replace the OpenClaw runtime assumptions with Hermes Agent while preserving the good Home Assistant packaging, ingress, persistence, dashboard, and validation patterns.

Do not treat the current image as production-ready until the Hermes runtime port is complete.

## Intended architecture

- Home Assistant add-on/app packaging
- Debian-based HA add-on image
- Hermes Agent runtime
- nginx ingress landing/operator dashboard
- optional web terminal for setup/recovery
- Home Assistant config mounted at `/ha-config`
- HomeOps/Hermes state persisted under `/config/.hermes` and `/config/homeops`
- built-in Home Assistant tools using the Supervisor/Core APIs from the add-on context

## Repository layout

- `homeops_ai/` — Home Assistant add-on package
- `homeops_ai/config.yaml` — add-on metadata, options, schema
- `homeops_ai/Dockerfile` — add-on image build
- `homeops_ai/run.sh` — add-on PID 1 runtime orchestrator
- `homeops_ai/dashboard_api.py` — local dashboard/status API
- `homeops_ai/ha_mcp_server.cjs` — Home Assistant MCP/tool bridge inherited from the OpenClaw line; to be evaluated for Hermes
- `scripts/validate_local.sh` — local validation entrypoint

## Roadmap

1. Rename and clean OpenClaw-specific runtime/state references.
2. Install Hermes Agent in the add-on image using the official installer or a pinned source build.
3. Map add-on options to Hermes config/environment safely.
4. Replace OpenClaw gateway lifecycle with Hermes gateway/API/dashboard lifecycle.
5. Convert bundled OpenClaw skills/bootstrap files into Hermes-native skills and workspace context.
6. Rework docs, translations, tests, and CI for a clean HomeOps AI public release.

## Name

**HomeOps AI** — the Hermes-powered operations brain for Home Assistant.

## Lineage

This project starts from the Home Assistant add-on work in `GitDakky/OpenClawHomeAssistant`, then ports the agent runtime and user experience to Hermes Agent.
