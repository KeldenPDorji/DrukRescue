# DrukRescue

**A Kubernetes-based emergency & disaster response platform for Bhutan.**
Citizens report incidents, the system dispatches the nearest available team, and everyone sees live status.

15 Python (FastAPI) microservices on Kubernetes, packaged with **Helm** (one shared library chart), delivered by
**ArgoCD (GitOps)**, observed with **Prometheus / Grafana / Loki / Tempo**. The Dispatch service **autoscales 2 → 6
pods on RabbitMQ queue depth** during a disaster surge.

College of Science and Technology, Royal University of Bhutan.
Team: Dupchu Wangmo · Kinley Palden · Kelden Phuntsho Dorji · Tshering Wangpo Dorji

> 📋 The plan is in [`rescue.md`](rescue.md). Who does what is in [`TASKS.md`](TASKS.md). How we work is in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Status

| Area | State |
|---|---|
| Service template (`libs/common`) | ✅ done |
| Core services: gateway, auth, incident, dispatch, location, notification | ✅ done, tested |
| Thin services: user, responder, vehicle | ✅ done, tested |
| Thin services: shelter, resource, alert, weather, analytics, audit | 🟡 scaffolded: they run and deploy, logic is in TASKS.md |
| Helm library chart + 16 charts, dev/demo envs, Dispatch HPA | ✅ renders and validates |
| ArgoCD app-of-apps, observability stack values | ✅ written, 🟡 to be verified on the cluster |
| CI (lint, test, build, push, GitOps bump) | ✅ written, 🟡 image scan is in TASKS.md D5 |
| Frontend | 🟡 login + citizen view; responder/admin views in TASKS.md B3 |
| Dashboards | 🟡 starter Command Centre; rest in TASKS.md D4 |

## Quick start (laptop, no Kubernetes)

Needs Docker and Python 3.12+.

```bash
make env     # creates .env with random secrets and prints the admin login
make up      # builds and starts all 15 services + Postgres, RabbitMQ, Redis, frontend
make seed    # demo responders, vehicles and logins (passwords printed once)
make smoke   # end-to-end check: report → verify → dispatch → notify → resolve → units freed
```

- App: http://localhost:8080 · API: http://localhost:8000/api · RabbitMQ UI: http://localhost:15672
- Traces/logs/metrics locally: set `OTEL_EXPORTER_OTLP_ENDPOINT=http://lgtm:4318` in `.env`, then
  `docker compose --profile obs up -d` and open Grafana at http://localhost:3000

Try the flow with curl:

```bash
TOKEN=$(curl -s localhost:8000/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"citizen@drukrescue.bt","password":"<printed by make seed>"}' | jq -r .access_token)
curl -s localhost:8000/api/incidents -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"type":"FLOOD","severity":"HIGH","description":"Flooding near Babesa","lat":27.4447,"lng":89.6476,"district":"Thimphu","location_name":"Babesa"}'
# then, as admin: POST /api/incidents/INC-2026-001/verify  → Dispatch assigns the nearest team within seconds
```

## On Kubernetes (Kind + ArgoCD)

```bash
make kind-up      # 3-node Kind, ingress-nginx, secrets, ArgoCD, root app-of-apps
make kind-load    # until CI has pushed images to GHCR
```

After that, **Git is the only way to change the cluster**: edit `deploy/`, push, and ArgoCD syncs.
Details and troubleshooting are in [`docs/runbook.md`](docs/runbook.md).

## Repository layout

```
libs/common/            drukcommon: the shared service template (health, metrics, tracing, logs, DB, events, auth)
services/<name>/        one folder per microservice: app/, tests/, requirements.txt
services/_template/     copy this to add a new service
frontend/               static web app (nginx)
deploy/charts/          Helm: drukrescue-lib (library), one chart per service, platform, observability
deploy/envs/            dev and demo values
deploy/argocd/          root app + app-of-apps
deploy/observability/   values for kube-prometheus-stack, Loki, Tempo, Alloy, prometheus-adapter
deploy/kind/            Kind cluster config
scripts/                bootstrap, secrets, seed, .env generator
loadtest/               k6 burst test
docs/                   architecture, event contracts, runbook
```

## Common commands

`make help` lists everything. The ones you'll use most:

| Command | What it does |
|---|---|
| `make test` / `make test-incident` | unit tests (all / one service) |
| `make lint` | ruff |
| `make helm-template ENV=demo` | objective (a): render all services from the library chart |
| `make up` / `make down` / `make logs` | local stack |
| `make kind-up` / `make kind-load` | cluster |

## Docs

- [Architecture](docs/architecture.md): services, request flow, failure handling, security, GitOps, observability
- [Event contracts](docs/events.md): every RabbitMQ message and who consumes it
- [Runbook](docs/runbook.md): operating and debugging the cluster
