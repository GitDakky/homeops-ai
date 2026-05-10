# Repository Guidelines

## Project Scope

This repository builds the **HomeOps AI (DEV)** Home Assistant add-on.
The add-on packages Hermes Agent + nginx + ttyd and manages startup/configuration glue.

## Architecture at a Glance

- Add-on root metadata/docs:
  - `README.md`
  - `DOCS.md`
  - `SECURITY.md`
  - `repository.yaml`
- Runtime implementation (all add-on behavior lives here):
  - `homeops_ai/run.sh` (PID 1 orchestrator)
  - `homeops_ai/hermes_config_helper.py` (safe JSON config edits)
  - `homeops_ai/render_nginx.py` (template rendering)
  - `homeops_ai/nginx.conf.tpl`
  - `homeops_ai/landing.html.tpl`
  - `homeops_ai/config.yaml` (HA options + schema)
  - `homeops_ai/translations/*.yaml` (all locale UI strings)
  - `homeops_ai/Dockerfile`
  - `homeops_ai/CHANGELOG.md`

## Core Rules

- Fix root causes, not symptoms.
- Keep edits surgical; do not refactor unrelated code.
- Never introduce insecure defaults.
- Never log secrets or auth tokens.
- Keep behavior backward-compatible unless the change explicitly requires a migration.

## Add-on Config Coupling Rules (Critical)

When adding/changing any add-on option, update **all** of the following in one change:

1. `homeops_ai/config.yaml`
   - `options:` default
   - `schema:` validation entry
   - comments/help text
2. `homeops_ai/translations/en.yaml`
3. `homeops_ai/translations/bg.yaml`
4. `homeops_ai/translations/de.yaml`
5. `homeops_ai/translations/es.yaml`
6. `homeops_ai/translations/pl.yaml`
7. `homeops_ai/translations/pt-BR.yaml`
8. `DOCS.md` configuration reference / troubleshooting if user-facing
9. `homeops_ai/CHANGELOG.md`

If any of these are skipped, the UX becomes inconsistent in HA.

## Runtime Safety Rules

- `run.sh` runs with `set -euo pipefail`; avoid constructs that fail unexpectedly under `set -e`.
- Validate all user-provided values from `/data/options.json` before injecting into shell/nginx/hermes config.
- Keep `run.sh` idempotent on restart (multiple starts must not corrupt state).
- Treat `/config/` as persistent state; never wipe user data unless explicitly requested.

## Gateway/Auth/Security Rules

- Hermes v2026.2.22+ redacts sensitive values in `hermes config get`.
  - For token retrieval guidance, prefer: `jq -r '.gateway.auth.token' /config/.hermes/config.yaml`.
- `trusted-proxy` mode may reject direct local CLI WS calls (`trusted_proxy_user_missing`); document this clearly instead of hiding it.
- For `lan_https` certificate logic, keep SAN generation deterministic and regeneration-triggered on SAN/IP changes.

## Template Coupling Rules

- If adding placeholders in `landing.html.tpl` or `nginx.conf.tpl`, update `render_nginx.py` in the same change.
- If landing-page guidance changes (commands/errors), sync corresponding troubleshooting text in `DOCS.md`.

## Versioning and Changelog

- User-visible changes should update:
  - `homeops_ai/CHANGELOG.md`
  - `homeops_ai/config.yaml` version
- Keep changelog entries user-facing and action-oriented.

## Coding Style

- Shell: POSIX-friendly Bash, explicit quoting, descriptive variable names.
- Python: small focused helpers, explicit error handling, no hidden side effects.
- YAML/Markdown: preserve existing style and structure.
- Avoid adding dependencies unless necessary.

## Validation Checklist (Run After Relevant Changes)

From repo root:

```sh
bash scripts/validate_local.sh
```

For option changes:
- verify `config.yaml` option + schema + all translations exist
- verify `DOCS.md` matches current behavior

For startup/auth/proxy/cert changes:
- verify log messages remain clear and actionable
- verify `landing.html.tpl` instructions match actual commands

## Commit Scope

- Group related changes only.
- Do not include unrelated formatting churn.
- Do not edit generated/cache folders (`__pycache__`, temporary outputs).
