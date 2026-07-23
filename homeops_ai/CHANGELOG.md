# Changelog

## [0.3.7]

### Changed
- Bundled Hermes Agent updated from `v2026.7.1` to `v2026.7.20` ([release notes](https://github.com/NousResearch/hermes-agent/releases/tag/v2026.7.20)).

## [0.3.6]

- Router: area-first entity injection in `tool_search_entities` — room-scoped queries
  ("state of the lights in the family room") now resolve the area's own entities via one
  `/api/template` render (full area-name token match, availability-filtered) and rank them
  ahead of name-scored results. Fixes "couldn't find any lights in the family room" when
  the room's fixtures are named for what they are (Lamps, Downlights, Pendant) rather
  than where they are.

## [0.3.5]

### Fixed
- **"Turn on the lamps in the family room" targeted the wrong entity and claimed "already on"** — two compounding faults found by live dogfooding:
  1. *Entity scoring*: a room group entity (Hue room "Family Room") outranked the actual "Lamps" circuit because room-name overlap scored higher than the fixture noun. New fixture-word scoring boost (lamps, downlights, pendant, spots, strip, chandelier, sconce...) makes named fixtures beat room groups.
  2. *Stale group state*: Hue room groups report last-known state even when every member bulb is unreachable, so the assistant said "already on" about powered-off lamps. `get_state` now reports each group member's live availability with an explicit staleness warning, and the fast-lane prompt instructs the model to treat `unavailable`/`unknown` as unreachable (suggest checking power) and to verify `changed=[]` service results with `get_state` before claiming success.
- **Self-heal for blank `homeassistant_token` option** — if the option is empty but a token from a previous configuration is persisted at `/config/secrets/homeassistant.token`, run.sh now reuses it (with a boot log line) instead of booting the gateway and router blind. Seen live: an add-on update wiped saved options, silently killing HA access until hand-patched.

### Tests
- 6 new offline unit tests: fixture-word ranking (lamps/downlights vs room group), group-member staleness warnings (full and partial), non-group passthrough, and prompt-contract assertions. Suite: 19 router tests.

## [0.3.4]

### Fixed
- **Fast-lane router was dead on arrival — every voice command escalated to the full agent (15–25 s instead of ~2–3 s)** — two separate empty-credential bugs in `run.sh`:
  1. `FAST_LLM_API_KEY` was only sourced from the `openrouter_api_key` add-on option; installs that configured OpenRouter via Hermes setup (key in `/config/.hermes/.env`) passed an empty key, so every fast-lane completion failed and fail-open escalated to the slow full agent. The router start block now falls back to the persisted Hermes env key.
  2. The router's HA API access assumed `SUPERVISOR_TOKEN` + `http://supervisor/core/api`; when `SUPERVISOR_TOKEN` is absent the live entity search and `call_service` tools were dead. The router now falls back to the user's long-lived token against `http://homeassistant:8123/api` (the base URL that token actually authenticates against), mirroring the gateway fix from 0.3.3.
- Both failures were silent; the router now logs explicit boot warnings when either credential is missing.

### Performance (measured on Longueville install, 221-light estate)
- Device query: 7.6 s → **2.0 s**
- Light on/off: 15–25 s → **~2.6 s** (with `enable_ha_service_calls: true`)

## [0.3.3]

### Fixed
- **Voice assistant said it had "no access to devices" — the entire `ha_*` toolset and the Home Assistant platform adapter were silently disabled** — `run.sh` only exported `HASS_TOKEN` from `SUPERVISOR_TOKEN`, but on affected installs `SUPERVISOR_TOKEN` was absent from the gateway's runtime environment, so the gateway booted with an *empty* `HASS_TOKEN`. Hermes gates the built-in HA tools (`ha_list_entities`, `ha_get_state`, `ha_list_services`, `ha_call_service`) and the homeassistant platform adapter on that variable being non-empty, so every session lost device access and the boot log showed `Platform 'Home Assistant' requirements not met (pip install aiohttp)` — a misleading hint; aiohttp was installed, the token was the missing requirement. The user's long-lived token (`homeassistant_token` option) was already persisted to `/config/secrets/homeassistant.token` but never wired into the gateway env. `run.sh` now prefers the long-lived token (with `HASS_URL=http://homeassistant:8123`, which that token authenticates against — it gets 401 from the `http://supervisor/core` proxy) and falls back to `SUPERVISOR_TOKEN` only when no long-lived token is configured. Verified live: gateway logs `✓ homeassistant connected` and voice queries can enumerate and control devices again.

## [0.3.2]

### Fixed
- **Hermes dashboard chat tab could not connect behind Home Assistant Ingress** — Hermes' WebSocket upgrade guard applies its DNS-rebinding defence to the browser `Origin` header: when `Origin` is present it must match the loopback host the dashboard is bound to, but browsers send the HA/ingress origin, so `/api/ws`, `/api/events`, `/api/pty` and `/api/pub` were all rejected with a 403 close. The chat tab showed "events feed disconnected — tool calls may not appear" and messages could not be sent. nginx (already the trust boundary for the Host rewrite) now strips the `Origin` header on the `/dashboard/` proxy so the upstream relies on its token/ticket auth instead. Verified live: browser-style Origins now connect and receive `gateway.ready`.
- **Voice/router escalations to the Hermes gateway returned "Invalid API key" after every add-on restart** — the gateway's OpenAI-compatible API server requires bearer auth (`api_server.key` in the Hermes config), but `run.sh` never passed that key to the HomeOps router, so every escalated request 401'd. The router start block now reads the key from `/config/.hermes/config.yaml` and exports it as `GATEWAY_API_KEY` (which `homeops_router.py` already honours), with a startup warning if no key is found. Previously this was fixed live in process-env only and silently regressed on restart.

## [0.3.1]

### Fixed
- **Hermes dashboard blank white page behind Home Assistant Ingress** — Hermes ≤ v0.18.0 silently rejects any `X-Forwarded-Prefix` longer than 64 characters (`hermes_cli/dashboard_auth/prefix.py`). HA Supervisor ingress prefixes plus our `/dashboard` suffix are 73 characters (`/api/hassio_ingress/<43-char-token>/dashboard`), so the dashboard dropped the prefix, emitted root-relative asset URLs (`/assets/…`), the browser fetched them from HA core, and the SPA never booted. The add-on image now patches the cap to 200 at build time via `patch_hermes_prefix.py`, with a hard verification gate: the image build fails if upstream changes the code or a realistic 73-char HA ingress prefix doesn't survive normalisation, and hostile prefixes (`..`, `//`, control chars, over-long) are re-checked to confirm they are still rejected. Reported upstream to NousResearch/hermes-agent; this build-time patch will be dropped once a fixed Hermes release ships.

## [0.3.0]

### Added
- **Temporal connector** — point the agent at a Temporal server (self-hosted or Temporal Cloud) for durable long-running workflows, robust schedules, and retryable batch jobs. Options: `enable_temporal`, `temporal_address`, `temporal_namespace`, `temporal_api_key` (secret), `temporal_tls_cert_path`/`temporal_tls_key_path` (mTLS), `temporal_task_queue`. Ships a bundled `temporal-operator` skill; read-only inspection by default, state-changing operations require operator confirmation.
- **Airflow connector** — connect to an Airflow webserver's stable REST API for scheduled DAGs and repeatable pipelines. Options: `enable_airflow`, `airflow_api_url`, `airflow_username`/`airflow_password` (basic auth) or `airflow_api_token` (bearer). Ships a bundled `airflow-operator` skill with the same read-first safety rules.
- Both connectors follow the existing integrations pattern: secrets in `/config/secrets/` (0600, never in logs or the repo), env flags for the agent, status cards on the Integrations tab, and nodes in the system graph.

## [0.2.5]

### Fixed
- **Blank dashboard page under HA Ingress** — Home Assistant sends `X-Ingress-Path` with a trailing slash on some Supervisor versions. Concatenating `/dashboard` produced a double-slash prefix that Hermes' `X-Forwarded-Prefix` validator rejected, so the SPA fell back to root-relative asset URLs and rendered blank. nginx now normalises the ingress path (strips trailing slashes) before building the prefix.
- **Stale operator console after updates** — the landing page is now served with `Cache-Control: no-cache`, so browsers revalidate on every load and add-on updates are visible immediately instead of showing a cached page from a previous version.

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
