# AGENTS.md — scripts (gates & dogfood)

Validation gates and the dogfood harness. These are the checks the root
AGENTS.md points at; keep them fast, offline, and deterministic.

## Ownership

- `validate_local.sh` — the full local gate: unit suites, release metadata,
  option coupling, legacy-terminology guard, SVG parse. Must pass before
  every push.
- `validate_no_openclaw_user_surface.py` — forbids legacy fork
  terminology outside `docs/legacy/`, `PORTING.md`, and the changelog.
- `validate_option_coupling.py` — config.yaml options ↔ schema ↔
  translations coupling guard.
- `validate_release_metadata.py` — version/changelog consistency.
- `dogfood_router.py` — end-to-end router harness. Offline mode boots the
  REAL router against fake LLM/gateway/HA upstreams and asserts lane
  choice, context diet, tool round-trips, escalation fidelity, and stats
  hygiene. `--live <url>` mode runs read-only probes against a running
  add-on for on-box dogfooding.

## Local Contracts

- New router scenarios go in `dogfood_router.py` as PASS/FAIL checks; the
  script must exit non-zero on any failure (CI-friendly).
- Live mode must stay read-only: health, stats, and harmless queries only.
- Fake upstreams must never require network access.
- Keep `validate_local.sh` as the single entry point; wire new gates into
  it rather than documenting extra commands.

## Verification

```sh
bash scripts/validate_local.sh
python3 scripts/dogfood_router.py
```
