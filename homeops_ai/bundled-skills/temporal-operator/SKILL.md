Use this skill when the Temporal connector is configured (TEMPORAL_ENABLED=true).

Connection:
- address: $TEMPORAL_ADDRESS (host:port, gRPC)
- namespace: $TEMPORAL_NAMESPACE
- default task queue: $TEMPORAL_TASK_QUEUE
- API key (Temporal Cloud): read from $TEMPORAL_API_KEY_FILE (/config/secrets/temporal.api_key) — never echo it
- mTLS (self-hosted TLS): cert/key at $TEMPORAL_TLS_CERT_PATH / $TEMPORAL_TLS_KEY_PATH

How to interact:
- Prefer the `temporal` CLI if installed: `temporal --address "$TEMPORAL_ADDRESS" --namespace "$TEMPORAL_NAMESPACE" workflow list`
- Cloud auth: add `--api-key "$(cat "$TEMPORAL_API_KEY_FILE")"` and `--tls`
- mTLS: add `--tls-cert-path "$TEMPORAL_TLS_CERT_PATH" --tls-key-path "$TEMPORAL_TLS_KEY_PATH"`
- Python: `pip install temporalio` in a venv for writing workers/workflows.

Good uses in a Home Assistant context:
- durable long-running jobs that must survive add-on restarts (multi-day monitoring, staged migrations)
- scheduled workflows (Temporal Schedules) as robust cron with retries, backoff, and visibility
- fan-out/fan-in batch work (e.g. re-checking hundreds of entities) with per-item retry state

Rules:
- Read-only inspection (list/describe workflows, schedules) is always fine.
- Starting/signalling/cancelling workflows changes external state — confirm with the operator first unless they asked explicitly.
- Never print API keys or cert contents into chat, logs, or committed files.
