# Architecture

This is how the plan in [`rescue.md`](../rescue.md) is built, and where each piece lives in the repo.

## Big picture

```
             ┌──────────── ingress-nginx (drukrescue.local) ────────────┐
             │  /      → frontend (nginx, static)                        │
             │  /api/* → gateway                                         │
             └───────────────────────────┬──────────────────────────────┘
                                         │ JWT check, RBAC, rate limit, X-User-* headers
                                         ▼
 ┌──────┐ ┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ ┌───────────┐ ┌─────────┐ …
 │ auth │ │ user │ │ incident │ │ dispatch │ │ notification │ │ responder │ │ vehicle │  (+ shelter, resource,
 └──┬───┘ └──────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘ └───────────┘ └─────────┘   alert, weather,
    │ REST               │ events     │ REST + events │ events                              analytics, audit,
    └──► user            ▼            ▼               ▼                                     location)
                 ┌──────────────────────────────────────────┐
                 │ RabbitMQ: exchange drukrescue.events     │
                 │           queue    dispatch.requests ────┼──► HPA scales dispatch 2 → 6
                 └──────────────────────────────────────────┘
   PostgreSQL (one schema + one user per service)   Redis (rate limits, weather cache)
```

## The 15 services

| Service | Kind | State | Code | Notes |
|---|---|---|---|---|
| gateway | core | Redis | `services/gateway` | routes in `app/rules.py` (ROUTES, RULES) |
| auth | core | `auth` schema | `services/auth` | scrypt passwords, HS256 JWT, bootstrap admin |
| incident | core | `incident` schema | `services/incident` | lifecycle in `app/lifecycle.py` |
| dispatch | core | none (stateless worker) | `services/dispatch` | the algorithm is documented at the top of `app/main.py` |
| location | core | none | `services/location` | Haversine in `app/geo.py` |
| notification | core | `notification` schema | `services/notification` | event → message text in `app/messages.py` |
| user | thin | `user` schema | `services/user` | profiles |
| responder | thin | `responder` schema | `services/responder` | atomic `claim` |
| vehicle | thin | `vehicle` schema | `services/vehicle` | atomic `claim` |
| shelter, resource, alert, weather, analytics, audit | thin | own schema / Redis | `services/<name>` | **scaffolds**, see [TASKS.md](../TASKS.md) |

All of them use the shared template `libs/common/drukcommon` (health, readiness, metrics, tracing, JSON logs, config, DB, events, identity).

## Request flow (the demo story)

1. **Citizen** `POST /api/incidents`. The gateway checks the JWT and forwards it with `X-User-Id`/`X-User-Role`.
2. **Incident** saves `INC-2026-001` as `REPORTED` (commit first), then publishes `incident.created`.
   Notification tells the citizen "Report received" and tells admins "New FLOOD report".
3. **Admin** `POST /api/incidents/INC-2026-001/verify` → `VERIFIED`, plus a message on `dispatch.requests`.
4. **Dispatch** (one message at a time per pod):
   checks the incident is still VERIFIED → `GET /responders?status=AVAILABLE` and `GET /vehicles?status=AVAILABLE`
   → `POST /location/nearest` → **claims** the nearest responder, then the best vehicle (incident-type preference:
   floods → RESCUE, fire → FIRE_TRUCK, …) → publishes `dispatch.assigned` → acks.
5. **Incident** consumes `dispatch.assigned` → `DISPATCHED`. Notification tells the citizen
   "Rescue Team 04 is coming with BP-1-R0001, ETA ~8 min" and the responder "New assignment".
6. **Responder** `POST /api/incidents/{id}/progress` with `EN_ROUTE` → `ON_SCENE` (`IN_PROGRESS`) → `RESOLVED`.
7. On `RESOLVED`/`CANCELLED`, Dispatch's `dispatch.releases` consumer frees the responder and vehicle.

### Failure handling worth explaining in the viva

| Situation | What happens | Where |
|---|---|---|
| Two Dispatch pods pick the same responder | `UPDATE … WHERE status='AVAILABLE'`, so only one wins; the other gets 409 and tries the next | `responder/app/main.py → claim` |
| Dispatch pod dies mid-assignment | message not acked → redelivered to another pod; the "still VERIFIED?" check makes it safe | `dispatch/app/main.py` |
| No free unit | wait, re-queue (attempt + 1); after 3 attempts publish `dispatch.unassigned` | `retry_later` |
| Incident cancelled while being dispatched | Incident ignores the assignment and asks Dispatch to release the units | `incident → on_dispatch_result` |
| RabbitMQ down | report is still saved in PostgreSQL; readiness fails; admin can re-dispatch later | `incident → publish`, `/readyz` |
| A handler keeps crashing | one redelivery, then dead-lettered to `drukrescue.dead-letter` (alert fires) | `drukcommon/events.py` |
| Same event delivered twice | consumers are idempotent (unique event id / state checks) | notification, incident |

