# Work split

Four people, each owning **~4 services + 1 platform area** (rescue.md section 17).
The foundation is done; what's left is below as tasks with IDs. Put your name in the table,
open a branch per task (`feat/B1-alert-service`), and tick the boxes in your PR.

| | Name | Services you own & must explain in the viva | Platform area |
|---|---|---|---|
| **A** | _______ | Gateway ✅, Auth ✅, User ✅, **Audit** | Security (JWT, NetworkPolicy, Secrets) |
| **B** | _______ | Incident ✅, Notification ✅, **Alert**, **Shelter** | Helm library chart ✅ + **frontend** |
| **C** | _______ | Dispatch ✅, Location ✅, Responder ✅, Vehicle ✅ | **Autoscaling + load testing** |
| **D** | Kelden Phuntsho Dorji | **Resource**, **Weather**, **Analytics** | **GitOps (CI + ArgoCD) + observability** |

✅ = already implemented and tested. "Own" means: read it, understand it, be able to change it and defend it.

### Picking your role (do this first, before writing any code)

**D is taken by Kelden:** D5 needs repo admin access (branch protection, GHCR packages, Actions permissions).
Dupchu, Kinley and Tshering split A, B and C between them:

| Role | Take it if you… | Why |
|---|---|---|
| **C** | are the strongest backend coder | Dispatch is the demo centrepiece and autoscaling (C2) is the hardest thing to get working on the cluster |
| **B** | enjoy UI / JavaScript | the responder + admin views (B3) are the biggest single task and the demo depends on them |
| **A** | are careful and detail-minded | NetworkPolicy proof, auth hardening, the security write-up |

Agree in the group chat, then the first PR each person opens adds their name to the table above.
That way two people never build the same thing.

### How to work (for you and any AI assistant helping you)

1. Before coding, read `rescue.md`, `CONTRIBUTING.md`, `docs/architecture.md`, `docs/events.md` and the
   `services/<name>/README.md` of every scaffolded service your role owns.
2. Get a working setup: `make venv && make test`, then `make env && make up && make seed && make smoke` (must print PASS).
3. One task at a time, on its own branch `feat/<task-id>-<short-name>`. Copy the existing patterns:
   `services/vehicle` (CRUD), `services/incident` (events, commit then publish), `services/dispatch` (calling other services),
   `services/responder` (atomic UPDATE). Validate input with Pydantic and check roles with `require_roles`.
4. Never read another service's tables. Consumers must be idempotent. If you change an event payload, update `docs/events.md` too.
5. Write tests for every endpoint and event handler. `make test-<service>` and `make lint` must be clean.
6. When done, tick the boxes here and in the service README, then open a PR.

**Hard rules:** never commit or push to `main` (use PRs, one teammate reviews). Never commit secrets (`.env`, passwords, tokens).
Don't change other roles' services, `libs/common` or `deploy/charts/drukrescue-lib` without telling the team first.
If the spec is unclear, ask in the group chat instead of guessing.

## Already done (foundation)

- Service template `libs/common/drukcommon`: health/readiness, Prometheus metrics with exemplars, OpenTelemetry, JSON logs with trace ids, DB per schema, RabbitMQ events (durable, acked, dead-lettered, traced), identity/RBAC helpers
- 9 services implemented with tests: gateway, auth, user, incident, dispatch, location, notification, responder, vehicle
- 6 services scaffolded (boot, health, metrics, DB schema, chart, ArgoCD app): shelter, resource, alert, weather, analytics, audit
- Helm library chart + 16 service charts; platform chart (PostgreSQL/RabbitMQ/Redis); dev and demo envs; Dispatch HPA on queue depth
- ArgoCD app-of-apps (services, platform, kube-prometheus-stack, Loki, Tempo, Alloy, prometheus-adapter)
- GitHub Actions: change detection, lint, tests, Helm render, image build/push to GHCR, GitOps tag bump
- docker-compose for local dev, Kind bootstrap, secrets script, seed script
- Frontend skeleton: login/register, notifications, citizen view

## Person A: Security

- [ ] **A1 · Audit service.** Spec: [`services/audit/README.md`](services/audit/README.md)
- [ ] **A2 · Prove the NetworkPolicies work on Kind.** From a throwaway pod in `drukrescue`, show that `curl incident:8000/healthz` is refused,
      while the gateway (and dispatch) can reach it. Check that Kind's CNI enforces policies (recent Kind versions do via kindnet; if not, document it).
      Write the commands and the expected output into `docs/runbook.md`.
