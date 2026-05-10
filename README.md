# HomeOps AI

**HomeOps AI** is a Home Assistant add-on that brings a Hermes-powered operations agent into HAOS properly — as a native add-on/app, not as a fragile side-load that HA can wipe on update.

The project is seeded from the GitDakky Hermes Home Assistant add-on work, but the direction is now Hermes-first: a clean, popular, installable Home Assistant AI operations layer.

## Product promise

HomeOps AI aims to become the most useful AI add-on for Home Assistant:

- diagnose Home Assistant issues from inside the supervised environment
- inspect live entities, devices, automations, services, templates, and bounded history
- keep a persistent operator workspace and Home Assistant skill pack
- expose a clean operator dashboard via Home Assistant ingress
- support voice-ready and OpenAI-compatible workflows where appropriate
- keep user data under add-on-managed persistent storage
- avoid unsupported HAOS hacks or non-native side-loaded services

## Install from the Home Assistant dashboard

HomeOps AI is intended to be installed through the Home Assistant **Settings → Apps** / add-on dashboard so it is managed by Home Assistant Supervisor and survives HAOS updates/rebuilds. Do **not** SSH into HAOS and install Hermes manually; Home Assistant can reset non-native applications.

> **Development status:** the repository is importable as an add-on repository, but the Hermes runtime port is still in progress. Use this only for development/testing until the first release is marked production-ready.

### One-click repository import

[![Open your Home Assistant instance and add this repository.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FGitDakky%2Fhomeops-ai)

1. Open your Home Assistant dashboard.
2. Go to **Settings → Apps**.
   - On older Home Assistant versions this may be **Settings → Add-ons** or **Settings → Add-ons → Add-on Store**.
3. Use the button above, or choose **Add repository** / **Add app repository** from the dashboard.
4. Paste this repository URL when prompted:

   ```text
   https://github.com/GitDakky/homeops-ai
   ```

5. Return to the Apps/Add-ons list and select **HomeOps AI**.
6. Click **Install**.
7. Open the **Configuration** tab before first start and review options such as:
   - terminal access
   - gateway/access mode
   - Home Assistant write permissions
   - provider/API environment variables
8. Click **Start**.
9. Open the HomeOps AI page from the Home Assistant sidebar/add-on page.

### Why install it this way?

Home Assistant OS and Supervisor own the application lifecycle. Installing through the dashboard means Home Assistant can:

- pull the correct add-on image
- mount persistent add-on storage under `/config`
- expose Home Assistant ingress properly
- inject Supervisor/Home Assistant API access safely
- restart/update the add-on without wiping state
- keep HomeOps AI visible and manageable from the dashboard

Manual installs inside HAOS are unsupported for this project.

## Starting Hermes in the integrated terminal

After the add-on starts, open the integrated terminal and run:

```sh
homeops-hermes
```

Short alias:

```sh
h
```

For setup/configuration:

```sh
homeops-onboard
homeops-configure
```

If `hermes` itself is on PATH you can also run `hermes` directly, but `homeops-hermes` sets the add-on-safe `HERMES_HOME=/config/.hermes` and workspace `/config/homeops` first.

## Current status

This repository has just been created from the proven Home Assistant add-on shell in `GitDakky/HermesHomeAssistant`. The first milestone is to replace the Hermes runtime assumptions with Hermes Agent while preserving the good Home Assistant packaging, ingress, persistence, dashboard, and validation patterns.

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
- `homeops_ai/ha_mcp_server.cjs` — Home Assistant MCP/tool bridge inherited from the Hermes line; to be evaluated for Hermes
- `scripts/validate_local.sh` — local validation entrypoint

## Roadmap

1. Rename and clean Hermes-specific runtime/state references.
2. Install Hermes Agent in the add-on image using the official installer or a pinned source build.
3. Map add-on options to Hermes config/environment safely.
4. Replace Hermes gateway lifecycle with Hermes gateway/API/dashboard lifecycle.
5. Convert bundled Hermes skills/bootstrap files into Hermes-native skills and workspace context.
6. Rework docs, translations, tests, and CI for a clean HomeOps AI public release.

## Name

**HomeOps AI** — the Hermes-powered operations brain for Home Assistant.

## Lineage

This project starts from the Home Assistant add-on work in `GitDakky/HermesHomeAssistant`, then ports the agent runtime and user experience to Hermes Agent.
