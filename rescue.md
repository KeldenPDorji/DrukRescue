# DrukRescue: Simplified Project Plan

**A Kubernetes-based emergency & disaster response platform**

Team: Dupchu Wangmo · Kinley Palden · Kelden Phuntsho Dorji · Tshering Wangpo Dorji
College of Science and Technology, Royal University of Bhutan

---

## 0. The one-paragraph pitch (memorise this)

Bhutan faces floods, GLOFs, landslides, earthquakes and forest fires, but emergency response still runs on phone calls and spreadsheets. **DrukRescue** gives citizens, responders and a command centre one shared system: citizens report incidents, the system dispatches the nearest available team, and everyone sees live status. Technically, it is **15 small microservices on Kubernetes**, deployed with **Helm + ArgoCD (GitOps)**, monitored with **Prometheus/Grafana/Loki/Tempo**, and it **scales the Dispatch service from 2 to 6 pods based on RabbitMQ queue depth** during a disaster surge.

---

## 1. The problem

| Today | Effect |
|---|---|
| Reports come by phone/spreadsheet; no single record per incident | Information gets lost or duplicated |
| Dispatchers can't see who's available or where vehicles/shelters are | Slow, guesswork-based dispatch |
| Response times are never measured | Nothing improves |

**Result:** slower response, wasted resources, avoidable loss of life.

---

## 2. Aim & objectives (these are what you get graded against; keep them)

**Aim:** Build and operate DrukRescue as microservices on Kubernetes, deployed through GitOps, fully observable, and able to scale itself during a disaster surge.

| # | Objective | Done when… |
|---|---|---|
| a | **Helm charts**: one shared library chart + one chart per service + per-env values | `helm template` renders all 15 services from the library |
| b | **GitOps with ArgoCD**: Git is the only path to the cluster | Changing a value in Git changes the cluster with no `kubectl apply` |
| c | **Observability**: Prometheus metrics, OpenTelemetry traces (Tempo), Loki logs, all in Grafana | One request can be followed metric → trace → log |
| d | **Custom-metric autoscaling**: Dispatch 2 → 6 replicas on RabbitMQ queue depth | Load test shows replicas rise and fall in Grafana |
| e | **Dashboards**: one application dashboard, one infrastructure dashboard | Both are saved as JSON in Git and load automatically |

---

## 3. Users (3 roles)

| Role | Can do |
|---|---|
| **Citizen** | Register/login, report emergency (type, description, location, optional photo), track status, see alerts, find nearby shelters |
| **Responder** | See assignments, accept/reject, update status & location, update incident progress |
| **Admin (Command Centre)** | See all incidents/resources, verify incidents, dispatch manually if needed, send area alerts, view analytics |

**Incident lifecycle:** `REPORTED → VERIFIED → DISPATCHED → IN_PROGRESS → RESOLVED` (plus `CANCELLED` for false reports)

---

## 4. The 15 microservices: split into "core" and "thin"

This is the main simplification. Only **6 services have real logic**. The other 9 are basic CRUD built from the same template in an afternoon each. You still have 15 independent services (as proposed), but you only have to *deeply* explain 6.

### Core (real logic: put your best effort here)

| Service | What it does | Talks to |
|---|---|---|
| **API Gateway** | Single entry point. Routes `/api/<service>/*`, checks JWT, adds `X-User-Id` / `X-User-Role` headers, rate limits | All services (REST) |
| **Auth** | Register, login, issue JWT with role (`CITIZEN`, `RESPONDER`, `ADMIN`) | User (REST) |
| **Incident** | Create/read/update incidents, owns the status lifecycle | Publishes events to RabbitMQ |
| **Dispatch** | Queue worker: takes a verified incident, finds nearest free responder + vehicle, assigns them | Responder, Vehicle, Location (REST); RabbitMQ |
| **Location** | Stateless geo helper: given a point and a list of units, returns them sorted by distance (Haversine formula) | Nothing, pure calculation |
| **Notification** | Listens to events and creates in-app notifications for citizens/responders | RabbitMQ consumer |

### Thin (CRUD from template)