- [ ] **A3 · Auth extras.** `POST /auth/password` (change password, needs the old one) and lockout after N failed logins (Redis counter in the gateway or a table in auth). Tests.
- [ ] **A4 · Security write-up.** One page for the report: threat model (who attacks what), and how each control in `docs/architecture.md#security` answers it. How to rotate the JWT secret.

## Person B: Frontend + Alert/Shelter

- [ ] **B1 · Alert service.** Spec: [`services/alert/README.md`](services/alert/README.md) (Notification already consumes `alert.issued`)
- [ ] **B2 · Shelter service.** Spec: [`services/shelter/README.md`](services/shelter/README.md)
- [ ] **B3 · Frontend views.** Responder view, admin (Command Centre) view, shelters/alerts cards on the citizen view.
      Spec: [`frontend/README.md`](frontend/README.md)
- [ ] **B4 · Responder accept/reject.** `POST /incidents/{id}/reject` (assigned responder only): move `DISPATCHED → VERIFIED`
      (add it to `TRANSITIONS`), publish `dispatch.release_requested`, re-queue with `excluded_responder_ids: [<responder id>]`.
      `ACCEPTED` already exists as a progress stage. Tests in `services/incident/tests`.

## Person C: Autoscaling + load testing

- [ ] **C1 · Burst load test.** Finish [`loadtest/burst.js`](loadtest/burst.js): 100 reports in under 60 s, verified (AUTO_VERIFY or admin),
      enough seeded units, summary saved to `loadtest/results/`. Write the result section of the test report.
- [ ] **C2 · Autoscaling on the cluster.** Switch to `env: demo` (in `deploy/argocd/apps/values.yaml`, via Git).
      Check `kubectl get --raw "/apis/external.metrics.k8s.io/v1beta1/namespaces/drukrescue/rabbitmq_queue_messages_ready?labelSelector=queue%3Ddispatch.requests"`,
      then run the burst and capture 2 → 6 → 2 in Grafana (screenshot for the report).
      If prometheus-adapter fights you for more than a day, add a KEDA `ScaledObject` (RabbitMQ scaler) to the dispatch chart behind a `keda.enabled` flag.
- [ ] **C3 · Manual dispatch.** Implement `POST /dispatch/manual {incident_id, responder_id, vehicle_id}` (admin): claim both (409 if taken),
      publish `dispatch.assigned`. Reuse `claim_first`/`release`. Tests in `services/dispatch/tests`.
- [ ] **C4 · Self-healing + zero-downtime evidence.** Demo steps 8 and 9: script `kubectl delete pod` and measure time to Ready (< 30 s);
      run k6 at low rate during a rolling update and show 0 failed requests.

## Person D: GitOps + observability

- [ ] **D1 · Resource service.** Spec: [`services/resource/README.md`](services/resource/README.md)
- [ ] **D2 · Weather service.** Spec: [`services/weather/README.md`](services/weather/README.md)
- [ ] **D3 · Analytics service.** Spec: [`services/analytics/README.md`](services/analytics/README.md)
- [ ] **D4 · Dashboards + alerts.** Finish `deploy/charts/observability/dashboards/command-centre.json` (active incidents by severity,
      error rate & latency per service) and create `cluster-health.json` (node CPU/mem, pod restarts, HPA current vs desired,
      PostgreSQL/RabbitMQ health, PVC usage, ArgoCD sync status). Add the missing alert rules. Tip: build in the Grafana UI, then export the JSON into Git.
      Document the metric → trace → log click path (objective c).
- [ ] **D5 · CI/GitOps hardening.** Add an image vulnerability scan (pinned by SHA) to `.github/workflows/ci.yml`; set up branch protection on
      `main` (PRs + green CI) while still letting the bump job push (or switch it to opening a PR); make the GHCR packages public
      or add an imagePullSecret; rehearse demo steps 9–10 (image tag change in Git → rollout; `git revert` → rollback).

## Everyone (week 7)

- [ ] `docs/runbook.md`: fill in the TODO sections
- [ ] Test report: unit tests (`make test`), load test (C1), autoscaling (C2), self-healing (C4)
- [ ] Two full dry runs of the demo script (rescue.md section 15) without help
