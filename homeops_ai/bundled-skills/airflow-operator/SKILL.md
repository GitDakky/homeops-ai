Use this skill when the Airflow connector is configured (AIRFLOW_ENABLED=true).

Connection:
- base URL: $AIRFLOW_API_URL (stable REST API lives under /api/v1, Airflow 3.x also /api/v2)
- basic auth: username $AIRFLOW_USERNAME + password from $AIRFLOW_PASSWORD_FILE (/config/secrets/airflow.password)
- or bearer token from $AIRFLOW_API_TOKEN_FILE (/config/secrets/airflow.api_token)
- never echo credentials

How to interact (curl examples):
- List DAGs:      curl -su "$AIRFLOW_USERNAME:$(cat "$AIRFLOW_PASSWORD_FILE")" "$AIRFLOW_API_URL/api/v1/dags?limit=100"
- Bearer variant: curl -sH "Authorization: Bearer $(cat "$AIRFLOW_API_TOKEN_FILE")" "$AIRFLOW_API_URL/api/v1/dags"
- DAG runs:       GET  /api/v1/dags/{dag_id}/dagRuns?order_by=-execution_date&limit=10
- Trigger a run:  POST /api/v1/dags/{dag_id}/dagRuns  with JSON {"conf": {...}}
- Task states:    GET  /api/v1/dags/{dag_id}/dagRuns/{run_id}/taskInstances
- Health:         GET  /api/v1/health (no auth on most installs)

Good uses in a Home Assistant context:
- repeatable scheduled pipelines (nightly backups, data exports, report generation)
- checking why a scheduled job failed (dagRuns + taskInstances + logs endpoints)
- triggering a known DAG on operator request

Rules:
- Read-only inspection (list DAGs, runs, task states, health) is always fine.
- Triggering DAG runs, pausing/unpausing DAGs, or clearing tasks changes external state — confirm with the operator first unless they asked explicitly.
- Treat DAG conf payloads as code review material: show the operator what will be sent before sending it.