| Service | Owns |
|---|---|
| **User** | Profiles (name, phone, email, role, address) |
| **Responder** | Responders: team, status (`AVAILABLE` / `BUSY` / `OFFLINE`), last lat/lng |
| **Vehicle** | Ambulances, fire trucks, rescue & police vehicles, status, lat/lng |
| **Shelter** | Shelters: name, lat/lng, capacity, occupied |
| **Resource** | Supply counts: medical kits, blankets, water, food |
| **Alert** | Area-wide warnings (title, message, district, severity, expiry) |
| **Weather** | Fetches weather for a district from a free API (e.g. Open-Meteo, no key) and caches it in Redis |
| **Analytics** | Consumes events, stores counts, serves `/stats` (incidents by type, avg time to dispatch) |
| **Audit** | Consumes every event and stores it as an append-only log (who did what, when) |

### What makes each service "independent" (say this in the viva)

- **Own image**: built and versioned by its own CI job
- **Own chart**: own Helm release and ArgoCD app
- **Own data**: own schema, no shared tables
- **Own scaling**: own replicas, probes, HPA
- **Contracts only**: talks to others through REST or RabbitMQ events, never their database

---

## 5. How a request flows (the demo story)

```
Citizen reports "Flood near Babesa"
   │
   ▼
API Gateway  (checks JWT)
   │
   ▼
Incident Service → saves INC-2026-001 as REPORTED → publishes incident.created
   │
   ▼
Admin clicks "Verify" → status VERIFIED → message put on queue dispatch.requests
   │
   ▼
Dispatch worker picks it up
   ├─ GET available responders (Responder svc)
   ├─ GET available vehicles  (Vehicle svc)
   ├─ POST to Location /nearest → closest team + vehicle
   ├─ marks both BUSY
   └─ publishes dispatch.assigned
   │
   ├──► Incident svc   → status DISPATCHED
   ├──► Notification   → "Rescue Team 04 dispatched" to citizen + responder
   ├──► Analytics      → records time-to-dispatch
   └──► Audit          → logs the action

Responder taps "En route" → "On scene" (IN_PROGRESS) → "Resolved"
Citizen's page shows: ✓ Reported ✓ Assigned ✓ En route ○ Resolved
```

---

## 6. Communication: keep it to two simple rules

1. **REST** when you need an answer right now (Gateway → services, Dispatch → Responder/Vehicle/Location).
2. **RabbitMQ** when something *happened* and others may care.

Use **one topic exchange** called `drukrescue.events` plus **one work queue** for dispatch.

| Event / queue | Published by | Consumed by |
|---|---|---|
| `incident.created` | Incident | Analytics, Audit, Notification |
| `incident.status_changed` | Incident | Analytics, Audit, Notification |
| queue `dispatch.requests` | Incident (on VERIFIED) | Dispatch (this is the queue that drives autoscaling) |
| `dispatch.assigned` | Dispatch | Incident, Notification, Analytics, Audit |
| `alert.issued` | Alert | Notification, Audit |

No Kafka, no gRPC. RabbitMQ only, REST only.

---

## 7. Data: one PostgreSQL, one schema per service

You don't need 15 databases. Run **one PostgreSQL StatefulSet** and give each service **its own schema and its own DB user** that can only touch that schema. That still satisfies "own data, no shared tables" and is easy to explain.

- **PostgreSQL**: all persistent data (schema per service)
- **Redis**: weather cache + gateway rate limiting only
- **RabbitMQ**: events + dispatch queue (durable queues)
- **Photos**: store in a PersistentVolume or skip and keep a URL field (stretch goal)
- **No PostGIS**: Location does Haversine distance in code. Enough for Bhutan-scale data.

---

## 8. Tech choices (keep everything in ONE language)

| Layer | Choice | Why |
|---|---|---|
| Services | **One language for all 15** (e.g. Python FastAPI *or* Node Express) | One template, one Dockerfile, everyone can read everyone's code |
| Frontend | One web app with 3 role-based views | Not counted in the 15; polling every 5 s for "live" status (no WebSockets) |
| Cluster | **Kind**, 3 nodes, on one laptop | Free, local |
| Packaging | **Helm**: library chart + per-service charts | Objective (a) |
| Delivery | **GitHub Actions + ArgoCD** (app-of-apps) | Objective (b) |
| Metrics | Prometheus + Alertmanager | Objective (c) |
| Traces | OpenTelemetry SDK in the template → Tempo | Objective (c) |
| Logs | JSON logs → Loki | Objective (c) |
| Scaling | Prometheus Adapter + HPA (KEDA as fallback) | Objective (d) |

