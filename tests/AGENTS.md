# AGENTS.md — tests

Offline unit tests. No network, no Home Assistant, no Docker. Everything
here must run in seconds on a bare Python 3.11+ with pytest (router tests)
or unittest (legacy suites run via `scripts/validate_local.sh`).

## Ownership

- `test_homeops_router.py` — router parsing/scoring/lane/tool contracts
  (pytest). Loads `homeops_ai/homeops_router.py` by file path.
- `test_run_helpers.py` — run.sh helper functions (unittest; requires `jq`
  on PATH — note: invoked via `bash -lc`, so login-shell PATH applies).
- `test_dashboard_api.py`, `test_oc_config_helper.py` — operator API and
  config helper suites (unittest).

## Local Contracts

- Every new runtime behavior in `homeops_ai/` needs a test here or a
  scenario in `scripts/dogfood_router.py` — preferably both.
- Router invariants that must stay covered: entity-table parsing, candidate
  cap (`MAX_FAST_ENTITIES`), escalation triggers, input validation on
  `call_service`/`get_state`, service-call gating, no-secrets-in-stats.
- Tests must not require credentials or touch real HA instances.

## Verification

```sh
python3 -m pytest tests/test_homeops_router.py -q
bash scripts/validate_local.sh
```