## Security

| Layer | Mechanism | Where |
|---|---|---|
| Identity | JWT HS256 (8 h), verified **only** at the gateway; secret in a K8s Secret | `drukcommon/auth.py`, `gateway/app/main.py` |
| Header spoofing | gateway strips client `X-User-*` and `Authorization` before forwarding | `DROP_REQUEST_HEADERS` |
| RBAC | coarse rules at the gateway + `require_roles(...)` in each service | `gateway/app/rules.py` |
| Internal-only endpoints | `/claim`, `/release`, `POST /users` are refused at the gateway | `RULES` (`NOBODY`) |
| Network | default-deny ingress in `drukrescue`; each service allows only the gateway, named callers and monitoring | `drukrescue-lib` NetworkPolicy, `platform/templates/network-policies.yaml` |
| Data isolation | one DB role per service, owning only its schema | `platform/files/init-db.sh` |
| Brute force | per-IP limit on login/register (10/min), per-user limit elsewhere (Redis) | `gateway/app/ratelimit.py` |
| Containers | non-root, read-only root FS, all capabilities dropped, seccomp RuntimeDefault | `_deployment.tpl` |
| Secrets | never in Git; `scripts/create-secrets.sh` / `make env` generate random values | |
| Audit | every event stored append-only | `services/audit` (TASKS.md A1) |

### Who may call whom (NetworkPolicy)

| Service | Accepts traffic from |
|---|---|
| gateway | ingress-nginx, frontend |
| frontend | ingress-nginx (and the gateway, which the shared template always allows) |
| every other service | gateway, plus: user ← auth · incident ← dispatch · responder/vehicle/location ← dispatch |
| all | `monitoring` namespace (Prometheus scrapes `/metrics`) |
| data namespace | only `drukrescue` and `monitoring` namespaces |

## Kubernetes and GitOps

```
deploy/
  charts/drukrescue-lib/    library chart: Deployment, Service, HPA, PDB, ConfigMap, NetworkPolicy, ServiceMonitor, Ingress
  charts/<service>/         ~15-line values.yaml + one template line
  charts/platform/          PostgreSQL, RabbitMQ, Redis (official images) + namespace policies
  charts/observability/     Grafana dashboards (JSON) + PrometheusRules
  envs/dev|demo/            values.yaml for all services + services/<name>.yaml overrides
  observability/            values for upstream charts: kube-prometheus-stack, loki, tempo, alloy, prometheus-adapter
  argocd/root-app.yaml      applied once; points at argocd/apps
  argocd/apps/              app-of-apps: one Application per service + platform + monitoring
  kind/kind-config.yaml     3-node cluster
```

The plan suggested two repos (code + config). We use **one repo** with a `deploy/` folder that ArgoCD watches.
It's the same GitOps principle (the cluster only changes when Git changes) with less overhead for a 4-person team.
`deploy/` can be split into its own repo later without changes to the charts.

```
push to main ─► CI: lint, test, helm template ─► build image ghcr.io/…/drukrescue-<svc>:sha-<commit>
             ─► CI commits image.tag bump to deploy/charts/<svc>/values.yaml
             ─► ArgoCD notices ─► rolling update (maxUnavailable 0, readiness-gated)
rollback = git revert the bump commit
```

## Observability

- **Metrics:** every service exposes `/metrics` (`http_requests_total`, `http_request_duration_seconds` with trace exemplars)
  plus the 4 custom metrics: `drukrescue_incidents_created_total`, `drukrescue_incidents_active`,
  `drukrescue_time_to_dispatch_seconds`, `drukrescue_units_available`.
- **Traces:** OpenTelemetry (FastAPI, httpx, SQLAlchemy, and RabbitMQ publish/consume with context in headers) → Tempo.
- **Logs:** JSON to stdout with `trace_id` → Alloy → Loki. Grafana links log ↔ trace (derived fields / tracesToLogs).
- **Metric → trace → log:** click an exemplar on a latency or time-to-dispatch panel → trace in Tempo → "Logs for this span".

## Autoscaling

`deploy/envs/demo/services/dispatch.yaml` holds the HPA on the external metric `rabbitmq_queue_messages_ready{queue="dispatch.requests"}`,
target 10 per pod, 2 → 6 replicas, scale-down after 120 s. RabbitMQ's `/metrics/per-object` endpoint provides the `queue` label;
prometheus-adapter (`deploy/observability/prometheus-adapter.yaml`) turns it into an external metric.
`PROCESSING_DELAY_SECONDS=2.5` makes each pod slow enough for the queue to build up during the burst test.
