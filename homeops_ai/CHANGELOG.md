# Changelog

## [0.2.4]

### Fixed
- **Hermes dashboard now actually starts** — the 0.2.3 `--skip-build` flag assumed the dashboard web UI dist ships with Hermes; it does not (`hermes_cli/web_dist` is gitignored upstream and the installer never builds it), so the dashboard exited at boot and `/dashboard/` had nothing to proxy to. The dashboard web UI is now **pre-built into the add-on image at Docker build time**, and startup health-checks the port (not just the PID) with an automatic build-at-boot fallback for resilience.

## [0.2.3]

### Fixed
- **Hermes dashboard unreachable via Ingress ("Invalid Host header")** — Hermes v0.18 validates the Host header against the interface the dashboard is bound to (DNS-rebinding defence). The nginx proxy forwarded the HA ingress hostname, which the loopback-bound dashboard rejected with `400 Invalid Host header`. The proxy now presents a loopback Host and passes `X-Forwarded-Prefix` (derived from HA's `X-Ingress-Path`) so dashboard URLs resolve correctly under Ingress.
- Dashboard startup now passes `--skip-build` (the web UI dist ships prebuilt in the image), avoiding a slow/fragile npm rebuild at container boot, with an automatic one-shot fallback to a building start if the dist is missing.

## [0.2.2]

### Fixed
- **Gateway boot loop on Hermes v0.18** — Hermes v0.18 auto-detects s6-overlay (PID 1 in every Home Assistant add-on base image) and redirects `hermes gateway run` to its own s6 service slot, which does not exist inside an HA add-on (`no such gateway 'default'`, exit 1, restart loop). The add-on now exports `HERMES_GATEWAY_NO_SUPERVISE=1` so the gateway runs in classic foreground mode under the add-on's own supervisor, as before.

## [0.2.1]

### Changed
- Bundled Hermes Agent updated from `v2026.5.7` (v0.13) to `v2026.7.1` (v0.18.0) — four upstream feature releases: background subagents, first-class Mixture-of-Agents, major memory-tool upgrade, faster startup/session-search, image-editing generation, and the upstream P0/P1 clean sweep. See the [v2026.7.1 release notes](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.1).

### Added
- Automated Hermes freshness: a scheduled `hermes-version-watch` workflow checks upstream twice a week and opens a validated pull request bumping the pin, add-on version, changelog, and docs (`scripts/bump_hermes_version.py`).

## [0.2.0]

### Added
- **Fast-lane voice router** (`homeops_router.py`, loopback port 8643): an OpenAI-compatible proxy that makes voice fast on large installs. It trims the entity table Home Assistant sends on every utterance down to the top `max_fast_entities` candidates, gives the fast model on-demand `search_entities`/`get_state`/`call_service` tools for everything else, and escalates complex requests to the full Hermes agent automatically. Fail-open by design. Point conversation integrations at `http://127.0.0.1:8643/v1`.
- **Voice tab** on the add-on page: live router stats — fast vs escalated turns, entity diet (seen → sent), p50/p95 latency — plus router health notes.
- Read-only router observability endpoints `/router/health` and `/router/stats`, proxied under ingress.
- Offline dogfood harness `scripts/dogfood_router.py`: boots the real router against fake LLM/gateway/HA upstreams and asserts lane choice, context diet, tool round-trips, escalation fidelity, and stats hygiene; `--live` mode probes a running add-on read-only.
- Router unit test suite `tests/test_homeops_router.py` (wired into `scripts/validate_local.sh`).
- DOX documentation rails: root `AGENTS.md` rewritten per the DOX method with child contracts in `homeops_ai/`, `tests/`, `scripts/`, and `docs/`.
- Agentic-OKF knowledge bundle scaffold under `docs/knowledge/`.

### Changed
- `call_service` in the router respects `enable_ha_service_calls` (default off) and strictly validates entity/domain/service names.
- DOCS.md: new "The voice router" section explaining the context-diet architecture and how to wire conversation integrations to it.

## [0.1.11]

### Changed
- Replaces the noisy Runtime board with a terse Operations board focused on Hermes sessions, copy/resume commands, and compact runtime status.

### Added
- Adds recent Hermes session discovery from the Hermes state database, with CLI fallback, using Hermes session IDs such as `20260511_011713_5fb357`.

## [0.1.10]

### Fixed
- Fixes Home Assistant Ingress action buttons so Dashboard and Terminal links preserve the add-on Ingress base path instead of resolving to Home Assistant root paths.
- Sets the Hermes Workspace button to a concrete browser URL derived from the current Home Assistant host and Workspace port.

## [0.1.9]

### Added
- Starts the Hermes Agent dashboard UI alongside the gateway and proxies it inside Home Assistant Ingress at `/dashboard/`.
- Adds Home Assistant UI buttons for Hermes Workspace, Hermes Dashboard, Hermes API UI, and terminal access.

## [0.1.8]

### Added
- Adds product-level model routing settings for fast, complex, deep, and local/ultra-fast lanes so users can choose models from the Home Assistant settings UI.
- Documents the routed-agent architecture and guidance for large Home Assistant installations where full entity context makes agents slow.

## [0.1.7]

### Changed
- Removes inherited legacy-agent wording from current architecture assets and keeps old source-fork history in `docs/legacy/OPENCLAW_CHANGELOG.md`.
- Adds a validation guard so legacy OpenClaw terminology cannot reappear in current user-facing or runtime files outside approved migration-history docs.

## [0.1.6]

### Fixed
- Forces Hermes API Server adapter configuration to follow the HomeOps gateway port option, including migrated installs that still carry the old 18790 setting in persistent Hermes config.
- Prevents the Hermes gateway from restarting endlessly when an old OpenClaw add-on or stale config is still bound to 18790.

## [0.1.5]

### Fixed
- Fixes Home Assistant restart loops caused by stale in-container listeners holding the ingress, terminal, dashboard, Workspace, or Hermes gateway ports after watchdog restarts.
- Restores Hermes-native default gateway port handling to 8642 in the runtime script.
- Adds no-op compatibility wrappers for the removed OpenClaw gateway relay lifecycle so Hermes restarts do not fail on missing functions.

## [0.1.4]

### Fixed
- Fixed Dockerfile Workspace build shell precedence so `pnpm install` and `pnpm build` run inside `/opt/hermes-workspace` instead of falling back to the add-on build context.
- Pinned a compatible global pnpm for the bundled Hermes Workspace build.

## [0.1.3]

### Changed
- Reworked HomeOps AI settings, dashboard language, and docs to be Hermes Agent-first.
- Added heavier references to official Hermes Agent documentation.
- Replaced remaining user-facing OpenClaw terminology in the add-on interface with Hermes Workspace, Hermes gateway/API, and Hermes config concepts.
- Updated dashboard API defaults to prefer Hermes environment names while retaining fallback compatibility during the port.

## [0.1.2]

### Added
- Package Hermes Agent from the latest stable upstream release `v2026.5.7` instead of tracking `main`.
- Ship the official `hermes-paperclip-adapter` package in the add-on image.
- Bundle Hermes Workspace from `https://hermes-workspace.com/` / `outsourc-e/hermes-workspace` and add a managed Workspace launcher.
- Add Home Assistant options for enabling Workspace and selecting the Workspace port.

### Changed
- Keep HomeOps AI focused on Hermes-native runtime packaging rather than inherited OpenClaw runtime assumptions.

## [0.1.1]

### Added
- Added Home Assistant add-on options for Hermes LLM provider, model, and OpenRouter API key.
- Added `homeops-hermes` / `h` terminal launcher workflow for Hermes inside the add-on.

### Changed
- Reworked the managed runtime path to start `hermes gateway run` instead of the inherited OpenClaw gateway.
- Mapped add-on model/provider options into Hermes config at startup.
- Updated the GitHub Docker smoke test to verify `hermes` and `homeops-hermes`.

## [0.1.0]

### Changed
- Seeded HomeOps AI as a Hermes-first Home Assistant add-on scaffold.
- Switched add-on metadata and Dockerfile direction toward Hermes Agent.
