# AGENTS.md — HomeOps AI add-on runtime

Everything the add-on does at runtime lives in this folder. Parent rail:
`../AGENTS.md` (public-repo, release, and coupling rules apply here fully).

## Ownership

- `run.sh` — PID 1 orchestrator: reads `/data/options.json`, configures
  Hermes, starts gateway → router → dashboard API → dashboard UI →
  workspace → nginx → ttyd.
- `homeops_router.py` — fast-lane voice router (see Local Contracts).
- `dashboard_api.py` — read-mostly operator API behind `/super/api/`.
- `hermes_config_helper.py`, `oc_config_helper.py` — safe config JSON/YAML edits.
- `render_nginx.py` + `nginx.conf.tpl` + `landing.html.tpl` — ingress UI.
- `config.yaml` — HA options + schema (couple with translations + DOCS.md).
- `Dockerfile` — image build; pin `ARG HERMES_VERSION` to a stable release.
- `bundled-skills/`, `bootstrap-workspace/` — seeded agent workspace.

## Local Contracts

### Router (homeops_router.py)

- OpenAI-compatible `/v1/chat/completions` on `ROUTER_PORT` (default 8643),
  loopback only. HA conversation integrations point HERE, not at the raw
  gateway, when `agent_mode: router`.
- Contract: parse entity table from the incoming system prompt → score
  against the utterance → send at most `MAX_FAST_ENTITIES` candidates to the
  fast model → expose `search_entities` / `get_state` / `call_service` tools
  for everything else → escalate complex/streaming requests verbatim to the
  Hermes gateway on `GATEWAY_INTERNAL_PORT`.
- Fail-open: any router error must escalate, never drop the request.
- `call_service` is gated by `ENABLE_HA_SERVICE_CALLS` (add-on option
  `enable_ha_service_calls`, default false). Validate all entity/domain/
  service strings against strict regexes before any HA API call.
- Read-only observability: `/router/health`, `/router/stats` (proxied under
  ingress `/router/`). Stats must never contain tokens or key material.
- stdlib only. No new Python dependencies in the image for the router.

### run.sh

- Runs with `set -euo pipefail`; avoid constructs that fail under `set -e`.
- Validate all user values from `/data/options.json` before injecting into
  shell/nginx/hermes config (see TERMINAL_PORT validation pattern).
- Idempotent on restart; `/config/` is persistent user state — never wipe.
- Kill stale port listeners via `stop_if_listening` before starting services.

### Gateway/auth

- Hermes v2026.2.22+ redacts secrets in `hermes config get`; for token
  retrieval prefer `jq -r '.gateway.auth.token' /config/.hermes/config.yaml`.
- `trusted-proxy` mode may reject direct local CLI WS calls
  (`trusted_proxy_user_missing`); document, don't hide.
- For `lan_https`, keep SAN generation deterministic and regeneration
  triggered on SAN/IP changes.

### Templates

- New placeholder in `landing.html.tpl` / `nginx.conf.tpl` ⇒ update
  `render_nginx.py` in the same change.
- Ingress links must be relative (`./terminal/`, `./dashboard/`,
  `./router/stats`) or derived from `window.location.pathname` — never
  absolute paths (breaks under HA Ingress).
- Landing-page guidance changes ⇒ sync troubleshooting text in `../DOCS.md`.

## Work Guidance

- Shell: POSIX-friendly Bash, explicit quoting, descriptive names.
- Python: small focused helpers, explicit error handling, no hidden side
  effects, stdlib preferred.
- YAML/Markdown: preserve existing style. Avoid new dependencies.

## Verification

```sh
bash ../scripts/validate_local.sh
python3 ../scripts/dogfood_router.py
bash -n run.sh
```
