# AGENTS.md — DOX rail for HomeOps AI

This repo uses the [DOX](https://github.com/agent0ai/dox) documentation method:
a hierarchy of `AGENTS.md` files that are **binding work contracts** for their
subtrees. This root file is the rail; child files own domain detail.

## DOX framework

- AGENTS.md files are binding work contracts for their subtrees.
- Work products, source materials, instructions, records, assets, and durable
  docs must stay understandable from the nearest applicable AGENTS.md plus
  every parent AGENTS.md above it.

### Read before editing

1. Read this root AGENTS.md.
2. Identify every file or folder you expect to touch.
3. Walk from the repository root to each target path and read every
   AGENTS.md found along each route.
4. Use the nearest AGENTS.md as the local contract and parent docs for
   repo-wide rules. Closer docs control local detail; no child doc may
   weaken DOX or the non-negotiables below.

Do not rely on memory. Re-read the applicable DOX chain in the current
session before editing.

### Update after editing

Every meaningful change requires a DOX pass before the task is done. Update
the closest owning AGENTS.md when a change affects purpose, scope, structure,
contracts, workflows, constraints, side effects, artifacts, or preferences.
Refresh affected Child DOX Indexes. Remove stale text immediately.

## Purpose

HomeOps AI is a Home Assistant add-on that packages **Hermes Agent** as a
local AI operations agent, plus a **fast-lane voice router** that makes
Assist voice interactions fast on large installs by dieting the entity
context and lazy-loading the rest through on-demand tools.

## Non-negotiable design rules (repo-wide)

- **PUBLIC REPO.** Never commit secrets, tokens, internal IPs, private
  hostnames, or real household entity data. Redact examples.
- Fix root causes, not symptoms. Keep edits surgical.
- Never introduce insecure defaults. Never log secrets or auth tokens.
- Keep behavior backward-compatible unless the change explicitly requires a
  migration.
- **Release rule:** every change Home Assistant must see requires a version
  bump in `homeops_ai/config.yaml` AND a matching top entry in
  `homeops_ai/CHANGELOG.md`, committed together and pushed to `main`.
- No OpenClaw terminology on current user-facing/runtime surfaces
  (`scripts/validate_no_openclaw_user_surface.py` enforces this; history
  lives only in `docs/legacy/` and `PORTING.md`).

## Verification (run from repo root)

```sh
bash scripts/validate_local.sh        # full local gate (tests + guards + SVG)
python3 scripts/dogfood_router.py     # offline end-to-end router dogfood
```

CI after push: `gh run list --repo GitDakky/homeops-ai --limit 6`
(or check GitHub Actions in the browser).

## Add-on config coupling (critical)

When adding/changing any add-on option, update **all** in one change:
`homeops_ai/config.yaml` (options + schema + comments), all six
`homeops_ai/translations/*.yaml`, `DOCS.md` if user-facing, and
`homeops_ai/CHANGELOG.md`. Skipping any yields inconsistent HA UX.

## Commit scope

- Group related changes only; no unrelated formatting churn.
- Do not edit generated/cache folders (`__pycache__`, temporary outputs).

## Child DOX Index

- `homeops_ai/AGENTS.md` — add-on runtime: run.sh lifecycle, router,
  Dockerfile, config/schema/translations, nginx + landing templates.
- `tests/AGENTS.md` — offline unit test suite; what must stay covered.
- `scripts/AGENTS.md` — validation gates and the dogfood harness.
- `docs/AGENTS.md` — documentation, knowledge bundle, and legacy history.