### The service template (build this first, in Week 2)

Every service starts as a copy of this. Get it right once.

```
service-template/
  app/
    main.py            # routes
    db.py              # DB connection using its own schema
    events.py          # RabbitMQ publish/consume helpers
  Dockerfile
  requirements.txt
```

Every service gets these for free from the template:

- `GET /healthz` (liveness) and `GET /readyz` (readiness: checks DB/RabbitMQ)
- `GET /metrics` (Prometheus)
- OpenTelemetry auto-instrumentation (traces to Tempo)
- JSON logging with `trace_id` in every line
- Reads config from env vars (DB URL, RabbitMQ URL, JWT secret)

---

## 9. Kubernetes layout

### Namespaces

| Namespace | Contains |
|---|---|
| `ingress-nginx` | Ingress controller (entry point) |
| `drukrescue` | The 15 app services + frontend |
| `data` | PostgreSQL, Redis, RabbitMQ |
| `monitoring` | Prometheus, Grafana, Loki, Tempo, OTel collector |
| `argocd` | ArgoCD |

### Repo structure

```
drukrescue/                 # app code repo
  services/<15 folders>
  frontend/
  .github/workflows/        # one workflow per service (path filter)

drukrescue-deploy/          # config repo (ArgoCD watches this)
  charts/
    drukrescue-lib/         # shared templates
    incident/               # Chart.yaml + values.yaml (tiny)
    dispatch/
    ... one per service
    platform/               # data + monitoring
  envs/
    dev/values.yaml         # 1 replica each, low resources
    demo/values.yaml        # 2 replicas each, HPA on
  argocd/
    root-app.yaml           # app-of-apps
```

### What the library chart renders for every service

`Deployment` · `Service` · `HPA` · `PodDisruptionBudget` · `ConfigMap` · `Secret` reference · `NetworkPolicy` · `ServiceMonitor`

A per-service `values.yaml` should be about 15 lines: image, port, env, replicas, resources.

---

## 10. GitOps flow

```
Push code → GitHub Actions (test, build, scan, push image)
         → CI commits new image tag to drukrescue-deploy
         → ArgoCD sees the change, applies Helm release
         → Rolling update; readiness probes gate each new pod
```

- **Single source of truth:** cluster state lives in Git. ArgoCD self-heal reverts manual changes.
- **App-of-apps:** one root Application creates one Application per service and per platform component.
- **Rollback:** `git revert` the tag bump. A bad rollout stalls on failed readiness while old pods keep serving.

---

## 11. Security (just enough)

- **JWT** (HS256, secret in a Kubernetes Secret), validated at the Gateway only
- **RBAC by role** in the Gateway: e.g. only `ADMIN` can verify incidents or send alerts
- **Kubernetes Secrets** for DB passwords and JWT secret (never in Git as plain text)
- **NetworkPolicy**: default-deny in `drukrescue`; allow ingress-nginx → gateway and gateway → services
- **Rate limiting** at the Gateway (Redis counter)
- **Audit log** of every important action

---

## 12. Autoscaling Dispatch on queue depth (your headline feature)

1. Surge: many reports arrive
2. `dispatch.requests` queue grows
3. Prometheus scrapes RabbitMQ queue depth
4. Prometheus Adapter exposes it to Kubernetes as an external metric
5. HPA scales Dispatch 2 → 6
6. Queue drains → scale down after 2 min

```yaml
# dispatch HPA (Helm values)
minReplicas: 2
maxReplicas: 6
metrics:
  - type: External
    external:
      metric:
        name: rabbitmq_queue_messages_ready
        selector:
          matchLabels:
            queue: dispatch.requests
      target:
        type: AverageValue
        averageValue: "10"     # messages per pod
behavior:
  scaleDown:
    stabilizationWindowSeconds: 120   # default is 5 min; this gives "scale down after 2 min"
```

**Why not CPU?** Dispatch mostly waits on network calls, so CPU stays low even when it's overwhelmed. Queue backlog shows real demand.

### ⚠️ Make sure the queue actually grows during the demo

