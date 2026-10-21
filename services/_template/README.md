# Service template

All 15 services were started from this. You only need it to add a **16th** service.
To work on an existing scaffold (shelter, alert, ...) go straight to its folder.

## Adding a new service `foo`

1. `cp -r services/_template services/foo` and rename `template` to `foo` in `app/main.py` and `conftest.py`.
2. Need a database? Add `app/models.py` (copy from `services/vehicle`) and add `foo` to:
   - `DB_SERVICES` in `deploy/charts/platform/values.yaml` (creates schema + DB user)
   - `scripts/create-secrets.sh` (generates its password) and `docker-compose.yml` (postgres env)
3. Helm: `cp -r deploy/charts/vehicle deploy/charts/foo` and edit `Chart.yaml` + `values.yaml`.
4. ArgoCD: add `foo` to `services:` in `deploy/argocd/apps/values.yaml`.
5. Gateway: add a route in `services/gateway/app/rules.py` (`ROUTES`) and any role rules.
6. docker-compose: copy one of the service blocks.
7. CI picks it up automatically: any folder under `services/` (except `_template`) is a service.

## What `create_app` gives you

| Feature | Where |
|---|---|
| `GET /healthz` liveness, `GET /readyz` readiness (DB + RabbitMQ) | `libs/common/drukcommon/app.py` |
| `GET /metrics` Prometheus, `http_requests_total`, latency histogram with trace exemplars | `metrics.py` |
| OpenTelemetry traces (FastAPI, httpx, SQLAlchemy, RabbitMQ publish/consume) | `tracing.py`, `events.py` |
| JSON logs with `trace_id` | `logs.py` |
| Env-var config | `config.py` |
| `X-User-Id` / `X-User-Role` → `Principal`, `require_roles(...)` | `auth.py` |
