# HomeOps AI Hermes porting notes

This repo was scaffolded from a legacy Home Assistant add-on because that project already solved the hard Home Assistant add-on packaging problems. The active runtime is now Hermes Agent; this file is retained only as migration history.

## Done

- Created fresh HomeOps AI repository scaffold.
- Renamed add-on directory to `homeops_ai`.
- Updated repository metadata, add-on slug, image name, and README direction.
- Switched the Dockerfile runtime install path toward the official Hermes Agent installer.

## Still to port before a release

- Replace `run.sh` OpenClaw lifecycle with Hermes lifecycle:
  - `hermes gateway run`
  - optional API server / dashboard processes
  - Hermes cron/status/log commands
- Replace `/config/.openclaw` and `/config/clawd` state with Hermes paths:
  - `/config/.hermes`
  - `/config/homeops` or another workspace directory
- Convert `hermes_config_helper.py` from OpenClaw JSON patching to Hermes `config.yaml` / `.env` management.
- Decide whether the inherited MCP bridge remains useful, or whether Hermes' native Home Assistant toolset is enough.
- Convert bundled skill/bootstrap content to Hermes-native skills and context.
- Replace OpenClaw-specific docs, tests, translations, dashboard strings, and troubleshooting.
- Rework security model around Hermes toolsets, provider keys, gateway platforms, and Home Assistant write permissions.

## Release rule

Current production releases should remain Hermes-native. Any remaining legacy references must either be migration-history only or deliberately compatibility-wrapped.