100 reports spread evenly over 10 minutes is under 1 per 5 seconds. Two Dispatch pods will clear that instantly, the queue stays near 0, and **the HPA never fires**. To get a visible scale-up:

- Fire the 100 reports as a **burst** (e.g. within the first 30–60 s) with k6 or Locust, and auto-verify them in the demo environment (`AUTO_VERIFY=true` in `envs/demo/values.yaml`).
- Give Dispatch a configurable `PROCESSING_DELAY_SECONDS` (≈2–3 s, explained as "route calculation + confirming with the team").
- Use `averageValue: "10"` (not 20). With ~100 messages waiting, the HPA wants 10 pods and caps at 6.

### Two setup gotchas

- RabbitMQ's Prometheus plugin only shows **per-queue** metrics on its detailed/per-object endpoint. Scrape that, or the `queue` label won't exist.
- If the Prometheus Adapter config fights you for more than a day, switch to **KEDA's RabbitMQ scaler**. It's already in your proposal as the fallback, so it isn't a deviation.

---

## 13. High availability & capacity

**Availability mechanisms**

- 2+ replicas per service in `demo`, spread across nodes (topology spread)
- PodDisruptionBudget: `minAvailable: 1`
- Liveness & readiness probes from the template
- Rolling updates with `maxUnavailable: 0` → zero downtime
- PostgreSQL on a PersistentVolume, durable RabbitMQ queues

**Known limit (say it before they ask):** Kind runs on one physical host, so it's not truly HA. Production would use a multi-host cluster and replicated PostgreSQL.

**Resource requests at peak (estimate)**

| Tier | Pods | CPU | Memory |
|---|---|---|---|
| Services (15 × 2) | 30 | 3.00 | 3.8 Gi |
| Dispatch burst (+4) | 4 | 0.40 | 0.5 Gi |
| Data layer | 3 | 0.85 | 1.8 Gi |
| GitOps + observability | ~8 | 1.65 | 3.9 Gi |
| **Total at peak** | **~45** | **5.90** | **10.0 Gi** |

Host target: 8 vCPU / 16 GB RAM. If the laptop struggles, set the thin services to 1 replica in `envs/dev`.

---

## 14. Dashboards

**Command Centre (application)**

- Active incidents by severity
- Incidents per minute by type
- Time to dispatch (p50 / p95)
- Responder & vehicle availability
- Dispatch queue depth vs replicas ← the money shot for the demo
- Error rate & latency per service

**Cluster Health (infrastructure)**

- Node CPU & memory
- Pod restarts & status
- HPA current vs desired replicas
- PostgreSQL & RabbitMQ health
- Persistent volume usage
- ArgoCD sync & health status

Custom app metrics to expose (keep it to these 4):

```
drukrescue_incidents_created_total{type, severity}      # Incident
drukrescue_incidents_active{severity}                    # Incident
drukrescue_time_to_dispatch_seconds (histogram)          # Dispatch
drukrescue_units_available{kind="responder|vehicle"}     # Responder / Vehicle
```

---

## 15. Final demo script (~10 minutes)

1. **Citizen** reports "Flooding near Babesa" → `INC-2026-001`, `REPORTED`
2. **Admin** verifies → Dispatch assigns nearest Rescue Team + Vehicle
3. **Notification** shows "Rescue team dispatched" to citizen
4. **Admin** sends area alert: "Flash flood warning – Babesa"
5. **Responder** updates: en route → on scene → resolved; citizen page updates live
6. **Grafana:** open the trace for that report, then jump to its logs in Loki
7. **Load test:** burst 100 reports → queue depth climbs → Dispatch 2 → 6 pods → drains → scales down
8. **Self-healing:** `kubectl delete pod <incident-pod>` → new pod Ready in < 30 s
9. **GitOps:** change the image tag in Git → ArgoCD rolls out v2 with zero failed requests
10. **Rollback:** `git revert` → ArgoCD rolls back

---

## 16. Expected outcomes

| Target | Metric |
|---|---|
| **2 → 6** | Dispatch replicas, scaled on queue depth |
| **0** | Downtime during a rolling update |
| **< 30 s** | To replace a killed pod |
| **100** | Incident reports in the load test |

**Deliverables:** working platform on Kind · Helm chart repo + GitOps config repo · Grafana dashboards + alert rules · documentation, runbook, test report.

---

## 17. Work plan (7 weeks)

| Week | Focus | Done when |
|---|---|---|
| 1 | Planning & proposal | ✅ Proposal presented |
| 2 | Foundation: service template, Dockerfile, Kind cluster, Postgres/Redis/RabbitMQ | Template service runs in Kind and talks to all 3 |
| 3 | Build the 6 core services + start thin ones (in parallel) | Report → verify → dispatch works end-to-end |
| 4 | Finish thin services; Helm library chart; Ingress; NetworkPolicy; RBAC | All 15 deploy via Helm |
| 5 | GitHub Actions + ArgoCD app-of-apps; observability stack | Push to main = auto deploy; traces & logs visible |
| 6 | Dashboards; custom-metric HPA; load testing | Scale 2 → 6 shown in Grafana |
| 7 | Testing, docs, runbook, dry run; final demo | Demo script runs twice without help |

### Suggested ownership (each person: ~4 services + 1 platform area)

| Member | Services | Platform area |
|---|---|---|
| Person A | Gateway, Auth, User, Audit | Security (JWT, NetworkPolicy, Secrets) |
| Person B | Incident, Notification, Alert, Shelter | Helm library chart + frontend |
| Person C | Dispatch, Location, Responder, Vehicle | Autoscaling + load testing |
| Person D | Resource, Weather, Analytics | GitOps (CI + ArgoCD) + observability |

(Assign names yourselves. Put the strongest backend person on Dispatch, since it's the demo centrepiece.)

---

## 18. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Laptop can't run the full stack | Requests sized up front (~6 CPU / 10 GiB); thin services drop to 1 replica in dev |
| 15 services in 7 weeks is tight | One template + shared Helm library chart; 9 of 15 are thin CRUD |
| Custom-metric HPA hard to wire | Prometheus Adapter plan A, KEDA RabbitMQ scaler fallback |
| Queue never grows in the demo | Burst load + processing delay + `averageValue: 10` (see §12) |

---

## 19. Things deliberately cut (and what to say if asked)

| Cut | Say this |
|---|---|
| Kafka | "RabbitMQ fits our scale and has simpler ops; Kafka is for very high-throughput streaming." |
| gRPC | "REST is enough for our latency needs and easier to debug." |
| PostGIS | "Haversine in code is accurate enough at district scale; PostGIS is the upgrade path." |
| Real SMS / push | "Notification is in-app; an SMS provider would plug in behind the same service." |
| WebSockets | "Polling every 5 s is simpler and good enough for status updates." |
| Separate DB per service | "Schema-per-service with separate DB users keeps ownership without 15 database servers." |

---

## 20. Heads-up on tools (as of late 2026)

- **ingress-nginx** has been retired by the Kubernetes project. It still works fine for a local Kind demo; if asked, the successor is the Gateway API.
- **Promtail** is deprecated in favour of **Grafana Alloy** for shipping logs to Loki. Either works for the demo; Alloy is the future-proof choice.
- **Bitnami** restricted its free images/charts in 2025. Use official images (`postgres`, `redis`, `rabbitmq`) in simple StatefulSets you write in the `platform` chart. This is also easier to explain.

---

## 21. Likely viva questions (short answers)

**Why microservices instead of one app?**
Each part scales, deploys and fails on its own. During a flood, only Incident and Dispatch get busy, so only those scale.

**Why Kubernetes?**
Self-healing, rolling updates, autoscaling and service discovery out of the box. We demo all four.

**Why GitOps?**
Git becomes the audit trail and single source of truth. Rollback is just `git revert`.

**Why scale on queue depth, not CPU?**
Dispatch is I/O-bound. CPU stays low while the backlog grows; queue depth measures real demand.

**What happens if RabbitMQ goes down?**
Queues are durable, so messages survive a restart. Producers fail their readiness check and retry; incidents are still saved in PostgreSQL first.

**What happens if Dispatch crashes mid-assignment?**
Messages are only acknowledged after the assignment is saved, so an unacknowledged message goes back on the queue and another pod picks it up.

**How do services stay independent if they share one PostgreSQL?**
Each has its own schema and DB user with permissions only on that schema. No service can read another's tables.

**Biggest limitation?**
Kind runs on one machine, so it's not real HA. Production needs a multi-node cluster and replicated PostgreSQL.